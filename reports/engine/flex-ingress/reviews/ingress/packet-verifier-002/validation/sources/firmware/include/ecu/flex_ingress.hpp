#pragma once
// Integer-only handoff for a future flex capture ISR. This does not configure
// a peripheral, qualify a sensor or own the floating-point Capture worker.
// Every call, including snapshot(), requires the same external serialization.
// Sample observed/owner time inside that serialization, after taking the lock.
// A timestamp from before lock acquisition can be older than an intervening
// call and correctly cause clock suppression, even for a stale ACK request.
#include "ecu/realtime.hpp"
#include <array>
#include <cstdint>
#include <limits>

namespace ecu::flex {
enum class IngressFault:std::uint8_t {
 None,Clock,Overflow,RepeatedLevel,ShortInterval,RateLimit,
 ContextChanged,InvalidContext,SequenceExhausted
};
inline const char* ingress_fault_name(IngressFault f){switch(f){
 case IngressFault::None:return "none";
 case IngressFault::Clock:return "clock";
 case IngressFault::Overflow:return "queue_overflow";
 case IngressFault::RepeatedLevel:return "repeated_level";
 case IngressFault::ShortInterval:return "short_interval";
 case IngressFault::RateLimit:return "callback_rate";
 case IngressFault::ContextChanged:return "context_changed";
 case IngressFault::InvalidContext:return "invalid_context";
 case IngressFault::SequenceExhausted:return "sequence_exhausted";
 default:return "unknown";
}}
struct IngressEdge {
 std::uint64_t captured_us=0,observed_us=0,context=0,sequence=0;
 std::uint32_t raw_capture=0;
 bool high=false;
};
struct IngressTicket {
 std::uint64_t context=0,generation=0;
 explicit operator bool()const{return context&&generation;}
};
struct IngressCounters {
 std::uint64_t callbacks=0,accepted=0,dequeued=0,discarded=0;
 std::uint64_t ignored_context=0,ignored_inactive=0,ignored_prearm=0;
 std::uint64_t suppressions=0,rejected_ack=0;
 std::array<std::uint64_t,9> faults{};
};
struct IngressSnapshot {
 IngressCounters counters;
 std::uint64_t context=0,fault_generation=0,acknowledged_generation=0;
 std::uint64_t armed_after_us=0,last_observed_us=0,last_suppression_us=0;
 unsigned queued=0;
 IngressFault last_fault=IngressFault::None;
 // retry_holdoff is evaluated at last_observed_us, not the time of this read.
 bool armed=false,pending_fault=false,terminal=false,retry_holdoff=false;
};
class Ingress {
public:
 static constexpr unsigned capacity=64;
 static constexpr std::uint64_t minimum_interval_us=50,maximum_age_us=5000;
 static constexpr std::uint64_t rate_window_us=10000,retry_holdoff_us=50000;
 static constexpr unsigned callbacks_per_window=32;
 // Suppress means the caller must mask ONLY this capture channel's interrupt.
 // No SDK call, shared timer reset or interrupt-register write occurs here.
 // The callback window is per armed episode. The trusted owner must not use
 // repeated normal stop/arm to bypass suppression/retry or claim a global IRQ
 // budget. Foreign/inactive callbacks depend on actual source-local masking.
 enum class Result:std::uint8_t {Accepted,Ignored,Suppress};
private:
 std::array<IngressEdge,capacity> queue_{};
 IngressCounters counters_;
 IngressTicket offered_;
 std::uint64_t context_=0,generation_=0,acknowledged_=0;
 std::uint64_t armed_after_=0,last_observed_=0,last_captured_=0;
 std::uint64_t suppressed_at_=0,rate_start_=0;
 unsigned head_=0,size_=0,rate_count_=0;
 IngressFault last_fault_=IngressFault::None;
 bool armed_=false,time_seen_=false,edge_seen_=false,last_high_=false;
 bool suppressed_=false,terminal_=false;
 static ECU_ISR_CODE void increment(std::uint64_t&n){if(n!=UINT64_MAX)++n;}
 ECU_ISR_CODE void discard(){
  // Count one operation per queued edge, without traversing the ring in ISR.
  if(counters_.discarded>UINT64_MAX-size_)counters_.discarded=UINT64_MAX;
  else counters_.discarded+=size_;
  head_=size_=0;edge_seen_=false;rate_count_=0;
 }
 ECU_ISR_CODE void suppress(IngressFault reason){
  discard();armed_=false;suppressed_=true;suppressed_at_=last_observed_;
  last_fault_=reason;offered_={};increment(counters_.suppressions);
  increment(counters_.faults[static_cast<unsigned>(reason)]);
  if(generation_==UINT64_MAX)terminal_=true;else ++generation_;
 }
 ECU_ISR_CODE bool clock(std::uint64_t now){
  if(time_seen_&&now<last_observed_){suppress(IngressFault::Clock);return false;}
  time_seen_=true;last_observed_=now;return true;
 }
 ECU_ISR_CODE bool pending()const{return terminal_||generation_!=acknowledged_;}
public:
 // The owner issues strictly increasing nonzero contexts for ANY acquisition
 // binding change, even when calibration is unchanged. Repeating the current
 // context is idempotent. Reuse/wrap is a terminal programming error.
 bool begin_context(std::uint64_t context,std::uint64_t now){
  if(!clock(now))return false;
  if(!context||(context_&&context<context_)){
   terminal_=true;suppress(IngressFault::InvalidContext);return false;
  }
  if(context==context_)return !terminal_;
  const bool changed=context_!=0;context_=context;offered_={};
  if(changed)suppress(IngressFault::ContextChanged);
  else{discard();armed_=false;}
  return !terminal_;
 }
 bool stop(std::uint64_t now){
  if(!clock(now))return false;
  discard();armed_=false;return true;
 }
 // The target owner must first disable this channel, clear only its pending
 // latch/status and stop GPIO output ownership. This fence rejects timestamps
 // at/before arm, including the indistinguishable boundary microsecond.
 bool arm(std::uint64_t context,std::uint64_t now){
  if(!clock(now)||!context||context!=context_||pending()||armed_)return false;
  if(suppressed_&&now-suppressed_at_<retry_holdoff_us)return false;
  discard();armed_=true;armed_after_=rate_start_=now;return true;
 }
 ECU_ISR_CODE Result push(std::uint64_t context,std::uint64_t captured,
                         std::uint64_t observed,bool high,bool clock_ok=true,
                         std::uint32_t raw_capture=0){
  increment(counters_.callbacks);
  if(!context||context!=context_){increment(counters_.ignored_context);return Result::Ignored;}
  if(!armed_){increment(counters_.ignored_inactive);return Result::Suppress;}
  if(!clock(observed))return Result::Suppress;
  if(!clock_ok||captured>observed||observed-captured>maximum_age_us){
   suppress(IngressFault::Clock);return Result::Suppress;
  }
  // Charge every matching active callback, even a discarded pre-arm latch.
  // This is a fixed callback-time window, not an estimate of sensor frequency.
  if(observed-rate_start_>=rate_window_us){rate_start_=observed;rate_count_=0;}
  if(rate_count_==callbacks_per_window){suppress(IngressFault::RateLimit);return Result::Suppress;}
  ++rate_count_;
  if(captured<=armed_after_){increment(counters_.ignored_prearm);return Result::Ignored;}
  if(edge_seen_){
   if(captured<=last_captured_){suppress(IngressFault::Clock);return Result::Suppress;}
   if(high==last_high_){suppress(IngressFault::RepeatedLevel);return Result::Suppress;}
   if(captured-last_captured_<minimum_interval_us){suppress(IngressFault::ShortInterval);return Result::Suppress;}
  }
  if(size_==capacity){suppress(IngressFault::Overflow);return Result::Suppress;}
  if(counters_.accepted==UINT64_MAX){terminal_=true;suppress(IngressFault::SequenceExhausted);return Result::Suppress;}
  ++counters_.accepted;
  auto&edge=queue_[(head_+size_)%capacity];
  edge.captured_us=captured;edge.observed_us=observed;edge.context=context;
  edge.sequence=counters_.accepted;edge.raw_capture=raw_capture;edge.high=high;
  ++size_;edge_seen_=true;last_captured_=captured;last_high_=high;
  return Result::Accepted;
 }
 bool pop(IngressEdge&edge){
  if(!size_)return false;
  edge=queue_[head_];head_=(head_+1)%capacity;--size_;increment(counters_.dequeued);return true;
 }
 // Only the owner preparing an invalid control input offers a fault. Reading
 // diagnostics never makes an ACK eligible. The caller may ACK only AFTER a
 // completed control observation consumed that same context/generation.
 IngressTicket offer_fault(){
  offered_=pending()&&context_?IngressTicket{context_,generation_}:IngressTicket{};
  return offered_;
 }
 bool acknowledge(IngressTicket ticket,std::uint64_t now){
  if(!clock(now)){increment(counters_.rejected_ack);return false;}
  if(terminal_||!ticket||ticket.context!=context_||ticket.generation!=generation_||
     ticket.context!=offered_.context||ticket.generation!=offered_.generation||
     ticket.generation==acknowledged_){increment(counters_.rejected_ack);return false;}
  acknowledged_=ticket.generation;offered_={};return true;
 }
 IngressSnapshot snapshot()const{
  IngressSnapshot s;s.counters=counters_;s.context=context_;s.fault_generation=generation_;
  s.acknowledged_generation=acknowledged_;s.armed_after_us=armed_after_;
  s.last_observed_us=last_observed_;s.last_suppression_us=suppressed_at_;s.queued=size_;
  s.last_fault=last_fault_;s.armed=armed_;s.pending_fault=pending();s.terminal=terminal_;
  s.retry_holdoff=suppressed_&&last_observed_-suppressed_at_<retry_holdoff_us;
  return s;
 }
};
static_assert(sizeof(Ingress)<=4096,"Bounded flex ingress must fit in4 KiB of DRAM");
} // namespace ecu::flex
