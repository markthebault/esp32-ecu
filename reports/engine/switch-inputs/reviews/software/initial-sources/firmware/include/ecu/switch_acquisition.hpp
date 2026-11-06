#pragma once
#include "ecu/secondary_tables.hpp"
#include <array>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>

// Portable SW2-J4 acquisition contract. This does not implement input
// protection or prove that a connected board is genuine. The target adapter
// owns J4 only while an Input rule requests it; SAFE_N is never used here.
namespace ecu::switch_input {
constexpr std::uint8_t address=0x20,marker_mask=0x3c,marker_value=0x28;
constexpr std::uint64_t poll_us=5000,budget_us=3000,fresh_us=20000,retry_us=100000;
constexpr std::array<std::uint8_t,7> configuration{0x7f,0,0,0,0,4,0};
enum class Kind:std::uint8_t {None,Marker,Iocon,Configure,Challenge,GuardedRead};
enum class Phase:std::uint8_t {Disabled,Marker,Iocon,Configure,Challenge,Read,Backoff,Fatal};
enum class Result:std::uint8_t {Ok,Unavailable,Timeout,BusError,ClockError,NoBudget};
enum class Fault:std::uint8_t {None,Unavailable,Timeout,BusError,Reply,Marker,Configuration,Loopback,Clock,Budget,PollGap,Internal};
inline const char*phase_name(Phase p){switch(p){
 case Phase::Disabled:return "not_requested";case Phase::Marker:return "checking_marker";
 case Phase::Iocon:return "setting_sequential_mode";case Phase::Configure:return "configuring";
 case Phase::Challenge:return "writing_loopback";case Phase::Read:return "reading_inputs";
 case Phase::Backoff:return "retry_wait";case Phase::Fatal:return "reset_required";
 default:return "unknown";
}}
inline const char*fault_name(Fault f){switch(f){
 case Fault::None:return "none";case Fault::Unavailable:return "bus_or_device_unavailable";
 case Fault::Timeout:return "i2c_timeout";case Fault::BusError:return "i2c_error";
 case Fault::Reply:return "invalid_reply";case Fault::Marker:return "marker_mismatch";
 case Fault::Configuration:return "configuration_mismatch";case Fault::Loopback:return "loopback_mismatch";
 case Fault::Clock:return "clock_reversed_or_exhausted";case Fault::Budget:return "acquisition_budget_exceeded";
 case Fault::PollGap:return "producer_gap";case Fault::Internal:return "acquisition_state_error";
 default:return "unknown";
}}
struct Request {
 Kind kind=Kind::None;std::uint64_t token=0,issued_us=0;
 std::uint8_t reg=0,write_size=0,read_size=0;
 std::array<std::uint8_t,7> data{};
 explicit operator bool()const{return kind!=Kind::None;}
};
struct Reply {
 Result result=Result::Unavailable;std::uint8_t size=0;
 // GuardedRead: registers0..10, followed by a separate IODIR read.
 std::array<std::uint8_t,12> data{};
};
struct Snapshot {
 Phase phase=Phase::Disabled;Fault fault=Fault::None,last_fault=Fault::None;
 std::uint8_t requested_mask=0,gpio=0;bool raw_known=false,ready=false,fault_pending=false,challenge_high=false;
 std::uint64_t fault_id=0,attempts=0,reads=0,failures=0,consumed_faults=0,configurations=0;
 std::uint64_t observed_us=0,read_completed_us=0,last_duration_us=0,max_duration_us=0,last_fault_us=0;
 std::array<secondary::SwitchSample,2> samples{};
};
class Acquisition {
 secondary::InputSource source_;
 Phase phase_=Phase::Disabled;Fault fault_=Fault::None,last_fault_=Fault::None;
 Request pending_{};std::uint8_t mask_=0,gpio_=0;
 bool known_=false,ready_=false,fault_pending_=false,challenge_high_=false,clock_seen_=false;
 std::uint64_t token_=0,fault_id_=0,attempts_=0,reads_=0,failures_=0,consumed_=0,configurations_=0;
 std::uint64_t next_due_=0,last_clock_=0,observed_=0,completed_=0,last_duration_=0,max_duration_=0,last_fault_us_=0;
 static void increment(std::uint64_t&n){if(n!=UINT64_MAX)++n;}
 void fail(Fault why,std::uint64_t now,bool fatal=false){
  pending_={};ready_=false;fault_=last_fault_=why;fault_pending_=true;last_fault_us_=now;
  increment(failures_);increment(fault_id_);
  phase_=fatal||fault_id_==UINT64_MAX?Phase::Fatal:Phase::Backoff;
  next_due_=now>UINT64_MAX-retry_us?UINT64_MAX:now+retry_us;
 }
 void disable(){
  pending_={};phase_=Phase::Disabled;mask_=0;known_=ready_=fault_pending_=clock_seen_=false;
  fault_=Fault::None;next_due_=last_clock_=observed_=completed_=0;gpio_=0;challenge_high_=false;
 }
public:
 // Host models use Synthetic. Only the actual target adapter supplies
 // TargetProtected; no JSON/config field can choose this provenance.
 explicit Acquisition(secondary::InputSource source=secondary::InputSource::Synthetic):source_(source){}
 Request next(std::uint8_t requested_mask,std::uint64_t now){
  if(!requested_mask){disable();return {};}
  if(requested_mask>3||(source_!=secondary::InputSource::Synthetic&&source_!=secondary::InputSource::TargetProtected)){
   mask_=requested_mask;fail(Fault::Internal,now,true);return {};
  }
  mask_=requested_mask;
  if(phase_==Phase::Disabled){phase_=Phase::Marker;next_due_=now;clock_seen_=false;}
  if((clock_seen_&&now<last_clock_)||now>UINT64_MAX-poll_us){fail(Fault::Clock,now,true);return {};}
  clock_seen_=true;last_clock_=now;
  if(phase_==Phase::Fatal)return {};
  if(pending_){fail(Fault::Internal,now,true);return {};}
  if(ready_&&known_&&now>=observed_&&now-observed_>fresh_us){fail(Fault::PollGap,now);return {};}
  if(now<next_due_)return {};
  if(phase_==Phase::Backoff)phase_=Phase::Marker;
  if(token_==UINT64_MAX){fail(Fault::Internal,now,true);return {};}
  Request op;op.token=++token_;op.issued_us=now;
  switch(phase_){
   case Phase::Marker:op.kind=Kind::Marker;op.reg=9;op.read_size=1;break;
   case Phase::Iocon:op.kind=Kind::Iocon;op.reg=5;op.write_size=1;op.data[0]=configuration[5];break;
   case Phase::Configure:op.kind=Kind::Configure;op.reg=0;op.write_size=7;op.data=configuration;break;
   case Phase::Challenge:op.kind=Kind::Challenge;op.reg=10;op.write_size=1;op.data[0]=challenge_high_?0:0x80;break;
   case Phase::Read:op.kind=Kind::GuardedRead;op.reg=0;op.read_size=12;break;
   default:fail(Fault::Internal,now,true);return {};
  }
  pending_=op;next_due_=now+poll_us;increment(attempts_);return op;
 }
 bool complete(std::uint64_t token,const Reply&reply,std::uint64_t started,std::uint64_t ended){
  // A stale/unsolicited completion cannot finish or replace a pending request.
  if(!pending_||!token||token!=pending_.token)return false;
  const auto op=pending_;pending_={};
  if(started<op.issued_us||ended<started||ended<last_clock_){fail(Fault::Clock,ended,true);return true;}
  last_duration_=ended-started;max_duration_=std::max(max_duration_,last_duration_);last_clock_=ended;
  if(reply.result==Result::ClockError){fail(Fault::Clock,ended,true);return true;}
  if(ended-op.issued_us>budget_us||reply.result==Result::NoBudget){fail(Fault::Budget,ended);return true;}
  if(reply.result!=Result::Ok){fail(reply.result==Result::Unavailable?Fault::Unavailable:reply.result==Result::Timeout?Fault::Timeout:Fault::BusError,ended);return true;}
  if(reply.size!=op.read_size){fail(Fault::Reply,ended);return true;}
  switch(op.kind){
   case Kind::Marker:
    if((reply.data[0]&marker_mask)!=marker_value){fail(Fault::Marker,ended);break;}
    phase_=Phase::Iocon;break;
   case Kind::Iocon:phase_=Phase::Configure;break;
   case Kind::Configure:increment(configurations_);phase_=Phase::Challenge;break;
   case Kind::Challenge:challenge_high_=op.data[0]!=0;phase_=Phase::Read;break;
   case Kind::GuardedRead:{
    bool config_ok=reply.data[11]==configuration[0];
    for(unsigned i=0;i<configuration.size();++i)config_ok&=reply.data[i]==configuration[i];
    config_ok&=reply.data[7]==0&&reply.data[10]==(challenge_high_?0x80:0);
    if(!config_ok){fail(Fault::Configuration,ended);break;}
    if((reply.data[9]&marker_mask)!=marker_value){fail(Fault::Marker,ended);break;}
    if(bool(reply.data[9]&0x40)!=challenge_high_){fail(Fault::Loopback,ended);break;}
    gpio_=reply.data[9];observed_=started;completed_=ended;known_=ready_=true;increment(reads_);
    if(!fault_pending_)fault_=Fault::None;
    phase_=Phase::Challenge;break;
   }
   default:fail(Fault::Internal,ended,true);break;
  }
  return true;
 }
 // Call only after a control observation consumed the same invalid snapshot.
 // Good reads alone cannot clear this latch. A new read is required after ACK.
 bool invalid_sample_consumed(std::uint64_t fault_id){
  if(!fault_pending_||!fault_id||fault_id!=fault_id_||phase_==Phase::Fatal)return false;
  fault_pending_=false;ready_=false;increment(consumed_);return true;
 }
 Snapshot snapshot()const{
  Snapshot s;s.phase=phase_;s.fault=fault_;s.last_fault=last_fault_;s.requested_mask=mask_;s.gpio=gpio_;s.raw_known=known_;
  s.ready=ready_&&!fault_pending_;s.fault_pending=fault_pending_;s.challenge_high=challenge_high_;
  s.fault_id=fault_id_;s.attempts=attempts_;s.reads=reads_;s.failures=failures_;s.consumed_faults=consumed_;s.configurations=configurations_;
  s.observed_us=observed_;s.read_completed_us=completed_;s.last_duration_us=last_duration_;s.max_duration_us=max_duration_;s.last_fault_us=last_fault_us_;
  for(unsigned i=0;i<2;++i)if(mask_&(1U<<i)){
   auto&sample=s.samples[i];sample.source=known_?source_:secondary::InputSource::Unavailable;
   sample.observed_us=known_?observed_:0;sample.level=bool(gpio_&(1U<<i));sample.valid=known_&&s.ready;
  }
  return s;
 }
};
} // namespace ecu::switch_input
