// Native execution adapter for the pinned production Speeduino ECU.
// The adapter supplies configuration and virtual pins. Engine algorithms stay
// in the external GPL source; this executable never opens hardware devices.
#include "FakeMega.h"
#include "globals.h"
#include "src/controllers/idle/idle.h"
#include "storage.h"
#include "pages.h"
#include "sensors.h"
#include "decoders.h"
#include "decoder_init.h"
#include "timers.h"
#include "init.h"
#include "logger.h"
#include "scheduler_fuel_controller.h"
#include "scheduler_ignition_controller.h"
#include "units.h"
#include <SimpleArduinoFake.h>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <unistd.h>
#include <limits.h>

extern void setup();
extern void loop();
extern "C" uint64_t speeduino_sim_micros();
extern "C" void speeduino_sim_advance(uint64_t);
namespace {
std::stringstream& serial_stream() { static auto* value = new std::stringstream; return *value; }
struct EarlySetup { EarlySetup() { fakeMega(serial_stream(), serial_stream()); } };
EarlySetup early_setup __attribute__((init_priority(65534)));
int adc[256]{};
int pins[256]{};
void (*interrupts_by_pin[256])(){};
int interrupt_modes[256]{};
std::string log_kind="none";
bool record_edges = false;
bool use_per_tooth = false;
bool logger_cam = false;
bool sequential_profile = false;
volatile uint8_t* output_ports[8]{};
uint8_t output_masks[8]{};
uint8_t output_pins[8]{};
bool output_high[8]{};
void prepare_hal() {
    using namespace fakeit;
    auto& mock = SimpleArduinoFake::getContext()._Function;
    When(Method(mock, micros)).AlwaysDo([]() -> unsigned long { return uint32_t(speeduino_sim_micros()); });
    When(Method(mock, millis)).AlwaysDo([]() -> unsigned long { return uint32_t(speeduino_sim_micros()/1000); });
    When(Method(mock, delay)).AlwaysDo([](unsigned long ms) { speeduino_sim_advance(speeduino_sim_micros()+ms*1000); });
    When(Method(mock, delayMicroseconds)).AlwaysDo([](unsigned int us) { speeduino_sim_advance(speeduino_sim_micros()+us); });
    When(Method(mock, analogRead)).AlwaysDo([](uint8_t pin) { return adc[pin]; });
    When(Method(mock, digitalRead)).AlwaysDo([](uint8_t pin) { return pins[pin]; });
    When(Method(mock, digitalWrite)).AlwaysDo([](uint8_t pin, uint8_t value) {
        pins[pin] = value;
        auto port=portOutputRegister(digitalPinToPort(pin));auto mask=digitalPinToBitMask(pin);
        if(value) *port |= mask; else *port &= ~mask;
    });
    When(Method(mock, attachInterrupt)).AlwaysDo([](uint8_t pin, void (*cb)(), int mode) { interrupts_by_pin[pin] = cb;interrupt_modes[pin]=mode; });
    When(Method(mock, detachInterrupt)).AlwaysDo([](uint8_t pin) { interrupts_by_pin[pin] = nullptr; });
}
void configure() {
    setStorageAPI(getBoardStorageApi());
    setTuneToEmpty();
    configPage2.pinMapping = 3;
    configPage2.nCylinders = 4;
    configPage2.nInjectors = 4;
    configPage2.strokes = FOUR_STROKE;
    configPage2.injType = INJ_TYPE_PORT;
    configPage2.injLayout = (logger_cam||sequential_profile)?INJ_SEQUENTIAL:INJ_SEMISEQUENTIAL;
    configPage2.divider = 2;
    configPage2.injTiming = sequential_profile?1:0;
    if(sequential_profile){for(unsigned n=0;n<4;++n){configPage2.injAng[n]=540;configPage2.injAngRPM[n]=5+20*n;}}
    configPage2.reqFuel = 107; // 2L/4cyl,300cc/min,14.7 AFR,25C rounded to0.1ms
    configPage2.injOpen = 9;
    configPage2.multiplyMAP = MULTIPLY_MAP_MODE_100;
    configPage2.fuelAlgorithm = LOAD_SOURCE_MAP;
    configPage2.perToothIgn = use_per_tooth;
    configPage2.ignAlgorithm = LOAD_SOURCE_MAP;
    configPage2.dutyLim = 80;
    configPage2.stoich = 147;
    configPage2.tpsMin = 0; configPage2.tpsMax = 255;
    configPage2.mapMin = 0; configPage2.mapMax = 200;
    configPage2.baroMin = 0; configPage2.baroMax = 200;
    configPage2.fpPrime = 2;
    configPage2.taeThresh = 255; configPage2.maeThresh = 255;
    configPage4.TrigPattern = DECODER_MISSING_TOOTH;
    configPage4.triggerTeeth = 60; configPage4.triggerMissingTeeth = 2;
    configPage4.triggerAngle = -90;
    configPage4.crankRPM = 45;
    configPage4.CrankAng = 5;
    configPage4.sparkMode = sequential_profile?IGN_MODE_SEQUENTIAL:IGN_MODE_WASTEDCOP;
    configPage4.TrigSpeed=CRANK_SPEED;configPage4.trigPatternSec=SEC_TRIGGER_SINGLE;
    configPage4.IgInv = 0; // virtual active-high charging
    configPage4.dwellRun = 28; configPage4.dwellCrank = 28;
    configPage4.useDwellLim = 1; configPage4.dwellLimit = 4;
    configPage4.sparkDur = 10;
    configPage4.floodClear = 95;
    configPage4.HardRevLim = 65; configPage4.SoftRevLim = 62;
    configPage4.engineProtectMaxRPM = 65;
    configPage6.engineProtectType = PROTECT_CUT_BOTH;
    configPage9.hardRevMode = HARD_REV_FIXED;
    configPage2.SoftLimitMode = SOFT_LIMIT_RELATIVE;
    configPage4.SoftLimRetard = 10;configPage4.SoftLimMax = 255;
    for (unsigned n = 0; n < 10; ++n) { configPage4.wueBins[n] = n*20; configPage2.wueValues[n] = 100; }
    for (unsigned n = 0; n < 6; ++n) {
        configPage6.voltageCorrectionBins[n] = 80+n*20;
        configPage6.injVoltageCorrectionValues[n] = 100;
        configPage4.dwellCorrectionValues[n] = 100;
        configPage4.iatRetBins[n] = n*40;
        configPage4.cltAdvBins[n] = n*40; configPage4.cltAdvValues[n] = 15;
    }
    for (unsigned n = 0; n < 9; ++n) { configPage6.airDenBins[n] = n*25; configPage6.airDenRates[n] = 100; }
    for (unsigned n = 0; n < 8; ++n) { configPage4.baroFuelBins[n] = 30+n*20; configPage4.baroFuelValues[n] = 100; }
    for (unsigned n = 0; n < 4; ++n) {
        configPage10.crankingEnrichBins[n] = n*60;
        configPage10.crankingEnrichValues[n] = 20; // stored in5% units
        configPage2.aseBins[n] = n*60;
    }
    for (unsigned n = 0; n < 32; ++n) {
        cltCalibrationTable.axis[n] = iatCalibrationTable.axis[n] = o2CalibrationTable.axis[n] = n*33;
        cltCalibrationTable.values[n] = iatCalibrationTable.values[n] = std::min(255u,n*8);
        o2CalibrationTable.values[n] = std::min(255u,80+n*5);
    }
    for (unsigned n = 0; n < 16; ++n) {
        fuelTable.axisX[n] = ignitionTable.axisX[n] = afrTable.axisX[n] = (n+1)*5;
        fuelTable.axisY[n] = ignitionTable.axisY[n] = afrTable.axisY[n] = (n+1)*8;
    }
    fuelTable.values.fill(85);
    ignitionTable.values.fill(40+10);
    afrTable.values.fill(147);
    // Persist through the real storage API, then let unmodified setup load it.
    saveEEPROMVersion(27);
    do { saveAllPages(); } while (isEepromWritePending());
    saveAllCalibrationTables();
    saveLastBaro(100);
}
void set_sensors(double map, double tps, double clt, double iat, double battery, double afr) {
    adc[pinNumbers.pinMAP] = std::lround(map/200*1024);
    adc[pinNumbers.pinTPS] = std::lround(tps/100*1023);
    adc[pinNumbers.pinCLT] = std::lround((clt+40)*33/8);
    adc[pinNumbers.pinIAT] = std::lround((iat+40)*33/8);
    adc[pinNumbers.pinBat] = std::lround(battery*10/245*1024);
    adc[pinNumbers.pinO2] = std::lround((afr*10-80)*33/5);
}
void status() {
    std::cout << "status " << speeduino_sim_micros() << ' ' << currentStatus.RPM << ' '
              << fuelSchedule1.pw << ' ' << int(currentStatus.advance) << ' '
              << currentStatus.MAP << ' ' << unsigned(currentStatus.VE) << ' '
              << unsigned(currentStatus.corrections) << ' ' << currentStatus.coolant << ' '
              << currentStatus.IAT << ' ' << unsigned(currentStatus.battery10) << ' '
              << unsigned(currentStatus.decoder.getStatus().syncStatus) << ' '
              << unsigned(currentStatus.schedulerCutState.fuelChannels) << ' '
              << unsigned(currentStatus.schedulerCutState.ignitionChannels) << ' '
              << unsigned(currentStatus.softLimitActive) << '\n';
    std::cout << "diagnostic " << unsigned(fuelSchedule1._status) << ' ' << fuelSchedule1._counter.load() << ' ' << fuelSchedule1._compare.load() << ' ' << currentStatus.decoder.getCrankAngle() << ' '
              << unsigned(currentStatus.schedulerCutState.fuelChannels) << ' ' << unsigned(currentStatus.schedulerCutState.ignitionChannels) << ' '
              << unsigned(ignitionSchedule1._status) << ' ' << currentStatus.dwell << ' ' << CRANK_ANGLE_MAX_IGN << ' ' << CRANK_ANGLE_MAX_INJ << ' ' << unsigned(currentStatus.nSquirts) << '\n';
}
}

