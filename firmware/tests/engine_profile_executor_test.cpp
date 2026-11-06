#include "ecu/timing_executor.hpp"
#include <cassert>
#include <iostream>

using namespace ecu;
struct IO {
 std::uint32_t mask=0,seen=0;
 bool write(unsigned channel,bool high){
  const auto kind=engine::channels::kind(channel);
  assert(kind==engine::channels::Kind::Injector||kind==engine::channels::Kind::Coil);
  const auto bit=std::uint32_t(1U<<channel);seen|=bit;
  if(high)mask|=bit;else mask&=~bit;return true;
 }
 void all_low(){mask=0;}
};
int main(){
 timing::Executor core;IO io;timing::Command cmd;
 cmd.angle.cylinders=cmd.output.cylinder_count=8;
 for(unsigned c=0;c<8;++c)cmd.angle.firing_order[c]=c+1;
 cmd.output.state=engine::State::Running;cmd.output.rpm=1000;
 cmd.output.advance_deg=10;cmd.output.pulse_ms=10;cmd.output.dwell_ms=1;
 cmd.sequence=cmd.tune_revision=cmd.sensor_revision=1;cmd.command_us=cmd.sampled_us=1;
 core.progress(1,io);core.command(cmd,1,io);
 std::uint64_t next_tooth=1000,next_command=5000;unsigned index=0,maximum_burst=0;
 for(std::uint64_t now=1;now<=300000;++now){
  if(now%100==0)core.progress(now,io);
  if(now==next_command){++cmd.sequence;cmd.command_us=cmd.sampled_us=now;core.command(cmd,now,io);next_command+=5000;}
  if(core.next_alarm()<=now){
   const auto before=core.stats().dispatched;core.dispatch(now,io);
   maximum_burst=std::max(maximum_burst,unsigned(core.stats().dispatched-before));
  }
  if(now==next_tooth){
   core.raw_capture(now);timing::Executor::Candidate candidate;core.prepare(candidate,now,20000);candidate.calculate(index,1000);
   assert(core.commit(candidate,now,io)==timing::Executor::Commit::Accepted);
   ++index;if(index==58){index=0;next_tooth+=3000;}else next_tooth+=1000;
  }
  assert(core.stats().fault==timing::Cause::None);
 }
 assert(io.seen==engine::channels::mask(8));
 // In particular INJ5..8 are held10ms, beyond the3.5ms coil limit. Their
 // kind must select the15ms injector watchdog and injector width accounting.
 assert(core.stats().max_injector_high_us==10000&&core.stats().max_coil_high_us==1000);
 assert(maximum_burst>=8&&maximum_burst<=timing::Executor::interrupt_budget);
 core.trip(300001,timing::Cause::Control,io);assert(!io.mask&&core.next_alarm()==timing::Executor::none);
 std::cout<<"All16 sparse engine outputs executed;10ms upper injectors,1ms coils, bounded bursts and global-low cut passed\n";
}
