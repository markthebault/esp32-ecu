// Distinct sixteen-GPIO fixture for the pinned, non-UNIT_TEST production ECU.
// Reuse the historical input/configuration helpers, not its eight-pin observer.
// No production decoder, control, callback or scheduler algorithm is replaced.
#define main historical_four_cylinder_main
#define speeduino_sim_observe historical_eight_pin_observer
#include "speeduino_sim.cpp"
#undef speeduino_sim_observe
#undef main
#include <array>
#include <set>
#include <vector>

namespace {
constexpr std::array<uint8_t,16> fixture_pins{{22,23,25,26,27,28,29,30,31,32,33,34,35,36,37,38}};
std::array<volatile uint8_t*,16> fixture_ports{};
std::array<uint8_t,16> fixture_masks{};
std::array<bool,16> fixture_high{};
unsigned requested_count=0,requested_spark=0,requested_layout=0;
bool fixture_record=false,halted=false;

std::vector<uint8_t> other_pins() {
    // Enumerate named bindings, including disabled auxiliaries. Never index
    // FakeMega's unchecked 70-element port tables with NOT_A_PIN (255).
    return {pinNumbers.pinTrigger,pinNumbers.pinTrigger2,pinNumbers.pinTrigger3,
        pinNumbers.pinTPS,pinNumbers.pinMAP,pinNumbers.pinEMAP,pinNumbers.pinIAT,
        pinNumbers.pinCLT,pinNumbers.pinO2,pinNumbers.pinO2_2,pinNumbers.pinBat,
        pinNumbers.pinTachOut,pinNumbers.pinFuelPump,pinNumbers.pinIdle1,
        pinNumbers.pinIdle2,pinNumbers.pinIdleUp,pinNumbers.pinIdleUpOutput,
        pinNumbers.pinCTPS,pinNumbers.pinFuel2Input,pinNumbers.pinSpark2Input,
        pinNumbers.pinBoost,pinNumbers.pinVVT_1,pinNumbers.pinVVT_2,pinNumbers.pinFan,
        pinNumbers.pinStepperDir,pinNumbers.pinStepperStep,pinNumbers.pinStepperEnable,
        pinNumbers.pinLaunch,pinNumbers.pinIgnBypass,pinNumbers.pinFlex,pinNumbers.pinVSS,
        pinNumbers.pinBaro,pinNumbers.pinResetControl,pinNumbers.pinFuelPressure,
        pinNumbers.pinOilPressure,pinNumbers.pinWMIEmpty,pinNumbers.pinWMIIndicator,
        pinNumbers.pinWMIEnabled,pinNumbers.pinAirConComp,pinNumbers.pinAirConFan,
        pinNumbers.pinAirConRequest};
}

void bind_fixture() {
    if(speeduino_sim_micros()!=0 || currentStatus.RPM || record_edges)
        throw std::runtime_error("fixture must be rebound before clock/input/output observation");
    stopFuelSchedulers();stopIgnitionSchedulers();
    closeAllInjectors();stopAllCoilsCharging();
    std::set<std::pair<volatile uint8_t*,uint8_t>> used;
    const auto others=other_pins();
    for(unsigned i=0;i<16;++i) {
        const auto pin=fixture_pins[i];
        if(pin>=70)throw std::runtime_error("fixture exceeds native port map");
        const auto port=portOutputRegister(digitalPinToPort(pin));
        const auto mask=digitalPinToBitMask(pin);
        if(!port || !mask || !used.emplace(port,mask).second)
            throw std::runtime_error("fixture output port/mask aliases another output");
        for(const auto auxiliary:others) {
            if(auxiliary==NOT_A_PIN)continue;
            if(auxiliary>=70)throw std::runtime_error("auxiliary outside native port map");
            if(auxiliary==pin || (port==portOutputRegister(digitalPinToPort(auxiliary)) &&
                    mask==digitalPinToBitMask(auxiliary)))
                throw std::runtime_error("fixture output aliases an input or auxiliary");
        }
        fixture_ports[i]=port;fixture_masks[i]=mask;
        if(i<8)pinNumbers.setInjectorPin(i,pin);else pinNumbers.setCoilPin(i-8,pin);
    }
    // Real setup may have validated/fallen back. Restore the requested modes
    // before invoking the unchanged public initializers on the new bindings.
    configPage2.nCylinders=requested_count;configPage2.nInjectors=requested_count;
    configPage2.injLayout=requested_layout;configPage4.sparkMode=requested_spark;
    initialiseIgnitionSchedules(currentStatus,configPage2,configPage4,configPage10,configPage13,pinNumbers);
    initialiseFuelSchedules(currentStatus,configPage2,configPage4,configPage6,configPage10,pinNumbers);
    for(unsigned i=0;i<16;++i) {
        if((i<8?pinNumbers.injectorPins[i]:pinNumbers.coilPins[i-8])!=fixture_pins[i] ||
                (*fixture_ports[i]&fixture_masks[i]))
            throw std::runtime_error("fixture failed binding or initial all-low check");
        fixture_high[i]=false;
    }
    startIgnitionSchedulers();startFuelSchedulers();
    fixture_record=true;
}

void geometry() {
    const std::array<int,8> fuel{{fuelSchedule1.channelDegrees,fuelSchedule2.channelDegrees,
        fuelSchedule3.channelDegrees,fuelSchedule4.channelDegrees,fuelSchedule5.channelDegrees,
        fuelSchedule6.channelDegrees,fuelSchedule7.channelDegrees,fuelSchedule8.channelDegrees}};
    const std::array<int,8> spark{{ignitionSchedule1.channelDegrees,ignitionSchedule2.channelDegrees,
        ignitionSchedule3.channelDegrees,ignitionSchedule4.channelDegrees,ignitionSchedule5.channelDegrees,
        ignitionSchedule6.channelDegrees,ignitionSchedule7.channelDegrees,ignitionSchedule8.channelDegrees}};
    std::cout<<"geometry {\"requested_cylinders\":"<<requested_count
        <<",\"cylinders\":"<<unsigned(configPage2.nCylinders)<<",\"injectors\":"<<unsigned(configPage2.nInjectors)
        <<",\"requested_spark_mode\":"<<requested_spark<<",\"configured_spark_mode\":"<<unsigned(configPage4.sparkMode)
        <<",\"requested_injection_layout\":"<<requested_layout<<",\"configured_injection_layout\":"<<unsigned(configPage2.injLayout)
        <<",\"effective_injection_layout\":"<<unsigned(currentStatus.injLayout)
        <<",\"ignition_outputs\":"<<unsigned(currentStatus.maxIgnOutputs)
        <<",\"primary_injector_outputs\":"<<unsigned(currentStatus.injOutputs.primary)
        <<",\"n_squirts\":"<<unsigned(currentStatus.nSquirts)<<",\"ignition_span_deg\":"<<CRANK_ANGLE_MAX_IGN
        <<",\"injection_span_deg\":"<<CRANK_ANGLE_MAX_INJ<<",\"sync_status\":"<<unsigned(currentStatus.decoder.getStatus().syncStatus)
        <<",\"reqFuel_point1ms\":"<<unsigned(configPage2.reqFuel)<<",\"divider\":"<<unsigned(configPage2.divider)
        <<",\"injection_timing\":"<<unsigned(configPage2.injTiming)
        <<",\"per_tooth\":"<<unsigned(configPage2.perToothIgn)<<",\"halted\":"<<(halted?"true":"false");
    auto array=[](const char*name,const auto&values) {
        std::cout<<",\""<<name<<"\":[";
        for(unsigned i=0;i<values.size();++i){if(i)std::cout<<',';std::cout<<unsigned(values[i]);}
        std::cout<<']';
    };
    array("fuel_schedule_degrees",fuel);array("spark_schedule_degrees",spark);
    array("native_output_pins",fixture_pins);array("native_port_masks",fixture_masks);
    std::array<unsigned,16> ports{};
    for(unsigned i=0;i<16;++i)ports[i]=digitalPinToPort(fixture_pins[i]);
    array("native_port_ids",ports);
    std::cout<<"}\n";
}
}

