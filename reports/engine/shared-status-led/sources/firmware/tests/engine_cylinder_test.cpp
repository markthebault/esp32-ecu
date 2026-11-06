#include "ecu/engine.hpp"
#include "ecu/engine_scheduler.hpp"
#include "ecu/timing_executor.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::engine;
Inputs inputs(double rpm=1200,double map=45){Inputs in;in.rpm=rpm;in.map_kpa=map;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sampled_us=1000;in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;return in;}
Tune tune(){Tune t;t.strategy=Strategy::Sequential;t.cylinder_trims_enabled=true;t.afterstart_pct=0;return t;}
Output step(const Tune&t,Inputs in=inputs()){Controller c;return c.step(t,in,1000);}
bool close(double a,double b){return std::abs(a-b)<1e-9;}
void charged_tooth_prediction(){
 struct Case{double advance;std::uint64_t tooth_us;bool lower_max,retain;};
 // Three actual accelerating-tooth timestamps from the asymmetric plant.
 // The target444deg tooth arrives6us before its committed coil-low alarm.
 for(const auto c:{Case{6,1862190,false,true},Case{5.999999,1862190,false,true},
     Case{6.001,1862190,false,true},Case{6,1862171,false,true},
     Case{6,1862160,false,false},Case{6.19,1862134,false,false},
     Case{6,1862196,false,false},Case{6,1862190,true,false}}){
  Tune t;t.strategy=Strategy::Sequential;t.cylinder_trims_enabled=true;
  Output o;o.state=State::Running;o.rpm=60000000./(260.5*360);o.fuel_cut=true;o.dwell_ms=2.8;o.advance_deg=10;
  o.cylinder_data=o.cylinder_trims_enabled=true;o.cylinder_advance_deg={7,12,15,c.advance};AngleScheduler s;
  assert(s.tooth(t,o,1857523,71,60,1857523,1857523));
  assert(s.tooth(t,o,1859086,72,60,1859086,1859086));
  Edge e;assert(s.pop(e)&&e.channel==7&&e.high);const auto rise=e.time_us;
  assert(s.tooth(t,o,1860641,73,60,1860641,1860641));const auto end=s.next_time();
  assert(end-rise<=3500);
  if(c.lower_max){t.max_dwell_ms=2.78f;o.dwell_ms=2.7;}
  assert(s.tooth(t,o,c.tooth_us,74,60,c.tooth_us,c.tooth_us)==c.retain);
  if(c.retain){assert(s.next_time()==end);assert(s.pop(e)&&e.channel==7&&!e.high&&e.time_us==end);}
  else assert(s.failed()&&s.next_time()==UINT64_MAX);
 }
}
void aligned_acceleration(){
 for(auto strategy:{Strategy::BatchWasted,Strategy::Sequential})for(double advance:{0.,6.,12.,18.,24.,30.,36.}){
  Tune t;t.strategy=strategy;Output o;o.state=State::Running;o.pulse_ms=2;o.dwell_ms=2.8;o.advance_deg=advance;
  AngleScheduler s;std::array<std::uint64_t,8> rise{};std::array<bool,8> high{};std::array<unsigned,8> counts{};
  for(unsigned n=0;n<480;++n){
   const auto now=std::uint64_t(std::llround(1+1100.*n-.7*n*n));
   while(s.next_time()<=now){Edge e;assert(s.pop(e)&&!s.event_forced_cut());assert(high[e.channel]!=e.high);high[e.channel]=e.high;
    if(e.high)rise[e.channel]=e.time_us;else{assert(e.time_us-rise[e.channel]<=(e.channel>=4?3500:15000));++counts[e.channel];}}
   o.rpm=60000000/(60*(1100-1.4*n));
   if(n%60<58)assert(s.tooth(t,o,now,n%(strategy==Strategy::Sequential?120:60),60,now,now));
  }
  for(auto count:counts)assert(count>=3);
 }
}
int main(){
 charged_tooth_prediction();aligned_acceleration();
 auto t=tune();assert(!validate(t));
 for(double rpm:{127.2,863.5,1777.3,5123.1})for(double load:{17.3,42.4,67.9,101.1})assert(lookup(t.cylinder_fuel[0],rpm,load)==100);
 const auto neutral=step(t);assert(!neutral.faults);
 for(unsigned i=0;i<4;++i)assert(neutral.cylinder_pulse_ms[i]==neutral.pulse_ms&&neutral.cylinder_advance_deg[i]==neutral.advance_deg);
 t.cylinder_fuel[1].cells.fill(120);t.cylinder_spark_deg[1]=-3;
 for(float deadtime:{.5f,1.5f}){
  t.deadtime_ms.fill(deadtime);const auto out=step(t);assert(!out.faults);
  assert(close(out.pulse_for(1)-deadtime,(out.pulse_ms-deadtime)*1.2));assert(close(out.advance_for(1),out.advance_deg-3));
  for(unsigned i:{0,2,3})assert(out.pulse_for(i)==out.pulse_ms&&out.advance_for(i)==out.advance_deg);
 }
 t.cylinder_trims_enabled=false;const auto disabled=step(t);assert(!disabled.faults&&disabled.pulse_for(1)==disabled.pulse_ms&&disabled.cylinder_fuel_pct[1]==100);
 auto forged=disabled;forged.cylinder_pulse_ms[1]=100;forged.cylinder_advance_deg[1]=100;assert(forged.pulse_for(1)==forged.pulse_ms&&forged.advance_for(1)==forged.advance_deg);
 t=tune();t.max_injection_ms=11;t.cylinder_fuel[2].cells.fill(150);const auto overflow=step(t,inputs(1200,100));
 assert(overflow.faults&Capacity);assert(overflow.cylinder_capacity_mask==4);assert(overflow.fuel_cut&&overflow.spark_cut);
 for(auto pw:overflow.cylinder_pulse_ms)assert(pw==0);
 t=tune();for(auto&m:t.cylinder_fuel)m.cells.fill(50);auto cold=inputs(200,100);cold.clt_c=0;
 const auto reduced=step(t,cold);assert(!reduced.faults&&reduced.pulse_ms>15);
 for(unsigned i=0;i<4;++i)assert(reduced.pulse_for(i)<15&&close(reduced.pulse_for(i)-reduced.deadtime_ms,(reduced.pulse_ms-reduced.deadtime_ms)*.5));
 AngleScheduler schedule;assert(schedule.tooth(t,reduced,1000,0,60,1000,1000));
 t=tune();t.spark.cells.fill(40);t.cylinder_spark_deg[0]=10;
 const auto limited=step(t,inputs(6450));assert(!limited.faults);assert(close(limited.advance_for(0),limited.advance_deg));assert(limited.cylinder_spark_clamp_mask&1);
 t.crank_advance_deg=15;const auto crank=step(t,inputs(200));assert(crank.advance_for(0)==15&&(crank.cylinder_spark_clamp_mask&1));
 t=tune();t.spark.cells.fill(-5);t.cylinder_spark_deg[0]=10;const auto floor=step(t,inputs(6450));
 assert(floor.advance_for(0)<0);assert(floor.cylinder_retard_floor_mask&2);
 t=tune();t.max_duty=.2f;auto command=step(t,inputs(1000));assert(!command.faults);
 ecu::timing::Executor::Candidate candidate;candidate.command.angle=angle_config(t);candidate.command.output=command;candidate.command.command_us=candidate.command.sampled_us=candidate.capture_us=1000;
 candidate.calculate(0,8000);assert(!candidate.valid); // Fresh tooth RPM, not old duty[].
 t.strategy=Strategy::BatchWasted;assert(validate(t));t.cylinder_trims_enabled=false;assert(!validate(t));
 t.max_duty=.85f;const auto edge_limit=step(t);assert(!edge_limit.faults&&demand_valid(angle_config(t),edge_limit,1200));
 t.cylinder_spark_deg[0]=11;assert(validate(t));t.cylinder_spark_deg[0]=0;t.cylinder_fuel[0].cells[0]=49;assert(validate(t));
 std::cout<<"Cylinder maps, dose/deadtime, mapping, global capacity, negative trims, clamps and fresh-RPM duty passed\n";
}
