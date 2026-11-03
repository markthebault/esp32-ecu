#pragma once
#include "ecu/engine_scheduler.hpp"
#include <array>
#include <cstdint>
#include <limits>

namespace ecu::timing {
enum class Cause : std::uint8_t {None,Control,Configuration,Clock,Timebase,CaptureAge,CaptureOverflow,
 ProducerTimeout,CommandTimeout,ToothTimeout,LateInterrupt,HighLimit,Plan,Contention,Gate,TraceBudget};
inline const char* cause_name(Cause c){switch(c){
 case Cause::Control:return "control_inhibit";case Cause::Configuration:return "configuration_change";
 case Cause::Clock:return "clock_reversed";case Cause::Timebase:return "capture_timebase";
 case Cause::CaptureAge:return "capture_late";case Cause::CaptureOverflow:return "capture_overflow";
 case Cause::ProducerTimeout:return "producer_timeout";case Cause::CommandTimeout:return "command_timeout";
 case Cause::ToothTimeout:return "tooth_timeout";case Cause::LateInterrupt:return "late_interrupt";
 case Cause::HighLimit:return "maximum_high_time";case Cause::Plan:return "invalid_angle_plan";
 case Cause::Contention:return "commit_contention";case Cause::Gate:return "hardware_gate";
 case Cause::TraceBudget:return "interrupt_budget";default:return "none";}}

struct Command {
 engine::AngleConfig angle;
 engine::Output output;
 std::uint64_t sequence=0,command_us=0,sampled_us=0;
 std::uint32_t tune_revision=0,sensor_revision=0;
 unsigned max_injector_high_us=15000,max_coil_high_us=3500;
 unsigned slots=60,missing=2,max_rpm=8000;
};
struct TimingStats {
 std::uint64_t dispatched=0,cuts=0,faults=0,recoveries=0,retries=0,
  max_lateness_us=0,max_capture_age_us=0,max_producer_gap_us=0,
  max_injector_high_us=0,max_coil_high_us=0,last_fault_us=0,last_progress_us=0,last_capture_us=0;
 std::uint32_t generation=0,epoch=0;
 std::uint8_t high_mask=0;
 Cause fault=Cause::None,last_fault=Cause::None,last_cut=Cause::None;
};
struct TimingEvent {
 std::uint64_t sequence=0,scheduled_us=0,actual_us=0;
 std::uint32_t tune_revision=0;
 std::uint8_t channel=255,high=0;
 Cause cause=Cause::None;
};

// Caller serializes every operation on one short target lock. prepare() copies
// only bounded state under that lock; Candidate::calculate() MUST run outside.
// ISR dispatch uses only fixed storage/integer helpers, verified in target ELF.
class Executor {
public:
 static constexpr std::uint64_t none=UINT64_MAX;
 static constexpr unsigned trace_capacity=128,interrupt_budget=16;
 static constexpr std::uint64_t lateness_limit_us=25,producer_timeout_us=5000;
 struct Candidate {
  engine::AngleScheduler scheduler;
  Command command;
  std::uint32_t generation=0,epoch=0;
  std::uint64_t capture_us=0,stall_deadline=none;
  bool valid=false;
  void calculate(unsigned tooth,double rpm){
   auto out=command.output;out.rpm=rpm;
   valid=scheduler.tooth(command.angle,out,capture_us,tooth,command.slots,command.command_us,command.sampled_us);
  }
 };
 enum class Commit {Accepted,Retry,Fault};

