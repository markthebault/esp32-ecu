#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace ecu::idle {
enum class Algorithm:std::uint32_t {OnOff,OpenLoop,ClosedLoop};
inline const char* algorithm_name(Algorithm a){switch(a){case Algorithm::OnOff:return "on_off";case Algorithm::OpenLoop:return "open_loop";default:return "closed_loop";}}
struct Config {
 Algorithm algorithm=Algorithm::ClosedLoop;
 float frequency_hz=100,control_period_ms=100,min_pct=0,max_pct=100;
 float tps_closed_pct=2,tps_hysteresis_pct=.5f,entry_rpm_above=300,exit_rpm_above=500,entry_delay_s=.25f;
 float afterstart_taper_s=2,dashpot_pct=8,dashpot_decay_pct_s=10,slew_pct_s=200,integral_limit_pct=40;
 float kd=0,derivative_filter_s=.1f,fast_idle_temp_c=50,fast_idle_hysteresis_c=5;
 std::array<float,6> coolant_c{-40,0,20,40,70,110},run_pct{65,50,38,30,20,20},crank_pct{75,65,55,45,35,35},target_add_rpm{400,300,200,100,0,0};
};
struct Base {bool enabled=false;double target_rpm=900,kp=.03,ki=.02;};
inline bool bounded(double v,double lo,double hi){return std::isfinite(v)&&v>=lo&&v<=hi;}
inline bool valid(const Config&c,const Base&b){
 if(unsigned(c.algorithm)>2||!bounded(b.target_rpm,600,1500)||!bounded(b.kp,0,double(.2f))||!bounded(b.ki,0,double(.2f))||
    !bounded(c.frequency_hz,50,250)||!bounded(c.control_period_ms,10,250)||!bounded(c.min_pct,0,99)||!bounded(c.max_pct,1,100)||c.min_pct>=c.max_pct||
    !bounded(c.tps_closed_pct,0,10)||!bounded(c.tps_hysteresis_pct,.1f,3)||!bounded(c.entry_rpm_above,0,1000)||!bounded(c.exit_rpm_above,0,1500)||c.exit_rpm_above<c.entry_rpm_above||
    !bounded(c.entry_delay_s,0,5)||!bounded(c.afterstart_taper_s,0,10)||!bounded(c.dashpot_pct,0,30)||!bounded(c.dashpot_decay_pct_s,1,100)||
    !bounded(c.slew_pct_s,1,1000)||!bounded(c.integral_limit_pct,0,100)||!bounded(c.kd,0,.1f)||!bounded(c.derivative_filter_s,.01f,1)||
    !bounded(c.fast_idle_temp_c,0,90)||!bounded(c.fast_idle_hysteresis_c,1,15))return false;
 if(c.algorithm==Algorithm::OnOff&&c.max_pct!=100)return false;
 for(unsigned i=0;i<6;++i){
  if(!bounded(c.coolant_c[i],-40,140)||(i&&c.coolant_c[i]<=c.coolant_c[i-1])||!bounded(c.run_pct[i],c.min_pct,c.max_pct)||!bounded(c.crank_pct[i],c.min_pct,c.max_pct)||!bounded(c.target_add_rpm[i],-500,1000)||!bounded(b.target_rpm+c.target_add_rpm[i],600,2500))return false;
 }
 return true;
}
inline double lookup(const std::array<float,6>&x,const std::array<float,6>&y,double v){
 if(v<=x.front())return y.front();
 for(unsigned i=1;i<6;++i)if(v<=x[i])return y[i-1]+(y[i]-y[i-1])*(v-x[i-1])/(x[i]-x[i-1]);
 return y.back();
}
enum class State:std::uint8_t {Disabled,Stopped,Cranking,Taper,OpenLoop,Waiting,ClosedLoop,Throttle,Dashpot,OnOff,Fault};
enum class Reason:std::uint8_t {None,Disabled,Stopped,Input,Stale,Clock,EngineFault,Throttle,Speed,EntryDelay,Overrun,Supply,Configuration};
inline const char* state_name(State s){switch(s){case State::Disabled:return "disabled";case State::Stopped:return "stopped";case State::Cranking:return "cranking";case State::Taper:return "crank_to_run_taper";case State::OpenLoop:return "open_loop";case State::Waiting:return "waiting";case State::ClosedLoop:return "closed_loop";case State::Throttle:return "throttle_open";case State::Dashpot:return "dashpot";case State::OnOff:return "on_off";default:return "fault";}}
inline const char* reason_name(Reason r){switch(r){case Reason::None:return "none";case Reason::Disabled:return "disabled";case Reason::Stopped:return "engine_stopped";case Reason::Input:return "invalid_input";case Reason::Stale:return "stale_input";case Reason::Clock:return "control_clock";case Reason::EngineFault:return "engine_fault";case Reason::Throttle:return "throttle_open";case Reason::Speed:return "above_entry_speed";case Reason::EntryDelay:return "entry_delay";case Reason::Overrun:return "overrun_cut";case Reason::Supply:return "valve_supply_out_of_range";default:return "invalid_configuration";}}
enum Flag:std::uint32_t {Enabled=1,InputValid=2,Closed=4,Crank=8,LowLimit=16,HighLimit=32,SlewLimit=64,IntegralHeld=128};
struct Input {double rpm=0,tps_pct=0,clt_c=85,battery_v=14;std::uint64_t sampled_us=0;bool valid=false,running=false,cranking=false,overrun=false,engine_fault=false;};
struct Output {
 double duty_pct=0,target_rpm=0,feedforward_pct=0,p_term=0,i_term=0,d_term=0;
 std::uint64_t pid_updates=0;std::uint32_t flags=0;
 State state=State::Disabled;Reason reason=Reason::Disabled;
};
class Controller {
 bool seen_=false,was_cranking_=false,throttle_=true,closed_=false,waiting_=false,fast_=false,pid_seen_=false,integral_held_=false;
 std::uint64_t last_=0,run_start_=0,entry_start_=0,pid_at_=0,updates_=0;
 double duty_=0,integral_=0,derivative_=0,last_pid_rpm_=0,dashpot_=0,last_p_=0,last_d_=0,crank_duty_=0;
 void clear_loop(){closed_=waiting_=pid_seen_=integral_held_=false;integral_=derivative_=last_p_=last_d_=0;}
 void clear(){clear_loop();was_cranking_=fast_=false;throttle_=true;run_start_=entry_start_=pid_at_=0;duty_=dashpot_=crank_duty_=0;}
public:
 void reset(){*this=Controller{};}
 Output step(const Config&c,const Base&b,const Input&in,std::uint64_t now){
  Output out;out.pid_updates=updates_;out.flags=b.enabled?std::uint32_t(Enabled):0U;
  const double dt=seen_&&now>=last_?(now-last_)/1e6:0;
  const bool clock=(!seen_||now>last_)&&dt<=.1;last_=now;seen_=true;
  auto stop=[&](State state,Reason reason){clear();out.state=state;out.reason=reason;return out;};
  if(!valid(c,b))return stop(State::Fault,Reason::Configuration);
  if(!b.enabled)return stop(State::Disabled,Reason::Disabled);
  if(!clock)return stop(State::Fault,Reason::Clock);
  if(!in.valid||!bounded(in.rpm,0,12000)||!bounded(in.tps_pct,0,100)||!bounded(in.clt_c,-40,140))return stop(State::Fault,Reason::Input);
  if(now<in.sampled_us||now-in.sampled_us>20000)return stop(State::Fault,Reason::Stale);
  if(!bounded(in.battery_v,9,16))return stop(State::Fault,Reason::Supply);
  out.flags|=InputValid;
  if(in.engine_fault)return stop(State::Fault,Reason::EngineFault);
  if(!in.running&&!in.cranking)return stop(State::Stopped,Reason::Stopped);
  if(in.overrun)return stop(State::Waiting,Reason::Overrun);
  out.target_rpm=b.target_rpm+lookup(c.coolant_c,c.target_add_rpm,in.clt_c);
  const double feedforward=lookup(c.coolant_c,c.run_pct,in.clt_c);
  if(throttle_){if(in.tps_pct<=c.tps_closed_pct)throttle_=false;}
  else if(in.tps_pct>c.tps_closed_pct+c.tps_hysteresis_pct)throttle_=true;
  if(throttle_){clear_loop();dashpot_=c.dashpot_pct;duty_=0;was_cranking_=false;out.state=State::Throttle;out.reason=Reason::Throttle;return out;}
  if(c.algorithm==Algorithm::OnOff){
   clear_loop();was_cranking_=false;
   if(in.clt_c<c.fast_idle_temp_c)fast_=true;else if(in.clt_c>=c.fast_idle_temp_c+c.fast_idle_hysteresis_c)fast_=false;
   duty_=fast_?100:0;out.duty_pct=duty_;out.feedforward_pct=duty_;out.state=State::OnOff;out.reason=Reason::None;return out;
  }
  if(in.cranking){
   clear_loop();was_cranking_=true;crank_duty_=lookup(c.coolant_c,c.crank_pct,in.clt_c);duty_=crank_duty_;dashpot_=0;
   out.duty_pct=duty_;out.feedforward_pct=duty_;out.flags|=Crank;out.state=State::Cranking;out.reason=Reason::None;return out;
  }
  if(was_cranking_){run_start_=now;was_cranking_=false;}
  double ff=feedforward;
  const bool taper=run_start_&&c.afterstart_taper_s>0&&now>=run_start_&&(now-run_start_)/1e6<c.afterstart_taper_s;
  if(taper)ff=crank_duty_+(feedforward-crank_duty_)*(now-run_start_)/(c.afterstart_taper_s*1e6);
  dashpot_=std::max(0.0,dashpot_-c.dashpot_decay_pct_s*dt);ff=std::clamp(ff+dashpot_,double(c.min_pct),double(c.max_pct));
  out.feedforward_pct=ff;out.reason=Reason::None;
  const bool speed=in.rpm<=out.target_rpm+(closed_?c.exit_rpm_above:c.entry_rpm_above);
  const bool eligible=c.algorithm==Algorithm::ClosedLoop&&!taper&&dashpot_==0&&speed;
  if(!eligible){
   clear_loop();out.state=taper?State::Taper:dashpot_>0?State::Dashpot:State::OpenLoop;
   if(c.algorithm==Algorithm::ClosedLoop&&!speed){out.state=State::Waiting;out.reason=Reason::Speed;}
  }else if(!closed_){
   if(!waiting_){entry_start_=now;waiting_=true;}
   if(now-entry_start_>=std::uint64_t(std::llround(c.entry_delay_s*1e6))){
    closed_=true;waiting_=false;pid_seen_=false;
    // Retain the last executed demand across entry instead of a P-step.
    integral_=duty_>0?std::clamp(duty_-ff-b.kp*(out.target_rpm-in.rpm),-double(c.integral_limit_pct),double(c.integral_limit_pct)):0;
   }else{out.state=State::Waiting;out.reason=Reason::EntryDelay;}
  }
  double desired=ff;
  if(closed_){
   out.state=State::ClosedLoop;out.reason=Reason::None;out.flags|=Closed;
   const auto period=std::uint64_t(std::llround(c.control_period_ms*1000));
   if(!pid_seen_||now-pid_at_>=period){
    const double elapsed=pid_seen_?(now-pid_at_)/1e6:0;
    if(pid_seen_&&elapsed>0){const double raw=(in.rpm-last_pid_rpm_)/elapsed;const double alpha=1-std::exp(-elapsed/c.derivative_filter_s);derivative_+=alpha*(raw-derivative_);}
    last_p_=b.kp*(out.target_rpm-in.rpm);last_d_=-c.kd*derivative_;
    const double candidate=std::clamp(integral_+b.ki*(out.target_rpm-in.rpm)*elapsed,-double(c.integral_limit_pct),double(c.integral_limit_pct));
    const double trial=ff+last_p_+candidate+last_d_;const double limited=std::clamp(trial,double(c.min_pct),double(c.max_pct));
    const double slew=pid_seen_?c.slew_pct_s*elapsed:0;
    const double achievable=std::clamp(limited,std::max(0.0,duty_-slew),std::min(100.0,duty_+slew));
    const double error=out.target_rpm-in.rpm;
    integral_held_=(trial>achievable&&error>0)||(trial<achievable&&error<0);
    if(!integral_held_)integral_=candidate;
    else{
     // Admit the part of an I step that reaches the achievable boundary.
     // Discarding the whole step can deadlock a pure-I loop forever when one
     // increment is larger than the available slew or saturation headroom.
     const double current=ff+last_p_+integral_+last_d_;
     const double delta=candidate-integral_;
     const double admitted=delta>0?std::min(delta,std::max(0.0,achievable-current)):std::max(delta,std::min(0.0,achievable-current));
     integral_=std::clamp(integral_+admitted,-double(c.integral_limit_pct),double(c.integral_limit_pct));
    }
    pid_at_=now;last_pid_rpm_=in.rpm;pid_seen_=true;if(updates_!=UINT64_MAX)++updates_;
   }
   desired=ff+last_p_+integral_+last_d_;if(integral_held_)out.flags|=IntegralHeld;
  }
  out.p_term=closed_?last_p_:0;out.i_term=closed_?integral_:0;out.d_term=closed_?last_d_:0;
  if(desired<c.min_pct)out.flags|=LowLimit;else if(desired>c.max_pct||duty_>c.max_pct)out.flags|=HighLimit;
  const double bounded_duty=std::clamp(desired,double(c.min_pct),double(c.max_pct));
  const double slew=c.slew_pct_s*dt;const double next=std::min(double(c.max_pct),std::clamp(bounded_duty,std::max(0.0,duty_-slew),std::min(100.0,duty_+slew)));
  if(next!=bounded_duty)out.flags|=SlewLimit;
  duty_=next;out.duty_pct=duty_;out.pid_updates=updates_;return out;
 }
};
} // namespace ecu::idle
