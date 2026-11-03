#pragma once
#include "ecu/engine.hpp"
#include "ecu/web_config.hpp"
namespace ecu::engine {
struct BoundInputs {Inputs input;const char* reason="physical inputs converted; proposals only";};
inline bool named_unit(const char*s,const char*a,const char*b=""){return !std::strcmp(s,a)||(*b&&!std::strcmp(s,b));}
inline BoundInputs bind_inputs(const web::Sample&s,const config::Config&c,std::uint64_t now){
 BoundInputs bound;auto&in=bound.input;const double supply=s.raw[7]*c.adc_reference_v/4095/.6;
 in.rpm=s.rpm;in.synced=s.synced;in.sampled_us=now;in.battery_v=s.raw[6]*c.adc_reference_v/4095*13;in.sensor_v=supply;in.sensors_valid=s.adc_ok&&!s.overflow;
 double values[6]{};bool valid[6]{};
 for(unsigned i=0;i<6;++i){const double av=s.raw[i]*c.adc_reference_v/4095;auto r=config::convert(c.sensors[i],av/.6,av,supply);values[i]=r.value;valid[i]=r.valid&&c.sensors[i].confirmed;}
 if(!named_unit(c.sensors[0].unit,"kPa")||!named_unit(c.sensors[1].unit,"%")||!named_unit(c.sensors[2].unit,"C","°C")||!named_unit(c.sensors[3].unit,"C","°C")){in.sensors_valid=false;bound.reason="Engine inputs require confirmed kPa, %, C/°C conversions";}
 for(unsigned i=0;i<4;++i){
  if(!valid[i]){in.sensors_valid=false;bound.reason="MAP/TPS/CLT/IAT conversions must be valid and independently confirmed";}
  if(c.sensors[i].mode==config::Mode::Voltage){in.sensors_valid=false;bound.reason="Raw-voltage readings cannot be relabelled as engine physical quantities";}
 }
 in.map_kpa=values[0];in.tps_pct=values[1];in.clt_c=values[2];in.iat_c=values[3];in.lambda=values[4];in.lambda_ready=valid[4]&&c.sensors[4].mode!=config::Mode::Voltage&&named_unit(c.sensors[4].unit,"lambda","λ");return bound;
}
}
