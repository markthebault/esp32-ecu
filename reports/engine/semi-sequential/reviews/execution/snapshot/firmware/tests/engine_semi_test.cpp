#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace ecu::engine;

// Prescribed constant shaft, independently calculated phases. This checks
// logical scheduling and integer timestamp rounding, not physical jitter.
void steady_pairs(unsigned slots,unsigned rpm,double end,std::array<unsigned,4> order){
 Tune tune;tune.strategy=Strategy::SemiSequential;tune.injection_end_deg=end;tune.firing_order=order;
 Output output;output.state=State::Running;output.rpm=rpm;output.advance_deg=10;output.pulse_ms=output.dwell_ms=1;
 AngleScheduler scheduler;std::array<std::vector<std::pair<std::uint64_t,bool>>,8> edges;
 std::array<std::uint64_t,8> rise{};std::array<unsigned,4> counts{};
 const double rev=60000000.0/rpm;double max_error=0;
 for(unsigned tooth=0;tooth<slots*10;++tooth){
  const auto now=std::uint64_t(std::llround(1+tooth*rev/slots));Edge edge;
  while(scheduler.next_time()<=now){
   assert(scheduler.pop(edge)&&!scheduler.event_forced_cut());
   if(edge.time_us>2*rev+1&&edge.time_us<=8*rev+1)edges[edge.channel].push_back({edge.time_us,edge.high});
   if(edge.high)rise[edge.channel]=edge.time_us;
   else{
    if(edge.channel<4)assert(edge.time_us-rise[edge.channel]==1000);
    else assert(std::abs(double(edge.time_us-rise[edge.channel])-1000)<=16);
    if(edge.channel<4&&edge.time_us>2*rev+1&&edge.time_us<=8*rev+1){
     ++counts[edge.channel];unsigned slot=0;while(order[slot]!=edge.channel+1)++slot;
     const double expected=std::fmod(90+180*slot+end,360),actual=std::fmod((edge.time_us-1)/rev*360,360);
     max_error=std::max(max_error,std::abs(std::remainder(actual-expected,360)));
    }
   }
  }
  if(tooth%slots<slots-2)assert(scheduler.tooth(tune,output,now,tooth%slots,slots,now,now));
 }
 for(auto count:counts)assert(count==6);
 for(unsigned group=0;group<2;++group){
  assert(edges[order[group]-1]==edges[order[group+2]-1]);
  assert(edges[order[group]+3]==edges[order[group+2]+3]);
 }
 assert(edges[order[0]-1]!=edges[order[1]-1]);
 assert(!scheduler.failed()&&scheduler.shortened_starts()==0&&max_error<.55);
}

struct IO {unsigned mask=0;void all_low(){mask=0;}bool write(unsigned ch,bool high){if(high)mask|=1U<<ch;else mask&=~(1U<<ch);return true;}};
void hot_mode_fault(){
 using namespace ecu::timing;
 Executor executor;IO io;Command cmd;cmd.angle.strategy=Strategy::Sequential;cmd.sequence=1;
 cmd.command_us=cmd.sampled_us=1;cmd.tune_revision=cmd.sensor_revision=1;
 executor.progress(1,io);executor.command(cmd,1,io);executor.phase(true,3001,1,io);
 cmd.sequence++;cmd.command_us=cmd.sampled_us=2;cmd.output.state=State::Running;
 cmd.output.rpm=1000;cmd.output.pulse_ms=3;cmd.output.dwell_ms=2.8;executor.command(cmd,2,io);
 executor.dispatch(3001,io);assert(executor.stats().fault==Cause::CamPhase&&!io.mask);
 executor.stop(3002,Cause::Configuration,io);
 cmd.angle.strategy=Strategy::SemiSequential;++cmd.tune_revision;++cmd.configuration_epoch;
 ++cmd.sequence;cmd.command_us=cmd.sampled_us=3003;executor.command(cmd,3003,io);
 assert(executor.stats().fault==Cause::CamPhase&&executor.stats().recoveries==0);
 Executor::Candidate candidate;executor.prepare(candidate,4000,20000);candidate.calculate(0,1000);
 assert(executor.commit(candidate,4000,io)==Executor::Commit::Fault&&!io.mask);
 // Even quiet inputs cannot clear the fault with a running command.
 for(std::uint64_t now=5000;now<=250000;now+=1000){
  ++cmd.sequence;cmd.command_us=cmd.sampled_us=now;executor.progress(now,io);executor.command(cmd,now,io);
  assert(!executor.recover(now,true));
 }
 // A stopped command still requires the existing supervised quiet interval.
 cmd.output.state=State::Stopped;bool recovered=false;
 for(std::uint64_t now=251000;now<=280000;now+=1000){
  ++cmd.sequence;cmd.command_us=cmd.sampled_us=now;executor.progress(now,io);executor.command(cmd,now,io);
  recovered=executor.recover(now,true)||recovered;
 }
 assert(recovered&&executor.stats().fault==Cause::None&&executor.stats().last_fault==Cause::CamPhase&&executor.stats().recoveries==1&&!io.mask);
}

int main(){
 std::array<unsigned,4> order{1,2,3,4};unsigned cases=0;
 do{for(unsigned slots:{36U,60U,120U})for(unsigned rpm:{1000U,8000U})for(double end:{0.,179.,180.,359.,360.,540.,719.}){steady_pairs(slots,rpm,end,order);++cases;}}while(std::next_permutation(order.begin()+1,order.end()));
 hot_mode_fault();std::cout<<cases<<" semi-sequential pair/phase/width cases and hot-mode fault retention passed\n";
}
