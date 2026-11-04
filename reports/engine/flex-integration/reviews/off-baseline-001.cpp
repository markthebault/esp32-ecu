#include "ecu/engine.hpp"
#include <iostream>
#include <iomanip>
#include <cstring>
using namespace ecu::engine;
void number(double d){std::uint64_t u;std::memcpy(&u,&d,8);std::cout<<std::hex<<u<<',';}
void row(const Output&o){std::cout<<unsigned(o.state)<<','<<o.faults<<','<<o.fuel_cut<<o.spark_cut<<o.pump<<o.fan<<',';for(auto x:{o.rpm,o.ve_pct,o.target_lambda,o.advance_deg,o.pulse_ms,o.dwell_ms,o.deadtime_ms,o.air_mg,o.warmup,o.afterstart,o.accel,o.ego,o.duty_pct,o.idle_pct})number(x);for(auto x:o.cylinder_pulse_ms)number(x);for(auto x:o.cylinder_advance_deg)number(x);for(auto x:o.cylinder_fuel_pct)number(x);for(auto x:o.cylinder_duty_pct)number(x);std::cout<<o.cylinder_capacity_mask<<','<<o.cylinder_spark_clamp_mask<<','<<o.cylinder_retard_floor_mask<<','<<o.load_model.flags<<','<<unsigned(o.transient_enrichment.phase)<<','<<unsigned(o.transient_enrichment.reason)<<','<<o.transient_enrichment.flags<<',';for(auto x:o.transient_enrichment.values)number(x);for(const auto*p:{&o.secondary_fuel,&o.secondary_spark}){std::cout<<unsigned(p->reason)<<','<<p->valid<<p->active<<p->clamped<<',';for(auto member:ecu::secondary::value_members)number(p->*member);}std::cout<<'\n';}
int main(){
 for(unsigned strategy=0;strategy<3;++strategy)for(unsigned transient=0;transient<4;++transient)for(unsigned apply=0;apply<2;++apply)for(unsigned second=0;second<6;++second){
  Tune t;t.strategy=static_cast<Strategy>(strategy);t.dfco_delay_s=.1;t.transient_enrichment.mode=static_cast<ecu::transient::Mode>(transient);t.transient_enrichment.apply=static_cast<ecu::transient::Apply>(apply);
  t.cylinder_trims_enabled=strategy==1;t.cylinder_fuel[0].cells.fill(75);t.cylinder_fuel[1].cells.fill(125);t.cylinder_spark_deg={-10,-5,5,10};
  const auto mode=static_cast<ecu::secondary::Mode>(second==5?3:second);
  for(auto*p:{&t.secondary_tables.fuel,&t.secondary_tables.spark}){p->mode=mode;p->cells=ecu::secondary::expected_cells(mode);p->condition=second==5?ecu::secondary::Condition::Ethanol:ecu::secondary::Condition::Rpm;p->threshold=second==5?50:1500;p->debounce_ms=0;}
  t.secondary_ve.cells.fill(mode==ecu::secondary::Mode::Multiply?150:mode==ecu::secondary::Mode::Add?10:95);t.secondary_spark.cells.fill(mode==ecu::secondary::Mode::Multiply?150:mode==ecu::secondary::Mode::Add?5:25);
  if(validate(t)){std::cerr<<"invalid scenario "<<strategy<<transient<<apply<<second<<'\n';return 2;}Controller c;
  for(unsigned n=0;n<100;++n){const std::uint64_t now=1000000+n*5000;Inputs s;s.rpm=n<4?0:n<10?200:n<21?800:n<41?2000:n<61?2500:n<66?6400:n<70?6600:2000;s.synced=s.phase_synced=s.rpm>0;s.sensors_valid=s.lambda_ready=true;s.sampled_us=now;s.map_kpa=n%3?50:80;s.tps_pct=n>=41&&n<61?0:n%10*3+5;s.clt_c=n<21?65:85;s.iat_c=25;s.lambda=1.1;s.battery_v=14;s.sensor_v=5;s.ethanol_pct=n%2?60:40;s.ethanol_qualified=true;s.table_switches[0]={now,ecu::secondary::InputSource::Synthetic,n%2!=0,true};s.table_switches[1]={now,ecu::secondary::InputSource::Synthetic,n%3!=0,true};
   if(n==81){s.sensors_valid=false;}
   if(n==86){s.sampled_us-=20001;}
   if(n==87){++s.sampled_us;}
   if(n==89){s.clt_c=116;}
   if(n==90){s.battery_v=6;}
#ifdef REVIEW_NEW
   if(second==5)s.flex_sample=ecu::flex::synthetic_value(s.ethanol_pct,true,now,t.flex_fuel.capture,t.revision);
#endif
   row(c.step(t,s,now));
  }
 }
}
