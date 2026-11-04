#pragma once
// Portable acquisition/correction groundwork. No GPIO, timer, engine Tune,
// storage, UI or target producer is connected by this header alone.
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace ecu { namespace flex {
enum class Source:std::uint8_t {Unavailable,TargetCapture,Synthetic};
enum class Reason:std::uint8_t {
 Disabled,Acquiring,Ready,InvalidConfig,Unavailable,RepeatedLevel,
 TimeReversed,Gap,Glitch,Frequency,SensorFault,PulseWidth,Overflow,
 Stale,Future,SourceChanged,ConfigurationChanged
};
inline const char* source_name(Source s){
 switch(s){case Source::Unavailable:return "unavailable";case Source::TargetCapture:return "target_capture";case Source::Synthetic:return "synthetic_edges";default:return "unknown";}
}
inline const char* reason_name(Reason r){switch(r){
 case Reason::Disabled:return "disabled";case Reason::Acquiring:return "acquiring";case Reason::Ready:return "ready";
 case Reason::InvalidConfig:return "invalid_configuration";case Reason::Unavailable:return "unavailable";
 case Reason::RepeatedLevel:return "repeated_level";case Reason::TimeReversed:return "time_reversed";
 case Reason::Gap:return "edge_gap";case Reason::Glitch:return "short_edge_interval";
 case Reason::Frequency:return "frequency_out_of_range";case Reason::SensorFault:return "sensor_fault_frequency";
 case Reason::PulseWidth:return "low_pulse_width_out_of_range";case Reason::Overflow:return "capture_overflow";
 case Reason::Stale:return "stale";case Reason::Future:return "future_edge";
 case Reason::SourceChanged:return "source_changed";case Reason::ConfigurationChanged:return "configuration_changed";
 default:return "unknown";
}}
inline bool range(double v,double low,double high){return std::isfinite(v)&&v>=low&&v<=high;}
inline double bounded(double v,double low,double high){return std::max(low,std::min(high,v));}
struct CaptureConfig {
 float low_hz=50,high_hz=150,fault_hz=170,tolerance_hz=1;
 float stale_ms=250,filter_ms=0;
 std::uint8_t cycles=8;
};
inline bool valid(const CaptureConfig&c){
 return range(c.low_hz,10,180)&&range(c.high_hz,c.low_hz+10,200)&&
  range(c.fault_hz,c.high_hz+5,500)&&range(c.tolerance_hz,0,2)&&
  range(c.stale_ms,250,2000)&&c.stale_ms>=2000./(c.low_hz-c.tolerance_hz)&&
  range(c.filter_ms,0,5000)&&c.cycles>=2&&c.cycles<=32;
}
inline bool same(const CaptureConfig&a,const CaptureConfig&b){return
 a.low_hz==b.low_hz&&a.high_hz==b.high_hz&&a.fault_hz==b.fault_hz&&a.tolerance_hz==b.tolerance_hz&&
 a.stale_ms==b.stale_ms&&a.filter_ms==b.filter_ms&&a.cycles==b.cycles;
}
struct Observation {
 Source source=Source::Unavailable;
 Reason reason=Reason::Unavailable,capture_reason=Reason::Acquiring,last_fault=Reason::Unavailable;
 bool valid=false,pending_fault=false,frequency_clamped=false,temperature_clamped=false;
 std::uint8_t window_cycles=0;
 std::uint64_t sample_us=0,window_start_us=0,last_edge_us=0;
 std::uint64_t edges=0,fault_generation=0,acknowledged_generation=0,config_epoch=1;
 double frequency_hz=NAN,low_pulse_us=NAN,ethanol_pct=NAN,fuel_temp_c=NAN;
 double unfiltered_ethanol_pct=NAN,unfiltered_fuel_temp_c=NAN,age_ms=NAN;
};
class Capture {
 CaptureConfig config_;
 Observation value_;
 bool config_valid_=true,input_seen_=false,seeded_=false,level_=false;
 bool rise_seen_=false,fall_seen_=false,filtered_=false,query_seen_=false;
 std::uint64_t input_us_=0,edge_us_=0,rise_us_=0,fall_us_=0,query_us_=0;
 std::uint64_t sum_period_=0,sum_width_=0,observed_fault_=0;
 std::array<std::uint64_t,32> periods_{},widths_{};
 unsigned count_=0,next_=0;
 bool exhausted_=false;
 void clear_series(){
  seeded_=rise_seen_=fall_seen_=filtered_=false;sum_period_=sum_width_=0;count_=next_=0;
  value_.valid=false;value_.window_cycles=0;value_.ethanol_pct=value_.fuel_temp_c=NAN;
  value_.unfiltered_ethanol_pct=value_.unfiltered_fuel_temp_c=NAN;
  value_.frequency_clamped=value_.temperature_clamped=false;
 }
 void fault(Reason reason){
  clear_series();value_.capture_reason=value_.last_fault=reason;
  if(value_.fault_generation==std::numeric_limits<std::uint64_t>::max())exhausted_=true;
  else ++value_.fault_generation;
 }
 void seed(std::uint64_t now,bool level){
  seeded_=true;level_=level;edge_us_=now;
  if(level){rise_seen_=true;rise_us_=now;fall_seen_=false;}
  else{fall_seen_=true;fall_us_=now;rise_seen_=false;}
 }
 void cycle(std::uint64_t now,std::uint64_t period,std::uint64_t width){
  const double hz=1000000./period;
  value_.frequency_hz=hz;value_.low_pulse_us=double(width);
  if(hz>=config_.fault_hz){fault(Reason::SensorFault);return;}
  if(!range(hz,config_.low_hz-config_.tolerance_hz,config_.high_hz+config_.tolerance_hz)){fault(Reason::Frequency);return;}
  // Fixed GM/Continental pulse-width convention, with2us timestamp tolerance.
  // A low pulse must also fit strictly inside the complete measured cycle.
  if(width>=period||width<998||width>5002){fault(Reason::PulseWidth);return;}
  if(count_==config_.cycles){sum_period_-=periods_[next_];sum_width_-=widths_[next_];}
  else ++count_;
  const auto max=std::numeric_limits<std::uint64_t>::max();
  if(sum_period_>max-period||sum_width_>max-width){fault(Reason::Overflow);return;}
  periods_[next_]=period;widths_[next_]=width;next_=(next_+1)%config_.cycles;
  sum_period_+=period;sum_width_+=width;
  value_.window_cycles=static_cast<std::uint8_t>(count_);
  value_.window_start_us=now-sum_period_;
  value_.frequency_hz=1000000.*count_/sum_period_;value_.low_pulse_us=double(sum_width_)/count_;
  const double raw_ethanol=100*(value_.frequency_hz-config_.low_hz)/(config_.high_hz-config_.low_hz);
  const double raw_temperature=.04125*value_.low_pulse_us-81.25;
  value_.frequency_clamped=raw_ethanol<0||raw_ethanol>100;
  value_.temperature_clamped=raw_temperature< -40||raw_temperature>125;
  value_.unfiltered_ethanol_pct=bounded(raw_ethanol,0,100);
  value_.unfiltered_fuel_temp_c=bounded(raw_temperature,-40,125);
  value_.capture_reason=Reason::Acquiring;
  if(count_<config_.cycles)return;
  const double alpha=!filtered_||config_.filter_ms==0?1:-std::expm1(-double(now-value_.sample_us)/(1000*config_.filter_ms));
  if(!filtered_){value_.ethanol_pct=value_.unfiltered_ethanol_pct;value_.fuel_temp_c=value_.unfiltered_fuel_temp_c;}
  else{value_.ethanol_pct+=(value_.unfiltered_ethanol_pct-value_.ethanol_pct)*alpha;value_.fuel_temp_c+=(value_.unfiltered_fuel_temp_c-value_.fuel_temp_c)*alpha;}
  filtered_=true;value_.sample_us=now;value_.capture_reason=Reason::Ready;
 }
public:
 explicit Capture(const CaptureConfig&config=CaptureConfig{}):config_(config),config_valid_(valid(config)){
  if(!config_valid_)value_.capture_reason=Reason::InvalidConfig;
 }
 const CaptureConfig&config()const{return config_;}
 bool configure(const CaptureConfig&config){
  if(same(config_,config))return false;
  config_=config;config_valid_=valid(config);fault(config_valid_?Reason::ConfigurationChanged:Reason::InvalidConfig);
  if(value_.config_epoch==std::numeric_limits<std::uint64_t>::max())exhausted_=true;else ++value_.config_epoch;
  return true;
 }
 // Caller supplies only genuinely captured edges, after clock-extension and
 // queue-overflow checks. No hardware qualification is implied by Source.
 void edge(std::uint64_t now,bool level,Source source=Source::Synthetic){
  if(value_.edges==std::numeric_limits<std::uint64_t>::max()){exhausted_=true;fault(Reason::Overflow);return;}
  ++value_.edges;
  if(!config_valid_){fault(Reason::InvalidConfig);return;}
  if(source!=Source::TargetCapture&&source!=Source::Synthetic){fault(Reason::Unavailable);return;}
  if(input_seen_&&now<=input_us_){fault(Reason::TimeReversed);return;}
  if(value_.source!=source){
   if(value_.source!=Source::Unavailable)fault(Reason::SourceChanged);
   value_.source=source;value_.frequency_hz=value_.low_pulse_us=NAN;
  }
  if(input_seen_&&now-input_us_>std::uint64_t(std::llround(config_.stale_ms*1000.)))fault(Reason::Gap);
  input_seen_=true;input_us_=now;value_.last_edge_us=now;
  if(!seeded_){seed(now,level);return;}
  if(level==level_){fault(Reason::RepeatedLevel);seed(now,level);return;}
  if(now-edge_us_<50){fault(Reason::Glitch);seed(now,level);return;}
  level_=level;edge_us_=now;
  if(!level){fall_seen_=true;fall_us_=now;return;}
  if(rise_seen_&&fall_seen_){
   const auto previous=rise_us_;cycle(now,now-previous,now-fall_us_);
   // A rejected cycle clears the entire window and seeds a fresh rising edge.
  }
  rise_seen_=true;rise_us_=now;fall_seen_=false;seeded_=true;
 }
 void overflow(){fault(Reason::Overflow);}
 Observation observe(std::uint64_t now){
  if(query_seen_&&now<query_us_)fault(Reason::TimeReversed);
  else{
   query_seen_=true;query_us_=now;
   if(input_seen_&&now<input_us_)fault(Reason::Future);
   else if(config_valid_){
    const auto stale=std::uint64_t(std::llround(config_.stale_ms*1000.));
    const bool old_sample=filtered_&&now>=value_.sample_us&&now-value_.sample_us>stale;
    const bool old_edge=input_seen_&&now>=input_us_&&now-input_us_>stale;
    if((old_sample||old_edge)&&value_.capture_reason!=Reason::Stale)fault(Reason::Stale);
   }
  }
  value_.pending_fault=exhausted_||value_.fault_generation!=value_.acknowledged_generation;
  value_.age_ms=filtered_&&now>=value_.sample_us?double(now-value_.sample_us)/1000:NAN;
  value_.valid=config_valid_&&filtered_&&value_.capture_reason==Reason::Ready&&!value_.pending_fault&&now>=value_.sample_us&&now-value_.sample_us<=std::uint64_t(std::llround(config_.stale_ms*1000.));
  value_.reason=!config_valid_?Reason::InvalidConfig:value_.pending_fault?value_.last_fault:value_.capture_reason;
  if(value_.pending_fault)observed_fault_=value_.fault_generation;
  return value_;
 }
 // ACK only after a completed control observation consumed the invalid sample.
 // A newer fault between observation and ACK cannot be cleared by an old ticket.
 bool acknowledge(std::uint64_t generation){
  if(exhausted_||!generation||generation!=observed_fault_||generation!=value_.fault_generation||generation==value_.acknowledged_generation)return false;
  value_.acknowledged_generation=generation;return true;
 }
};

struct CorrectionConfig {
 bool enabled=false,temperature_enabled=false;
 std::array<float,6> ethanol_bins{{0,20,40,60,80,100}};
 std::array<float,6> fuel_pct{{100,100,100,100,100,100}},spark_deg{};
 std::array<float,6> temperature_c{{-40,0,20,40,80,125}};
 std::array<float,6> temperature_pct{{100,100,100,100,100,100}};
};
template<std::size_t N>inline bool ascending(const std::array<float,N>&a,double low,double high){
 for(unsigned n=0;n<N;++n)if(!range(a[n],low,high)||(n&&a[n]<=a[n-1]))return false;
 return true;
}
inline bool valid(const CorrectionConfig&c){
 if(!ascending(c.ethanol_bins,0,100)||!ascending(c.temperature_c,-40,125)||
  c.ethanol_bins.front()!=0||c.ethanol_bins.back()!=100||c.temperature_c.front()!=-40||c.temperature_c.back()!=125||
  (c.temperature_enabled&&!c.enabled))return false;
 for(unsigned n=0;n<6;++n)if(!range(c.fuel_pct[n],0,255)||!range(c.spark_deg[n],-40,40)||!range(c.temperature_pct[n],0,255))return false;
 return true;
}
inline double lookup(const std::array<float,6>&x,const std::array<float,6>&y,double value){
 unsigned n=0;while(n<4&&value>x[n+1])++n;
 const double fraction=bounded((value-x[n])/(x[n+1]-x[n]),0,1);
 return y[n]+(y[n+1]-y[n])*fraction;
}
struct Corrections {
 Reason reason=Reason::Disabled;bool valid=true,enabled=false;
 double fuel_factor=1,spark_add_deg=0,temperature_factor=1;
};
inline Corrections evaluate(const CorrectionConfig&c,const CaptureConfig&capture,const Observation&o,std::uint64_t now){
 Corrections result;result.enabled=c.enabled;
 if(!valid(c)||!valid(capture)){result.valid=false;result.reason=Reason::InvalidConfig;return result;}
 if(!c.enabled)return result;
 result.valid=false;result.fuel_factor=result.spark_add_deg=result.temperature_factor=NAN;
 if(!o.valid||o.pending_fault){result.reason=o.reason;return result;}
 if(o.source!=Source::TargetCapture&&o.source!=Source::Synthetic){result.reason=Reason::Unavailable;return result;}
 if(now<o.sample_us){result.reason=Reason::Future;return result;}
 if(now-o.sample_us>std::uint64_t(std::llround(capture.stale_ms*1000.))){result.reason=Reason::Stale;return result;}
 if(!range(o.ethanol_pct,0,100)||!range(o.fuel_temp_c,-40,125)){result.reason=Reason::Unavailable;return result;}
 result.fuel_factor=lookup(c.ethanol_bins,c.fuel_pct,o.ethanol_pct)/100;
 result.spark_add_deg=lookup(c.ethanol_bins,c.spark_deg,o.ethanol_pct);
 result.temperature_factor=c.temperature_enabled?lookup(c.temperature_c,c.temperature_pct,o.fuel_temp_c)/100:1;
 result.valid=true;result.reason=Reason::Ready;return result;
}
}} // namespace ecu::flex
