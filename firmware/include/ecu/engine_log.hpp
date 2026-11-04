#pragma once
#include "ecu/engine_data.hpp"

namespace ecu::engine_log {
enum class State : std::uint8_t {Idle,Recording,Timeout,Stopped,Clock,CounterLimit};
inline const char* state_name(State s){switch(s){case State::Recording:return "recording";case State::Timeout:return "timeout";case State::Stopped:return "stopped";case State::Clock:return "clock_reversed";case State::CounterLimit:return "counter_limit";default:return "idle";}}
struct Row {engine::RuntimeSample sample;std::uint64_t recorded_us=0;std::uint32_t log_id=0,sequence=0;};
struct Header {
 State state=State::Idle;engine::DataSource source=engine::DataSource::None;
 std::uint32_t log_id=0,period_ms=0,duration_s=0,total=0,retained=0,overwritten=0,missed_periods=0,repeated=0,invalid=0;
 std::uint64_t started_us=0,deadline_us=0,ended_us=0;
 std::uint32_t first_sequence()const{return retained?total-retained+1:1;}
};
struct Page {
 static constexpr unsigned capacity=16;
 Header header;std::array<Row,capacity> rows{};unsigned count=0;
 std::uint32_t next_after=0,gap_first=0,gap_last=0;
 bool superseded=false,future_cursor=false,invalid_row=false;
};
// Task-only, externally serialized fixed ring. No allocation or device writes.
// Retention is bounded; a consumer collects by row sequence and discloses gaps.
class Recorder {
public:
 static constexpr unsigned capacity=256;
 static bool valid_period(unsigned ms){return ms==20||ms==50||ms==100||ms==200||ms==500||ms==1000;}
 bool start(unsigned period_ms,unsigned duration_s,engine::DataSource source,std::uint64_t now){
  expire(now);
  if(header_.state==State::Recording||!valid_period(period_ms)||duration_s<1||duration_s>900||
     (source!=engine::DataSource::Target&&source!=engine::DataSource::Synthetic)||header_.log_id==UINT32_MAX||
     now>UINT64_MAX-std::uint64_t(duration_s)*1000000)return false;
  const auto id=header_.log_id+1;header_={};header_.log_id=id;header_.state=State::Recording;header_.source=source;
  header_.period_ms=period_ms;header_.duration_s=duration_s;header_.started_us=now;header_.deadline_us=now+std::uint64_t(duration_s)*1000000;
  next_due_=last_observed_=now;last_snapshot_=0;return true;
 }
 bool stop(std::uint32_t id,std::uint64_t now){
  if(!id||id!=header_.log_id)return false;
  expire(now);if(header_.state==State::Recording){missed_through(now);header_.state=State::Stopped;header_.ended_us=now;}return true;
 }
 void expire(std::uint64_t now){
  if(header_.state!=State::Recording)return;
  if(now<last_observed_){header_.state=State::Clock;header_.ended_us=now;}
  else if(now>=header_.deadline_us){missed_through(header_.deadline_us-1);header_.state=State::Timeout;header_.ended_us=header_.deadline_us;}
  last_observed_=now;
 }
 bool append(const engine::RuntimeSample& sample,std::uint64_t now){
  expire(now);if(header_.state!=State::Recording||now<next_due_)return false;
  const auto period=std::uint64_t(header_.period_ms)*1000;
  const auto skipped=(now-next_due_)/period;
  header_.missed_periods+=static_cast<std::uint32_t>(std::min<std::uint64_t>(skipped,UINT32_MAX-header_.missed_periods));
  next_due_+=(skipped+1)*period;
  if(!sample.has(engine::Present)||!sample.sequence||sample.source!=header_.source||sample.control_us>now||sample.sampled_us>now){++header_.invalid;return false;}
  if(sample.sequence<=last_snapshot_){++header_.repeated;return false;}
  if(header_.total==UINT32_MAX){header_.state=State::CounterLimit;header_.ended_us=now;return false;}
  last_snapshot_=sample.sequence;const auto sequence=++header_.total;
  rows_[(sequence-1)%capacity]={sample,now,header_.log_id,sequence};
  if(header_.retained<capacity)++header_.retained;else ++header_.overwritten;
  return true;
 }
 Header header()const{return header_;}
 bool current(std::uint32_t id)const{return id&&id==header_.log_id;}
 bool read(std::uint32_t id,std::uint32_t sequence,Row& row)const{
  if(!current(id)||!sequence||sequence<header_.first_sequence()||sequence>header_.total)return false;
  const auto&found=rows_[(sequence-1)%capacity];if(found.log_id!=id||found.sequence!=sequence)return false;
  row=found;return true;
 }
 void page(std::uint32_t id,std::uint32_t after,Page& out)const{
  // Entries beyond count are unspecified. Avoid a full3.5KiB Page temporary
  // (and clearing unused rows) while the task mutex is held.
  out.header=header_;out.count=0;out.next_after=after;out.gap_first=out.gap_last=0;
  out.superseded=out.future_cursor=out.invalid_row=false;
  if(!current(id)){out.superseded=true;return;}
  if(after>header_.total){out.future_cursor=true;return;}
  if(after==header_.total)return;
  auto from=after+1;const auto first=header_.first_sequence();
  if(from<first){out.gap_first=from;out.gap_last=first-1;from=first;}
  for(unsigned n=0;n<Page::capacity&&from<=header_.total;++n,++from){
   if(!read(id,from,out.rows[n])){out.invalid_row=true;out.count=0;return;}
   ++out.count;out.next_after=from;
  }
 }
private:
 void missed_through(std::uint64_t last){
  if(last<next_due_)return;
  const auto count=(last-next_due_)/(std::uint64_t(header_.period_ms)*1000)+1;
  header_.missed_periods+=static_cast<std::uint32_t>(std::min<std::uint64_t>(count,UINT32_MAX-header_.missed_periods));
 }
 Header header_;std::array<Row,capacity> rows_{};
 std::uint64_t next_due_=0,last_observed_=0,last_snapshot_=0;
};
static_assert(sizeof(Recorder)<112*1024,"Engine recorder exceeds its explicit256-row load-model diagnostic RAM budget");
}