extern "C" void speeduino_sim_observe() {
    if(!fixture_record)return;
    for(unsigned i=0;i<16;++i) {
        const bool high=(*fixture_ports[i]&fixture_masks[i])!=0;
        if(high==fixture_high[i])continue;
        fixture_high[i]=high;
        // Effective modes are captured at the actual port observation, not
        // inferred later from requested setup or a more recent status sample.
        std::cout<<"edge "<<speeduino_sim_micros()<<' '<<unsigned(fixture_pins[i])<<' '<<unsigned(high)
            <<' '<<unsigned(currentStatus.decoder.getStatus().syncStatus)<<' '<<CRANK_ANGLE_MAX_IGN
            <<' '<<CRANK_ANGLE_MAX_INJ<<' '<<unsigned(currentStatus.injLayout)
            <<' '<<unsigned(currentStatus.maxIgnOutputs)<<' '<<unsigned(currentStatus.injOutputs.primary)<<'\n';
    }
}

int main(int argc,char**argv) {
    try {
        if(argc<3 || argc>4)throw std::runtime_error("count1..8, sequential/wasted_cop/semi, optional --per-tooth required");
        const std::string count(argv[1]),mode(argv[2]);
        if(count.size()!=1 || count[0]<'1' || count[0]>'8')throw std::runtime_error("count outside1..8");
        requested_count=count[0]-'0';
        sequential_profile=mode=="sequential";semi_sequential_profile=mode=="semi";
        if(!sequential_profile && !semi_sequential_profile && mode!="wasted_cop")throw std::runtime_error("unknown profile mode");
        if(argc==4){if(std::string(argv[3])!="--per-tooth")throw std::runtime_error("unknown option");use_per_tooth=true;}
        char binary[PATH_MAX];auto length=readlink("/proc/self/exe",binary,sizeof(binary)-1);
        if(length<=0)throw std::runtime_error("cannot locate executable");
        binary[length]='\0';const std::string path(binary);
        if(setenv("GCOV_PREFIX",(path.substr(0,path.find_last_of('/'))+"/gcov").c_str(),1)!=0)
            throw std::runtime_error("cannot isolate dependency instrumentation");
        prepare_hal();configure();
        configPage2.nCylinders=requested_count;configPage2.nInjectors=requested_count;
        configPage2.engineType=EVEN_FIRE;
        // Non-sequential fuel arithmetic assumes two squirts per720deg.
        // For N1, zero selects production's default two, whereas divider1
        // would request one squirt and deliver only half the intended fuel.
        configPage2.divider=requested_count/2;
        requested_layout=configPage2.injLayout;requested_spark=configPage4.sparkMode;
        do{saveAllPages();}while(isEepromWritePending());
        setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();
        bind_fixture();set_sensors(100,0,85,25,14,14.7);
        std::cout<<"ready_profiles "<<unsigned(pinNumbers.pinTrigger)<<' '<<unsigned(pinNumbers.pinTrigger2)<<'\n';
        geometry();std::cout<<std::flush;
        std::string command;
        while(std::cin>>command) {
            if(command=="advance" || command=="tooth") {
                uint64_t us=0;if(!(std::cin>>us))throw std::runtime_error("missing time");
                speeduino_sim_advance(us);
                if(command=="tooth") {
                    auto cb=currentStatus.decoder.primary.callback;
                    if(!cb)throw std::runtime_error("primary callback missing");
                    pins[pinNumbers.pinTrigger]=HIGH;cb();pins[pinNumbers.pinTrigger]=LOW;
                }
                run_loop();
            } else if(command=="input") {
                uint64_t us=0;unsigned channel=0,high=0;
                if(!(std::cin>>us>>channel>>high)||channel>1||high>1)throw std::runtime_error("invalid trigger edge");
                speeduino_sim_advance(us);const auto pin=channel?pinNumbers.pinTrigger2:pinNumbers.pinTrigger;
                if(pin>=70 || digitalPinToInterrupt(pin)==NOT_AN_INTERRUPT)throw std::runtime_error("input has no native interrupt");
                const bool changed=pins[pin]!=int(high);pins[pin]=high;
                const auto interrupt=digitalPinToInterrupt(pin);auto cb=interrupts_by_pin[interrupt];const auto edge=interrupt_modes[interrupt];
                if(changed && cb && (edge==CHANGE || (edge==RISING&&high) || (edge==FALLING&&!high)))cb();
                run_loop();
            } else if(command=="sensors") {
                double v[6]{};for(auto&value:v)if(!(std::cin>>value)||!std::isfinite(value))throw std::runtime_error("invalid sensor");
                if(v[0]<0||v[0]>200||v[1]<0||v[1]>100||v[2]<-40||v[2]>140||v[3]<-40||v[3]>140||v[4]<0||v[4]>24.5||v[5]<8||v[5]>23.5)
                    throw std::runtime_error("sensor outside fixture calibration");
                set_sensors(v[0],v[1],v[2],v[3],v[4],v[5]);
            } else if(command=="status")status();
            else if(command=="geometry")geometry();
            else if(command=="halt") {
                stopFuelSchedulers();stopIgnitionSchedulers();closeAllInjectors();stopAllCoilsCharging();halted=true;
            } else if(command=="quit")break;
            else throw std::runtime_error("unsupported profile fixture command");
            speeduino_sim_observe();
            if(!std::cin)throw std::runtime_error("malformed input");
            std::cout<<"ok\n"<<std::flush;
        }
        stopFuelSchedulers();stopIgnitionSchedulers();closeAllInjectors();stopAllCoilsCharging();
        return 0;
    } catch(const std::exception&error){std::cerr<<error.what()<<'\n';return 2;}
}
