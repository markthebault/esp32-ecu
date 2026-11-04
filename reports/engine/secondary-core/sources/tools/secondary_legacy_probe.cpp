// Exact before/after probe for the disabled secondary-table path. It prints
// existing controller observations as binary F64 words, not rounded decimals.
#include "ecu/engine.hpp"
#include <cstring>
#include <iomanip>
#include <iostream>
using namespace ecu::engine;
static void value(double v){std::uint64_t bits;std::memcpy(&bits,&v,sizeof(bits));std::cout<<std::hex<<bits<<',';}
int main(){
 unsigned rows=0;
 for(unsigned strategy=0;strategy<3;++strategy)for(unsigned source=0;source<3;++source)
 for(unsigned afr=0;afr<3;++afr)for(unsigned ae=0;ae<4;++ae){
  Tune t;t.strategy=Strategy(strategy);t.cylinder_trims_enabled=strategy==1;
  t.load_model.fuel_source=t.load_model.spark_source=ecu::load::Source(source);
  t.load_model.ve_axis=t.load_model.spark_axis=t.load_model.lambda_axis=t.load_model.trim_axis=ecu::load::Axis(source);
  t.load_model.afr=ecu::load::Afr(afr);t.load_model.afr_delay_s=.05f;
  t.load_model.aux_role=source==2?ecu::load::AuxRole::Emap:ecu::load::AuxRole::PostcatMonitor;
  t.transient_enrichment.mode=ecu::transient::Mode(ae);t.ego_enabled=true;
  for(auto*m:{&t.ve,&t.spark,&t.lambda})for(unsigned n=0;n<16;++n)
   m->load[n]=source==0?10+n*6.f:source==1?n*100.f/15:10+n*30.f;
  for(unsigned c=0;c<4;++c){t.cylinder_spark_deg[c]=float(c)-1.5f;for(unsigned n=0;n<6;++n)t.cylinder_fuel[c].load[n]=source==0?10+n*20.f:source==1?n*20.f:10+n*90.f;}
  if(validate(t))return 2;
  Controller controller;
  for(unsigned n=0;n<72;++n){
   const std::uint64_t now=1000000+n*5000;
   Inputs in;in.rpm=n<4?0:n<12?220:n<50?1500+(n%8)*100:6200+(n%5)*150;
   in.map_kpa=35+(n%13)*3.25;in.tps_pct=n<40?8+(n%11)*2.5:.5;
   in.clt_c=n<20?35:85;in.iat_c=25;in.lambda=.85+(n%5)*.07;
   in.battery_v=8+(n%9);in.sensor_v=5;in.synced=in.phase_synced=true;
   in.sensors_valid=true;in.lambda_ready=n%7!=0;in.sampled_us=now;
   in.aux_pressure_kpa=125;in.aux_pressure_qualified=source==2;
   if(n==29)in.sampled_us=now-21000;
   if(n==31)in.sensors_valid=false;
   if(n==33)in.clt_c=116;
   if(n==35)in.map_kpa=111;
   if(n==37)in.synced=false;
   if(n==39)in.phase_synced=false;
   const auto o=controller.step(t,in,now);
   std::cout<<std::dec<<strategy<<','<<source<<','<<afr<<','<<ae<<','<<n<<','<<unsigned(o.state)<<','<<o.faults<<','<<o.fuel_cut<<','<<o.spark_cut<<','<<o.pump<<','<<o.fan<<',';
   for(double v:{o.rpm,o.ve_pct,o.target_lambda,o.advance_deg,o.pulse_ms,o.dwell_ms,o.deadtime_ms,o.air_mg,o.warmup,o.afterstart,o.accel,o.ego,o.duty_pct,o.idle_pct})value(v);
   for(unsigned c=0;c<4;++c){value(o.cylinder_pulse_ms[c]);value(o.cylinder_advance_deg[c]);value(o.cylinder_fuel_pct[c]);value(o.cylinder_duty_pct[c]);}
   std::cout<<std::dec<<o.cylinder_data<<','<<o.cylinder_trims_enabled<<','<<unsigned(o.cylinder_capacity_mask)<<','<<unsigned(o.cylinder_spark_clamp_mask)<<','<<unsigned(o.cylinder_retard_floor_mask)<<',';
   for(float v:o.load_model.values)value(v);
   std::cout<<std::dec<<o.load_model.flags<<','<<unsigned(o.load_model.reason)<<',';
   for(float v:o.transient_enrichment.values)value(v);
   std::cout<<std::dec<<unsigned(o.transient_enrichment.flags)<<','<<unsigned(o.transient_enrichment.reason)<<','<<unsigned(o.transient_enrichment.phase)<<','<<unsigned(o.idle.flags)<<','<<unsigned(o.idle.state)<<','<<unsigned(o.idle.reason)<<',';
   for(double v:{o.idle.duty_pct,o.idle.target_rpm,o.idle.feedforward_pct,o.idle.p_term,o.idle.i_term,o.idle.d_term})value(v);
   std::cout<<std::dec<<o.idle.pid_updates<<'\n';++rows;
  }
 }
 return rows==7776?0:3;
}
