#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include <cassert>
#include <iostream>
#include <algorithm>
using namespace ecu::engine;
using namespace ecu::timing;
struct IO {unsigned mask=0;void all_low(){mask=0;}bool write(unsigned ch,bool high){if(high)mask|=1U<<ch;else mask&=~(1U<<ch);return true;}};
Command stopped(unsigned epoch=1){Command c;c.angle.strategy=Strategy::Sequential;c.sequence=c.tune_revision=c.sensor_revision=1;c.command_us=c.sampled_us=1;c.configuration_epoch=c.phase_epoch=epoch;return c;}
unsigned invalid_noise(bool mark){Executor x;IO io;auto c=stopped();c.angle.strategy=Strategy::BatchWasted;for(unsigned t=1;t<100001;t+=1000){c.sequence++;c.command_us=c.sampled_us=t;x.progress(t,io);x.command(c,t,io);if(mark)x.raw_capture(t);x.trip(t,Cause::Timebase,io);x.recover(t,true);}return unsigned(x.stats().recoveries);}
int main(){
 Executor stale;IO a;auto c=stopped();stale.progress(1,a);stale.command(c,1,a);stale.phase(true,100000,1,a);stale.stop(100,Cause::Configuration,a);
 c.sequence++;c.command_us=c.sampled_us=101;c.configuration_epoch=3;c.output.state=State::Running;c.output.rpm=1000;c.output.pulse_ms=3;c.output.dwell_ms=2.8;stale.command(c,101,a);
 assert(stale.stats().fault==Cause::None&&stale.next_alarm()==Executor::none&&!a.mask);assert(stale.current_command().output.faults&CamPhase);
 c.sequence++;c.command_us=c.sampled_us=102;c.phase_epoch=3;c.output.state=State::Stopped;stale.command(c,102,a);stale.phase(true,100000,102,a);
 c.sequence++;c.command_us=c.sampled_us=103;c.output.state=State::Running;stale.command(c,103,a);assert(stale.stats().fault==Cause::None);
 Executor unguarded;IO b;auto u=stopped();unguarded.command(u,1,b);unguarded.phase(true,100000,1,b);unguarded.stop(2,Cause::Configuration,b);unguarded.phase(true,100000,3,b);unguarded.phase(false,Executor::none,4,b);
 Executor guarded;IO g;guarded.command(u,1,g);guarded.phase(true,100000,1,g);guarded.stop(2,Cause::Configuration,g);unsigned worker_epoch=1,current_epoch=2;bool hold=true;if(worker_epoch==current_epoch&&!hold)guarded.phase(true,100000,3,g);
 assert(unguarded.stats().fault==Cause::CamPhase&&guarded.stats().fault==Cause::None);
 std::array<unsigned,3> rest{2,3,4};unsigned orders=0;
 do{Tune t;t.strategy=Strategy::Sequential;t.firing_order={1,rest[0],rest[1],rest[2]};Output o;o.state=State::Running;o.rpm=1000;o.advance_deg=10;o.pulse_ms=3;o.dwell_ms=2.8;AngleScheduler scheduler;std::array<unsigned,8> count{};std::array<std::uint64_t,8> rise{};
  for(unsigned n=70;n<1100;++n){const auto now=1+std::uint64_t(n)*1000;Edge e;while(scheduler.next_time()<=now){assert(scheduler.pop(e)&&!scheduler.event_forced_cut());if(e.high)rise[e.channel]=e.time_us;else{assert(rise[e.channel]&&e.time_us-rise[e.channel]==(e.channel<4?3000:2800));unsigned pos=0;for(;pos<4;++pos)if(t.firing_order[pos]==e.channel%4+1)break;const double goal=std::fmod(90+180*pos+(e.channel<4?540:-10)+720,720);double angle=std::fmod((e.time_us-1)*.006,720);assert(std::abs(angle-goal)<.007);if(e.time_us>240001&&e.time_us<=960001)++count[e.channel];}}
   if(n%60<58)assert(scheduler.tooth(t,o,now,n%120,60,now,now));}
  for(auto n:count){assert(n==6);}
  ++orders;
 }while(std::next_permutation(rest.begin(),rest.end()));
 std::cout<<"{\"stale_phase_evidence_waits_without_latch\":true,\"fresh_epoch_can_activate\":true,\"unguarded_old_worker_phase\":\""<<cause_name(unguarded.stats().fault)<<"\",\"guarded_old_worker_phase\":\""<<cause_name(guarded.stats().fault)<<"\",\"invalid_noise_recoveries_without_activity_mark\":"<<invalid_noise(false)<<",\"invalid_noise_recoveries_with_activity_mark\":"<<invalid_noise(true)<<",\"firing_orders_checked\":"<<orders<<",\"720_counts_widths_and_angles_passed\":true}\n";
}
