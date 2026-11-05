// Interactive coupling fixture; unchanged pinned production objects and HAL.
// No RPM, sync, MAP, PID output or scheduler status is injected.
#define main numerical_benchmark_main
#define speeduino_sim_observe speeduino_base_observe
#include "speeduino_sim.cpp"
#undef speeduino_sim_observe
#undef main
#include <iomanip>
extern "C" void speeduino_sim_observe();

namespace {
bool monitor_boost=false,last_boost=false;
std::uint64_t next_main_loop_us=0;
unsigned main_loop_period_us=1000;
unsigned pressure_cut_kpa=220;
unsigned protection_rpm100=65;
void advance_with_main_loop(std::uint64_t stamp){
 while(next_main_loop_us<=stamp){
  speeduino_sim_advance(next_main_loop_us);run_loop();speeduino_sim_observe();next_main_loop_us+=main_loop_period_us;
 }
 speeduino_sim_advance(stamp);
}
void sensors(double map,double tps,double clt,double iat,double battery,double afr){
 if(!std::isfinite(map)||map<0||map>400||!std::isfinite(tps)||tps<0||tps>100||!std::isfinite(clt)||clt< -273.15||clt>2000||!std::isfinite(iat)||iat< -273.15||iat>2000||!std::isfinite(battery)||battery<0||battery>24||!std::isfinite(afr)||afr<5||afr>40)throw std::runtime_error("Invalid coupling sensors");
 set_sensors(map,tps,clt,iat,battery,afr);adc[pinNumbers.pinMAP]=std::lround(map/400*1023);
 // A physical 10-bit ADC rails at its endpoints. This explicit fixture policy
 // also prevents out-of-range AFR values from reaching production as >10 bits.
 for(const auto pin:{pinNumbers.pinMAP,pinNumbers.pinTPS,pinNumbers.pinCLT,pinNumbers.pinIAT,pinNumbers.pinBat,pinNumbers.pinO2})adc[pin]=std::max(0,std::min(1023,adc[pin]));
}
void boost_status(){
 std::cout<<"booststatus "<<speeduino_sim_micros()<<' '<<currentStatus.MAP<<' '<<unsigned(currentStatus.TPS)<<' '<<currentStatus.RPM<<' '
  <<currentStatus.boostDuty<<' '<<currentStatus.boostTarget<<' '<<unsigned(pins[pinNumbers.pinBoost]!=0)<<' '
  <<unsigned(currentStatus.engineProtect.boostCut)<<' '<<boostTimer.counter.load()<<' '<<boostTimer.compare.load()<<' '<<unsigned(currentStatus.iatCorrection)<<'\n';
}
}
extern "C" void speeduino_sim_observe(){
 speeduino_base_observe();if(!monitor_boost)return;
 const bool high=pins[pinNumbers.pinBoost]!=0;
 if(high!=last_boost){last_boost=high;std::cout<<"boostedge "<<speeduino_sim_micros()<<' '<<unsigned(high)<<'\n';}
}
int main(int argc,char**argv){
 try{
  if(argc<4||argc>8)throw std::runtime_error("Expected mode duty target [--default-unarmed-compare] [--loop-period-us=N] [--cut-kpa=N] [--protect-rpm100=N]");
  const std::string mode=argv[1];std::size_t used=0;
  auto integer=[&](const char*p){const std::string text(p);const auto value=std::stoul(text,&used);if(used!=text.size()||value>10000)throw std::runtime_error("Bad profile integer");return unsigned(value);};
  const auto duty=integer(argv[2]),target=integer(argv[3]);bool unarmed=false,have_period=false,have_cut=false,have_protection_rpm=false;
  for(int n=4;n<argc;++n){const std::string option=argv[n];
   if(option=="--default-unarmed-compare"&&!unarmed)unarmed=true;
   else if(option.find("--loop-period-us=")==0&&!have_period){main_loop_period_us=integer(option.c_str()+17);have_period=true;}
   else if(option.find("--cut-kpa=")==0&&!have_cut){pressure_cut_kpa=integer(option.c_str()+10);have_cut=true;}
   else if(option.find("--protect-rpm100=")==0&&!have_protection_rpm){protection_rpm100=integer(option.c_str()+17);have_protection_rpm=true;}
   else throw std::runtime_error("Unknown or repeated coupling option");
  }
  if((mode!="off"&&mode!="open_loop"&&mode!="closed_loop")||duty>90||duty%2||target<50||target>210||target%2||main_loop_period_us<100||main_loop_period_us>10000||pressure_cut_kpa<100||pressure_cut_kpa>300||pressure_cut_kpa%2||protection_rpm100>65)throw std::runtime_error("Unrepresentable profile");
  char executable[PATH_MAX];const auto count=readlink("/proc/self/exe",executable,sizeof(executable)-1);if(count<=0)throw std::runtime_error("Cannot locate fixture");executable[count]='\0';
  const auto parent=std::string(executable).substr(0,std::string(executable).find_last_of('/'));if(setenv("GCOV_PREFIX",(parent+"/gcov").c_str(),1))throw std::runtime_error("Cannot isolate coverage");
  std::cout<<std::setprecision(17);use_per_tooth=true;prepare_hal();configure();
  configPage2.reqFuel=96; // Declared1.8L/300cc matched bench, rounded0.1ms.
  configPage2.mapMin=0;configPage2.mapMax=400;configPage2.boostMinDuty=0;configPage2.boostMaxDuty=90;
  configPage4.ADCFILTER_MAP=configPage4.ADCFILTER_TPS=0;configPage2.mapSample=MAPSamplingInstantaneous;
  configPage4.engineProtectMaxRPM=protection_rpm100;
  configPage4.boostType=mode=="closed_loop"?CLOSED_LOOP_BOOST:OPEN_LOOP_BOOST;
  configPage6.boostEnabled=mode!="off";configPage6.boostFreq=12;configPage6.boostMode=BOOST_MODE_FULL;
  configPage6.boostKP=10;configPage6.boostKI=0;configPage6.boostKD=0;configPage6.boostCutEnabled=true;configPage6.boostLimit=pressure_cut_kpa/2;
  configPage10.boostIntv=100;configPage10.boostSens=1000;configPage9.boostByGearEnabled=0;
  configPage15.boostControlEnable=EN_BOOST_CONTROL_FIXED;configPage15.boostControlEnableThreshold=120;configPage15.boostDCWhenDisabled=0;
  const unsigned axis[]={0,10,20,40,80,120,160,200};
  for(unsigned n=0;n<8;++n){boostTable.axisX[n]=boostTableLookupDuty.axisX[n]=5+10*n;boostTable.axisY[n]=axis[n];boostTableLookupDuty.axisY[n]=50+25*n;}
  boostTable.values.fill(mode=="closed_loop"?target/2:duty/2);boostTableLookupDuty.values.fill(duty*2);
  // The old NA reference neutralized this correction at fixed25C. Dynamic
  // charge temperature needs an explicit matched ideal-density curve.
  for(unsigned n=0;n<9;++n){const unsigned stored=n*25;configPage6.airDenBins[n]=stored;configPage6.airDenRates[n]=std::lround(100*298.15/(273.15+stored-40));}
  do{saveAllPages();}while(isEepromWritePending());
  if(!unarmed)boostTimer.compare.store(0); // Declared native initial condition.
  setPinMapping(3);sensors(100,0,85,25,14,14.7);setup();sensors(100,0,85,25,14,14.7);
  if(configPage2.reqFuel!=96||configPage2.mapMax!=400||configPage6.boostFreq!=12||configPage6.boostEnabled!=(mode!="off")||configPage6.boostLimit!=pressure_cut_kpa/2||configPage4.engineProtectMaxRPM!=protection_rpm100||!configPage6.boostCutEnabled||!configPage2.perToothIgn)throw std::runtime_error("Setup changed coupling profile");
  for(unsigned n=0;n<8;++n){auto pin=n<4?pinNumbers.injectorPins[n]:pinNumbers.coilPins[n-4];output_pins[n]=pin;output_masks[n]=digitalPinToBitMask(pin);output_ports[n]=portOutputRegister(digitalPinToPort(pin));output_high[n]=(*output_ports[n]&output_masks[n])!=0;}
  record_edges=true;last_boost=pins[pinNumbers.pinBoost]!=0;monitor_boost=true;
  std::cout<<"ready "<<unsigned(pinNumbers.pinTrigger)<<"\npins";for(unsigned n=0;n<8;++n)std::cout<<' '<<unsigned(output_pins[n]);std::cout<<'\n'<<std::flush;
  std::string command;
  while(std::cin>>command){
   if(command=="quit")break;
   if(command=="advance"||command=="tooth"){
    std::uint64_t stamp;if(!(std::cin>>stamp)||stamp<speeduino_sim_micros()||stamp>60000000)throw std::runtime_error("Invalid bounded coupling time");advance_with_main_loop(stamp);
    if(command=="tooth"){auto cb=currentStatus.decoder.primary.callback;if(!cb)throw std::runtime_error("Missing actual decoder callback");pins[pinNumbers.pinTrigger]=HIGH;cb();pins[pinNumbers.pinTrigger]=LOW;}
   }else if(command=="sensors"){double m,t,c,i,b,a;if(!(std::cin>>m>>t>>c>>i>>b>>a))throw std::runtime_error("Missing sensors");sensors(m,t,c,i,b,a);}
   else if(command=="adcstatus"){std::cout<<"adcstatus";for(const auto pin:{pinNumbers.pinMAP,pinNumbers.pinTPS,pinNumbers.pinCLT,pinNumbers.pinIAT,pinNumbers.pinBat,pinNumbers.pinO2})std::cout<<' '<<adc[pin];std::cout<<'\n';}
   else if(command=="status")status();
   else if(command=="booststatus")boost_status();
   else if(command=="profile")std::cout<<"profile "<<unsigned(configPage2.reqFuel)<<' '<<unsigned(configPage4.HardRevLim)<<' '<<unsigned(configPage4.SoftRevLim)<<' '<<unsigned(configPage6.engineProtectType)<<' '<<unsigned(configPage9.hardRevMode)<<' '<<unsigned(configPage2.perToothIgn)<<'\n';
   else if(command=="boostprofile")std::cout<<"boostprofile "<<unsigned(configPage6.boostEnabled)<<' '<<unsigned(configPage4.boostType)<<' '<<unsigned(configPage6.boostFreq)<<' '<<unsigned(configPage6.boostLimit)<<' '<<unsigned(configPage2.boostMinDuty)<<' '<<unsigned(configPage2.boostMaxDuty)<<' '<<unsigned(configPage6.boostKP)<<' '<<unsigned(configPage6.boostKI)<<' '<<unsigned(configPage6.boostKD)<<' '<<unsigned(configPage10.boostIntv)<<' '<<unsigned(configPage10.boostSens)<<' '<<unsigned(unarmed)<<' '<<main_loop_period_us<<' '<<unsigned(configPage6.boostCutEnabled)<<' '<<MAP.toUser(configPage6.boostLimit)<<' '<<unsigned(configPage4.engineProtectMaxRPM)<<'\n';
   else if(command=="boostmaps"){
    std::cout<<"boostmaps";
    auto table=[](const auto&t){for(auto v:t.axisX)std::cout<<' '<<unsigned(v);for(auto v:t.axisY)std::cout<<' '<<unsigned(v);for(auto v:t.values)std::cout<<' '<<unsigned(v);};
    table(boostTable);table(boostTableLookupDuty);for(auto v:configPage6.airDenBins)std::cout<<' '<<unsigned(v);for(auto v:configPage6.airDenRates)std::cout<<' '<<unsigned(v);std::cout<<'\n';
   }
   else if(command=="halt"){stopFuelSchedulers();stopIgnitionSchedulers();closeAllInjectors();stopAllCoilsCharging();}
   else throw std::runtime_error("Unsupported coupling command");
   speeduino_sim_observe();std::cout<<"ok\n"<<std::flush;
  }
  if(!std::cin.eof()&&std::cin.fail())throw std::runtime_error("Malformed coupling command");return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
