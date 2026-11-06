// Native execution adapter for the pinned production Speeduino ECU.
// The adapter supplies configuration and virtual pins. Engine algorithms stay
// in the external GPL source; this executable never opens hardware devices.
#include "FakeMega.h"
#include "globals.h"
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

    // Review-only fixture is persisted before the unchanged production setup.
    auto setting=[](const char* name, unsigned fallback) {
        auto* s=std::getenv(name);return s?unsigned(std::stoul(s)):fallback;
    };
    for(unsigned n=0;n<16;++n){
        fuelTable2.axisX[n]=ignitionTable2.axisX[n]=(n+1)*5;
        fuelTable2.axisY[n]=ignitionTable2.axisY[n]=(n+1)*8;
    }
    fuelTable2.values.fill(setting("REVIEW_FCELL",110));
    ignitionTable2.values.fill(setting("REVIEW_SCELL",60));
    configPage10.fuel2Mode=setting("REVIEW_FMODE",0);
    configPage10.spark2Mode=setting("REVIEW_SMODE",0);
    configPage10.fuel2Algorithm=configPage10.spark2Algorithm=static_cast<LoadSource>(setting("REVIEW_SOURCE",0));
    configPage10.fuel2SwitchVariable=configPage10.spark2SwitchVariable=setting("REVIEW_CONDITION",0);
    configPage10.fuel2SwitchValue=configPage10.spark2SwitchValue=setting("REVIEW_THRESHOLD",1000);
    configPage10.fuel2InputPin=setting("REVIEW_FPIN",14);configPage10.spark2InputPin=setting("REVIEW_SPIN",15);
    configPage10.fuel2InputPolarity=1;configPage10.spark2InputPolarity=1;
    configPage10.fuel2InputPullup=0;configPage10.spark2InputPullup=0;

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
int main(int argc,char** argv) {
    try {
        // Upstream dependency archives carry gcov instrumentation. Redirect its
        // exit-time files to this executable's cache, never the external repo.
        char binary[PATH_MAX];auto length=readlink("/proc/self/exe",binary,sizeof(binary)-1);
        if(length<=0) throw std::runtime_error("cannot locate native executable");
        binary[length]='\0';std::string path(binary);auto parent=path.substr(0,path.find_last_of('/'));
        if(setenv("GCOV_PREFIX",(parent+"/gcov").c_str(),1)!=0)throw std::runtime_error("cannot isolate coverage artifacts");
        for(int arg=1;arg<argc;++arg){
            const std::string flag(argv[arg]);
            if(flag=="--per-tooth")use_per_tooth=true;
            else if(flag=="--logger-cam")logger_cam=true;
            else if(flag=="--sequential")sequential_profile=true;
            else if(flag=="--semi-sequential")semi_sequential_profile=true;
            else throw std::runtime_error("unsupported native profile flag");
        }
        if(semi_sequential_profile&&(sequential_profile||logger_cam))throw std::runtime_error("conflicting cycle profiles");
        prepare_hal(); configure();
        // Pin numbers are resolved by setup. Prime the standard v0.4 sensors.
        setPinMapping(3);
        set_sensors(100,0,85,25,14,14.7);
        setup();
        set_sensors(100,0,85,25,14,14.7);
        for(unsigned n=0;n<8;++n) {
            auto pin=n<4?pinNumbers.injectorPins[n]:pinNumbers.coilPins[n-4];
            output_pins[n]=pin;output_masks[n]=digitalPinToBitMask(pin);
            output_ports[n]=portOutputRegister(digitalPinToPort(pin));
            output_high[n]=(*output_ports[n]&output_masks[n]) != 0;
        }
        record_edges = true;
        std::cout << "ready " << unsigned(pinNumbers.pinTrigger) << '\n';
        std::cout << "pins";
        for (unsigned n=0;n<4;++n) std::cout << ' ' << unsigned(pinNumbers.injectorPins[n]);
        for (unsigned n=0;n<4;++n) std::cout << ' ' << unsigned(pinNumbers.coilPins[n]);
        std::cout << '\n' << std::flush;
        std::string command;
        while (std::cin >> command) {
            if (command == "advance") { uint64_t us; std::cin>>us; speeduino_sim_advance(us); loop(); }
            else if (command == "tooth") { uint64_t us; std::cin>>us; speeduino_sim_advance(us); auto cb=currentStatus.decoder.primary.callback; if(!cb) throw std::runtime_error("primary ISR missing"); pins[pinNumbers.pinTrigger]=HIGH; cb(); pins[pinNumbers.pinTrigger]=LOW; loop(); }
            else if (command == "input") {
                uint64_t us=0;unsigned channel=0,high=0;
                if(!(std::cin>>us>>channel>>high)||channel>1||high>1)throw std::runtime_error("invalid virtual trigger input");
                speeduino_sim_advance(us);auto pin=channel?pinNumbers.pinTrigger2:pinNumbers.pinTrigger;
                if(pin==NOT_A_PIN||digitalPinToInterrupt(pin)==NOT_AN_INTERRUPT)throw std::runtime_error("trigger pin has no configured native interrupt");
                const bool changed=pins[pin]!=int(high);pins[pin]=high;
                const auto interrupt=digitalPinToInterrupt(pin);auto cb=interrupts_by_pin[interrupt];const auto mode=interrupt_modes[interrupt];
                if(changed&&cb&&(mode==CHANGE||(mode==RISING&&high)||(mode==FALLING&&!high)))cb();
                loop();
            }
            else if (command == "logger") {
                std::string action;std::cin>>action;
                if(action=="composite"){startCompositeLogger();log_kind=action;}
                else if(action=="tooth"){startToothLogger();log_kind=action;}
                else if(action=="stop"){
                    if(currentStatus.toothLogEnabled)stopToothLogger();
                    if(currentStatus.compositeTriggerUsed)stopCompositeLogger();
                }else throw std::runtime_error("invalid logger mode");
            }
            else if (command == "logread") {
                const unsigned count=currentStatus.isToothLog1Full?TOOTH_LOG_SIZE:toothHistoryIndex;
                if(count>TOOTH_LOG_SIZE)throw std::runtime_error("invalid production logger count");
                std::cout<<"loginfo "<<log_kind<<' '<<count<<' '<<unsigned(TOOTH_LOG_SIZE)<<' '<<currentStatus.isToothLog1Full<<'\n';
                for(unsigned i=0;i<count;++i)std::cout<<"logrow "<<i<<' '<<toothHistory[i]<<' '<<unsigned(compositeLogHistory[i])<<'\n';
            }
            else if (command == "loggerprofile") {
                std::cout<<"loggerprofile "<<unsigned(pinNumbers.pinTrigger)<<' '<<unsigned(pinNumbers.pinTrigger2)<<' '
                         <<unsigned(currentStatus.decoder.primary.edge)<<' '<<unsigned(currentStatus.decoder.secondary.edge)<<' '
                         <<unsigned(configPage2.injLayout)<<'\n';
            }
            else if (command == "sensors") { double m,t,c,i,b,a;std::cin>>m>>t>>c>>i>>b>>a;set_sensors(m,t,c,i,b,a); }

            else if(command=="reviewgpio") {
                unsigned fuel,spark;std::cin>>fuel>>spark;
                if(fuel>1||spark>1)throw std::runtime_error("review GPIO level");
                pins[pinNumbers.pinFuel2Input]=fuel;pins[pinNumbers.pinSpark2Input]=spark;
                loop();
            }
            else if(command=="reviewstatus") {
                std::cout<<"reviewstatus "<<speeduino_sim_micros()<<' '<<currentStatus.RPM<<' '<<currentStatus.MAP<<' '
                    <<unsigned(currentStatus.TPS)<<' '<<unsigned(currentStatus.VE1)<<' '<<unsigned(currentStatus.VE2)<<' '<<unsigned(currentStatus.VE)<<' '
                    <<int(currentStatus.advance1)<<' '<<int(currentStatus.advance2)<<' '<<int(currentStatus.advance)<<' '
                    <<currentStatus.secondFuelTableActive<<' '<<currentStatus.secondSparkTableActive<<' '
                    <<unsigned(configPage10.fuel2Mode)<<' '<<unsigned(configPage10.spark2Mode)<<' '
                    <<unsigned(pinNumbers.pinFuel2Input)<<' '<<unsigned(pinNumbers.pinSpark2Input)<<' '
                    <<digitalRead(pinNumbers.pinFuel2Input)<<' '<<digitalRead(pinNumbers.pinSpark2Input)<<' '
                    <<fuelSchedule1.pw<<' '<<unsigned(currentStatus.rotationStatus)<<' '
                    <<unsigned(configPage10.fuel2InputPin)<<' '<<unsigned(configPage10.spark2InputPin)<<' '<<unsigned(BOARD_MAX_IO_PINS)<<'\n';
            }

            else if (command == "status") status();
            else if(command=="injectorprofile"){
                std::cout<<"injectorprofile "<<unsigned(configPage2.injLayout)<<' '<<unsigned(currentStatus.injLayout)<<' '
                         <<unsigned(configPage2.injTiming)<<' '<<unsigned(configPage4.inj4cylPairing)<<' '
                         <<unsigned(currentStatus.nSquirts)<<' '<<CRANK_ANGLE_MAX_INJ<<' '
                         <<unsigned(currentStatus.injOutputs.primary)<<' '<<unsigned(configPage4.sparkMode)<<'\n';
            }
            else if(command=="trimconfig"){
                unsigned enabled=0;if(!(std::cin>>enabled))throw std::runtime_error("missing enable");
                if(!sequential_profile||enabled>1)throw std::runtime_error("trim profile requires sequential mode");
                configPage6.fuelTrimEnabled=enabled;
                for(unsigned channel=0;channel<4;++channel){
                    int spark=0;if(!(std::cin>>spark))throw std::runtime_error("missing spark trim");if(spark< -20||spark>20)throw std::runtime_error("spark trim range");
                    configPage13.ignTrim[channel]=spark;auto&table=trimTables[channel];
                    for(unsigned i=0;i<6;++i){unsigned value=0;if(!(std::cin>>value))throw std::runtime_error("missing trim axis");if(value>255||!value||(i&&value<=table.axisX[i-1]))throw std::runtime_error("trim RPM axis");table.axisX[i]=value;}
                    for(unsigned i=0;i<6;++i){unsigned value=0;if(!(std::cin>>value))throw std::runtime_error("missing trim axis");if(value>255||!value||(i&&value<=table.axisY[i-1]))throw std::runtime_error("trim load axis");table.axisY[i]=value;}
                    for(unsigned i=0;i<36;++i){int pct=0;if(!(std::cin>>pct))throw std::runtime_error("missing fuel trim");if(pct< -50||pct>50)throw std::runtime_error("fuel trim range");table.values[i]=FUEL_TRIM.toRaw(static_cast<int8_t>(pct));}
                    invalidate_cache(&table.get_value_cache);
                }
            }
            else if(command=="trimlookup"){
                unsigned rpm=0,load=0;std::cin>>rpm>>load;std::cout<<"trimlookup";
                for(unsigned channel=0;channel<4;++channel)std::cout<<' '<<int(FUEL_TRIM.toUser(get3DTableValue(&trimTables[channel],load,rpm)));
                std::cout<<'\n';
            }
            else if(command=="channelpw"){
                std::cout<<"channelpw "<<fuelSchedule1.pw<<' '<<fuelSchedule2.pw<<' '<<fuelSchedule3.pw<<' '<<fuelSchedule4.pw<<'\n';
            }
            else if(command=="aeconfig"){
                // Explicit before-start benchmark configuration. No production
                // sensor, correction or pulse-width algorithm is replaced.
                if(ae_profile||speeduino_sim_micros()!=0)throw std::runtime_error("AE profile is before-start only");
                unsigned a[32]{};
                for(auto &v:a)if(!(std::cin>>v)||v>255)throw std::runtime_error("AE raw byte range");
                if(a[0]>1||a[1]>1||a[7]>100||a[8]>a[9]||a[10]<100||a[11]>a[12]||a[13]>3)throw std::runtime_error("AE profile range");
                for(unsigned offset:{16u,24u})for(unsigned i=1;i<4;++i)if(a[offset+i]<=a[offset+i-1])throw std::runtime_error("AE axes must increase");
                configPage2.aeMode=a[0];configPage2.aeApplyMode=a[1];
                configPage2.taeThresh=a[2];configPage2.maeThresh=a[3];
                configPage2.taeMinChange=a[4];configPage2.maeMinChange=a[5];
                configPage2.aeTime=a[6];configPage2.decelAmount=a[7];
                configPage2.aeTaperMin=a[8];configPage2.aeTaperMax=a[9];
                configPage2.aeColdPct=a[10];configPage2.aeColdTaperMin=a[11];configPage2.aeColdTaperMax=a[12];
                configPage2.mapSample=static_cast<MAPSamplingMethod>(a[13]);
                configPage4.ADCFILTER_TPS=a[14];configPage4.ADCFILTER_MAP=a[15];
                for(unsigned i=0;i<4;++i){configPage4.taeBins[i]=a[16+i];configPage4.taeValues[i]=a[20+i];configPage4.maeBins[i]=a[24+i];configPage4.maeRates[i]=a[28+i];}
                ae_profile=true;
            }
            else if(command=="loadconfig"){
                // Before-start virtual sensor/tune fixture. Production sensor,
                // lookup, fuel arithmetic and scheduling code remain intact.
                if(load_profile||speeduino_sim_micros()!=0)throw std::runtime_error("load profile is before-start only");
                unsigned a[8]{};for(auto&v:a)if(!(std::cin>>v)||v>255)throw std::runtime_error("load profile raw byte range");
                if(a[0]>2||a[1]>2||a[2]>2||a[3]>2||a[4]>120||a[5]>1)throw std::runtime_error("load profile enum or delay range");
                configPage2.fuelAlgorithm=static_cast<LoadSource>(a[0]);configPage2.ignAlgorithm=static_cast<LoadSource>(a[1]);configPage2.multiplyMAP=a[2];
                configPage2.includeAFR=a[3]==2;configPage2.incorporateAFR=a[3]==1;
                configPage6.egoType=a[3]==2?EGO_TYPE_WIDE:EGO_TYPE_OFF;configPage6.egoAlgorithm=EGO_ALGORITHM_NONE;configPage6.ego_sdelay=a[4];
                configPage6.useEMAP=a[5];configPage2.EMAPMin=-20;configPage2.EMAPMax=620;pinNumbers.pinEMAP=201;adc[201]=192;
                // A dedicated virtual absolute-pressure input represents the
                // declared barometric datum, including a fixed manual fixture.
                configPage6.useExtBaro=1;configPage2.baroMin=0;configPage2.baroMax=200;pinNumbers.pinBaro=202;adc[202]=512;
                configPage4.ADCFILTER_MAP=a[6];configPage4.ADCFILTER_TPS=a[7];configPage4.ADCFILTER_BARO=0;
                // Profile is selected after the legacy setup. Prime the new
                // ADC paths through production initialization/read functions
                // before the first loop can divide by the EMAP observation.
                initialiseMAPBaro();readPolledSensors(1U<<MAP_READ_TIMER_BIT);load_profile=true;
            }
            else if(command=="loadprofile"){
                std::cout<<"loadprofile "<<unsigned(configPage2.fuelAlgorithm)<<' '<<unsigned(configPage2.ignAlgorithm)<<' '<<unsigned(configPage2.multiplyMAP)<<' '
                    <<(configPage2.includeAFR?2:configPage2.incorporateAFR?1:0)<<' '<<unsigned(configPage6.ego_sdelay)<<' '<<unsigned(configPage6.useEMAP)<<' '
                    <<unsigned(configPage4.ADCFILTER_MAP)<<' '<<unsigned(configPage4.ADCFILTER_TPS)<<' '<<unsigned(configPage6.useExtBaro)<<' '
                    <<unsigned(configPage6.egoType)<<' '<<unsigned(configPage6.egoAlgorithm)<<' '<<unsigned(configPage4.ADCFILTER_BARO)<<' '
                    <<int(configPage2.EMAPMin)<<' '<<configPage2.EMAPMax<<' '<<int(configPage2.baroMin)<<' '<<configPage2.baroMax<<' '<<unsigned(pinNumbers.pinEMAP)<<' '<<unsigned(pinNumbers.pinBaro)<<'\n';
            }
            else if(command=="pressure"){
                double emap=0,baro=0;if(!load_profile||!(std::cin>>emap>>baro)||!std::isfinite(emap)||!std::isfinite(baro)||emap<20||emap>500||baro<50||baro>110)throw std::runtime_error("virtual absolute-pressure range");
                adc[201]=std::lround((emap+20)/640*1024);adc[202]=std::lround(baro/200*1024);
                if(speeduino_sim_micros()==0)readPolledSensors(1U<<BARO_READ_TIMER_BIT);
            }
            else if(command=="loadmap"){
                unsigned id=0;if(!load_profile||speeduino_sim_micros()!=0||!(std::cin>>id)||id>2||(load_maps&(1U<<id)))throw std::runtime_error("load map is before-start once only");
                auto fill=[&](auto&table){
                    for(auto*axis:{&table.axisX,&table.axisY})for(unsigned i=0;i<16;++i){unsigned v=0;if(!(std::cin>>v)||v>255||(i&&v<=(*axis)[i-1]))throw std::runtime_error("load map axis range or quantization collapse");(*axis)[i]=v;}
                    for(unsigned i=0;i<256;++i){unsigned v=0;if(!(std::cin>>v)||v>255)throw std::runtime_error("load map cell range");table.values[i]=v;}invalidate_cache(&table.get_value_cache);
                };
                if(id==0)fill(fuelTable);else if(id==1)fill(ignitionTable);else fill(afrTable);load_maps|=1U<<id;
            }
            else if(command=="loadmapread"){
                unsigned id=0;if(!(std::cin>>id)||id>2)throw std::runtime_error("load map identifier");
                std::cout<<"loadmapread";auto read=[&](const auto&table){for(auto v:table.axisX)std::cout<<' '<<unsigned(v);for(auto v:table.axisY)std::cout<<' '<<unsigned(v);for(auto v:table.values)std::cout<<' '<<unsigned(v);};
                if(id==0)read(fuelTable);else if(id==1)read(ignitionTable);else read(afrTable);std::cout<<'\n';
            }
            else if(command=="loadstatus"){
                std::cout<<"loadstatus "<<speeduino_sim_micros()<<' '<<currentStatus.fuelLoad<<' '<<currentStatus.ignLoad<<' '<<currentStatus.MAP<<' '<<unsigned(currentStatus.TPS)<<' '
                    <<currentStatus.EMAP<<' '<<unsigned(currentStatus.baro)<<' '<<unsigned(currentStatus.afrTarget)<<' '<<unsigned(currentStatus.O2)<<' '<<unsigned(currentStatus.runSecs)<<' '<<unsigned(currentStatus.VE)<<'\n';
            }
            else if(command=="aeprofile"){
                std::cout<<"aeprofile "<<unsigned(configPage2.aeMode)<<' '<<unsigned(configPage2.aeApplyMode)<<' '
                    <<unsigned(configPage2.taeThresh)<<' '<<unsigned(configPage2.maeThresh)<<' '<<unsigned(configPage2.taeMinChange)<<' '<<unsigned(configPage2.maeMinChange)<<' '
                    <<unsigned(configPage2.aeTime)<<' '<<unsigned(configPage2.decelAmount)<<' '<<unsigned(configPage2.aeTaperMin)<<' '<<unsigned(configPage2.aeTaperMax)<<' '
                    <<unsigned(configPage2.aeColdPct)<<' '<<unsigned(configPage2.aeColdTaperMin)<<' '<<unsigned(configPage2.aeColdTaperMax)<<' '
                    <<unsigned(configPage2.mapSample)<<' '<<unsigned(configPage4.ADCFILTER_TPS)<<' '<<unsigned(configPage4.ADCFILTER_MAP);
                for(unsigned i=0;i<4;++i)std::cout<<' '<<unsigned(configPage4.taeBins[i]);
                for(unsigned i=0;i<4;++i)std::cout<<' '<<unsigned(configPage4.taeValues[i]);
                for(unsigned i=0;i<4;++i)std::cout<<' '<<unsigned(configPage4.maeBins[i]);
                for(unsigned i=0;i<4;++i)std::cout<<' '<<unsigned(configPage4.maeRates[i]);
                std::cout<<'\n';
            }
            else if(command=="aestatus"){
                std::cout<<"aestatus "<<speeduino_sim_micros()<<' '<<unsigned(currentStatus.TPS)<<' '<<unsigned(currentStatus.TPSlast)<<' '
                    <<currentStatus.MAP<<' '<<getMAPDelta()<<' '<<getMAPDeltaTime()<<' '<<currentStatus.tpsDOT<<' '<<currentStatus.mapDOT<<' '
                    <<currentStatus.AEamount<<' '<<currentStatus.isAcceleratingTPS<<' '<<currentStatus.isDeceleratingTPS<<' '<<currentStatus.AEStartTime<<'\n';
            }
            else if (command == "profile") {
                std::cout << "profile " << unsigned(configPage2.reqFuel) << ' ' << unsigned(configPage4.HardRevLim) << ' '
                          << unsigned(configPage4.SoftRevLim) << ' ' << unsigned(configPage6.engineProtectType) << ' '
                          << unsigned(configPage9.hardRevMode) << ' ' << unsigned(configPage2.perToothIgn) << '\n';
            }
            else if(command=="cycleprofile"){
                std::cout<<"cycleprofile "<<unsigned(configPage2.injLayout)<<' '<<unsigned(configPage4.sparkMode)<<' '<<unsigned(configPage4.TrigSpeed)<<' '<<unsigned(configPage4.trigPatternSec)<<' '<<unsigned(configPage2.injTiming);
                for(unsigned n=0;n<4;++n)std::cout<<' '<<configPage2.injAng[n];std::cout<<'\n';
            }
            else if(command=="idleconfig"){
                unsigned algorithm,hz,kp,ki,kd,tps,hysteresis,taper,minimum,maximum,fasttemp,seed,invert;
                if(!(std::cin>>algorithm>>hz>>kp>>ki>>kd>>tps>>hysteresis>>taper>>minimum>>maximum>>fasttemp>>seed>>invert)||algorithm>6||!hz||hz>250||hz%2||kp>255||ki>255||kd>255||tps>200||hysteresis>150||taper>100||minimum>=maximum||maximum>100||fasttemp>130||seed>1||invert>1)throw std::runtime_error("invalid idle profile");
                if(idle_profile)throw std::runtime_error("idle configuration is before-start only");
                configPage6.iacAlgorithm=algorithm;configPage6.idleFreq=FREQUENCY.toRaw(hz);configPage6.iacChannels=0;configPage6.iacPWMdir=invert;configPage6.iacPWMrun=false;
                configPage6.idleKP=kp;configPage6.idleKI=ki;configPage6.idleKD=kd;configPage2.iacTPSlimit=tps;configPage2.iacRPMlimitHysteresis=hysteresis;configPage2.idleTaperTime=taper;
                configPage2.iacCLminValue=minimum;configPage2.iacCLmaxValue=maximum;configPage6.iacFastTemp=fasttemp;
                configPage2.idleUpEnabled=false;configPage2.idleUpAdder=0;configPage2.idleUpOutputEnabled=false;configPage15.airConIdleSteps=0;
                for(unsigned i=0;i<10;++i){unsigned duty,target;if(!(std::cin>>duty>>target)||duty>100||target<60||target>250)throw std::runtime_error("invalid idle table");configPage6.iacBins[i]=20*i;configPage6.iacOLPWMVal[i]=duty;configPage6.iacCLValues[i]=target;}
                for(unsigned i=0;i<4;++i){unsigned duty;if(!(std::cin>>duty)||duty>100)throw std::runtime_error("invalid idle crank table");configPage6.iacCrankBins[i]=60*i;configPage6.iacCrankDuty[i]=duty;}
                idle_profile=true;initialiseIdle(true);
                std::cout<<"idleregisters "<<speeduino_sim_micros()<<' '<<IDLE_COUNTER.load()<<' '<<IDLE_COMPARE.load()<<' '<<ECU_SIM_TIMER_BITS<<' '<<ECU_SIM_IDLE_TICK_US<<' '<<unsigned(pinNumbers.pinIdle1)<<' '<<unsigned(seed)<<' '<<unsigned(invert)<<'\n';
                if(seed)IDLE_COMPARE=static_cast<software_timer_t::counter_t>(IDLE_COUNTER.load()+1);
            }
            else if(command=="idlestatus"){
                std::cout<<"idlestatus "<<unsigned(configPage6.iacAlgorithm)<<' '<<unsigned(FREQUENCY.toUser(configPage6.idleFreq))<<' '<<unsigned(currentStatus.idleLoad)<<' '<<unsigned(currentStatus.CLIdleTarget)*10<<' '<<unsigned(currentStatus.idleOn)<<' '<<unsigned(idle_high)<<' '<<IDLE_COUNTER.load()<<' '<<IDLE_COMPARE.load()<<'\n';
            }
            else if(command=="idledisable"){disableIdle();}
            else if(command=="idleclock"){uint64_t us;std::cin>>us;speeduino_sim_advance(us);}
            else if(command=="idleprobe"){
                unsigned rpm,rotation,tps;int clt;if(!(std::cin>>rpm>>rotation>>clt>>tps)||rpm>8000||rotation>2||clt< -40||clt>140||tps>200)throw std::runtime_error("invalid isolated idle input");
                currentStatus.RPM=rpm;currentStatus.coolant=clt;currentStatus.TPS=tps;currentStatus.rotationStatus=static_cast<EngineRotationStatus>(rotation);idleControl();
            }
            else if (command == "halt") { stopFuelSchedulers();stopIgnitionSchedulers();closeAllInjectors();stopAllCoilsCharging();if(idle_profile)disableIdle(); }
            else if (command == "quit") break;
            else throw std::runtime_error("unknown command");
            speeduino_sim_observe();
            if (!std::cin) throw std::runtime_error("bad command arguments");
            std::cout << "ok\n" << std::flush;
        }
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 2; }
}