 template<class IO> void command(const Command& c,std::uint64_t now,IO& io){
  const auto expired=expiry(now);if(expired!=Cause::None)trip(now,expired,io);
  const bool changed=c.tune_revision!=command_.tune_revision||c.sensor_revision!=command_.sensor_revision||
   c.slots!=command_.slots||c.missing!=command_.missing||c.max_rpm!=command_.max_rpm;
  if(changed){stop(now,Cause::Configuration,io);++stats_.epoch;}
  ++stats_.generation;
  if(!c.sequence||c.sequence<=command_.sequence||c.command_us>now||c.sampled_us>now||
     now-c.command_us>=20000||now-c.sampled_us>=20000){trip(now,Cause::CommandTimeout,io);return;}
  if(c.max_injector_high_us<1000||c.max_injector_high_us>15000||c.max_coil_high_us<500||c.max_coil_high_us>3500){trip(now,Cause::Plan,io);return;}
  command_=c;
  command_deadline_=std::min(c.command_us,c.sampled_us)+20000;
  active_=c.output.proposed_enabled();
  if(!active_)stop(now,Cause::Control,io);
  else scheduler_.refresh_control(c.command_us,c.sampled_us);
 }
 void prepare(Candidate& c,std::uint64_t capture_us,std::uint64_t stall_timeout)const{
  c.scheduler=scheduler_;c.command=command_;c.generation=stats_.generation;c.epoch=stats_.epoch;
  c.capture_us=capture_us;c.stall_deadline=capture_us+stall_timeout;c.valid=false;
 }
 template<class IO> Commit commit(const Candidate& c,std::uint64_t now,IO& io){
  if(c.generation!=stats_.generation||c.epoch!=stats_.epoch||c.command.sequence!=command_.sequence){++stats_.retries;return Commit::Retry;}
  if(stats_.fault!=Cause::None)return Commit::Fault;
  if(now<c.capture_us||now-c.capture_us>1000){trip(now,Cause::CaptureAge,io);return Commit::Fault;}
  stats_.max_capture_age_us=std::max(stats_.max_capture_age_us,now-c.capture_us);
  if(!c.valid||c.scheduler.failed()){trip(now,Cause::Plan,io);return Commit::Fault;}
  if(!active_)return Commit::Accepted;
  if(now>=command_deadline_||now>=c.stall_deadline){trip(now,Cause::CommandTimeout,io);return Commit::Fault;}
  const auto next=c.scheduler.next_time();
  if(next!=none&&next<now&&now-next>lateness_limit_us){trip(now,Cause::LateInterrupt,io);return Commit::Fault;}
  scheduler_=c.scheduler;tooth_deadline_=c.stall_deadline;++stats_.generation;return Commit::Accepted;
 }
 template<class IO> void progress(std::uint64_t now,IO& io){
  const auto expired=expiry(now);if(expired!=Cause::None)trip(now,expired,io);
  if(stats_.last_progress_us&&now>=stats_.last_progress_us)
   stats_.max_producer_gap_us=std::max(stats_.max_producer_gap_us,now-stats_.last_progress_us);
  stats_.last_progress_us=now;producer_deadline_=now+producer_timeout_us;
 }
 ECU_ISR_CODE void raw_capture(std::uint64_t us){capture_seen_=true;if(us>stats_.last_capture_us)stats_.last_capture_us=us;}
 ECU_ISR_CODE std::uint64_t next_alarm()const{
  if(stats_.fault!=Cause::None||!active_)return none;
  auto next=scheduler_.next_time();
  if(command_deadline_<next)next=command_deadline_;
  if(tooth_deadline_<next)next=tooth_deadline_;
  if(producer_deadline_<next)next=producer_deadline_;
  for(unsigned ch=0;ch<8;++ch)if((stats_.high_mask&(1U<<ch))&&high_deadlines_[ch]<next)next=high_deadlines_[ch];
  return next;
 }
 template<class IO> ECU_ISR_CODE void stop(std::uint64_t now,Cause cause,IO& io){
  io.all_low();
  for(unsigned ch=0;ch<8;++ch)if(stats_.high_mask&(1U<<ch))record_low(ch,now);
  if(stats_.high_mask||scheduler_.next_time()!=none){++stats_.cuts;record(now,now,255,false,cause);}
  stats_.high_mask=0;scheduler_.cut();tooth_deadline_=none;active_=false;
  stats_.last_cut=cause;++stats_.generation;
 }
 template<class IO> ECU_ISR_CODE void trip(std::uint64_t now,Cause cause,IO& io){
  if(stats_.fault==Cause::None){stats_.fault=cause;stats_.last_fault=cause;stats_.last_fault_us=now;++stats_.faults;record(now,now,255,false,cause);}
  stop(now,cause,io);active_=false;++stats_.epoch;
 }
 template<class IO> ECU_ISR_CODE void dispatch(std::uint64_t now,IO& io){
  if(now<last_dispatch_us_){trip(now,Cause::Clock,io);return;}
  last_dispatch_us_=now;
  if(stats_.fault!=Cause::None||!active_)return;
  if(now>=command_deadline_){trip(now,Cause::CommandTimeout,io);return;}
  if(now>=producer_deadline_){trip(now,Cause::ProducerTimeout,io);return;}
  if(now>=tooth_deadline_){trip(now,Cause::ToothTimeout,io);return;}
  for(unsigned ch=0;ch<8;++ch)if((stats_.high_mask&(1U<<ch))&&now>high_deadlines_[ch]){trip(now,Cause::HighLimit,io);return;}
  if(scheduler_.expired_unstarted(now)){trip(now,Cause::LateInterrupt,io);return;}
  for(unsigned count=0;count<interrupt_budget;++count){
   const auto due=scheduler_.next_time();
   if(due==none||due>now)break;
   if(now-due>lateness_limit_us){trip(now,Cause::LateInterrupt,io);return;}
   engine::Edge edge;
   if(!scheduler_.pop(edge)||scheduler_.event_forced_cut()){trip(now,Cause::CommandTimeout,io);return;}
   ++stats_.generation;
   if(edge.channel>=8){trip(now,Cause::Plan,io);return;}
   const auto bit=static_cast<std::uint8_t>(1U<<edge.channel);
   if(bool(stats_.high_mask&bit)==edge.high){trip(now,Cause::Plan,io);return;}
   current_event_=edge;
   if(!io.write(edge.channel,edge.high)){trip(now,Cause::Gate,io);return;}
   if(edge.high){
    stats_.high_mask|=bit;rise_us_[edge.channel]=now;
    high_deadlines_[edge.channel]=now+(edge.channel<4?command_.max_injector_high_us:command_.max_coil_high_us);
   }else{record_low(edge.channel,now);stats_.high_mask&=static_cast<std::uint8_t>(~bit);}
   const auto late=now-due;if(late>stats_.max_lateness_us)stats_.max_lateness_us=late;
   ++stats_.dispatched;record(due,now,static_cast<std::uint8_t>(edge.channel),edge.high,Cause::None);
  }
  if(scheduler_.next_time()!=none&&scheduler_.next_time()<=now){trip(now,Cause::TraceBudget,io);return;}
  for(unsigned ch=0;ch<8;++ch)if((stats_.high_mask&(1U<<ch))&&now>=high_deadlines_[ch]){trip(now,Cause::HighLimit,io);return;}
 }
 bool recover(std::uint64_t now,bool fresh_stopped){
  const bool quiet=!capture_seen_||(now>=stats_.last_capture_us&&now-stats_.last_capture_us>150000);
  const bool continuous=!last_recovery_check_us_||(now>last_recovery_check_us_&&now-last_recovery_check_us_<=20000);
  last_recovery_check_us_=now;
  if(stats_.fault==Cause::None||!fresh_stopped||!quiet||stats_.high_mask||now>=command_deadline_||
     command_.output.state!=engine::State::Stopped||command_.output.faults){quiet_since_=none;return false;}
  if(!continuous)quiet_since_=none;
  if(quiet_since_==none||now<quiet_since_)quiet_since_=now;
  if(now-quiet_since_<20000)return false;
  scheduler_.reset();stats_.fault=Cause::None;++stats_.recoveries;++stats_.epoch;++stats_.generation;
  active_=false;quiet_since_=none;return true;
 }
 const TimingStats& stats()const{return stats_;}
 std::uint64_t trace_sequence()const{return trace_sequence_;}
 bool trace(std::uint64_t sequence,TimingEvent& event)const{
  if(!sequence||sequence>trace_sequence_||trace_sequence_-sequence>=trace_capacity)return false;
  const auto& found=trace_[(sequence-1)%trace_capacity];if(found.sequence!=sequence)return false;
  event=found;return true;
 }
 const Command& current_command()const{return command_;}
 const engine::Edge& current_event()const{return current_event_;}
 double event_advance()const{return scheduler_.event_advance();}
 std::uint64_t event_requested_dwell_us()const{return scheduler_.event_requested_dwell_us();}
private:
 ECU_ISR_CODE Cause expiry(std::uint64_t now)const{
  if(stats_.fault!=Cause::None||!active_)return Cause::None;
  if(now>=command_deadline_)return Cause::CommandTimeout;
  if(now>=producer_deadline_)return Cause::ProducerTimeout;
  if(now>=tooth_deadline_)return Cause::ToothTimeout;
  return Cause::None;
 }
 ECU_ISR_CODE void record_low(unsigned ch,std::uint64_t now){
  const auto width=now>=rise_us_[ch]?now-rise_us_[ch]:0;
  auto& maximum=ch<4?stats_.max_injector_high_us:stats_.max_coil_high_us;
  if(width>maximum)maximum=width;
 }
 ECU_ISR_CODE void record(std::uint64_t scheduled,std::uint64_t actual,std::uint8_t channel,bool high,Cause cause){
  const auto sequence=++trace_sequence_;auto& event=trace_[(sequence-1)%trace_capacity];
  event.sequence=sequence;event.scheduled_us=scheduled;event.actual_us=actual;
  event.tune_revision=command_.tune_revision;event.channel=channel;event.high=high;event.cause=cause;
 }
 engine::AngleScheduler scheduler_;
 engine::Edge current_event_{};
 Command command_;
 TimingStats stats_;
 std::array<std::uint64_t,8> rise_us_{},high_deadlines_{};
 std::array<TimingEvent,trace_capacity> trace_{};
 std::uint64_t trace_sequence_=0,command_deadline_=none,producer_deadline_=none,
  tooth_deadline_=none,last_dispatch_us_=0,quiet_since_=none,last_recovery_check_us_=0;
 bool active_=false,capture_seen_=false;
};
}
