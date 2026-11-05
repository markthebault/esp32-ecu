#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace ecu::transient {
enum class Mode : std::uint8_t {LegacyTps,Off,TpsRate,MapRate};
enum class Apply : std::uint8_t {Multiply,AddReference};
enum class Phase : std::uint8_t {Inactive,Acceleration,Deceleration};
enum class Reason : std::uint8_t {Disabled,Legacy,Inhibited,Priming,BelowThreshold,Accelerating,Decelerating,Expired,Reversed,AcquisitionGap,AcquisitionClock,ControlClock};
inline const char* mode_name(Mode m){switch(m){case Mode::LegacyTps:return "legacy_tps";case Mode::Off:return "off";case Mode::TpsRate:return "tps_rate";case Mode::MapRate:return "map_rate";default:return "unknown";}}
inline const char* apply_name(Apply a){switch(a){case Apply::Multiply:return "multiply";case Apply::AddReference:return "add_reference";default:return "unknown";}}
inline const char* reason_name(Reason r){switch(r){case Reason::Disabled:return "disabled";case Reason::Legacy:return "legacy_tps_decay";case Reason::Inhibited:return "engine_inhibited";case Reason::Priming:return "priming_acquisition_window";case Reason::BelowThreshold:return "below_threshold";case Reason::Accelerating:return "acceleration_hold";case Reason::Decelerating:return "deceleration_hold";case Reason::Expired:return "event_expired";case Reason::Reversed:return "source_reversed";case Reason::AcquisitionGap:return "acquisition_gap";case Reason::AcquisitionClock:return "acquisition_clock_reversed";case Reason::ControlClock:return "control_clock_reversed";default:return "unknown";}}
struct Config {
 Mode mode=Mode::LegacyTps;Apply apply=Apply::Multiply;
 float sample_period_ms=20,tps_threshold_pct_s=40,map_threshold_kpa_s=40,
  tps_min_change_pct=.5f,map_min_change_kpa=.5f,duration_ms=200,max_enrichment_pct=100,
  decel_fuel_pct=100,rpm_taper_start=3000,rpm_taper_end=6000,
  cold_multiplier_pct=100,cold_taper_start_c=0,cold_taper_end_c=70;
 std::array<float,4> tps_rates{0,100,500,1500},tps_added_pct{0,10,30,50},
  map_rates{0,100,500,1500},map_added_pct{0,10,30,50};
};
struct ScalarField {const char*name;float Config::*member;};
inline constexpr ScalarField scalar_fields[]={
 {"sample_period_ms",&Config::sample_period_ms},{"tps_threshold_pct_s",&Config::tps_threshold_pct_s},{"map_threshold_kpa_s",&Config::map_threshold_kpa_s},
 {"tps_min_change_pct",&Config::tps_min_change_pct},{"map_min_change_kpa",&Config::map_min_change_kpa},{"duration_ms",&Config::duration_ms},
 {"max_enrichment_pct",&Config::max_enrichment_pct},{"decel_fuel_pct",&Config::decel_fuel_pct},{"rpm_taper_start",&Config::rpm_taper_start},{"rpm_taper_end",&Config::rpm_taper_end},
 {"cold_multiplier_pct",&Config::cold_multiplier_pct},{"cold_taper_start_c",&Config::cold_taper_start_c},{"cold_taper_end_c",&Config::cold_taper_end_c}};
