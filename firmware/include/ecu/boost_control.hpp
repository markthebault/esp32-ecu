#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

// Portable development core. No pin, timer, vehicle or engine output is
// configured here. Pressure-envelope/engine/target/UI integration is separate.
namespace ecu::boost {
enum class Mode:std::uint8_t {Off,OpenLoop,ClosedLoop};
enum class Activation:std::uint8_t {Barometric,Fixed};
inline const char* mode_name(Mode m){switch(m){case Mode::Off:return "off";case Mode::OpenLoop:return "open_loop";case Mode::ClosedLoop:return "closed_loop";default:return "unknown";}}
inline bool bounded(double v,double lo,double hi){return std::isfinite(v)&&v>=lo&&v<=hi;}
constexpr unsigned bins=8;
struct Table {
 std::array<float,bins> rpm{500,1000,1500,2000,3000,4000,6000,8000};
 std::array<float,bins> axis{0,5,10,20,40,60,80,100};
 std::array<float,bins*bins> cells{}; // Row-major: axis rows, RPM columns.
};
struct Config {
 // Pressure protection may be enabled with the solenoid controller Off.
 // A valve mode requires protection; legacy NA operation stays separate.
 bool pressure_enabled=false;
 Mode mode=Mode::Off;Activation activation=Activation::Barometric;
 float maximum_map_kpa=300,cut_kpa=220,cut_hysteresis_kpa=10,recovery_ms=250;
 float frequency_hz=25,control_period_ms=100,min_pct=0,max_pct=90;
 float minimum_rpm=800,minimum_tps_pct=5,activation_kpa=120,activation_hysteresis_kpa=2,inactive_pct=0;
 float kp=.5f,ki=.1f,kd=0,integral_limit_pct=40,derivative_filter_s=.1f,slew_pct_s=100;
 Table open_duty{},target{},feedforward{};
 Config(){
  target.cells.fill(150);
  feedforward.axis={50,75,100,125,150,200,250,300};
 }
};
inline bool table_valid(const Table&t,double axis_lo,double axis_hi,double cell_lo,double cell_hi){
 for(unsigned n=0;n<bins;++n){
  if(!bounded(t.rpm[n],100,10000)||!bounded(t.axis[n],axis_lo,axis_hi)||
     (n&&(t.rpm[n]<=t.rpm[n-1]||t.axis[n]<=t.axis[n-1])))return false;
 }
 for(auto value:t.cells)if(!bounded(value,cell_lo,cell_hi))return false;
 return true;
}
inline bool valid(const Config&c){
 if(unsigned(c.mode)>2||unsigned(c.activation)>1||(c.mode!=Mode::Off&&!c.pressure_enabled))return false;
 if(!bounded(c.maximum_map_kpa,110,400)||!bounded(c.cut_kpa,100,c.maximum_map_kpa)||
    !bounded(c.cut_hysteresis_kpa,1,50)||c.cut_kpa-c.cut_hysteresis_kpa<50||!bounded(c.recovery_ms,0,5000)||
    !bounded(c.frequency_hz,10,50)||!bounded(c.control_period_ms,20,250)||
    !bounded(c.min_pct,0,99)||!bounded(c.max_pct,1,100)||c.min_pct>=c.max_pct||
    !bounded(c.minimum_rpm,500,4000)||!bounded(c.minimum_tps_pct,0,100)||
    !bounded(c.activation_kpa,50,c.cut_kpa)||!bounded(c.activation_hysteresis_kpa,1,20)||!bounded(c.inactive_pct,0,100)||
    !bounded(c.kp,0,10)||!bounded(c.ki,0,10)||!bounded(c.kd,0,10)||
    !bounded(c.integral_limit_pct,0,100)||!bounded(c.derivative_filter_s,0,2)||!bounded(c.slew_pct_s,1,2000))return false;
 return table_valid(c.open_duty,0,100,0,100)&&table_valid(c.target,0,100,50,c.cut_kpa-c.cut_hysteresis_kpa)&&
        table_valid(c.feedforward,50,400,0,100);
}
inline double lookup(const Table&t,double rpm,double axis){
 unsigned x=0,y=0;
 while(x+2<bins&&rpm>=t.rpm[x+1])++x;
 while(y+2<bins&&axis>=t.axis[y+1])++y;
 const double fx=std::clamp((rpm-t.rpm[x])/(t.rpm[x+1]-t.rpm[x]),0.,1.);
 const double fy=std::clamp((axis-t.axis[y])/(t.axis[y+1]-t.axis[y]),0.,1.);
 const double a=t.cells[y*bins+x]+(t.cells[y*bins+x+1]-t.cells[y*bins+x])*fx;
 const double b=t.cells[(y+1)*bins+x]+(t.cells[(y+1)*bins+x+1]-t.cells[(y+1)*bins+x])*fx;
 return a+(b-a)*fy;
}
enum class Reason:std::uint8_t {Disabled,Ready,Configuration,Clock,Stale,Map,Throttle,Baro,Stopped,Cranking,EngineFault,Overrun,Activation,TargetBelowAmbient,Overboost,Recovery,PressureOnly};
inline const char* reason_name(Reason r){switch(r){
 case Reason::Disabled:return "disabled";case Reason::Ready:return "ready";case Reason::Configuration:return "invalid_configuration";
 case Reason::Clock:return "control_clock";case Reason::Stale:return "stale_input";case Reason::Map:return "map_unavailable";
 case Reason::Throttle:return "throttle_gate";case Reason::Baro:return "baro_unavailable";case Reason::Stopped:return "stopped_or_below_rpm";
 case Reason::Cranking:return "cranking";case Reason::EngineFault:return "engine_fault";case Reason::Overrun:return "overrun";
 case Reason::Activation:return "below_activation";case Reason::TargetBelowAmbient:return "target_not_above_ambient";
 case Reason::Overboost:return "overboost";case Reason::Recovery:return "overboost_recovery";case Reason::PressureOnly:return "pressure_protection_only";
 default:return "unknown";
}}
enum Flag:std::uint32_t {Enabled=1,PressureValid=2,ValveAllowed=4,PidUpdated=8,LowLimited=16,HighLimited=32,SlewLimited=64,IntegralHeld=128,OverboostLatched=256,RecoveryWaiting=512,NoNewSample=1024};
struct Input {
 double rpm=0,map_kpa=0,tps_pct=0,baro_kpa=100;
 std::uint64_t sampled_us=0;
 bool map_qualified=false,tps_qualified=false,baro_qualified=false;
 bool running=false,cranking=false,engine_fault=false,overrun=false;
};
struct Output {
 double duty_pct=0,demand_pct=0,target_kpa=NAN,feedforward_pct=NAN,error_kpa=NAN,p_term=0,i_term=0,d_term=0;
 std::uint64_t pid_updates=0,overboost_events=0;
 std::uint32_t flags=0;Reason reason=Reason::Disabled;
 bool inhibit_engine=false;
};
class Controller {
 bool seen_=false,sample_seen_=false,overboost_=false,recovering_=false,active_=false,pid_seen_=false;
 std::uint64_t last_=0,last_sampled_=0,recovery_at_=0,pid_at_=0,pid_sampled_=0,updates_=0,events_=0;
 double duty_=0,demand_=0,integral_=0,derivative_=0,last_map_=0,p_=0,d_=0;
 void clear_loop(){active_=pid_seen_=false;duty_=demand_=integral_=derivative_=p_=d_=0;}
public:
 void reset(){*this=Controller{};}
 Output step(const Config&c,const Input&in,std::uint64_t now){
  Output o;o.pid_updates=updates_;o.overboost_events=events_;
  const double dt=seen_&&now>=last_?(now-last_)/1e6:0;
  const bool clock=(!seen_||now>last_)&&dt<=.1;
  last_=now;seen_=true;
  auto stop=[&](Reason reason,bool inhibit=false){
   clear_loop();o.reason=reason;o.inhibit_engine=inhibit;
   o.flags&=~ValveAllowed;
   if(overboost_)o.flags|=OverboostLatched;
   o.overboost_events=events_;return o;
  };
  if(!valid(c))return stop(Reason::Configuration,true);
  if(!c.pressure_enabled){overboost_=recovering_=false;return stop(Reason::Disabled);}
  o.flags|=Enabled;
  // Invalid or discontinuous observations cannot clear a pressure latch.
  if(!clock){recovering_=false;return stop(Reason::Clock,true);}
  if(now<in.sampled_us||now-in.sampled_us>20000){recovering_=false;return stop(Reason::Stale,true);}
  if(sample_seen_&&in.sampled_us<last_sampled_){recovering_=false;return stop(Reason::Clock,true);}
  last_sampled_=in.sampled_us;sample_seen_=true;
  if(!in.map_qualified||!bounded(in.map_kpa,10,c.maximum_map_kpa)){
   recovering_=false;
   // A qualified finite sample above the envelope still establishes a high
   // pressure witness. It must never become a release observation.
   if(in.map_qualified&&std::isfinite(in.map_kpa)&&in.map_kpa>c.cut_kpa&&!overboost_){overboost_=true;++events_;}
   return stop(Reason::Map,true);
  }
  o.flags|=PressureValid;
  if(in.map_kpa>c.cut_kpa){
   if(!overboost_){overboost_=true;++events_;}
   recovering_=false;return stop(Reason::Overboost,true);
  }
  if(overboost_){
   if(in.map_kpa<=c.cut_kpa-c.cut_hysteresis_kpa){
    if(!recovering_){recovering_=true;recovery_at_=now;}
    if(now-recovery_at_>=static_cast<std::uint64_t>(std::llround(double(c.recovery_ms)*1000))){overboost_=recovering_=false;}
   }else recovering_=false;
   if(overboost_){o.flags|=RecoveryWaiting;return stop(Reason::Recovery,true);}
  }
  if(c.mode==Mode::Off)return stop(Reason::PressureOnly);
  if(in.engine_fault)return stop(Reason::EngineFault);
  if(!bounded(in.rpm,0,12000)||!in.running||in.rpm<c.minimum_rpm)return stop(Reason::Stopped);
  if(in.cranking)return stop(Reason::Cranking);
  if(in.overrun)return stop(Reason::Overrun);
  if(!in.tps_qualified||!bounded(in.tps_pct,0,100)||in.tps_pct<c.minimum_tps_pct)return stop(Reason::Throttle);
  o.flags|=ValveAllowed;
  if(c.mode==Mode::OpenLoop){
   pid_seen_=false;integral_=derivative_=p_=d_=0;
   demand_=lookup(c.open_duty,in.rpm,in.tps_pct);o.feedforward_pct=demand_;
  }else{
   if(!in.baro_qualified||!bounded(in.baro_kpa,50,110))return stop(Reason::Baro,true);
   o.target_kpa=lookup(c.target,in.rpm,in.tps_pct);o.error_kpa=o.target_kpa-in.map_kpa;
   if(o.target_kpa<=in.baro_kpa)return stop(Reason::TargetBelowAmbient);
   const double threshold=c.activation==Activation::Barometric?in.baro_kpa:c.activation_kpa;
   if(active_){if(in.map_kpa<threshold-c.activation_hysteresis_kpa)active_=false;}
   else if(in.map_kpa>=threshold)active_=true;
   if(!active_){
    clear_loop();o.reason=Reason::Activation;
    // Explicit spool proposal, default zero. Fault/stop paths always use zero.
    o.demand_pct=c.inactive_pct;o.duty_pct=duty_=std::clamp(double(c.inactive_pct),0.,double(c.max_pct));
    return o;
   }
   o.feedforward_pct=lookup(c.feedforward,in.rpm,o.target_kpa);
   const auto period=static_cast<std::uint64_t>(std::llround(double(c.control_period_ms)*1000));
   if(!pid_seen_||now-pid_at_>=period){
    if(pid_seen_&&in.sampled_us<=pid_sampled_)o.flags|=NoNewSample;
    else{
     const double sample_dt=pid_seen_?(in.sampled_us-pid_sampled_)/1e6:0;
     p_=c.kp*o.error_kpa;
     if(sample_dt>0){
      const double measured=-(in.map_kpa-last_map_)/sample_dt;
      const double alpha=c.derivative_filter_s>0?sample_dt/(c.derivative_filter_s+sample_dt):1;
      derivative_+=alpha*(measured-derivative_);
     }else derivative_=0;
     d_=c.kd*derivative_;
     const double candidate=std::clamp(integral_+c.ki*o.error_kpa*sample_dt,-double(c.integral_limit_pct),double(c.integral_limit_pct));
     // Limit the I increment to available output travel over a PID sample
     // interval. Rejecting the entire increment when it exceeds one control
     // tick's slew budget would make a valid pure-I controller stall forever.
     const double base=o.feedforward_pct+p_+d_;
     const double budget=c.slew_pct_s*sample_dt;
     const double lower=std::min(integral_,std::clamp(duty_-budget,double(c.min_pct),double(c.max_pct))-base);
     const double upper=std::max(integral_,std::clamp(duty_+budget,double(c.min_pct),double(c.max_pct))-base);
     integral_=std::clamp(candidate,lower,upper);
     if(integral_!=candidate)o.flags|=IntegralHeld;
     demand_=o.feedforward_pct+p_+integral_+d_;
     pid_at_=now;pid_sampled_=in.sampled_us;last_map_=in.map_kpa;pid_seen_=true;
     o.pid_updates=++updates_;o.flags|=PidUpdated;
    }
   }
  }
  o.demand_pct=demand_;
  const double bounded_duty=std::clamp(demand_,double(c.min_pct),double(c.max_pct));
  if(demand_<c.min_pct)o.flags|=LowLimited;
  if(demand_>c.max_pct)o.flags|=HighLimited;
  const double limited=std::clamp(bounded_duty,duty_-c.slew_pct_s*dt,duty_+c.slew_pct_s*dt);
  if(limited!=bounded_duty)o.flags|=SlewLimited;
  duty_=std::clamp(limited,0.,100.);o.duty_pct=duty_;
  o.p_term=p_;o.i_term=integral_;o.d_term=d_;o.reason=Reason::Ready;return o;
 }
};
} // namespace ecu::boost
