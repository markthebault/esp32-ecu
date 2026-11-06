#include "config_json.hpp"
#include "ecu/engine_binding.hpp"
#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

namespace {
unsigned checks=0;
void require(bool ok,const char*message){++checks;if(!ok)throw std::runtime_error(message);}
void close(double actual,double expected,double tolerance,const char*message){
 require(std::isfinite(actual)&&std::abs(actual-expected)<=tolerance,message);
}
unsigned adc(double voltage,double reference=3.3){
 return static_cast<unsigned>(std::clamp(std::floor(4096*voltage/reference),0.,4095.));
}
ecu::web::Sample sample(double supply,double reference=3.3){
 ecu::web::Sample s;s.adc_ok=true;s.synced=s.phase_synced=true;s.rpm=2000;
 s.raw={adc(.42*supply*.6,reference),adc(.18*supply*.6,reference),
        adc(3*.6,reference),adc(1.8*.6,reference),adc(2.5*.6,reference),
        adc(2*.6,reference),adc(14./13,reference),adc(supply*.6,reference)};
 return s;
}
}
int main(int argc,char**argv){
 try{
  if(argc!=2)return 2;
  std::ifstream file(argv[1]);const std::string text((std::istreambuf_iterator<char>(file)),{});
  auto*j=cJSON_Parse(text.c_str());ecu::config::Config defaults;
  require(j&&ecu::web::parse(j,defaults),"actual profile defaults parse");
  auto c=defaults;
  const char*units[]={"kPa","%","C","C","lambda"};
  const double low[]={10,0,-40,-40,.5},high[]={110,100,160,160,1.5};
  for(unsigned i=0;i<5;++i){auto&s=c.sensors[i];s.mode=ecu::config::Mode::Linear;
   std::snprintf(s.unit,sizeof(s.unit),"%s",units[i]);s.confirmed=true;s.y0=low[i];s.y1=high[i];
  }
  c.sensors[0].ratiometric=c.sensors[1].ratiometric=true;
  require(ecu::config::valid(c),"ratiometric engine fixture validates");
  auto map=c.sensors[0];
  for(double supply:{4.,4.75,4.8,4.9,5.,5.25,5.3}){
   auto r=ecu::config::convert(map,.42*supply,.42*supply*.6,supply);
   require(r.valid,"valid ratio sample");close(r.value,50,1e-10,"constant physical pressure across supply sweep");
   close(r.sensor_v,.42*supply,0,"raw connector voltage retained");
   close(r.transfer_v,2.1,1e-12,"nominal-supply equivalent voltage");
  }
  map.mode=ecu::config::Mode::Table;map.point_count=3;
  map.points[0]={.5,10};map.points[1]={2.1,50};map.points[2]={4.5,110};
  for(double supply:{4.75,4.8,5.,5.25})close(ecu::config::convert(map,.42*supply,1,supply).value,50,1e-10,"table ratio");
  map.mode=ecu::config::Mode::Linear;map.y0=110;map.y1=10;
  close(ecu::config::convert(map,.42*4.8,1,4.8).value,70,1e-10,"reverse slope ratio");
  map.y0=10;map.y1=110;map.reference_supply_v=4.8;
  close(ecu::config::convert(map,2.1*5/4.8,1,5).value,50,1e-10,"explicit non-five-volt calibration reference");
  map=c.sensors[0];map.fault_low_v=.45;
  require(!ecu::config::convert(map,.43,.258,4).valid,"normalization cannot mask raw low-voltage fault");
  map=c.sensors[0];map.fault_high_v=4.6;
  require(!ecu::config::convert(map,4.65,2.79,5.3).valid,"normalization cannot mask raw high-voltage fault");
  map=c.sensors[0];
  for(double supply:std::array<double,5>{0.,3.99,5.31,NAN,INFINITY})require(!ecu::config::convert(map,2.1,1.26,supply).valid,"invalid supply does not fall back to absolute voltage");
  double filtered=2.1;
  for(double supply:{5.,4.8,5.2,4.9}){
   filtered=ecu::config::readout_filter(map,.42*supply,supply,filtered,5,false);
   close(filtered,2.1,1e-12,"normalize before filtering prevents supply-step display error");
  }
  filtered=ecu::config::readout_filter(map,2.1,0,filtered,5,false);
  require(!std::isfinite(filtered),"bad supply invalidates display filter basis");
  filtered=ecu::config::readout_filter(map,2.016,4.8,filtered,5,false);
  close(filtered,2.1,1e-12,"display filter reseeds after supply recovery");
  require(!std::isfinite(ecu::config::readout_filter(map,2.1,5,filtered,5,false,false)),"ADC failure invalidates ratio filter");
  close(ecu::config::readout_filter(map,2.1,5,0,5,true),2.1,0,"configuration changes reseed filter");
  double unavailable=NAN;
  require(!ecu::config::convert(map,2.1,1.26,5,&unavailable).valid,"missing filtered basis cannot silently use raw input");
  auto absolute=map;absolute.ratiometric=false;
  close(ecu::config::convert(absolute,2.016,1.2096,4.8).value,47.9,1e-10,"legacy absolute curve retains its behavior");
  require(ecu::config::convert(absolute,2.1,1.26,NAN).valid,"absolute curves do not acquire a new supply dependency");
  for(auto mode:{ecu::config::Mode::Voltage,ecu::config::Mode::Ntc}){
   auto invalid=c;invalid.sensors[2].mode=mode;invalid.sensors[2].pullup_fitted=true;invalid.sensors[2].ratiometric=true;
   require(!ecu::config::valid(invalid),"voltage and NTC reject explicit ratio mode");
  }
  ecu::engine::Tune tune;tune.afterstart_pct=0;tune.dfco_enabled=false;tune.warmup_pct.fill(100);
  for(double supply:{4.76,4.8,4.9,5.,5.24}){
   auto bound=ecu::engine::bind_inputs(sample(supply),c,1000000,&tune);
   require(bound.input.sensors_valid,"actual raw ADC engine binding qualifies");
   close(bound.input.map_kpa,50,.08,"ADC pressure ratio accuracy");close(bound.input.tps_pct,10,.05,"ADC TPS ratio accuracy");
   ecu::engine::Controller controller;const auto o=controller.step(tune,bound.input,1000000);
   require(!o.faults&&!o.fuel_cut&&!o.spark_cut,"normal rail admits virtual control only");
  }
  // A common ADC-reference error cancels in the signal/supply ratio. It still
  // changes the measured absolute rail used by the unchanged engine guard.
  close(ecu::engine::bind_inputs(sample(5,3.4),c,1000000,&tune).input.map_kpa,50,.08,"common ADC reference error cancels in ratio");
  for(double supply:{4.7,5.29}){
   const auto bound=ecu::engine::bind_inputs(sample(supply),c,1000000,&tune);
   require(bound.input.sensors_valid,"conversion is distinct from engine rail qualification");
   ecu::engine::Controller controller;const auto o=controller.step(tune,bound.input,1000000);
   require((o.faults&ecu::engine::BadSensor)&&o.fuel_cut&&o.spark_cut,"unchanged rail guard cuts fuel and spark");
  }
  auto bound=ecu::engine::bind_inputs(sample(5),c,1000000,&tune);ecu::engine::Controller controller;
  require(controller.step(tune,bound.input,1020001).faults&ecu::engine::Stale,"ratio mode does not bypass freshness");
  auto old=cJSON_Duplicate(j,true);cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(old,"schema_version"),1);
  for(unsigned i=0;i<6;++i){auto*s=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(old,"sensors"),i);cJSON_DeleteItemFromObjectCaseSensitive(s,"ratiometric");cJSON_DeleteItemFromObjectCaseSensitive(s,"reference_supply_v");}
  require(ecu::web::parse(old,c),"legacy profile accepted into previously ratio-enabled config");
  for(const auto&s:c.sensors)require(!s.ratiometric&&s.reference_supply_v==5,"legacy parse explicitly clears ratio settings");
  require(ecu::web::upgrade_profile_document(old),"owned legacy document normalizes");
  require(ecu::web::parse(old,c),"normalized profile reparses");
  auto*first=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(old,"sensors"),0);
  cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(old,"schema_version"),1);
  require(!ecu::web::parse(old,c),"mixed legacy/new fields reject");
  cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(old,"schema_version"),2);
  cJSON_DeleteItemFromObjectCaseSensitive(first,"ratiometric");
  require(!ecu::web::parse(old,c),"profile2 requires an explicit ratio flag");
  cJSON_Delete(old);cJSON_Delete(j);
  std::cout<<checks<<" ratiometric parser/filter/binding/controller checks passed\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
