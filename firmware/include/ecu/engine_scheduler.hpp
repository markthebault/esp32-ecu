#pragma once
#include "ecu/engine.hpp"
#include "ecu/realtime.hpp"
namespace ecu::engine {
struct AngleConfig {
 double tooth1_btdc_deg=90,max_dwell_ms=3.5;
 Strategy strategy=Strategy::BatchWasted;
 std::array<unsigned,4> firing_order{1,3,4,2};
 double injection_end_deg=540,cam_sync_deg=450,cam_window_deg=20;
};
inline AngleConfig angle_config(const Tune&t){return {t.tooth1_btdc_deg,t.max_dwell_ms,t.strategy,t.firing_order,t.injection_end_deg,t.cam_sync_deg,t.cam_window_deg};}
// Portable crank-angle event scheduler for native SIL. It has no GPIO writes.
// Every decoded tooth refreshes pending deadlines. Injector close deadlines are
// fixed once opened; advance latches at dwell start and phase/speed corrections
// continue for that target angle, bounded by maximum dwell.
// Target hardware compare/ISR integration and jitter qualification are separate.
class AngleScheduler {
public:
 enum class StopReason {None,BadCommand,ToothOrder,Deadline,DwellLimit,CamPhase};
 static const char* reason_name(StopReason r){switch(r){case StopReason::BadCommand:return "invalid_command";case StopReason::ToothOrder:return "tooth_order";case StopReason::Deadline:return "unreachable_deadline";case StopReason::DwellLimit:return "dwell_limit";case StopReason::CamPhase:return "cam_phase_lost";default:return "none";}}
private:
 struct Slot {bool high=false,pending=false,phase_known=false,fired=false,inhibited=false;std::uint64_t start=0,end=0;std::int64_t cycle=0;double advance=0,previous_phase=0;std::uint64_t requested_dwell_us=0;};
 std::array<Slot,8> slots_{};
 bool initialized_=false;unsigned previous_tooth_=0;std::int64_t revolution_=0;
 std::uint64_t previous_time_=0;double angle_=0,us_per_degree_=0;
 std::uint64_t shortened_=0,skipped_initial_=0,popped_dwell_=0;double popped_advance_=0;
 bool failed_=false,forced_cut_=false;std::uint64_t expires_=UINT64_MAX;
 StopReason reason_=StopReason::None;
 bool fail(StopReason reason){reason_=reason;failed_=true;cut();return false;}
public:
 void reset(){*this=AngleScheduler{};}
 ECU_ISR_CODE void cut(){for(auto&s:slots_)s=Slot{};initialized_=false;}
 bool failed()const{return failed_;}
 void fail_phase(){if(!failed_)fail(StopReason::CamPhase);}
 StopReason stop_reason()const{return reason_;}
 ECU_ISR_CODE bool event_forced_cut()const{return forced_cut_;}
 void refresh_control(std::uint64_t command_us,std::uint64_t sampled_us){const auto base=std::min(command_us,sampled_us);expires_=base>UINT64_MAX-20000?UINT64_MAX:base+20000;}
 std::uint64_t shortened_starts()const{return shortened_;}
 ECU_ISR_CODE double event_advance()const{return popped_advance_;}
 ECU_ISR_CODE std::uint64_t event_requested_dwell_us()const{return popped_dwell_;}
 std::uint64_t skipped_initial()const{return skipped_initial_;}
 ECU_ISR_CODE std::uint64_t next_time()const{
  auto next=std::numeric_limits<std::uint64_t>::max();for(const auto&s:slots_)if(s.pending)next=std::min(next,s.high?s.end:s.start);return next==UINT64_MAX?next:std::min(next,expires_);
 }
 ECU_ISR_CODE bool expired_unstarted(std::uint64_t now)const{
  for(const auto& s:slots_)if(s.pending&&!s.high&&s.start<=now&&s.end<=now)return true;
  return false;
 }
 ECU_ISR_CODE bool pop(Edge&edge){
  unsigned channel=8;auto time=next_time();if(time==std::numeric_limits<std::uint64_t>::max())return false;
  forced_cut_=false;
  if(time==expires_){cut();forced_cut_=true;edge={time,0,false};return true;}
  // Off transitions win ties. Never merge independent coil channels.
  for(unsigned i=0;i<8;++i)if(slots_[i].pending&&(slots_[i].high?slots_[i].end:slots_[i].start)==time){if(channel==8||slots_[i].high)channel=i;}
  auto&s=slots_[channel];edge={time,channel,!s.high};popped_advance_=s.advance;popped_dwell_=s.requested_dwell_us;
  s.high=!s.high;if(!s.high){if(s.inhibited)s=Slot{};else{s.pending=false;s.fired=true;++s.cycle;}}return true;
 }
 bool tooth(const Tune&t,const Output&o,std::uint64_t now,unsigned index,unsigned slots,std::uint64_t command_us,std::uint64_t sampled_us){
  return tooth(angle_config(t),o,now,index,slots,command_us,sampled_us);
 }
 bool tooth(const AngleConfig&t,const Output&o,std::uint64_t now,unsigned index,unsigned slots,std::uint64_t command_us,std::uint64_t sampled_us){
  if(failed_)return false;
  if(now<command_us||now-command_us>20000||now<sampled_us||now-sampled_us>20000){cut();return false;}
  if(!o.proposed_enabled()){cut();return true;}
  refresh_control(command_us,sampled_us);
  const bool sequential=t.strategy==Strategy::Sequential;
  const unsigned cycle_slots=slots*(sequential?2:1);const double span=sequential?720:360;
  if(!slots||slots>120||index>=cycle_slots||!range(o.rpm,50,8000)||!range(t.max_dwell_ms,.5,3.5)||!range(o.dwell_ms,.5,t.max_dwell_ms)||(!o.fuel_cut&&!range(o.pulse_ms,.001,15))||!finite(o.advance_deg)||!range(t.tooth1_btdc_deg,0,359)||!firing_order_valid(t.firing_order)||!range(t.injection_end_deg,0,719)||(t.strategy!=Strategy::BatchWasted&&!sequential))return fail(StopReason::BadCommand);
  const double step=360.0/slots;
  if(!initialized_){revolution_=0;angle_=index*step;us_per_degree_=60000000/o.rpm/360;}
  else{
   if(now<=previous_time_)return fail(StopReason::ToothOrder);
   if(index<previous_tooth_)++revolution_;
   const double angle=revolution_*span+index*step,delta=angle-angle_;
   if(delta<=0)return fail(StopReason::ToothOrder);
   us_per_degree_=(now-previous_time_)/delta;angle_=angle;
  }
  auto deadline=[&](double goal,std::uint64_t&result){const double offset=(goal-angle_)*us_per_degree_;if(!finite(offset)||offset<0||offset>3000000)return false;const auto delta=std::uint64_t(std::llround(offset));if(delta>UINT64_MAX-now)return false;result=now+delta;return true;};
  double cylinder_phase[4]{};for(unsigned i=0;i<4;++i)cylinder_phase[t.firing_order[i]-1]=180*i;
  for(unsigned ch=0;ch<8;++ch){auto&s=slots_[ch];const bool coil=ch>=4,enabled=coil?!o.spark_cut:!o.fuel_cut;
   // A normal selective cut cancels future starts. An already active pulse
   // completes at its bounded closing deadline; never discard its low edge.
   // Fault/stale-data cuts use the executor's explicit global-low path.
   if(!enabled){if(s.high)s.inhibited=true;else s=Slot{};continue;}
   if(s.inhibited)continue;
   const auto committed=s;
   double phase=std::fmod(t.tooth1_btdc_deg+(coil?cylinder_phase[ch-4]-(s.high?s.advance:o.advance_deg):sequential?cylinder_phase[ch]+t.injection_end_deg:180),span);if(phase<0)phase+=span;
   if(!s.phase_known){
    s.cycle=static_cast<std::int64_t>(std::floor((angle_-phase)/span))+1;s.phase_known=true;
   }else{
    // Keep the same physical target across the 0/360-degree representation
    // boundary when advance changes; otherwise one firing is skipped.
    const double change=phase-s.previous_phase;
    if(change>span/2)--s.cycle;else if(change< -span/2)++s.cycle;
   }
   s.previous_phase=phase;
   double goal=s.cycle*span+phase;
   if(coil||sequential){
    const auto requested=std::uint64_t(std::llround((coil?o.dwell_ms:o.pulse_ms)*1000));
    if(!coil&&s.high)continue; // An open injector always retains its low edge.
    std::uint64_t end;
    // A new advance demand can arrive too late to charge a full dwell. Keep
    // the previously committed full-dwell firing for this cycle. Applying
    // an impossible update would either undercharge or skip a normal firing.
    const bool reachable=goal>angle_&&deadline(goal,end)&&end>now;
    if(!s.high&&(!reachable||end-now<requested)&&committed.pending&&committed.start>=now&&committed.end>now){s=committed;continue;}
    if(!s.high&&(!reachable||end-now<requested)){
     ++s.cycle;goal+=span;++skipped_initial_;if(!deadline(goal,end))return fail(StopReason::Deadline);
    }
    else if(!reachable)return fail(StopReason::Deadline);
    if(s.high){
     if(end-s.start>std::uint64_t(std::llround(t.max_dwell_ms*1000)))return fail(StopReason::DwellLimit);
     s.end=end;
    }else{
     const auto width=requested;s.requested_dwell_us=coil?requested:0;
     if(end-now<width)return fail(StopReason::Deadline);
     const auto start=end>width?end-width:now;
     if(start<now){s.start=now;++shortened_;}else s.start=start;
     s.end=end;s.pending=true;
    }
    if(!s.high)s.advance=o.advance_deg;
   }else if(!s.high){
    const auto width=std::uint64_t(std::llround(o.pulse_ms*1000));
    if(!width||width>15000)return fail(StopReason::BadCommand);
    if(goal<=angle_)s.start=now;else if(!deadline(goal,s.start))return fail(StopReason::Deadline);
    if(s.start>UINT64_MAX-width)return fail(StopReason::Deadline);
    s.end=s.start+width;s.pending=true;
   }
  }
  previous_tooth_=index;previous_time_=now;initialized_=true;return true;
 }
};
}
