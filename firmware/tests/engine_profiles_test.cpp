#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include "ecu/tuning_layout.hpp"
#include <cassert>
#include <iostream>
#include <string>
#include <type_traits>

using namespace ecu::engine;
bool emit_cases=false;
static_assert(std::is_same<Tune,ExpandedTune>::value);
static_assert(!std::is_same<LegacyTune,ExpandedTune>::value);
static_assert(std::is_same<Output,ExpandedOutput>::value);
static_assert(!std::is_same<LegacyOutput,ExpandedOutput>::value);
static_assert(std::is_same<AngleConfig,ExpandedAngleConfig>::value);
static_assert(!std::is_same<LegacyAngleConfig,ExpandedAngleConfig>::value);
static_assert(std::is_same<AngleScheduler,ExpandedAngleScheduler>::value);
static_assert(!std::is_same<LegacyAngleScheduler,ExpandedAngleScheduler>::value);

ExpandedTune profile(unsigned count,Strategy strategy,bool reversed=false){
 ExpandedTune t;t.cylinders=count;t.strategy=strategy;t.firing_order.fill(0);
 for(unsigned i=0;i<count;++i)t.firing_order[i]=reversed&&i?count-i+1:i+1;
 t.displacement_cc=500*count;t.rpm_limit=8000;t.afterstart_pct=0;t.warmup_pct.fill(100);
 t.deadtime_ms.fill(.9f);t.dwell_ms.fill(1);t.spark.cells.fill(10);
 t.cylinder_trims_enabled=strategy==Strategy::Sequential;
 for(unsigned c=0;c<count;++c){
  t.cylinder_spark_deg[c]=float(c)-3.5f;
  t.cylinder_fuel[c].cells.fill(90+2*c);
 }
 return t;
}
ExpandedOutput demand(const ExpandedTune&t,unsigned rpm){
 Inputs in;in.rpm=rpm;in.map_kpa=40;in.tps_pct=10;in.clt_c=85;in.iat_c=25;
 in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sampled_us=1000000;
 in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;
 Controller controller;auto out=controller.step(t,in,in.sampled_us);
 if(out.faults)std::cerr<<"Unexpected motored demand fault: cylinders="<<t.cylinders<<" strategy="<<unsigned(t.strategy)<<" rpm="<<rpm<<" faults="<<out.faults<<'\n';
 assert(!out.faults&&out.cylinder_count==t.cylinders&&out.cylinder_data);
 return out;
}

