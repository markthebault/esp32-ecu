// Native raw-ADC fixture linked to the attested production Speeduino loop.
// ADC voltage/reference relationships are authored outside this executable.
#define main numerical_benchmark_main
#include "speeduino_sim.cpp"
#undef main

int main(){
 try{
  char binary[PATH_MAX];auto length=readlink("/proc/self/exe",binary,sizeof(binary)-1);
  if(length<=0)throw std::runtime_error("Cannot locate owned executable");
  binary[length]='\0';const std::string path(binary);const auto parent=path.substr(0,path.find_last_of('/'));
  if(setenv("GCOV_PREFIX",(parent+"/gcov").c_str(),1))throw std::runtime_error("Cannot isolate coverage");
  prepare_hal();configure();
  configPage2.mapMin=10;configPage2.mapMax=110;
  configPage4.ADCFILTER_MAP=0;configPage2.mapSample=MAPSamplingInstantaneous;
  do{saveAllPages();}while(isEepromWritePending());
  setPinMapping(3);set_sensors(100,10,85,25,14,14.7);setup();set_sensors(100,10,85,25,14,14.7);
  if(configPage2.mapMin!=10||configPage2.mapMax!=110||configPage4.ADCFILTER_MAP!=0)
   throw std::runtime_error("Production setup changed the declared calibration");
  std::cout<<"{\"kind\":\"ready\",\"time_us\":"<<speeduino_sim_micros()<<",\"calibration\":\"ADC0..1023 to10..110kPa\",\"physical_execution\":false}\n"<<std::flush;
  std::string command;
  while(std::cin>>command){
   if(command=="adc"){
    std::uint64_t time;unsigned code;
    if(!(std::cin>>time>>code)||code>1023)throw std::runtime_error("Invalid ADC fixture");
    speeduino_sim_advance(time);adc[pinNumbers.pinMAP]=code;run_loop();
    std::cout<<"{\"kind\":\"sample\",\"time_us\":"<<speeduino_sim_micros()<<",\"raw_map_adc\":"<<code
      <<",\"map_kpa\":"<<currentStatus.MAP<<",\"rpm\":"<<currentStatus.RPM
      <<",\"loop_count\":"<<loop_count<<",\"physical_execution\":false}\n"<<std::flush;
   }else if(command=="quit")break;
   else throw std::runtime_error("Unsupported fixture command");
  }
  if(!std::cin.eof()&&std::cin.fail())throw std::runtime_error("Malformed fixture stream");
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
