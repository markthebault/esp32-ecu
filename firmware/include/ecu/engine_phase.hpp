#pragma once
#include "ecu/control.hpp"
#include "ecu/engine_scheduler.hpp"

namespace ecu::engine {
// One rising cam edge per four-stroke cycle. This deliberately does not infer
// OEM patterns or recover a lost phase while the shaft is still turning.
// Task context only: floating-point mapping never runs in the capture ISR.
template<std::size_t CylinderCapacity>class BasicPhaseDecoder {
public:
 enum class Reason : std::uint8_t {AwaitingCrank,AwaitingCam,Confirming,Locked,Window,Cycle,TimeOrder,Unmapped,Timeout,CrankLost};
 static const char* reason_name(Reason r){switch(r){
  case Reason::AwaitingCam:return "awaiting_cam";case Reason::Confirming:return "confirming_cam";
  case Reason::Locked:return "phase_locked";case Reason::Window:return "cam_outside_window";
  case Reason::Cycle:return "cam_cycle_mismatch";case Reason::TimeOrder:return "cam_time_order";
  case Reason::Unmapped:return "cam_timestamp_unmapped";case Reason::Timeout:return "cam_timeout";
  case Reason::CrankLost:return "crank_sync_lost";default:return "awaiting_crank";}}
 explicit BasicPhaseDecoder(MissingTooth::Config wheel={60,2,8000},BasicAngleConfig<CylinderCapacity> angle={}):wheel_(wheel),angle_(angle),crank_(wheel){}
 bool valid()const{return crank_.valid()&&strategy_valid(angle_.strategy)&&range(angle_.tooth1_btdc_deg,0,359)&&range(angle_.cam_sync_deg,0,719)&&range(angle_.cam_window_deg,5,45);}
 bool required()const{return angle_.strategy==Strategy::Sequential;}
 bool crank_synced()const{return crank_.synced();}
 bool phase_synced()const{return known_&&!faulted_&&crank_.synced();}
 bool synced()const{return crank_.synced()&&(!required()||phase_synced());}
 bool faulted()const{return faulted_;}
 double rpm()const{return crank_.rpm();}
 unsigned tooth()const{return crank_.tooth();}
 unsigned phase_tooth()const{return crank_.tooth()+(phase_synced()?unsigned((revolution_-parity_+2)%2)*wheel_.slots:0);}
 std::uint64_t stall_timeout()const{return crank_.stall_timeout();}
 std::uint64_t deadline()const{return phase_synced()?deadline_:UINT64_MAX;}
 std::uint64_t losses()const{return losses_;}
 std::uint64_t rejected()const{return rejected_;}
 std::uint64_t accepted()const{return accepted_;}
 std::uint64_t last_cam_us()const{return last_cam_;}
 double cam_error_deg()const{return cam_error_;}
 Reason reason()const{
  if(faulted_)return reason_;
  if(!crank_.synced())return Reason::AwaitingCrank;
  return known_?Reason::Locked:candidate_?Reason::Confirming:Reason::AwaitingCam;
 }
 void reset(){crank_.reset();clear_phase();faulted_=false;reason_=Reason::AwaitingCrank;}
 void invalidate(Reason why){
  if(!required())return;
  if(!faulted_){++losses_;reason_=why;faulted_=true;}
  known_=candidate_=pending_=false;deadline_=UINT64_MAX;
 }
 bool edge(std::uint64_t us,std::uint64_t observed=UINT64_MAX){
  if(!valid())return false;
  if(observed==UINT64_MAX)observed=us;
  if(phase_synced()&&observed>=deadline_)invalidate(Reason::Timeout);
  const bool before=crank_.synced();const bool gap=crank_.edge(us);
  if(!crank_.synced()){
   if(before&&known_)invalidate(Reason::CrankLost);
   clear_history();candidate_=known_=pending_=false;deadline_=UINT64_MAX;return gap;
  }
  if(!history_count_)revolution_=0;
  else if(crank_.tooth()<previous_tooth_)++revolution_;
  previous_tooth_=crank_.tooth();
  const double step=360.0/wheel_.slots;
  const auto sample=Sample{us,revolution_*360.0+crank_.tooth()*step,60000000.0/(rpm()*360)};
  history_[history_next_]=sample;history_next_=(history_next_+1)%history_.size();if(history_count_<history_.size())++history_count_;
  if(phase_synced()){
   // Check the old deadline before extending it with a new speed estimate.
   if(us>=deadline_)invalidate(Reason::Timeout);else update_deadline(sample);
  }
  retry_cam(observed);
  return gap;
 }
 bool cam(std::uint64_t us,std::uint64_t observed=UINT64_MAX){
  if(!valid()||!required()||faulted_||!crank_.synced()||!history_count_)return false;
  if(observed==UINT64_MAX)observed=us;
  if(observed<us||observed-us>1000)return reject(Reason::Unmapped);
  if(phase_synced()&&observed>=deadline_){invalidate(Reason::Timeout);return false;}
  if(pending_){pending_=false;return reject(Reason::TimeOrder);}
  double raw=0;
  if(!map_cam(us,raw)){
   // A timely cam callback may precede timestamp-earlier crank callbacks.
   // Retain one bounded pending edge without delaying crank scheduling.
   const double history_lag_limit=1000+(wheel_.missing+1)*360.0/wheel_.slots*latest().us_per_degree;
   if(us>latest().us&&us-latest().us<=history_lag_limit){pending_=true;pending_us_=us;return false;}
   return reject(Reason::Unmapped);
  }
  return accept_cam(us,raw);
 }
 void tick(std::uint64_t now){
  const bool before=crank_.synced();crank_.tick(now);
  if(!crank_.synced()){
   if(before&&known_)invalidate(Reason::CrankLost);
   clear_history();known_=candidate_=pending_=false;deadline_=UINT64_MAX;
  }else{
   retry_cam(now);
   if(phase_synced()&&now>=deadline_)invalidate(Reason::Timeout);
  }
 }
private:
 bool accept_cam(std::uint64_t us,double raw){
  if((candidate_||known_)&&us<=last_cam_)return reject(Reason::TimeOrder);
  double expected=std::fmod(angle_.tooth1_btdc_deg+angle_.cam_sync_deg,720.0);
  const auto shift=static_cast<std::int64_t>(std::llround((raw-expected)/360));
  const double center=expected+shift*360.0;cam_error_=raw-center;
  if(std::abs(cam_error_)>angle_.cam_window_deg)return reject(Reason::Window);
  if((candidate_||known_)&&shift!=last_shift_+2)return reject(Reason::Cycle);
  const bool confirm=candidate_||known_;candidate_=true;known_=confirm;
  parity_=int((shift%2+2)%2);last_shift_=shift;last_cam_=us;next_center_=center+720;++accepted_;
  if(known_)update_deadline(latest());
  return !faulted_;
 }
 void retry_cam(std::uint64_t now){
  if(!pending_||faulted_||!history_count_)return;
  if(phase_synced()&&now>=deadline_){invalidate(Reason::Timeout);return;}
  if(now>pending_us_&&now-pending_us_>1000){pending_=false;reject(Reason::Unmapped);return;}
  double raw=0;if(map_cam(pending_us_,raw)){const auto us=pending_us_;pending_=false;accept_cam(us,raw);}
 }
 struct Sample {std::uint64_t us=0;double angle=0,us_per_degree=0;};
 const Sample& latest()const{return history_[(history_next_+history_.size()-1)%history_.size()];}
 void clear_history(){history_count_=history_next_=previous_tooth_=0;revolution_=0;}
 void clear_phase(){clear_history();known_=candidate_=pending_=false;last_cam_=pending_us_=0;last_shift_=0;parity_=0;deadline_=UINT64_MAX;cam_error_=next_center_=0;}
 bool reject(Reason why){++rejected_;if(known_)invalidate(why);else{candidate_=false;last_cam_=0;}return false;}
 bool map_cam(std::uint64_t us,double& raw)const{
  // At120 slots/8000RPM, a1ms callback delay spans16 teeth. Keep64 accepted
  // samples, so callbacks may arrive after newer crank captures. Never use
  // a future sample as an earlier revolution's reference.
  const auto first=(history_next_+history_.size()-history_count_)%history_.size();
  const Sample* before=nullptr;
  for(unsigned i=0;i<history_count_;++i){const auto&s=history_[(first+i)%history_.size()];
   if(s.us<=us)before=&s;
   else if(before){raw=before->angle+(s.angle-before->angle)*double(us-before->us)/double(s.us-before->us);return true;}
   else return false;
  }
  if(!before)return false;
  const double delta=double(us-before->us)/before->us_per_degree;
  if(!finite(delta)||delta<0||delta>(wheel_.missing+2)*360.0/wheel_.slots)return false;
  raw=before->angle+delta;return true;
 }
 void update_deadline(const Sample&s){
  // This is an angle-window watchdog projected using the latest decoded
  // speed, plus the target's bounded1ms capture processing allowance. Abrupt
  // deceleration may inhibit conservatively; a fresh sample cannot revive an
  // already expired window. GPTimer independently enforces this deadline.
  const double remaining=next_center_+angle_.cam_window_deg-s.angle;
  const double delta=remaining*s.us_per_degree+1000;
  if(!finite(delta)||delta<=0||delta>3000000||s.us>UINT64_MAX-std::uint64_t(std::ceil(delta))){invalidate(Reason::Timeout);return;}
  deadline_=s.us+std::uint64_t(std::ceil(delta));
 }
 MissingTooth::Config wheel_;BasicAngleConfig<CylinderCapacity> angle_;MissingTooth crank_;
 std::array<Sample,64> history_{};unsigned history_next_=0,history_count_=0,previous_tooth_=0;
 std::int64_t revolution_=0,last_shift_=0;int parity_=0;
 bool candidate_=false,known_=false,faulted_=false,pending_=false;
 Reason reason_=Reason::AwaitingCrank;
 std::uint64_t deadline_=UINT64_MAX,last_cam_=0,pending_us_=0,losses_=0,rejected_=0,accepted_=0;
 double cam_error_=0,next_center_=0;
};
using PhaseDecoder=BasicPhaseDecoder<4>;
using ExpandedPhaseDecoder=BasicPhaseDecoder<8>;
}