// An externally motored, constant shaft is an analytic timing fixture. It is
// deliberately independent of the generalized controller's phase helper and
// is not an engine/combustion plant or a physical timing test.
void motored(unsigned count,Strategy strategy,unsigned rpm,unsigned teeth,double closing,bool reversed){
 auto t=profile(count,strategy,reversed);t.injection_end_deg=closing;
 assert(!validate(t));auto out=demand(t,rpm);ExpandedAngleScheduler scheduler;
 const double revolution=60000000.0/rpm,span=strategy==Strategy::Sequential?720:360;
 const auto epoch=std::uint64_t(1000000);
 const auto begin=epoch+std::uint64_t(std::llround(4.123*revolution));
 const auto end=epoch+std::uint64_t(std::llround(14.123*revolution));
 std::array<bool,18> high{};std::array<std::uint64_t,18> rise{};
 std::array<unsigned,18> falls{};double maximum_spark_error=0,maximum_injector_error=0,maximum_injector_bound=0;
 for(unsigned tooth=0;tooth<teeth*18;++tooth){
  const auto now=epoch+std::uint64_t(std::llround(tooth*revolution/teeth));
  while(scheduler.next_time()<=now){
   Edge edge;assert(scheduler.pop(edge)&&!scheduler.event_forced_cut());
   const auto kind=channels::kind(edge.channel);const auto cylinder=channels::cylinder(edge.channel);
   assert((kind==channels::Kind::Injector||kind==channels::Kind::Coil)&&cylinder<count);
   assert(high[edge.channel]!=edge.high);high[edge.channel]=edge.high;
   if(edge.high){rise[edge.channel]=edge.time_us;}
   else{
    const auto width=edge.time_us-rise[edge.channel];
    if(kind==channels::Kind::Injector)assert(width==std::uint64_t(std::llround(out.pulse_for(cylinder)*1000)));
    else assert(width>0&&width<=3500&&std::abs(double(width)-1000)<25);
   }
   if(edge.time_us<=begin||edge.time_us>end)continue;
   const bool coil=kind==channels::Kind::Coil;
   if(edge.high!=(strategy==Strategy::BatchWasted&&!coil))continue;
   ++falls[edge.channel]; // Count batch injector starts; other channels' ends.
   unsigned rank=0;while(t.firing_order[rank]!=cylinder+1)++rank;
   const double goal=90+(coil?720.0*rank/count-out.advance_for(cylinder):
     strategy==Strategy::BatchWasted?180:720.0*rank/count+closing);
   const double actual=double(edge.time_us-epoch)/revolution*360;
   const double error=std::abs(std::remainder(actual-goal,span));
   if(coil)maximum_spark_error=std::max(maximum_spark_error,error);
   else maximum_injector_error=std::max(maximum_injector_error,error);
   // Captures and compare times are rounded to integer microseconds. Once an
   // injector opens its low edge is deliberately fixed, so a one-us interval
   // quantization error projects across the pulse and up to the missing-tooth
   // gap. Derive that bound from the independent shaft instead of applying a
   // short-pulse tolerance to every pulse length. Spark is refreshed by teeth.
   const double interval=revolution/teeth;
   const double horizon=out.pulse_for(cylinder)*1000+3*interval;
   const double bound=coil||strategy==Strategy::BatchWasted?.55:
     std::max(.55,(1+horizon/(interval-1))*360/revolution);
   if(!coil)maximum_injector_bound=std::max(maximum_injector_bound,bound);
   if(error>bound)std::cerr<<"Motored phase failure: cylinders="<<count<<" strategy="<<unsigned(strategy)<<" rpm="<<rpm<<" teeth="<<teeth<<" closing="<<closing<<" reversed="<<reversed<<" channel="<<edge.channel<<" error="<<error<<" bound="<<bound<<'\n';
   assert(error<=bound);
  }
  if(tooth%teeth<teeth-2){
   assert(scheduler.tooth(t,out,now,tooth%(teeth*(strategy==Strategy::Sequential?2:1)),teeth,now,now));
  }
 }
 assert(!scheduler.failed()&&maximum_spark_error<.55&&std::isfinite(maximum_injector_error));
 const auto expected=strategy==Strategy::Sequential?5U:10U;
 for(unsigned cylinder=0;cylinder<count;++cylinder){
  assert(falls[channels::injector(cylinder)]==expected);
  assert(falls[channels::coil(cylinder)]==expected);
 }
 for(unsigned c=count;c<8;++c)assert(!falls[channels::injector(c)]&&!falls[channels::coil(c)]);
 scheduler.cut();assert(scheduler.next_time()==UINT64_MAX);
 if(emit_cases)std::cout<<"{\"kind\":\"motored_case\",\"cylinders\":"<<count<<",\"strategy_code\":"<<unsigned(strategy)
  <<",\"rpm\":"<<rpm<<",\"wheel_slots\":"<<teeth<<",\"closing_deg\":"<<closing<<",\"reversed_order\":"<<(reversed?"true":"false")
  <<",\"logical_outputs\":"<<2*count<<",\"counted_edges_per_output\":"<<expected<<",\"max_spark_error_deg\":"<<maximum_spark_error
  <<",\"max_injector_error_deg\":"<<maximum_injector_error<<",\"injector_bound_deg\":"<<maximum_injector_bound<<",\"passed\":true}\n";
}

