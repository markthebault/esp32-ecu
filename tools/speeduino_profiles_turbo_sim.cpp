// Generated include changes only the project fixture's main/observer names.
// All production controller/decoder/scheduler objects remain unchanged.
extern "C" void speeduino_sim_observe();
#include "speeduino_profiles_base.inc"
#include <iomanip>

namespace {
bool boost_monitor=false,boost_high=false;
uint64_t next_loop_us=0;
unsigned loop_period_us=1000,cut_kpa=220,protect_rpm100=65,required_fuel=107;

uint64_t wire_unsigned(const std::string& text,uint64_t maximum) {
    if(text.empty())throw std::runtime_error("empty wire integer");uint64_t value=0;
    for(const char c:text) {
        if(c<'0'||c>'9')throw std::runtime_error("invalid whole wire integer");
        const unsigned digit=unsigned(c-'0');
        if(value>maximum/10||(value==maximum/10&&digit>maximum%10))throw std::runtime_error("wire integer exceeds bound");
        value=value*10+digit;
    }
    return value;
}
double wire_real(const std::string& text) {
    std::size_t used=0;const double value=std::stod(text,&used);
    if(used!=text.size()||!std::isfinite(value))throw std::runtime_error("invalid whole wire real");
    return value;
}
bool wire_line(std::string& line) {
    line.clear();char c;
    while(std::cin.get(c)) {
        if(c=='\n')return true;
        if(c=='\0'||line.size()>=4096)throw std::runtime_error("overlong or NUL wire line");
        line.push_back(c);
    }
    if(!std::cin.eof())throw std::runtime_error("wire read failed");return !line.empty();
}

void calendar(uint64_t target) {
    if(target<speeduino_sim_micros()||target>60000000)throw std::runtime_error("invalid bounded coupling time");
    while(next_loop_us<=target) {
        speeduino_sim_advance(next_loop_us);run_loop();speeduino_sim_observe();next_loop_us+=loop_period_us;
    }
    speeduino_sim_advance(target);
}
void turbo_sensors(double map,double tps,double clt,double iat,double battery,double afr) {
    if(!std::isfinite(map)||map<0||map>400||!std::isfinite(tps)||tps<0||tps>100||
       !std::isfinite(clt)||clt< -273.15||clt>2000||!std::isfinite(iat)||iat< -273.15||iat>2000||
       !std::isfinite(battery)||battery<0||battery>24||!std::isfinite(afr)||afr<5||afr>40)
        throw std::runtime_error("invalid coupling sensors");
    set_sensors(map,tps,clt,iat,battery,afr);
    adc[pinNumbers.pinMAP]=std::lround(map/400*1023);
    for(const auto pin:{pinNumbers.pinMAP,pinNumbers.pinTPS,pinNumbers.pinCLT,pinNumbers.pinIAT,pinNumbers.pinBat,pinNumbers.pinO2})
        adc[pin]=std::max(0,std::min(1023,adc[pin]));
}
void boost_status() {
    std::cout<<"booststatus "<<speeduino_sim_micros()<<' '<<currentStatus.MAP<<' '<<unsigned(currentStatus.TPS)<<' '<<currentStatus.RPM<<' '
        <<currentStatus.boostDuty<<' '<<currentStatus.boostTarget<<' '<<unsigned(pins[pinNumbers.pinBoost]!=0)<<' '
        <<unsigned(currentStatus.engineProtect.boostCut)<<' '<<boostTimer.counter.load()<<' '<<boostTimer.compare.load()<<' '<<unsigned(currentStatus.iatCorrection)<<'\n';
}
}

extern "C" void speeduino_sim_observe() {
    speeduino_profiles_observe();
    if(!boost_monitor)return;
    const auto pin=pinNumbers.pinBoost;
    const bool high=(*portOutputRegister(digitalPinToPort(pin))&digitalPinToBitMask(pin))!=0;
    if(high!=(pins[pin]!=0))throw std::runtime_error("boost port/digitalWrite observations disagree");
    if(high!=boost_high){boost_high=high;std::cout<<"boostedge "<<speeduino_sim_micros()<<' '<<unsigned(high)<<'\n';}
}