namespace {
bool review_observe=false,review_previous=false,review_armed=false;
unsigned review_rises=0;uint64_t review_first_rise=0,review_last_rise=0;
uint64_t review_last=0,review_high_us=0;
unsigned review_edges=0;
bool review_pin(){return (*portOutputRegister(digitalPinToPort(pinNumbers.pinIdle1))&digitalPinToBitMask(pinNumbers.pinIdle1))!=0;}
void begin_window(){review_previous=review_pin();review_last=speeduino_sim_micros();review_high_us=0;review_edges=0;review_rises=0;review_first_rise=review_last_rise=0;review_observe=true;}
void finish_window(const char* stage,unsigned algorithm){
 auto now=speeduino_sim_micros();if(review_previous)review_high_us+=now-review_last;review_last=now;review_observe=false;
 std::cout<<"window "<<algorithm<<' '<<review_armed<<' '<<stage<<' '<<unsigned(currentStatus.idleLoad)<<' '<<review_high_us<<' '<<review_edges<<' '<<review_pin()<<' '<<(review_rises>1?(review_last_rise-review_first_rise)/(review_rises-1):0)<<'\n';
}
}
extern "C" void speeduino_sim_observe(){
 if(!review_observe)return;auto now=speeduino_sim_micros();auto high=review_pin();
 if(high!=review_previous){if(review_previous)review_high_us+=now-review_last;if(high){if(!review_rises)review_first_rise=now;review_last_rise=now;review_rises++;}review_last=now;review_previous=high;review_edges++;}
}
int main(){
 setenv("GCOV_PREFIX","/home/mark/persospace/esp32-ecu/.cache/engine/idle-control-review/gcov",1);
 prepare_hal();configure();setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();
 for(bool arm:{false,true})for(unsigned algorithm:{unsigned(IAC_ALGORITHM_PWM_OL),unsigned(IAC_ALGORITHM_PWM_CL),unsigned(IAC_ALGORITHM_PWM_OLCL)}){
  configPage6.iacAlgorithm=algorithm;configPage6.idleFreq=25;configPage6.iacPWMdir=0;configPage6.iacChannels=0;configPage6.iacPWMrun=0;
  configPage6.idleKP=0;configPage6.idleKI=0;configPage6.idleKD=0;configPage2.iacCLminValue=0;configPage2.iacCLmaxValue=100;
  for(unsigned n=0;n<4;n++){configPage6.iacCrankBins[n]=n*70;configPage6.iacCrankDuty[n]=50;}
  for(unsigned n=0;n<10;n++){configPage6.iacBins[n]=n*25;configPage6.iacOLPWMVal[n]=50;}
  currentStatus.coolant=85;currentStatus.RPM=300;currentStatus.rotationStatus=EngineRotationStatus::Cranking;
  initialiseIdle(true);review_armed=arm;
  std::cout<<"registers "<<ECU_SIM_TIMER_BITS<<' '<<algorithm<<' '<<arm<<' '<<speeduino_sim_micros()<<' '<<IDLE_COUNTER.load()<<' '<<IDLE_COMPARE.load()<<' '<<review_pin()<<'\n';
  if(arm)IDLE_COMPARE=static_cast<software_timer_t::counter_t>(IDLE_COUNTER.load()+1);
  idleControl();begin_window();speeduino_sim_advance(speeduino_sim_micros()+200000);finish_window("cranking",algorithm);
  disableIdle();begin_window();speeduino_sim_advance(speeduino_sim_micros()+200000);finish_window("after_disable",algorithm);
 }
}