void bounds_and_faults(){
 for(unsigned count:{0U,9U}){
  ExpandedTune t;t.cylinders=count;assert(validate(t));
  Controller c;Inputs in;const auto out=c.step(t,in,1);assert(out.faults==BadTune);
 }
 for(unsigned count=1;count<=8;++count){
  auto t=profile(count,Strategy::Sequential);assert(!validate(t));
  auto bad=t;bad.firing_order[0]=2;assert(validate(bad));
  if(count>1){bad=t;bad.firing_order[1]=1;assert(validate(bad));}
  if(count<8){bad=t;bad.firing_order[count]=1;assert(validate(bad));}
  auto out=demand(t,1000);ExpandedAngleScheduler scheduler;
  assert(scheduler.tooth(t,out,1000000,0,60,1000000,1000000));
  scheduler.refresh_control(1000000,1000000);
  bool expired=false;Edge edge;
  while(scheduler.next_time()!=UINT64_MAX){
   assert(scheduler.pop(edge));if(scheduler.event_forced_cut()){assert(edge.time_us==1020000);expired=true;}
  }
  assert(expired);
 }
 // Cylinder8 must be judged exactly like the first seven. One excessive trim
 // globally inhibits all logical channels without losing its identifying bit.
 auto t=profile(8,Strategy::Sequential);t.max_injection_ms=8;
 for(auto&map:t.cylinder_fuel){map.cells.fill(50);}
 t.cylinder_fuel[7].cells.fill(150);
 Inputs in;in.rpm=1000;in.map_kpa=100;in.tps_pct=10;in.clt_c=85;in.iat_c=25;
 in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sampled_us=1;
 in.synced=in.phase_synced=in.sensors_valid=true;
 Controller c;auto out=c.step(t,in,1);assert(out.faults&Capacity);assert(out.cylinder_capacity_mask==128);
 assert(out.fuel_cut&&out.spark_cut);for(auto value:out.cylinder_pulse_ms)assert(value==0);
 t=profile(8,Strategy::Sequential);in.rpm=8000;Controller overrev;out=overrev.step(t,in,1);
 assert(out.faults&OverRev);assert(out.fuel_cut&&out.spark_cut);
}
struct IO {unsigned writes=0;void all_low(){}bool write(unsigned,bool){++writes;return true;}};
void public_boundary_guards(){
 for(unsigned count=1;count<=8;++count){
  auto t=profile(count,Strategy::Sequential);ecu::tuning::Page page;
  assert(ecu::tuning::representable(t));ecu::tuning::encode_page(t,1,page);Tune decoded;
  assert(ecu::tuning::decode_page(page,1,decoded)&&decoded.cylinders==count&&decoded.firing_order==t.firing_order);
  for(unsigned policy:{4U,8U}){
   ecu::timing::Executor executor(policy);IO io;ecu::timing::Command cmd;
   cmd.angle=angle_config(t);cmd.output=demand(t,1000);cmd.sequence=1;
   cmd.command_us=cmd.sampled_us=1000000;executor.progress(1000000,io);executor.command(cmd,1000000,io);
   assert((executor.stats().fault==ecu::timing::Cause::Plan)==(count>policy));assert(io.writes==0);
  }
 }
 // The fixed-capacity aliases are preserved for explicit legacy consumers.
 LegacyTune old;old.cylinders=8;assert(validate(old));
}
void configuration_fence(){
 for(unsigned change=0;change<5;++change){
  auto t=profile(8,Strategy::Sequential);auto out=demand(t,1000);ExpandedAngleScheduler scheduler;
  assert(scheduler.tooth(t,out,1000000,0,60,1000000,1000000));
  assert(scheduler.next_time()!=UINT64_MAX);
  if(change==0){t=profile(1,Strategy::Sequential);out=demand(t,1000);}
  if(change==1){t.strategy=Strategy::SemiSequential;t.cylinder_trims_enabled=false;out=demand(t,1000);}
  if(change==2)std::swap(t.firing_order[1],t.firing_order[2]);
  if(change==3)t.injection_end_deg=100;
  assert(!scheduler.tooth(t,out,1001000,1,change==4?36:60,1001000,1001000));
  assert(scheduler.failed()&&scheduler.next_time()==UINT64_MAX);
  scheduler.reset();out=demand(t,1000);
  assert(scheduler.tooth(t,out,1002000,0,60,1002000,1002000));
 }
}
void conserved_cycle_dose(){
 double reference=0;
 for(unsigned count=1;count<=8;++count)for(auto strategy:{Strategy::BatchWasted,Strategy::SemiSequential,Strategy::Sequential}){
  auto t=profile(count,strategy);t.displacement_cc=1000;t.cylinder_trims_enabled=false;
  const auto out=demand(t,1000);const auto openings=strategy==Strategy::Sequential?1:2;
  const double total=count*openings*(out.pulse_ms-out.deadtime_ms);
  if(!reference)reference=total;
  assert(std::abs(total-reference)<1e-5);
 }
}
int main(int argc,char**argv){
 if(argc>2||(argc==2&&std::string(argv[1])!="--jsonl"))return 2;
 emit_cases=argc==2;
 unsigned cases=0;
 for(unsigned count=1;count<=8;++count)for(auto strategy:{Strategy::BatchWasted,Strategy::SemiSequential,Strategy::Sequential})
  for(unsigned rpm:{500U,2000U,7500U})for(unsigned teeth:{36U,60U,120U})
   for(double closing:{0.,540.,719.})for(bool reversed:{false,true}){
    motored(count,strategy,rpm,teeth,closing,reversed);++cases;
   }
 bounds_and_faults();public_boundary_guards();configuration_fence();conserved_cycle_dose();
 if(emit_cases)std::cout<<"{\"kind\":\"summary\",\"motored_cases\":"<<cases<<",\"passed\":true,\"physical_operation_verified\":false}\n";
 else std::cout<<cases<<" expanded1..8 motored timing cases, dose conservation, capacity, deadlines and boundary guards passed\n";
}
