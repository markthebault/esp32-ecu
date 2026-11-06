// Real pinned production setup/loop/boost/protection in the existing native
// HAL. Only this input/output entry is new; no controller status is injected.
#define main numerical_benchmark_main
#define speeduino_sim_observe speeduino_base_observe
#include "speeduino_sim.cpp"
#undef speeduino_sim_observe
#undef main
#include <iomanip>

namespace {
bool monitor_boost=false,last_boost=false;
void before(std::uint64_t target){
 if(target<speeduino_sim_micros())throw std::runtime_error("Clock reversal");
 while((speeduino_sim_micros()/1000+1)*1000<target){
  speeduino_sim_advance((speeduino_sim_micros()/1000+1)*1000);run_loop();
 }
 speeduino_sim_advance(target);
}
void input(double map,double tps){
 if(!std::isfinite(map)||map<0||map>400||!std::isfinite(tps)||tps<0||tps>100)throw std::runtime_error("Invalid sensor input");
 set_sensors(map,tps,85,25,14,14.7);
 adc[pinNumbers.pinMAP]=std::lround(map/400*1023);
}
void report(){
 std::cout<<"{\"kind\":\"sample\",\"time_us\":"<<speeduino_sim_micros()<<",\"map_kpa\":"<<currentStatus.MAP
  <<",\"raw_map_adc\":"<<adc[pinNumbers.pinMAP]<<",\"tps_raw_half_pct\":"<<unsigned(currentStatus.TPS)
  <<",\"tps_pct\":"<<double(currentStatus.TPS)/2<<",\"boost_lookup_tps_coordinate\":"<<unsigned(currentStatus.TPS)*2
  <<",\"boost_lookup_y_factor\":"<<getConversionFactor(decltype(boostTable)::YDomain)
  <<",\"boost_stored_tps_coordinate\":"<<unsigned(currentStatus.TPS)*2/getConversionFactor(decltype(boostTable)::YDomain)<<",\"rpm\":"<<currentStatus.RPM
  <<",\"rotation_code\":"<<unsigned(currentStatus.rotationStatus)<<",\"boost_duty_pct\":"<<double(currentStatus.boostDuty)/100
  <<",\"boost_target_kpa\":"<<currentStatus.boostTarget<<",\"boost_pin_high\":"<<(pins[pinNumbers.pinBoost]!=0)
  <<",\"timer_counter\":"<<boostTimer.counter.load()<<",\"timer_compare\":"<<boostTimer.compare.load()
  <<",\"boost_cut\":"<<currentStatus.engineProtect.boostCut<<",\"fuel_channels\":"<<unsigned(currentStatus.schedulerCutState.fuelChannels)
  <<",\"spark_channels\":"<<unsigned(currentStatus.schedulerCutState.ignitionChannels)<<",\"physical_execution\":false}\n"<<std::flush;
}
}
extern "C" void speeduino_sim_observe(){
 speeduino_base_observe();
 if(!monitor_boost)return;
 const bool high=pins[pinNumbers.pinBoost]!=0;
 if(high!=last_boost){last_boost=high;std::cout<<"{\"kind\":\"boost_edge\",\"time_us\":"<<speeduino_sim_micros()<<",\"high\":"<<high<<",\"physical_execution\":false}\n";}
}
int main(int argc,char**argv){
 try{
  if(argc<6||argc>8)throw std::runtime_error("Expected mode duty target frequency cut [--default-unarmed-compare] [--tps-duty-ramp]");
  bool default_compare=false,tps_ramp=false;
  for(int n=6;n<argc;++n){const std::string option=argv[n];
   if(option=="--default-unarmed-compare"&&!default_compare)default_compare=true;
   else if(option=="--tps-duty-ramp"&&!tps_ramp)tps_ramp=true;
   else throw std::runtime_error("Unsupported/duplicate fixture option");
  }
  const std::string mode=argv[1];std::size_t used=0;
  auto integer=[&](const char*text){const std::string value=text;const auto n=std::stoul(value,&used);if(used!=value.size()||n>400)throw std::runtime_error("Invalid integer");return unsigned(n);};
  const unsigned duty=integer(argv[2]),target=integer(argv[3]),frequency=integer(argv[4]),cut=integer(argv[5]);
  if((mode!="off"&&mode!="open"&&mode!="closed")||duty>100||(mode=="open"&&duty%2)||target<50||target>300||target%2||frequency<10||frequency>50||frequency%2||cut<100||cut>400||cut%2)throw std::runtime_error("Unrepresentable production profile");
  char executable[PATH_MAX];const auto length=readlink("/proc/self/exe",executable,sizeof(executable)-1);
  if(length<=0)throw std::runtime_error("Cannot locate executable");executable[length]='\0';
  const auto parent=std::string(executable).substr(0,std::string(executable).find_last_of('/'));
  if(setenv("GCOV_PREFIX",(parent+"/gcov").c_str(),1))throw std::runtime_error("Cannot isolate coverage");
  std::cout<<std::boolalpha<<std::setprecision(17);
  prepare_hal();configure();
  configPage2.mapMin=0;configPage2.mapMax=400;configPage2.boostMinDuty=0;configPage2.boostMaxDuty=90;
  configPage4.ADCFILTER_MAP=configPage4.ADCFILTER_TPS=0;configPage2.mapSample=MAPSamplingInstantaneous;
  configPage4.boostType=mode=="closed"?CLOSED_LOOP_BOOST:OPEN_LOOP_BOOST;
  configPage6.boostEnabled=mode!="off";configPage6.boostFreq=frequency/2;configPage6.boostMode=BOOST_MODE_FULL;
  configPage6.boostKP=10;configPage6.boostKI=0;configPage6.boostKD=0;
  configPage6.boostCutEnabled=true;configPage6.boostLimit=cut/2;configPage4.engineProtectMaxRPM=0;
  configPage10.boostIntv=100;configPage10.boostSens=1000;configPage9.boostByGearEnabled=0;
  configPage15.boostControlEnable=EN_BOOST_CONTROL_FIXED;configPage15.boostControlEnableThreshold=120;configPage15.boostDCWhenDisabled=0;
  const unsigned axis[]={0,10,20,40,80,120,160,200};
  for(unsigned n=0;n<8;++n){boostTable.axisX[n]=boostTableLookupDuty.axisX[n]=5+10*n;boostTable.axisY[n]=axis[n];boostTableLookupDuty.axisY[n]=50+25*n;}
  boostTable.values.fill(mode=="closed"?target/2:duty/2);boostTableLookupDuty.values.fill(duty*2);
  if(tps_ramp){if(mode!="open")throw std::runtime_error("TPS duty ramp requires open loop");
   for(unsigned row=0;row<8;++row)for(unsigned col=0;col<8;++col)boostTable.values[row*8+col]=axis[row]/4;
  }
  do{saveAllPages();}while(isEepromWritePending());
  // The generic32-bit native timer starts compare at UINT32_MAX, which never
  // fires in a60s run. Declare a virtual reset-to-zero register fixture for
  // this channel; retain the untouched default as a negative execution witness.
  if(!default_compare)boostTimer.compare.store(0);
  setPinMapping(3);input(100,50);setup();input(100,50);
  if(configPage6.boostEnabled!=(mode!="off")||configPage2.mapMax!=400||configPage6.boostFreq!=frequency/2||configPage6.boostLimit!=cut/2||pin_modes[pinNumbers.pinBoost]!=OUTPUT)throw std::runtime_error("Production setup changed profile");
  last_boost=pins[pinNumbers.pinBoost]!=0;monitor_boost=true;
  std::cout<<"{\"kind\":\"ready\",\"time_us\":"<<speeduino_sim_micros()<<",\"boost_pin\":"<<unsigned(pinNumbers.pinBoost)
   <<",\"crank_pin\":"<<unsigned(pinNumbers.pinTrigger)<<",\"frequency_hz\":"<<frequency<<",\"mode\":\""<<mode
   <<"\",\"cut_kpa\":"<<cut<<",\"native_initial_compare\":"<<(default_compare?UINT32_MAX:0)
   <<",\"tps_duty_ramp\":"<<tps_ramp<<",\"native_timer_tick_us\":4,\"physical_execution\":false}\n"<<std::flush;
  std::string command;
  while(std::cin>>command){
   std::uint64_t time;if(command=="quit")break;
   if(!(std::cin>>time))throw std::runtime_error("Missing input time");before(time);
   if(command=="sensors"){double map,tps;if(!(std::cin>>map>>tps))throw std::runtime_error("Missing sensors");input(map,tps);}
   else if(command=="trigger"){
    unsigned level;if(!(std::cin>>level)||level>1)throw std::runtime_error("Invalid trigger");
    const auto pin=pinNumbers.pinTrigger;const auto irq=digitalPinToInterrupt(pin);if(irq==NOT_AN_INTERRUPT)throw std::runtime_error("No primary IRQ");
    const bool changed=pins[pin]!=int(level);pins[pin]=level;const auto callback=interrupts_by_pin[irq];const auto edge=interrupt_modes[irq];
    if(changed&&callback&&(edge==CHANGE||(edge==RISING&&level)||(edge==FALLING&&!level)))callback();
   }else if(command!="observe")throw std::runtime_error("Unsupported input");
   run_loop();speeduino_sim_observe();if(command=="observe")report();
  }
  if(!std::cin.eof()&&std::cin.fail())throw std::runtime_error("Malformed input stream");
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
