// Geometry-only startup probe of the unchanged pinned production ECU. Reuse
// the existing native HAL/config writer; the production algorithms stay in
// their independently attested objects. This does not observe extra GPIOs or
// pretend that the legacy v0.4 fixture has sixteen distinct output pins.
#define main existing_four_cylinder_adapter_main
#include "speeduino_sim.cpp"
#undef main

int main(int argc,char**argv){
 try{
  if(argc!=3)throw std::runtime_error("count1..8 and sequential/wasted_cop/semi required");
  const std::string number=argv[1],mode=argv[2];
  if(number.size()!=1||number[0]<'1'||number[0]>'8')throw std::runtime_error("count outside1..8");
  const unsigned count=number[0]-'0';
  sequential_profile=mode=="sequential";semi_sequential_profile=mode=="semi";
  if(!sequential_profile&&!semi_sequential_profile&&mode!="wasted_cop")throw std::runtime_error("unknown mode");
  // Keep dependency instrumentation inside this fresh, owned executable's
  // directory. No upstream source or global installation is written.
  char binary[PATH_MAX];auto length=readlink("/proc/self/exe",binary,sizeof(binary)-1);
  if(length<=0)throw std::runtime_error("cannot locate native executable");
  binary[length]='\0';std::string path(binary);const auto parent=path.substr(0,path.find_last_of('/'));
  if(setenv("GCOV_PREFIX",(parent+"/gcov").c_str(),1)!=0)throw std::runtime_error("cannot isolate instrumentation");
  prepare_hal();configure();
  configPage2.nCylinders=count;configPage2.nInjectors=count;
  configPage2.engineType=EVEN_FIRE;configPage2.strokes=FOUR_STROKE;
  configPage2.divider=std::max(1U,count/2);
  configPage2.injLayout=sequential_profile?INJ_SEQUENTIAL:INJ_SEMISEQUENTIAL;
  configPage2.injTiming=sequential_profile||semi_sequential_profile;
  configPage4.sparkMode=sequential_profile?IGN_MODE_SEQUENTIAL:IGN_MODE_WASTEDCOP;
  const auto requested_spark=unsigned(configPage4.sparkMode),requested_layout=unsigned(configPage2.injLayout);
  // Persist through production storage before unmodified setup reloads it.
  do{saveAllPages();}while(isEepromWritePending());
  setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();
  if(currentStatus.RPM||record_edges)throw std::runtime_error("geometry fixture unexpectedly active");
  const std::array<int,8> fuel_angles{fuelSchedule1.channelDegrees,fuelSchedule2.channelDegrees,
   fuelSchedule3.channelDegrees,fuelSchedule4.channelDegrees,fuelSchedule5.channelDegrees,
   fuelSchedule6.channelDegrees,fuelSchedule7.channelDegrees,fuelSchedule8.channelDegrees};
  const std::array<int,8> spark_angles{ignitionSchedule1.channelDegrees,ignitionSchedule2.channelDegrees,
   ignitionSchedule3.channelDegrees,ignitionSchedule4.channelDegrees,ignitionSchedule5.channelDegrees,
   ignitionSchedule6.channelDegrees,ignitionSchedule7.channelDegrees,ignitionSchedule8.channelDegrees};
  std::cout<<"{\"requested_cylinders\":"<<count<<",\"cylinders\":"<<unsigned(configPage2.nCylinders)
   <<",\"injectors\":"<<unsigned(configPage2.nInjectors)<<",\"requested_spark_mode\":"<<requested_spark
   <<",\"spark_mode\":"<<unsigned(configPage4.sparkMode)<<",\"requested_injection_layout\":"<<requested_layout
   <<",\"configured_injection_layout\":"<<unsigned(configPage2.injLayout)<<",\"effective_injection_layout\":"<<unsigned(currentStatus.injLayout)
   <<",\"ignition_outputs\":"<<unsigned(currentStatus.maxIgnOutputs)<<",\"primary_injector_outputs\":"<<unsigned(currentStatus.injOutputs.primary)
   <<",\"n_squirts\":"<<unsigned(currentStatus.nSquirts)<<",\"ignition_span_deg\":"<<CRANK_ANGLE_MAX_IGN
   <<",\"injection_span_deg\":"<<CRANK_ANGLE_MAX_INJ<<",\"rpm\":"<<currentStatus.RPM;
  auto array=[](const char*name,const auto&values){std::cout<<",\""<<name<<"\":[";for(unsigned i=0;i<values.size();++i){if(i)std::cout<<',';std::cout<<values[i];}std::cout<<']';};
  array("fuel_schedule_degrees",fuel_angles);array("spark_schedule_degrees",spark_angles);
  std::cout<<",\"scope\":\"production_setup_geometry_only_no_GPIO_or_engine_evidence\"}\n";
  stopFuelSchedulers();stopIgnitionSchedulers();
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
