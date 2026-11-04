#pragma once
#include "ecu/switch_acquisition.hpp"

namespace ecu::status_led {
constexpr std::uint8_t address=0x21;
// GP0..2 drive active-high RGB transistor inputs. Every other GP is an unused
// output held low, including the output-only GP7. No input is left floating.
// IOCON.ODR=1 is also a nonzero readback marker. An all-zero image would
// mistake byte-mode reads repeating IODIR=0 for a valid sequential frame.
constexpr std::array<std::uint8_t,7> configuration{0,0,0,0,0,4,0};
constexpr std::uint64_t verify_us=100000,fresh_us=250000;
enum class Pattern:std::uint8_t {Off,Normal,Pairing,Problem};
enum class Phase:std::uint8_t {OffLatch,Iocon,Configure,Verify,Ready,Write,Backoff,Fatal};
inline const char*phase_name(Phase p){switch(p){
 case Phase::OffLatch:return "initializing_off";case Phase::Iocon:return "setting_sequential_mode";
 case Phase::Configure:return "configuring";case Phase::Verify:return "verifying_registers";
 case Phase::Ready:return "monitoring_latch";case Phase::Write:return "writing_color";
 case Phase::Backoff:return "retry_wait";case Phase::Fatal:return "reset_required";default:return "unknown";
}}
inline const char*pattern_name(Pattern p){switch(p){case Pattern::Off:return "off";case Pattern::Normal:return "green";
 case Pattern::Pairing:return "blue_blink";case Pattern::Problem:return "red_blink";default:return "unknown";}}
inline std::uint8_t color(Pattern p,std::uint64_t now){
 if(p==Pattern::Normal)return 2;
 if(p==Pattern::Off)return 0;
 return (now/250000)%2?(p==Pattern::Pairing?4:1):0;
}
struct Snapshot {
 Pattern desired=Pattern::Problem;Phase phase=Phase::OffLatch;
 switch_input::Fault fault=switch_input::Fault::None,last_fault=switch_input::Fault::None;
 std::uint8_t desired_rgb=0,written_rgb=0,verified_latch=0;
 bool configured=false,known=false,fresh=false,ready=false;
 std::uint64_t observed_us=0,completed_us=0,attempts=0,verifications=0,failures=0,budget_skips=0;
 std::uint64_t last_duration_us=0,max_duration_us=0;
};
class Acquisition {
 using Fault=switch_input::Fault;
 using Result=switch_input::Result;
 using Kind=switch_input::Kind;
 using Request=switch_input::Request;
 Snapshot value_;
 switch_input::Request pending_;
 std::uint64_t token_=0,last_clock_=0,due_=0;
 bool clock_seen_=false;
 static void increment(std::uint64_t&v){if(v!=UINT64_MAX)++v;}
 void fail(switch_input::Fault why,std::uint64_t now,bool fatal=false){
  pending_={};value_.fault=value_.last_fault=why;value_.configured=value_.ready=false;
  value_.phase=fatal?Phase::Fatal:Phase::Backoff;increment(value_.failures);
  due_=now>UINT64_MAX-switch_input::retry_us?UINT64_MAX:now+switch_input::retry_us;
 }
public:
 // One owner, one operation per tick. issued_us is the SHARED tick origin,
 // never a second LED deadline. GuardedRead needs two integer-ms SDK slots.
 switch_input::Request next(Pattern pattern,std::uint64_t now,std::uint64_t issued_us){
  value_.desired=pattern;value_.desired_rgb=color(pattern,now);
  if(value_.phase==Phase::Fatal)return {};
  if(static_cast<unsigned>(pattern)>static_cast<unsigned>(Pattern::Problem)||pending_){fail(Fault::Internal,now,true);return {};}
  if((clock_seen_&&now<last_clock_)||issued_us>now||now>UINT64_MAX-switch_input::poll_us){fail(Fault::Clock,now,true);return {};}
  last_clock_=now;clock_seen_=true;
  if(value_.phase==Phase::Ready&&value_.desired_rgb!=value_.written_rgb){value_.phase=Phase::Write;due_=now;}
  if(now<due_)return {};
  if(value_.phase==Phase::Backoff)value_.phase=Phase::OffLatch;
  const auto needed=value_.phase==Phase::Verify||value_.phase==Phase::Ready?2000U:1000U;
  if(now-issued_us>switch_input::budget_us-needed){increment(value_.budget_skips);return {};}
  if(token_==UINT64_MAX){fail(Fault::Internal,now,true);return {};}
  Request op;op.token=++token_;op.issued_us=issued_us;
  switch(value_.phase){
   case Phase::OffLatch:op.kind=Kind::Configure;op.reg=10;op.write_size=1;op.data[0]=0;break;
   case Phase::Iocon:op.kind=Kind::Iocon;op.reg=5;op.write_size=1;op.data[0]=configuration[5];break;
   case Phase::Configure:op.kind=Kind::Configure;op.reg=0;op.write_size=7;op.data=configuration;break;
   case Phase::Write:op.kind=Kind::Configure;op.reg=10;op.write_size=1;op.data[0]=value_.desired_rgb;break;
   case Phase::Verify:case Phase::Ready:op.kind=Kind::GuardedRead;op.read_size=12;break;
   default:fail(Fault::Internal,now,true);return {};
  }
  pending_=op;due_=now+switch_input::poll_us;increment(value_.attempts);return op;
 }
 bool complete(std::uint64_t token,const switch_input::Reply&r,std::uint64_t started,std::uint64_t ended){
  if(!pending_||!token||token!=pending_.token)return false;
  const auto op=pending_;pending_={};
  if(started<op.issued_us||started<last_clock_||ended<started||r.result==Result::ClockError){fail(Fault::Clock,std::max(last_clock_,ended),true);return true;}
  last_clock_=ended;value_.last_duration_us=ended-started;value_.max_duration_us=std::max(value_.max_duration_us,value_.last_duration_us);
  if(ended-op.issued_us>switch_input::budget_us||r.result==Result::NoBudget){fail(Fault::Budget,ended);return true;}
  if(r.result!=Result::Ok){fail(r.result==Result::Unavailable?Fault::Unavailable:r.result==Result::Timeout?Fault::Timeout:Fault::BusError,ended);return true;}
  if(r.size!=op.read_size){fail(Fault::Reply,ended);return true;}
  switch(value_.phase){
   case Phase::OffLatch:value_.written_rgb=0;value_.phase=Phase::Iocon;break;
   case Phase::Iocon:value_.phase=Phase::Configure;break;
   case Phase::Configure:value_.phase=Phase::Verify;break;
   case Phase::Write:value_.written_rgb=op.data[0];value_.phase=Phase::Verify;break;
   case Phase::Verify:case Phase::Ready:{
    bool ok=r.data[11]==configuration[0]&&r.data[7]==0&&r.data[9]==value_.written_rgb&&r.data[10]==value_.written_rgb;
    for(unsigned i=0;i<configuration.size();++i)ok&=r.data[i]==configuration[i];
    if(!ok){fail(Fault::Configuration,ended);break;}
    value_.configured=value_.known=true;value_.verified_latch=r.data[10];value_.observed_us=started;value_.completed_us=ended;
    value_.fault=Fault::None;value_.phase=Phase::Ready;increment(value_.verifications);
    due_=ended>UINT64_MAX-verify_us?UINT64_MAX:ended+verify_us;break;
   }
   default:fail(Fault::Internal,ended,true);break;
  }
  return true;
 }
 Snapshot snapshot(std::uint64_t now)const{
  auto s=value_;s.fresh=s.known&&s.configured&&now>=s.observed_us&&now>=s.completed_us&&now-s.observed_us<=fresh_us;
  s.ready=s.fresh&&s.phase==Phase::Ready&&s.verified_latch==s.desired_rgb&&s.fault==switch_input::Fault::None;
  return s;
 }
};
} // namespace ecu::status_led
