// Native execution adapter for the pinned production Speeduino ECU.
// The adapter supplies configuration and virtual pins. Engine algorithms stay
// in the external GPL source; this executable never opens hardware devices.
#include "FakeMega.h"
#include "globals.h"
#include "storage.h"
#include "pages.h"
#include "sensors.h"
#include "load_source.h"
#include "secondaryTables.h"
#include "corrections.h"
#include "decoders.h"
#include "decoder_init.h"
#include "timers.h"
#include "init.h"
#include "logger.h"
#include "scheduler_fuel_controller.h"
#include "scheduler_ignition_controller.h"
#include "units.h"
#include "src/controllers/idle/idle.h"
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
bool semi_sequential_profile = false;
bool idle_profile=false,idle_high=false;
bool ae_profile=false;
bool load_profile=false;unsigned load_maps=0;
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
    configPage2.injTiming = (sequential_profile||semi_sequential_profile)?1:0;
    if(sequential_profile||semi_sequential_profile){for(unsigned n=0;n<4;++n){configPage2.injAng[n]=sequential_profile?540:180;configPage2.injAngRPM[n]=5+20*n;}}
    if(semi_sequential_profile)configPage4.inj4cylPairing=INJ_PAIR_13_24;
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
extern "C" void speeduino_sim_observe() {
    if (!record_edges) return;
    for(unsigned n=0;n<8;++n) {
        bool high=(*output_ports[n]&output_masks[n]) != 0;
        if(high!=output_high[n]) {
            output_high[n]=high;
            std::cout << "edge " << speeduino_sim_micros() << ' ' << unsigned(output_pins[n]) << ' ' << unsigned(high) << ' ' << unsigned(currentStatus.decoder.getStatus().syncStatus) << ' ' << CRANK_ANGLE_MAX_IGN << '\n';
        }
    }
    if(idle_profile){
        const bool high=(*portOutputRegister(digitalPinToPort(pinNumbers.pinIdle1))&digitalPinToBitMask(pinNumbers.pinIdle1))!=0;
        if(high!=idle_high){idle_high=high;std::cout<<"edge "<<speeduino_sim_micros()<<' '<<unsigned(pinNumbers.pinIdle1)<<' '<<unsigned(high)<<" 0 0\n";}
    }
}

