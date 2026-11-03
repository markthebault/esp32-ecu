#include "ecu/timing_executor.hpp"
#include "ecu/capture_clock.hpp"
#include <cassert>
#include <iostream>
#include <vector>

using namespace ecu::timing;
struct IO {
 unsigned mask=0;bool permit=true;unsigned writes=0,cuts=0;
 bool write(unsigned ch,bool high){++writes;if(!permit&&high)return false;if(high)mask|=1U<<ch;else mask&=~(1U<<ch);return true;}
 void all_low(){mask=0;++cuts;}
};
Command running(std::uint64_t now=1){
 Command c;c.sequence=1;c.command_us=c.sampled_us=now;c.tune_revision=c.sensor_revision=1;
 c.output.state=ecu::engine::State::Running;c.output.rpm=1000;c.output.advance_deg=10;
 c.output.pulse_ms=3;c.output.dwell_ms=2.8;return c;
}
void clock_tests(){
 CaptureClock clock;assert(!clock.ready());assert(!clock.sync(80000001,10,12));
 assert(!clock.sync(80000000,10,21));assert(clock.sync(80000000,1000,1002));
 const auto epoch=clock.epoch_us();assert(epoch==1001);
 for(auto time:{std::uint64_t(2000),std::uint64_t(53688000),std::uint64_t(107375000),std::uint64_t(4000000000)}){
  const auto tick=static_cast<std::uint32_t>((time-epoch)*80);
  auto r=clock.map(tick,time+9);assert(r.error==CaptureClock::Error::None&&r.time_us==time&&r.age_us==9);
  auto later=clock.map(tick+80,time+11),earlier=clock.map(tick,time+12);
  assert(later.time_us==time+1&&earlier.time_us==time); // callback order is irrelevant
  assert(clock.map(tick,time+5001).error==CaptureClock::Error::TooOld);
 }
 assert(clock.map(80000,200).error==CaptureClock::Error::BeforeEpoch);
 assert(clock.map(80000,epoch+500).error==CaptureClock::Error::Future);
}
void transactional_tests(){
 Executor core;IO io;auto cmd=running();core.progress(1,io);core.command(cmd,1,io);
 Executor::Candidate candidate;core.prepare(candidate,1000,20000);candidate.calculate(0,1000);
 assert(core.commit(candidate,1001,io)==Executor::Commit::Accepted);
 core.prepare(candidate,2000,20000);candidate.calculate(1,1000);
 core.trip(2000,Cause::Gate,io);
 assert(core.commit(candidate,2001,io)==Executor::Commit::Retry);assert(!io.mask&&core.stats().fault==Cause::Gate);
 Executor other;IO other_io;other.progress(1,other_io);other.command(cmd,1,other_io);
 other.prepare(candidate,1000,20000);candidate.calculate(0,1000);
 ++cmd.sequence;cmd.command_us=cmd.sampled_us=1000;++cmd.tune_revision;other.command(cmd,1000,other_io);
 assert(other.commit(candidate,1000,other_io)==Executor::Commit::Retry);
 other.prepare(candidate,1000,20000);candidate.calculate(0,1000);
 assert(other.commit(candidate,2500,other_io)==Executor::Commit::Fault);assert(other.stats().fault==Cause::CaptureAge);
}
void deadline_tests(){
 Executor core;IO io;auto cmd=running();core.progress(1,io);core.command(cmd,1,io);
 // Supervision is armed even when there are no pending scheduler edges.
 assert(core.next_alarm()==5001);core.dispatch(5001,io);
 assert(core.stats().fault==Cause::ProducerTimeout&&!io.mask);
 Executor stale;IO stale_io;stale.progress(1,stale_io);stale.command(cmd,1,stale_io);
 for(unsigned t=1000;t<=20000;t+=1000){stale.progress(t,stale_io);}
 stale.dispatch(20001,stale_io);assert(stale.stats().fault==Cause::CommandTimeout);
 Executor::Candidate candidate;Executor tooth;IO tooth_io;
 cmd=running(1000);tooth.progress(1000,tooth_io);tooth.command(cmd,1000,tooth_io);
 tooth.prepare(candidate,1000,2000);candidate.calculate(0,1000);assert(tooth.commit(candidate,1000,tooth_io)==Executor::Commit::Accepted);
 tooth.dispatch(3000,tooth_io);assert(tooth.stats().fault==Cause::ToothTimeout);
}
void execution_tests(){
 Executor core;IO io;auto cmd=running();core.progress(1,io);core.command(cmd,1,io);
 std::uint64_t now=1,next_tooth=1000,next_command=5000;unsigned index=0;
 Executor::Candidate candidate;
 for(;now<=180000;++now){
  if(now%100==0)core.progress(now,io);
  if(now==next_command){++cmd.sequence;cmd.command_us=cmd.sampled_us=now;core.command(cmd,now,io);next_command+=5000;}
  if(core.next_alarm()<=now){
   Executor::Candidate racing;core.prepare(racing,now,20000);racing.calculate(index,1000);
   core.dispatch(now,io);
   assert(core.commit(racing,now,io)==Executor::Commit::Retry);
  }
  if(now==next_tooth){
   core.raw_capture(now);core.prepare(candidate,now,20000);candidate.calculate(index,1000);
   assert(core.commit(candidate,now,io)==Executor::Commit::Accepted);
   ++index;if(index==58){index=0;next_tooth+=3000;}else next_tooth+=1000;
  }
  assert(core.stats().fault==Cause::None);
 }
 assert(core.stats().dispatched>30);assert(core.stats().max_injector_high_us==3000);
 assert(core.stats().max_coil_high_us==2800);
 // An IRQ from an older compare must peek the current next event; no pop.
 const auto events=core.stats().dispatched;core.dispatch(now,io);assert(core.stats().dispatched==events);
}
void late_and_gate_tests(){
 for(bool reject_gate:{false,true}){
  Executor core;IO io;auto cmd=running();core.progress(1,io);core.command(cmd,1,io);
  Executor::Candidate c;core.prepare(c,1000,100000);c.calculate(0,1000);assert(core.commit(c,1000,io)==Executor::Commit::Accepted);
  for(unsigned t=1000;t<=8000;t+=1000){core.progress(t,io);}
  ++cmd.sequence;cmd.command_us=cmd.sampled_us=8000;core.command(cmd,8000,io);
  auto due=core.next_alarm();assert(due>8000&&due<18000);
  if(reject_gate){io.permit=false;core.dispatch(due,io);assert(core.stats().fault==Cause::Gate);}
  else{core.dispatch(due+26,io);assert(core.stats().fault==Cause::LateInterrupt&&io.writes==0);}
  assert(!io.mask);
 }
}
void recovery_tests(){
 Executor core;IO io;auto cmd=running();core.progress(1,io);core.command(cmd,1,io);
 core.raw_capture(0);core.trip(1000,Cause::LateInterrupt,io);
 cmd.output.state=ecu::engine::State::Stopped;cmd.output.fuel_cut=cmd.output.spark_cut=true;
 for(unsigned now=10000;now<=180000;now+=5000){
  ++cmd.sequence;cmd.command_us=cmd.sampled_us=now;core.progress(now,io);core.command(cmd,now,io);
  const bool recovered=core.recover(now,true);
  if(now<175000)assert(!recovered);
 }
 assert(core.stats().fault==Cause::None&&core.stats().recoveries==1&&io.mask==0);
 core.trip(185000,Cause::Gate,io);
 for(unsigned now=190000;now<400000;now+=5000){
  ++cmd.sequence;cmd.command_us=cmd.sampled_us=now;core.progress(now,io);core.command(cmd,now,io);
  core.raw_capture(now);assert(!core.recover(now,true));
 }
 assert(core.stats().fault==Cause::Gate);
 Executor delayed;IO delayed_io;cmd=running();delayed.progress(1,delayed_io);delayed.command(cmd,1,delayed_io);
 delayed.progress(6000,delayed_io);assert(delayed.stats().fault==Cause::ProducerTimeout);
 ++cmd.sequence;cmd.command_us=cmd.sampled_us=6000;delayed.command(cmd,6000,delayed_io);
 assert(delayed.stats().fault==Cause::ProducerTimeout); // fresh data cannot hide an expired deadline
}
void independent_high_and_short_pulse_tests(){
 for(bool tiny:{false,true}){
  Executor core;IO io;auto cmd=running();cmd.output.spark_cut=true;
  cmd.output.pulse_ms=tiny?.001:3;cmd.max_injector_high_us=1000;
  core.progress(1,io);core.command(cmd,1,io);
  Executor::Candidate candidate;core.prepare(candidate,1000,100000);candidate.calculate(0,1000);
  assert(core.commit(candidate,1000,io)==Executor::Commit::Accepted);
  for(unsigned now=1000;now<48000;++now){
   if(now%1000==0)core.progress(now,io);
   if(now%5000==0){++cmd.sequence;cmd.command_us=cmd.sampled_us=now;core.command(cmd,now,io);}
   if(tiny&&now>=46000&&now<46003)continue; // delayed IRQ passes both planned edges
   if(core.next_alarm()<=now)core.dispatch(now,io);
   if(core.stats().fault!=Cause::None)break;
  }
  assert(!io.mask);
  if(tiny){assert(core.stats().fault==Cause::LateInterrupt&&io.writes==0);}
  else{assert(core.stats().fault==Cause::HighLimit&&core.stats().max_injector_high_us==1000);}
 }
}
int main(){clock_tests();transactional_tests();deadline_tests();execution_tests();late_and_gate_tests();recovery_tests();independent_high_and_short_pulse_tests();
 std::cout<<"Capture timebase, transactional timing, independent expiry, output edges and fault tests passed\n";}
