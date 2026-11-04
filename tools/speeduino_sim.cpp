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
