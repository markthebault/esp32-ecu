#include "ecu/engine_binding.hpp"
#include <cstdio>
#include <cstring>
#include <cstdlib>
static unsigned checks=0;
static void check(bool x,const char*label){++checks;if(!x){std::fprintf(stderr,"failed: %s\n",label);std::exit(1);}}
int main(){
 ecu::config::Config c;const char*ids[]={"map","tps","clt","iat","wideband","postcat"};
 const char*units[]={"kPa","%","C","C","lambda","kPa"};double values[]={45,10,85,25,1,100};
 for(unsigned n=0;n<6;++n){auto&v=c.sensors[n];std::strcpy(v.id,ids[n]);std::strcpy(v.label,ids[n]);std::strcpy(v.unit,units[n]);v.confirmed=true;v.mode=ecu::config::Mode::Linear;v.y0=v.y1=values[n];}
 check(ecu::config::valid(c),"fixture config valid");
 ecu::web::Sample s;s.raw.fill(2048);s.raw[6]=1317;s.raw[7]=3723;s.adc_ok=true;s.synced=true;s.phase_synced=true;s.rpm=2000;
 // Existing completed observations are output provenance, never flex input.
 s.engine.flex_fuel.source=1;s.engine.flex_fuel.flags=0x1ffff;
 ecu::engine::Tune t;
 for(unsigned scenario=0;scenario<3;++scenario){
  t.flex_fuel.correction.enabled=scenario==1;t.flex_fuel.input_confirmed=true;
  t.secondary_fuel.mode=scenario==2?ecu::secondary::Mode::Conditional:ecu::secondary::Mode::Off;
  t.secondary_fuel.condition=ecu::secondary::Condition::Ethanol;t.secondary_fuel.threshold=40;
  const auto b=ecu::engine::bind_inputs(s,c,1000000,&t);
  check(b.input.sensors_valid,"physical values qualify in isolated fixture");
  check(b.input.flex_sample.observation.source==ecu::flex::Source::Unavailable,"no target producer or copied runtime record");
  check(!b.input.flex_sample.observation.valid,"no raw capture qualification");
  ecu::engine::Controller control;const auto o=control.step(t,b.input,1000000);
  if(scenario==0)check(!o.fuel_cut&&!o.spark_cut&&o.pulse_ms>0,"Off historical path available");
  else{check(o.fuel_cut&&o.spark_cut&&(o.faults&ecu::engine::BadSensor),"required missing target capture inhibits");check(!o.flex_fuel.control_ok,"input confirmation alone cannot qualify");}
 }
 std::printf("{\"passed\":true,\"checks\":%u,\"scope\":\"Native binding isolation only; no target capture producer or device execution\"}\n",checks);
}