struct ArrayField {const char*name;std::array<float,4> Config::*member;};
inline constexpr ArrayField array_fields[]={{"tps_rates",&Config::tps_rates},{"tps_added_pct",&Config::tps_added_pct},{"map_rates",&Config::map_rates},{"map_added_pct",&Config::map_added_pct}};
inline bool bounded(float v,float low,float high){return std::isfinite(v)&&v>=low&&v<=high;}
inline bool valid(const Config&c){
 if(static_cast<unsigned>(c.mode)>3||static_cast<unsigned>(c.apply)>1||
    !bounded(c.sample_period_ms,5,100)||!bounded(c.duration_ms,0,2000)||
    !bounded(c.tps_threshold_pct_s,0,2550)||!bounded(c.map_threshold_kpa_s,0,2550)||
    !bounded(c.tps_min_change_pct,0,10)||!bounded(c.map_min_change_kpa,0,10)||
    !bounded(c.max_enrichment_pct,0,650)||!bounded(c.decel_fuel_pct,0,100)||
    !bounded(c.rpm_taper_start,50,8000)||!bounded(c.rpm_taper_end,c.rpm_taper_start,8000)||
    !bounded(c.cold_multiplier_pct,100,255)||!bounded(c.cold_taper_start_c,-40,140)||
    !bounded(c.cold_taper_end_c,c.cold_taper_start_c,140))return false;
 for(unsigned i=0;i<4;++i){
  if(!bounded(c.tps_rates[i],0,2550)||!bounded(c.map_rates[i],0,2550)||
     !bounded(c.tps_added_pct[i],0,255)||!bounded(c.map_added_pct[i],0,255)||
     (i&&(c.tps_rates[i]<=c.tps_rates[i-1]||c.map_rates[i]<=c.map_rates[i-1])))return false;
 }
 return true;
}
inline bool equal(const Config&a,const Config&b){
 return a.mode==b.mode&&a.apply==b.apply&&a.sample_period_ms==b.sample_period_ms&&
 a.tps_threshold_pct_s==b.tps_threshold_pct_s&&a.map_threshold_kpa_s==b.map_threshold_kpa_s&&
 a.tps_min_change_pct==b.tps_min_change_pct&&a.map_min_change_kpa==b.map_min_change_kpa&&
 a.duration_ms==b.duration_ms&&a.max_enrichment_pct==b.max_enrichment_pct&&a.decel_fuel_pct==b.decel_fuel_pct&&
 a.rpm_taper_start==b.rpm_taper_start&&a.rpm_taper_end==b.rpm_taper_end&&
 a.cold_multiplier_pct==b.cold_multiplier_pct&&a.cold_taper_start_c==b.cold_taper_start_c&&a.cold_taper_end_c==b.cold_taper_end_c&&
 a.tps_rates==b.tps_rates&&a.tps_added_pct==b.tps_added_pct&&a.map_rates==b.map_rates&&a.map_added_pct==b.map_added_pct;
}
enum Value : unsigned {TpsDot,MapDot,WindowMs,TriggerDot,CorrectionPct,UnclampedPct,RemainingMs,AddedFuelMg,value_count};
inline constexpr const char* value_names[]={"tps_dot_pct_s","map_dot_kpa_s","window_ms","trigger_dot","correction_pct","unclamped_pct","remaining_ms","added_fuel_mg"};
enum Flag : std::uint16_t {RateValid=1,Active=2,Clamped=4,Retriggered=8,Reversed=16};
struct Output {
 std::array<float,value_count> values{NAN,NAN,NAN,0,100,100,0,0};
 std::uint16_t flags=0;
 Mode mode=Mode::LegacyTps;Apply apply=Apply::Multiply;Phase phase=Phase::Inactive;Reason reason=Reason::Priming;
 bool available=false;
 bool active()const{return phase!=Phase::Inactive;}
 double correction()const{return values[CorrectionPct]/100.0;}
};
static_assert(sizeof(Output)<=40,"Transient diagnostic exceeds its explicit memory budget");
struct Input {double tps_pct=0,map_kpa=0,rpm=0,clt_c=0;std::uint64_t sampled_us=0;bool eligible=false,allow_unknown_map=false;double maximum_map_kpa=110;};
class Controller {
 Config config_;bool configured_=false,control_seen_=false,history_=false;
 std::uint64_t last_control_=0,last_sample_=0,anchor_sample_=0,expires_=0;
 double anchor_tps_=0,anchor_map_=0,peak_=0,correction_=1,unclamped_=1;
 Output observation_;
 void clear(Reason reason){history_=false;expires_=0;peak_=0;correction_=unclamped_=1;observation_=Output{};observation_.reason=reason;}
 void seed(const Input&i){history_=true;last_sample_=anchor_sample_=i.sampled_us;anchor_tps_=i.tps_pct;anchor_map_=i.map_kpa;}
 Output result(const Config&c,std::uint64_t now){
  observation_.mode=c.mode;observation_.apply=c.apply;
  observation_.available=true;
  observation_.values[CorrectionPct]=static_cast<float>(correction_*100);
  observation_.values[UnclampedPct]=static_cast<float>(unclamped_*100);
  observation_.values[RemainingMs]=expires_>now?static_cast<float>((expires_-now)/1000.0):0;
  return observation_;
 }
 static double lookup(const std::array<float,4>&x,const std::array<float,4>&y,double v){
  unsigned i=0;while(i<2&&v>x[i+1])++i;const double f=std::clamp((v-x[i])/(x[i+1]-x[i]),0.0,1.0);return y[i]+(y[i+1]-y[i])*f;
 }
public:
 void reset(){*this=Controller{};}
 Output inhibit(const Config&c,Reason reason=Reason::Inhibited){clear(reason);control_seen_=false;return result(c,0);}
 Output step(const Config&c,const Input&i,std::uint64_t now){
  if(!configured_||!equal(c,config_)){clear(Reason::Priming);control_seen_=false;config_=c;configured_=true;}
  const bool map_valid=std::isfinite(i.map_kpa)&&i.map_kpa>=10&&i.map_kpa<=i.maximum_map_kpa;
  const bool map_optional=i.allow_unknown_map&&c.mode==Mode::TpsRate&&std::isnan(i.map_kpa);
  if(!std::isfinite(i.maximum_map_kpa)||i.maximum_map_kpa<110||i.maximum_map_kpa>400||!valid(c)||!i.eligible||!std::isfinite(i.tps_pct)||(!map_valid&&!map_optional)||!std::isfinite(i.rpm)||!std::isfinite(i.clt_c)||
     i.tps_pct<0||i.tps_pct>100||i.rpm<0||i.rpm>12000||i.clt_c< -40||i.clt_c>140||now<i.sampled_us||now-i.sampled_us>20000)return inhibit(c);
  if(c.mode==Mode::Off||c.mode==Mode::LegacyTps)return inhibit(c,c.mode==Mode::Off?Reason::Disabled:Reason::Legacy);
  if(control_seen_&&now<=last_control_){clear(Reason::ControlClock);control_seen_=false;return result(c,now);}
  control_seen_=true;last_control_=now;
  bool expired=false;
  if(expires_&&now>=expires_){expires_=0;peak_=0;correction_=unclamped_=1;observation_.phase=Phase::Inactive;observation_.flags&=~(Active|Clamped);observation_.reason=Reason::Expired;expired=true;}
  if(!history_){seed(i);return result(c,now);}
  if(i.sampled_us<last_sample_){clear(Reason::AcquisitionClock);return result(c,now);}
  if(i.sampled_us==last_sample_)return result(c,now);
  if(i.sampled_us-last_sample_>20000){clear(Reason::AcquisitionGap);seed(i);return result(c,now);}
  last_sample_=i.sampled_us;
  if(i.sampled_us-anchor_sample_<std::uint64_t(std::llround(c.sample_period_ms*1000)))return result(c,now);
  const double dt=(i.sampled_us-anchor_sample_)/1e6;
  // Gates use the same F32 precision as tune/diagnostic values, so an
  // unobservable double-rounding residue cannot extend an equal-rate hold.
  const double tps_change=static_cast<float>(i.tps_pct-anchor_tps_),map_change=static_cast<float>(i.map_kpa-anchor_map_);
  const double tps=std::abs(tps_change)>c.tps_min_change_pct?std::clamp(tps_change/dt,-2550.0,2550.0):0;
  const double map=std::isfinite(map_change)?(std::abs(map_change)>c.map_min_change_kpa?std::clamp(map_change/dt,-2550.0,2550.0):0):NAN;
  anchor_sample_=i.sampled_us;anchor_tps_=i.tps_pct;anchor_map_=i.map_kpa;
  observation_.values[TpsDot]=static_cast<float>(tps);observation_.values[MapDot]=static_cast<float>(map);observation_.values[WindowMs]=static_cast<float>(dt*1000);
  observation_.flags&=Active|Clamped;observation_.flags|=RateValid;
  const double rate=observation_.values[c.mode==Mode::TpsRate?TpsDot:MapDot],threshold=c.mode==Mode::TpsRate?c.tps_threshold_pct_s:c.map_threshold_kpa_s;
  if(expires_&&rate*observation_.values[TriggerDot]<0){
   expires_=0;peak_=0;correction_=unclamped_=1;observation_.phase=Phase::Inactive;observation_.flags&=~(Active|Clamped);observation_.flags|=Reversed;observation_.reason=Reason::Reversed;
  }
  // Expiring the previous hold must not discard a newly acquired window.
  // Otherwise a coincident control/sample delivery loses a valid event that
  // the same acquisition would start after an expiry-only control poll.
  if(std::abs(rate)<=threshold||c.duration_ms==0){if(!expires_&&observation_.reason!=Reason::Reversed&&!expired)observation_.reason=c.duration_ms==0?Reason::Disabled:Reason::BelowThreshold;return result(c,now);}
  if(expires_&&std::abs(rate)<=peak_)return result(c,now);
  const auto duration=std::uint64_t(std::llround(c.duration_ms*1000));
  if(duration>UINT64_MAX-i.sampled_us){clear(Reason::AcquisitionClock);return result(c,now);}
  const auto deadline=i.sampled_us+duration;
  if(now>=deadline){observation_.reason=Reason::Expired;return result(c,now);}
  if(expires_)observation_.flags|=Retriggered;
  expires_=deadline;peak_=std::abs(rate);observation_.values[TriggerDot]=static_cast<float>(rate);observation_.flags|=Active;
  if(rate<0){observation_.phase=Phase::Deceleration;observation_.reason=Reason::Decelerating;correction_=unclamped_=c.decel_fuel_pct/100.0;observation_.flags&=~Clamped;}
  else{
   double added=c.mode==Mode::TpsRate?lookup(c.tps_rates,c.tps_added_pct,rate):lookup(c.map_rates,c.map_added_pct,rate);
   if(c.rpm_taper_end>c.rpm_taper_start)added*=std::clamp((c.rpm_taper_end-i.rpm)/(c.rpm_taper_end-c.rpm_taper_start),0.0,1.0);
   double cold=1;if(c.cold_taper_end_c>c.cold_taper_start_c)cold+=(c.cold_multiplier_pct/100.0-1)*std::clamp((c.cold_taper_end_c-i.clt_c)/(c.cold_taper_end_c-c.cold_taper_start_c),0.0,1.0);
   added*=cold;unclamped_=1+added/100;correction_=1+std::min(added,double(c.max_enrichment_pct))/100;
   observation_.phase=Phase::Acceleration;observation_.reason=Reason::Accelerating;
   if(added>c.max_enrichment_pct)observation_.flags|=Clamped;else observation_.flags&=~Clamped;
  }
  return result(c,now);
 }
};
} // namespace ecu::transient
