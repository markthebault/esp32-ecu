#include "ecu/engine_binding.hpp"
#include <cstring>
#include <iostream>
namespace eng=ecu::engine;
namespace sec=ecu::secondary;
static unsigned checks=0,failures=0;
static void check(bool v,const char*n){++checks;if(!v){++failures;std::cout<<"FAIL,"<<n<<'\n';}}
static eng::Tune alpha(){
 eng::Tune t;t.load_model.fuel_source=t.load_model.spark_source=ecu::load::Source::Tps;
 t.load_model.ve_axis=t.load_model.spark_axis=t.load_model.lambda_axis=t.load_model.trim_axis=ecu::load::Axis::TpsPercent;t.load_model.pressure=ecu::load::Pressure::None;
 for(auto*m:{&t.ve,&t.spark,&t.lambda})for(unsigned n=0;n<16;++n)m->load[n]=n*100.f/15;
 for(auto&m:t.cylinder_fuel)for(unsigned n=0;n<6;++n)m.load[n]=n*20;
 return t;
}
static ecu::config::Config calibration(){
 ecu::config::Config c;const char*ids[]={"map","tps","clt","iat","wideband","postcat"};const char*units[]={"kPa","%","C","C","lambda","kPa"};const double values[]={60,50,85,25,1,125};
 for(unsigned n=0;n<6;++n){auto&s=c.sensors[n];std::strcpy(s.id,ids[n]);std::strcpy(s.label,ids[n]);std::strcpy(s.unit,units[n]);s.mode=ecu::config::Mode::Linear;s.confirmed=true;s.v0=.5;s.v1=4.5;s.y0=s.y1=values[n];s.points[0]={.5,0};s.points[1]={4.5,100};}
 return c;
}
static ecu::web::Sample sample(){ecu::web::Sample s;s.adc_ok=s.synced=s.phase_synced=true;s.rpm=2000;s.raw.fill(1861);s.raw[6]=1337;s.raw[7]=3723;return s;}
int main(){
 for(unsigned kind=0;kind<2;++kind)for(unsigned mode=0;mode<5;++mode)for(unsigned source=0;source<3;++source)for(unsigned condition=0;condition<4;++condition){
  auto t=alpha();auto&r=kind?t.secondary_tables.spark:t.secondary_tables.fuel;auto&m=kind?t.secondary_spark:t.secondary_ve;r.mode=sec::Mode(mode);r.cells=sec::expected_cells(r.mode);r.source=ecu::load::Source(source);r.axis=ecu::load::Axis(source);r.condition=sec::Condition(condition);r.threshold=50;
  m.cells.fill(mode==1?100:mode==2?0:kind?15:85);for(unsigned n=0;n<16;++n)m.load[n]=source==0?10+n*6.f:source==1?n*100.f/15:10+n*30.f;
  if(source==2)t.load_model.aux_role=ecu::load::AuxRole::Emap;
  check(!eng::validate(t),"binding fixture is valid");
  auto c=calibration();auto s=sample();auto b=eng::bind_inputs(s,c,100000,&t);check(b.input.sensors_valid,"healthy pressure binding");
  const bool need_map=mode!=0&&(source!=1||(mode==3&&condition==1));
  c.sensors[0].confirmed=false;b=eng::bind_inputs(s,c,100000,&t);check(b.input.sensors_valid==!need_map,"unconfirmed MAP follows secondary dependency");
  c=calibration();std::strcpy(c.sensors[0].unit,"V");b=eng::bind_inputs(s,c,100000,&t);check(b.input.sensors_valid==!need_map,"MAP unit mismatch follows dependency");
  const bool need_emap=mode!=0&&source==2;
  c=calibration();c.sensors[5].confirmed=false;b=eng::bind_inputs(s,c,100000,&t);check(b.input.sensors_valid==!need_emap,"unconfirmed EMAP follows secondary dependency");
  c=calibration();c.sensors[5].mode=ecu::config::Mode::Voltage;b=eng::bind_inputs(s,c,100000,&t);check(b.input.sensors_valid==!need_emap,"raw voltage never pressure role");
  c=calibration();s.overflow=true;b=eng::bind_inputs(s,c,100000,&t);check(!b.input.sensors_valid,"capture overflow preserved");
  s=sample();s.adc_ok=false;b=eng::bind_inputs(s,c,100000,&t);check(!b.input.sensors_valid,"ADC failure preserved");
 }
 std::cout<<"TOTAL,"<<checks<<",FAILURES,"<<failures<<'\n';return failures?1:0;
}