unsigned checks=0;
void check(const char* kind,unsigned mode,int v1,int v2,int actual,int expected,bool active,bool expected_active,int info=0){
 ++checks;
 std::cout<<kind<<','<<mode<<','<<v1<<','<<v2<<','<<actual<<','<<expected<<','<<active<<','<<expected_active<<','<<info<<'\n';
 if(actual!=expected||active!=expected_active){std::cerr<<"probe mismatch "<<kind<<' '<<mode<<' '<<v1<<' '<<v2<<' '<<actual<<' '<<expected<<' '<<active<<' '<<expected_active<<'\n';std::exit(2);}
}
int main(){
 setenv("GCOV_PREFIX","/home/mark/persospace/esp32-ecu/.cache/engine/secondary-architecture-review/gcov",1);
 prepare_hal();configure();setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();
 currentStatus.RPM=1000;currentStatus.RPMdiv100=10;currentStatus.rotationStatus=EngineRotationStatus::Running;
 currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.EMAP=200;currentStatus.ethanolPct=35;currentStatus.LOOP_TIMER=0;
 for(unsigned i=0;i<16;++i){fuelTable2.axisX[i]=ignitionTable2.axisX[i]=(i+1)*5;fuelTable2.axisY[i]=ignitionTable2.axisY[i]=(i+1)*8;}
 configPage10.fuel2Algorithm=LOAD_SOURCE_MAP;configPage10.spark2Algorithm=LOAD_SOURCE_MAP;
 pinNumbers.pinFuel2Input=25;pinNumbers.pinSpark2Input=26;
 std::cout<<"kind,mode,primary,secondary,actual,expected,active,expected_active,info\n";
 for(unsigned mode:{0,1,2,5,7})for(unsigned v1:{0,1,85,100,150,255})for(unsigned v2:{0,1,50,100,150,255}){
  configPage10.fuel2Mode=mode;fuelTable2.values.fill(v2);invalidate_cache(&fuelTable2.get_value_cache);
  currentStatus.VE1=currentStatus.VE=v1;calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  int expected=mode==1?std::min(255u,(v1*v2+50)/100):mode==2?std::min(255u,v1+v2):v1;
  check("fuel_arithmetic",mode,v1,v2,currentStatus.VE,expected,currentStatus.secondFuelTableActive,mode==1||mode==2,currentStatus.VE2);
  if(currentStatus.VE2!=((mode==1||mode==2)?v2:0))return 5;
 }
 for(unsigned variable=0;variable<4;++variable)for(int delta:{-1,0,1}){
  configPage10.fuel2Mode=FUEL2_MODE_CONDITIONAL_SWITCH;configPage10.fuel2SwitchVariable=variable;
  configPage10.fuel2SwitchValue=variable==0?1000:variable==1?50:variable==2?100:35;
  currentStatus.RPM=1000;currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.ethanolPct=35;
  if(variable==0)currentStatus.RPM+=delta;else if(variable==1)currentStatus.MAP+=delta;else if(variable==2)currentStatus.TPS+=delta;else currentStatus.ethanolPct+=delta;
  fuelTable2.values.fill(65);invalidate_cache(&fuelTable2.get_value_cache);currentStatus.VE1=currentStatus.VE=85;
  calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  check("fuel_condition",variable,configPage10.fuel2SwitchValue,delta,currentStatus.VE,delta>0?65:85,currentStatus.secondFuelTableActive,delta>0,currentStatus.TPS);
 }
 for(unsigned polarity:{0,1})for(unsigned level:{0,1}){
  configPage10.fuel2Mode=FUEL2_MODE_INPUT_SWITCH;configPage10.fuel2InputPolarity=polarity;pins[25]=level;
  fuelTable2.values.fill(65);invalidate_cache(&fuelTable2.get_value_cache);currentStatus.VE1=currentStatus.VE=85;
  calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  check("fuel_input",4,polarity,level,currentStatus.VE,polarity==level?65:85,currentStatus.secondFuelTableActive,polarity==level,currentStatus.VE2);
 }
 // Establish actual production soft-retard correction; all remaining fixture
 // corrections are neutral from the original persisted benchmark setup.
 currentStatus.RPM=6300;currentStatus.RPMdiv100=63;currentStatus.rotationStatus=EngineRotationStatus::Running;
 configPage2.fixAngEnable=0;configPage4.SoftRevLim=62;configPage4.SoftLimRetard=10;configPage4.SoftLimMax=255;configPage2.SoftLimitMode=SOFT_LIMIT_RELATIVE;
 const int corrected=correctionsIgn(20);if(corrected!=10){std::cerr<<"neutral correction profile failed "<<corrected<<'\n';return 3;}
 for(unsigned mode:{0,1,2,3,4,5,7}){
  configPage10.spark2Mode=mode;configPage10.spark2SwitchVariable=SPARK2_CONDITION_RPM;configPage10.spark2SwitchValue=6000;
  configPage10.spark2InputPolarity=1;pins[26]=1;
  const int second=mode==1?150:20;
  ignitionTable2.values.fill(second+40);invalidate_cache(&ignitionTable2.get_value_cache);
  currentStatus.advance1=corrected;currentStatus.advance=corrected;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  const int expected=mode==1?15:mode==2?30:(mode==3||mode==4)?10:corrected;
  check("spark_correction_order",mode,corrected,second,currentStatus.advance,expected,currentStatus.secondSparkTableActive,mode>=1&&mode<=4,currentStatus.advance2);
 }
 for(unsigned mode:{1,2,3,4})for(unsigned inhibit:{1,2}){
  configPage2.fixAngEnable=inhibit==1;currentStatus.rotationStatus=inhibit==2?EngineRotationStatus::Cranking:EngineRotationStatus::Running;
  configPage10.spark2Mode=mode;currentStatus.advance1=currentStatus.advance=5;currentStatus.advance2=111;currentStatus.secondSparkTableActive=true;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  check("spark_inhibited",mode,inhibit,20,currentStatus.advance,5,currentStatus.secondSparkTableActive,false,currentStatus.advance2);
 }
 configPage2.fixAngEnable=0;currentStatus.rotationStatus=EngineRotationStatus::Running;currentStatus.RPM=1000;currentStatus.RPMdiv100=10;
 for(unsigned variable=0;variable<4;++variable)for(int delta:{-1,0,1}){
  configPage10.spark2Mode=SPARK2_MODE_CONDITIONAL_SWITCH;configPage10.spark2SwitchVariable=variable;
  configPage10.spark2SwitchValue=variable==0?1000:variable==1?50:variable==2?100:35;
  currentStatus.RPM=1000;currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.ethanolPct=35;
  if(variable==0)currentStatus.RPM+=delta;else if(variable==1)currentStatus.MAP+=delta;else if(variable==2)currentStatus.TPS+=delta;else currentStatus.ethanolPct+=delta;
  ignitionTable2.values.fill(60);invalidate_cache(&ignitionTable2.get_value_cache);currentStatus.advance1=currentStatus.advance=10;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  check("spark_condition",variable,configPage10.spark2SwitchValue,delta,currentStatus.advance,delta>0?20:10,currentStatus.secondSparkTableActive,delta>0,currentStatus.TPS);
 }
 for(unsigned polarity:{0,1})for(unsigned level:{0,1}){
  configPage10.spark2Mode=SPARK2_MODE_INPUT_SWITCH;configPage10.spark2InputPolarity=polarity;pins[26]=level;
  ignitionTable2.values.fill(60);invalidate_cache(&ignitionTable2.get_value_cache);currentStatus.advance1=currentStatus.advance=10;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  check("spark_input",4,polarity,level,currentStatus.advance,polarity==level?20:10,currentStatus.secondSparkTableActive,polarity==level,currentStatus.advance2);
 }
 for(unsigned mode:{1,2})for(int v1:{-128,-40,-5,0,20,70,127})for(int v2:{-40,-1,0,1,50,100,150,215}){
  configPage10.spark2Mode=mode;ignitionTable2.values.fill(v2+40);invalidate_cache(&ignitionTable2.get_value_cache);
  currentStatus.advance1=currentStatus.advance=v1;calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  const int percent=std::max(0,v2);
  // Exact rounded signed div100 behavior is probed, not assumed truncation.
  const int num=percent*v1;
  const int product=num>=0?(num+50)/100:(num-50)/100;
  const int sum=v1+std::max(-128,std::min(127,v2));
  const int expected=std::max(-128,std::min(127,mode==1?product:sum));
  check("spark_arithmetic",mode,v1,v2,currentStatus.advance,expected,currentStatus.secondSparkTableActive,true,currentStatus.advance2);
 }
 // Secondary load source is independent and does not change primary fuelLoad.
 for(unsigned row=0;row<16;++row)for(unsigned col=0;col<16;++col)fuelTable2.values[row*16+col]=10+row*4;
 invalidate_cache(&fuelTable2.get_value_cache);currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.EMAP=200;currentStatus.RPM=1000;currentStatus.fuelLoad=50;
 configPage10.fuel2Mode=FUEL2_MODE_INPUT_SWITCH;configPage10.fuel2InputPolarity=1;pins[25]=1;
 for(auto source:{LOAD_SOURCE_MAP,LOAD_SOURCE_TPS,LOAD_SOURCE_IMAPEMAP}){
  configPage10.fuel2Algorithm=source;currentStatus.VE1=currentStatus.VE=85;calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  const int expected=source==LOAD_SOURCE_MAP?18:source==LOAD_SOURCE_TPS?56:12;
  check("fuel_independent_source",source,50,getLoad(source,currentStatus),currentStatus.VE,expected,currentStatus.secondFuelTableActive,true,currentStatus.fuelLoad);
  if(currentStatus.fuelLoad!=50)return 4;
 }
 std::cerr<<"PASSED "<<checks<<" controlled production secondary-table checks\n";
}
