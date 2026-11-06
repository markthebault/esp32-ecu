#pragma once
#include "ecu/realtime.hpp"
#include <array>
#include <cstdint>
#include <limits>

namespace ecu::trigger_log {
enum class State : std::uint8_t {Idle,Armed,Full,Timeout,Stopped,Clock};
inline const char* name(State state){switch(state){
 case State::Armed:return "armed";case State::Full:return "full";case State::Timeout:return "timeout";
 case State::Stopped:return "stopped";case State::Clock:return "clock_reversed";default:return "idle";}}
struct Record {
 std::uint64_t captured_us=0,callback_us=0;
 std::uint32_t raw_counter=0,configuration_epoch=0;
 bool cam=false,high=false,timebase_valid=false;
};
struct Header {
 State state=State::Idle;
 std::uint32_t frame_id=0;
 unsigned requested=0,count=0,prearm_ignored=0,invalid_timebase_ignored=0;
 std::uint64_t started_us=0,deadline_us=0,ended_us=0;
};
// A single finite capture, frozen on completion. Every method is serialized by
// the caller's target lock. No allocation, blocking, decoder or output writes.
class Capture {
public:
 static constexpr unsigned capacity=512;
 bool start(unsigned requested,unsigned timeout_ms,std::uint64_t now){
  expire(now);
  if(header_.state==State::Armed||requested<16||requested>capacity||timeout_ms<50||timeout_ms>5000||
     header_.frame_id==UINT32_MAX||now>UINT64_MAX-static_cast<std::uint64_t>(timeout_ms)*1000)return false;
  const auto id=header_.frame_id+1;header_={};header_.frame_id=id;header_.state=State::Armed;
  header_.requested=requested;header_.started_us=now;last_observed_us_=now;header_.deadline_us=now+static_cast<std::uint64_t>(timeout_ms)*1000;return true;
 }
 bool stop(std::uint32_t frame_id,std::uint64_t now){
  if(!frame_id||frame_id!=header_.frame_id)return false;
  expire(now);if(header_.state==State::Armed){header_.state=State::Stopped;header_.ended_us=now;}return true;
 }
 ECU_ISR_CODE void expire(std::uint64_t now){
  if(header_.state!=State::Armed)return;
  if(now<last_observed_us_){header_.state=State::Clock;header_.ended_us=now;}
  else if(now>=header_.deadline_us){header_.state=State::Timeout;header_.ended_us=now;}
  last_observed_us_=now;
 }
 ECU_ISR_CODE void append(const Record& record){
  expire(record.callback_us);if(header_.state!=State::Armed)return;
  if(!record.timebase_valid||record.captured_us>record.callback_us){++header_.invalid_timebase_ignored;return;}
  // A pending IRQ from before arming must not appear as a new input edge.
  if(record.captured_us<header_.started_us){++header_.prearm_ignored;return;}
  records_[header_.count++]=record;
  if(header_.count==header_.requested){header_.state=State::Full;header_.ended_us=record.callback_us;}
 }
 Header header()const{return header_;}
 bool read(std::uint32_t frame_id,unsigned index,Record& record)const{
  if(frame_id!=header_.frame_id||index>=header_.count)return false;
  record=records_[index];return true;
 }
private:
 Header header_;
 std::uint64_t last_observed_us_=0;
 std::array<Record,capacity> records_{};
};
}