int main(int argc,char**argv) {
    try {
        // Dependency destructors carry gcov instrumentation, including on
        // rejected CLI inputs. Isolate it before examining any argument.
        char binary[PATH_MAX];const auto length=readlink("/proc/self/exe",binary,sizeof(binary)-1);
        if(length<=0)throw std::runtime_error("cannot locate executable");binary[length]='\0';const std::string path(binary);
        if(setenv("GCOV_PREFIX",(path.substr(0,path.find_last_of('/'))+"/gcov").c_str(),1))throw std::runtime_error("cannot isolate instrumentation");
        if(argc<6||argc>11)throw std::runtime_error("count engine_mode boost_mode duty target and optional clock/limit/fuel flags required");
        auto integer=[](const std::string& text) {
            if(text.empty())throw std::runtime_error("empty integer");
            unsigned value=0;
            for(const char digit:text){if(digit<'0'||digit>'9'||value>10000)throw std::runtime_error("invalid integer");value=value*10+unsigned(digit-'0');}
            if(value>10000)throw std::runtime_error("integer exceeds bound");return value;
        };
        requested_count=integer(argv[1]);const std::string engine=argv[2],mode=argv[3];
        const auto duty=integer(argv[4]),target=integer(argv[5]);
        sequential_profile=engine=="sequential";semi_sequential_profile=engine=="semi";
        if(requested_count<1||requested_count>8||(!sequential_profile&&!semi_sequential_profile&&engine!="wasted_cop"))throw std::runtime_error("invalid engine profile");
        bool unarmed=false;std::set<std::string> flags;
        for(int i=6;i<argc;++i) {
            const std::string option=argv[i];const auto at=option.find('=');const auto name=option.substr(0,at);
            if(!flags.insert(name).second)throw std::runtime_error("repeated option");
            if(option=="--default-unarmed-compare"){unarmed=true;continue;}
            if(at==std::string::npos)throw std::runtime_error("option requires integer");
            const auto value=integer(option.substr(at+1));
            if(name=="--loop-period-us")loop_period_us=value;
            else if(name=="--cut-kpa")cut_kpa=value;
            else if(name=="--protect-rpm100")protect_rpm100=value;
            else if(name=="--required-fuel")required_fuel=value;
            else throw std::runtime_error("unknown option");
        }
        if((mode!="off"&&mode!="open_loop"&&mode!="closed_loop")||duty>90||duty%2||target<50||target>210||target%2||
           loop_period_us<100||loop_period_us>10000||cut_kpa<100||cut_kpa>300||cut_kpa%2||protect_rpm100>65||required_fuel<1||required_fuel>255)
            throw std::runtime_error("unrepresentable profile");
        std::cout<<std::setprecision(17);use_per_tooth=true;prepare_hal();configure();
        configPage2.nCylinders=requested_count;configPage2.nInjectors=requested_count;
        configPage2.engineType=EVEN_FIRE;configPage2.divider=requested_count/2;configPage2.reqFuel=required_fuel;
        requested_layout=configPage2.injLayout;requested_spark=configPage4.sparkMode;
        configPage2.mapMin=0;configPage2.mapMax=400;configPage2.boostMinDuty=0;configPage2.boostMaxDuty=90;
        configPage4.ADCFILTER_MAP=configPage4.ADCFILTER_TPS=0;configPage2.mapSample=MAPSamplingInstantaneous;
        configPage4.engineProtectMaxRPM=protect_rpm100;
        configPage4.boostType=mode=="closed_loop"?CLOSED_LOOP_BOOST:OPEN_LOOP_BOOST;
        configPage6.boostEnabled=mode!="off";configPage6.boostFreq=12;configPage6.boostMode=BOOST_MODE_FULL;
        configPage6.boostKP=10;configPage6.boostKI=configPage6.boostKD=0;
        configPage6.boostCutEnabled=true;configPage6.boostLimit=cut_kpa/2;
        configPage10.boostIntv=100;configPage10.boostSens=1000;configPage9.boostByGearEnabled=0;
        configPage15.boostControlEnable=EN_BOOST_CONTROL_FIXED;configPage15.boostControlEnableThreshold=120;configPage15.boostDCWhenDisabled=0;
        const unsigned axis[]={0,10,20,40,80,120,160,200};
        for(unsigned n=0;n<8;++n){boostTable.axisX[n]=boostTableLookupDuty.axisX[n]=5+10*n;boostTable.axisY[n]=axis[n];boostTableLookupDuty.axisY[n]=50+25*n;}
        boostTable.values.fill(mode=="closed_loop"?target/2:duty/2);boostTableLookupDuty.values.fill(duty*2);
        for(unsigned n=0;n<9;++n){const unsigned stored=n*25;configPage6.airDenBins[n]=stored;configPage6.airDenRates[n]=std::lround(100*298.15/(273.15+stored-40));}
        do{saveAllPages();}while(isEepromWritePending());
        if(!unarmed)boostTimer.compare.store(0);
        setPinMapping(3);turbo_sensors(100,0,85,25,14,14.7);setup();bind_fixture();turbo_sensors(100,0,85,25,14,14.7);
        const auto pin=pinNumbers.pinBoost;
        if(pin>=70)throw std::runtime_error("boost pin exceeds native port map");
        boost_high=(*portOutputRegister(digitalPinToPort(pin))&digitalPinToBitMask(pin))!=0;boost_monitor=true;
        std::cout<<"ready_profiles_turbo "<<unsigned(pinNumbers.pinTrigger)<<' '<<unsigned(pinNumbers.pinTrigger2)<<'\n';
        geometry();std::cout<<std::flush;
        std::string line;
        while(wire_line(line)) {
            std::istringstream input(line);std::vector<std::string> words;std::string word;
            while(input>>word)words.push_back(word);
            if(words.empty())continue;const auto&command=words[0];
            auto arity=[&](unsigned count){if(words.size()!=count)throw std::runtime_error("wrong whole-command arity");};
            // Validate the complete command before any clock/input/ADC or
            // output mutation. Numeric prefix extraction is not sufficient.
            if(command=="advance"||command=="tooth")arity(2);
            else if(command=="input")arity(4);
            else if(command=="sensors")arity(7);
            else arity(1);
            if(command=="quit")break;
            if(command=="advance"||command=="tooth") {
                const auto stamp=wire_unsigned(words[1],60000000);calendar(stamp);
                if(command=="tooth"){auto cb=currentStatus.decoder.primary.callback;if(!cb)throw std::runtime_error("missing primary callback");pins[pinNumbers.pinTrigger]=HIGH;cb();pins[pinNumbers.pinTrigger]=LOW;}
            }else if(command=="input") {
                const auto stamp=wire_unsigned(words[1],60000000);const auto channel=wire_unsigned(words[2],1),high=wire_unsigned(words[3],1);
                if(channel&&!sequential_profile)throw std::runtime_error("unconfigured secondary trigger input");
                calendar(stamp);const auto trigger=channel?pinNumbers.pinTrigger2:pinNumbers.pinTrigger;
                if(trigger>=70||digitalPinToInterrupt(trigger)==NOT_AN_INTERRUPT)throw std::runtime_error("input has no native interrupt");
                const bool changed=pins[trigger]!=int(high);pins[trigger]=high;
                const auto irq=digitalPinToInterrupt(trigger);auto cb=interrupts_by_pin[irq];const auto edge=interrupt_modes[irq];
                if(changed&&cb&&(edge==CHANGE||(edge==RISING&&high)||(edge==FALLING&&!high)))cb();
            }else if(command=="sensors") {
                double v[6]{};for(unsigned i=0;i<6;++i)v[i]=wire_real(words[i+1]);turbo_sensors(v[0],v[1],v[2],v[3],v[4],v[5]);
            }else if(command=="adcstatus") {
                std::cout<<"adcstatus";for(const auto p:{pinNumbers.pinMAP,pinNumbers.pinTPS,pinNumbers.pinCLT,pinNumbers.pinIAT,pinNumbers.pinBat,pinNumbers.pinO2})std::cout<<' '<<adc[p];std::cout<<'\n';
            }else if(command=="geometry")geometry();
            else if(command=="status")status();
            else if(command=="booststatus")boost_status();
            else if(command=="boostprofile") {
                std::cout<<"boostprofile "<<unsigned(configPage6.boostEnabled)<<' '<<unsigned(configPage4.boostType)<<' '<<unsigned(configPage6.boostFreq)<<' '<<unsigned(configPage6.boostLimit)<<' '
                    <<unsigned(configPage2.boostMinDuty)<<' '<<unsigned(configPage2.boostMaxDuty)<<' '<<unsigned(configPage6.boostKP)<<' '<<unsigned(configPage6.boostKI)<<' '<<unsigned(configPage6.boostKD)<<' '
                    <<unsigned(configPage10.boostIntv)<<' '<<unsigned(configPage10.boostSens)<<' '<<unsigned(unarmed)<<' '<<loop_period_us<<' '<<unsigned(configPage6.boostCutEnabled)<<' '
                    <<MAP.toUser(configPage6.boostLimit)<<' '<<unsigned(configPage4.engineProtectMaxRPM)<<' '<<unsigned(configPage2.reqFuel)<<' '<<unsigned(pin)<<' '
                    <<unsigned(digitalPinToPort(pin))<<' '<<unsigned(digitalPinToBitMask(pin))<<'\n';
            }else if(command=="boostmaps") {
                std::cout<<"boostmaps";auto table=[](const auto&t){for(auto v:t.axisX)std::cout<<' '<<unsigned(v);for(auto v:t.axisY)std::cout<<' '<<unsigned(v);for(auto v:t.values)std::cout<<' '<<unsigned(v);};
                table(boostTable);table(boostTableLookupDuty);for(auto v:configPage6.airDenBins)std::cout<<' '<<unsigned(v);for(auto v:configPage6.airDenRates)std::cout<<' '<<unsigned(v);std::cout<<'\n';
            }else if(command=="halt") {
                // Same explicit engine-only halt as the historical turbo
                // fixture. Production boost remains independently observable.
                stopFuelSchedulers();stopIgnitionSchedulers();closeAllInjectors();stopAllCoilsCharging();halted=true;
            }else throw std::runtime_error("unsupported expanded turbo command");
            speeduino_sim_observe();std::cout<<"ok\n"<<std::flush;
        }
        stopFuelSchedulers();stopIgnitionSchedulers();closeAllInjectors();stopAllCoilsCharging();return 0;
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
}
