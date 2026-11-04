#include "ecu/engine.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::engine;
Tune neutral(Strategy strategy=Strategy::BatchWasted){
 Tune t;t.strategy=strategy;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);t.crank_pct.fill(100);
 t.transient_enrichment.mode=ecu::transient::Mode::TpsRate;t.transient_enrichment.tps_min_change_pct=0;return t;
}
Inputs input(std::uint64_t now,double tps=10){Inputs i;i.rpm=1000;i.map_kpa=50;i.tps_pct=tps;i.clt_c=85;i.iat_c=25;i.battery_v=14;i.sensor_v=5;i.lambda=1.1;i.sampled_us=now;i.synced=i.phase_synced=i.sensors_valid=i.lambda_ready=true;return i;}
Output rising(Controller&c,const Tune&t){Output o;for(unsigned n=0;n<=4;++n)o=c.step(t,input(n*5000,10+n*.5),n*5000);return o;}
void dose_accounting(){
 for(auto strategy:{Strategy::BatchWasted,Strategy::Sequential,Strategy::SemiSequential})for(auto apply:{ecu::transient::Apply::Multiply,ecu::transient::Apply::AddReference}){
  auto t=neutral(strategy);t.transient_enrichment.apply=apply;Controller active;auto a=rising(active,t);
  auto off=t;off.transient_enrichment.mode=ecu::transient::Mode::Off;Controller baseline;auto b=rising(baseline,off);
  assert(!a.faults&&!b.faults);
  const double reference=100000*.0005/(287.05*298.15)*1e6/t.stoich_afr,openings=strategy==Strategy::Sequential?1:2,flow=t.injector_cc_min*t.fuel_density_g_cc/60;
  const double expected=apply==ecu::transient::Apply::Multiply?(b.pulse_ms-b.deadtime_ms)*1.1+b.deadtime_ms:b.pulse_ms+reference*.1/openings/flow;
  assert(std::abs(a.pulse_ms-expected)<1e-6);
  assert(std::abs(a.accel-(a.pulse_ms-a.deadtime_ms)/(b.pulse_ms-b.deadtime_ms))<1e-6);
  if(strategy==Strategy::Sequential){
   t.cylinder_trims_enabled=true;t.cylinder_fuel[0].cells.fill(125);Controller trimmed;auto v=rising(trimmed,t);
   assert(!v.faults&&std::abs(v.cylinder_pulse_ms[0]-(a.pulse_ms-a.deadtime_ms)*1.25-a.deadtime_ms)<1e-6);
  }
 }
}
void decel_and_feedback(){
 auto t=neutral();t.ego_enabled=true;t.transient_enrichment.apply=ecu::transient::Apply::AddReference;t.transient_enrichment.decel_fuel_pct=0;Controller c;auto o=rising(c,t);assert(o.ego==1&&o.accel>1);
 for(unsigned n=1;n<=4;++n)o=c.step(t,input(20000+n*5000,12-n*.5),20000+n*5000);
 assert(!o.faults&&o.fuel_cut&&!o.spark_cut&&o.pulse_ms==0&&o.dwell_ms>0);
 for(auto p:o.cylinder_pulse_ms)assert(p==0);
 for(unsigned n=9;n<=50;++n)o=c.step(t,input(n*5000,10),n*5000);
 assert(!o.transient_enrichment.active()&&!o.fuel_cut&&o.ego>1);
}
void fault_capacity_and_restart(){
 auto t=neutral();Controller c;auto o=rising(c,t);assert(o.accel>1);
 auto bad=input(25000,50);bad.sensors_valid=false;o=c.step(t,bad,25000);assert(o.faults&BadSensor);
 o=c.step(t,input(30000,80),30000);assert(!o.faults&&o.accel==1&&!o.transient_enrichment.active());
 // A valid but reversed acquisition stamp cannot differentiate across history.
 bad=input(35000,10);bad.sampled_us=29000;o=c.step(t,bad,35000);assert(!o.faults&&o.accel==1);
 auto small=neutral();small.max_injection_ms=8;small.transient_enrichment.max_enrichment_pct=650;small.transient_enrichment.tps_added_pct.fill(255);Controller limited;auto v=rising(limited,small);
 assert(v.faults&Capacity);assert(v.fuel_cut&&v.spark_cut&&v.pulse_ms==0&&v.cylinder_capacity_mask==15);
 assert(v.transient_enrichment.values[ecu::transient::CorrectionPct]>100&&!v.transient_enrichment.active());
 auto stopped=input(40000,0);stopped.rpm=0;stopped.synced=false;o=c.step(t,stopped,40000);assert(o.state==State::Stopped);
 o=c.step(t,input(45000,80),45000);assert(!o.faults&&o.accel==1);
}
int main(){dose_accounting();decel_and_feedback();fault_capacity_and_restart();std::cout<<"Transient full-cycle multiplier/adder, openings/deadtime/trims, decel0, EGO, fault/restart and whole-command capacity passed\n";}
