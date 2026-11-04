#pragma once
#include "ecu/load_model.hpp"
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>

// Secondary-table arithmetic and qualified switch selection. This module has
// no I2C/GPIO access. A target producer must supply genuinely observed inputs;
// declaring TargetProtected here does not provide that hardware or producer.
namespace ecu::secondary {
enum class Kind:std::uint8_t {Fuel,Spark};
enum class Mode:std::uint8_t {Off,Multiply,Add,Conditional,Input};
enum class Condition:std::uint8_t {Rpm,Map,Tps,Ethanol};
enum class Cells:std::uint8_t {Absolute,Multiplier,Adder};
enum class InputSource:std::uint8_t {Unavailable,TargetProtected,Synthetic};
inline const char* input_source_name(InputSource s){return s==InputSource::Unavailable?"unavailable":s==InputSource::TargetProtected?"target_protected_input":s==InputSource::Synthetic?"synthetic_input":"unknown";}
enum class Reason:std::uint8_t {
 Disabled,Multiply,Add,ConditionPrimary,ConditionSecondary,InputPrimary,
 InputSecondary,Debouncing,InputUnavailable,InputStale,InputTimeReversed,
 RequiredMap,RequiredTps,RequiredEmap,RequiredEthanol,CrankingBypass,
 InvalidConfig,Arithmetic
};
struct Rule {
 Mode mode=Mode::Off;
 load::Source source=load::Source::Map;
 load::Axis axis=load::Axis::MapKpa;
 Cells cells=Cells::Absolute;
 Condition condition=Condition::Rpm;
 float threshold=3000,debounce_ms=20;
 std::uint8_t input_channel=0;
 bool active_high=true;
};
struct Config {
 Rule fuel,spark;
 Config(){spark.input_channel=1;}
};
inline const char* mode_name(Mode m){switch(m){
 case Mode::Off:return "off";case Mode::Multiply:return "multiply";
 case Mode::Add:return "add";case Mode::Conditional:return "conditional";
 case Mode::Input:return "input";default:return "unknown";
}}
inline const char* cells_name(Cells c){switch(c){
 case Cells::Absolute:return "absolute";case Cells::Multiplier:return "multiplier";
 case Cells::Adder:return "adder";default:return "unknown";
}}
inline const char* condition_name(Condition c){switch(c){
 case Condition::Rpm:return "rpm";case Condition::Map:return "map_kpa";
 case Condition::Tps:return "tps_pct";case Condition::Ethanol:return "ethanol_pct";
 default:return "unknown";
}}
inline const char* reason_name(Reason r){switch(r){
 case Reason::Disabled:return "disabled";case Reason::Multiply:return "multiply";
 case Reason::Add:return "add";case Reason::ConditionPrimary:return "condition_primary";
 case Reason::ConditionSecondary:return "condition_secondary";
 case Reason::InputPrimary:return "input_primary";case Reason::InputSecondary:return "input_secondary";
 case Reason::Debouncing:return "input_initial_qualification";
 case Reason::InputUnavailable:return "input_unavailable";case Reason::InputStale:return "input_stale";
 case Reason::InputTimeReversed:return "input_time_reversed";
 case Reason::RequiredMap:return "required_map_unavailable";
 case Reason::RequiredTps:return "required_tps_unavailable";
 case Reason::RequiredEmap:return "required_emap_unavailable";
 case Reason::RequiredEthanol:return "required_ethanol_unavailable";
 case Reason::CrankingBypass:return "cranking_spark_bypass";
 case Reason::InvalidConfig:return "invalid_configuration";
 case Reason::Arithmetic:return "invalid_arithmetic";default:return "unknown";
}}
inline bool range(double v,double lo,double hi){return std::isfinite(v)&&v>=lo&&v<=hi;}
inline double threshold_max(Condition c){return c==Condition::Rpm?10000:c==Condition::Map?110:100;}
inline Cells expected_cells(Mode m){return m==Mode::Multiply?Cells::Multiplier:m==Mode::Add?Cells::Adder:Cells::Absolute;}
inline double cell_min(Kind k,Cells c){return k==Kind::Fuel||c==Cells::Multiplier?0:c==Cells::Adder?-40:-5;}
inline double cell_max(Kind k,Cells c){return k==Kind::Fuel||c==Cells::Multiplier?255:c==Cells::Adder?70:40;}
inline bool valid(const Rule&r){
 return static_cast<unsigned>(r.mode)<=4&&static_cast<unsigned>(r.source)<=2&&
  static_cast<unsigned>(r.axis)<=2&&r.axis==static_cast<load::Axis>(r.source)&&
  static_cast<unsigned>(r.cells)<=2&&static_cast<unsigned>(r.condition)<=3&&
  range(r.threshold,0,threshold_max(r.condition))&&range(r.debounce_ms,0,500)&&
  r.input_channel<2&&(r.mode==Mode::Off||r.cells==expected_cells(r.mode));
}
inline bool same_rule(const Rule&a,const Rule&b){
 return a.mode==b.mode&&a.source==b.source&&a.axis==b.axis&&a.cells==b.cells&&
  a.condition==b.condition&&a.threshold==b.threshold&&a.debounce_ms==b.debounce_ms&&
  a.input_channel==b.input_channel&&a.active_high==b.active_high;
}
struct Requirements {
 bool map=false,emap=false,ethanol=false;
 std::uint8_t switch_mask=0;
};
// Deliberately qualify every configured source, including a conditionally
// inactive table, before allowing control. A missing dependency never silently
// selects table1. Secondary spark selection alone is bypassed while cranking;
// the static pressure/ethanol dependency contract remains unchanged.
inline Requirements requirements(const Config&c){
 Requirements r;
 for(const auto*p:{&c.fuel,&c.spark}){
  if(p->mode==Mode::Off)continue;
  r.map|=p->source==load::Source::Map||p->source==load::Source::PressureRatio;
  r.emap|=p->source==load::Source::PressureRatio;
  if(p->mode==Mode::Conditional){r.map|=p->condition==Condition::Map;r.ethanol|=p->condition==Condition::Ethanol;}
  if(p->mode==Mode::Input&&p->input_channel<2)r.switch_mask|=1U<<p->input_channel;
 }
 return r;
}
inline bool valid(const Config&c,const load::Config&primary){
 if(!valid(c.fuel)||!valid(c.spark))return false;
 return !requirements(c).emap||primary.aux_role==load::AuxRole::Emap;
}
struct SwitchSample {
 std::uint64_t observed_us=0;
 InputSource source=InputSource::Unavailable;
 bool level=false,valid=false;
};
struct Input {
 double rpm=0,map_kpa=NAN,tps_pct=NAN,emap_kpa=NAN,ethanol_pct=NAN;
 bool map_qualified=false,emap_qualified=false,ethanol_qualified=false;
 std::array<SwitchSample,2> switches{};
};
struct SwitchState {
 Reason reason=Reason::InputUnavailable;
 bool valid=false,level=false,pending=false,pending_level=false;
 InputSource source=InputSource::Unavailable;
 double age_ms=NAN;
};
class SwitchFilter {
 bool observed_=false,qualified_=false,candidate_=false,stable_=false,last_level_=false;
 std::uint64_t candidate_since_=0,last_sample_=0,last_now_=0;
 std::uint64_t debounce_us_=0;
 std::uint8_t channel_=0;
 InputSource source_=InputSource::Unavailable;
public:
 void reset(){*this=SwitchFilter{};}
 SwitchState step(const SwitchSample&s,const Rule&r,std::uint64_t now){
  SwitchState out;out.source=s.source;
  if(!valid(r)||r.mode!=Mode::Input){reset();out.reason=Reason::InvalidConfig;return out;}
  const auto debounce=std::uint64_t(std::llround(double(r.debounce_ms)*1000));
  if(!s.valid||s.source==InputSource::Unavailable||static_cast<unsigned>(s.source)>2){reset();return out;}
  if(now<s.observed_us||(observed_&&now<last_now_)){
   reset();out.reason=Reason::InputTimeReversed;return out;
  }
  out.age_ms=(now-s.observed_us)/1000.;
  if(now-s.observed_us>20000){reset();out.reason=Reason::InputStale;return out;}
  if(observed_&&(channel_!=r.input_channel||debounce_us_!=debounce||source_!=s.source))reset();
  if(observed_&&(s.observed_us<last_sample_||(s.observed_us==last_sample_&&s.level!=last_level_))){
   reset();out.reason=Reason::InputTimeReversed;return out;
  }
  if(!observed_){candidate_=s.level;candidate_since_=s.observed_us;}
  else if(candidate_!=s.level){candidate_=s.level;candidate_since_=s.observed_us;}
  // Qualification advances on observed sample time, never on repeated calls
  // with a held sample. A gap over20ms loses qualification immediately.
  if(observed_&&s.observed_us-last_sample_>20000){qualified_=false;candidate_since_=s.observed_us;}
  observed_=true;last_sample_=s.observed_us;last_level_=s.level;last_now_=now;
  channel_=r.input_channel;debounce_us_=debounce;source_=s.source;
  if(s.observed_us-candidate_since_>=debounce){stable_=candidate_;qualified_=true;}
  out.valid=qualified_;out.level=stable_;out.pending=!qualified_||candidate_!=stable_;out.pending_level=candidate_;
  out.reason=qualified_?Reason::InputPrimary:Reason::Debouncing;
  return out;
 }
};
struct Observation {
 Mode mode=Mode::Off;Cells cells=Cells::Absolute;load::Source source=load::Source::Map;
 Reason reason=Reason::Disabled;InputSource input_source=InputSource::Unavailable;
 Condition condition=Condition::Rpm;load::Axis axis=load::Axis::MapKpa;std::uint8_t input_channel=0;
 bool available=false,evaluated=false,active=false,clamped=false,pending=false,input_qualified=false,input_level=false,pending_level=false,input_valid=false,input_raw=false,active_high=true,valid=false;
 float primary=NAN,secondary=NAN,combined=NAN,coordinate=NAN,condition_value=NAN,input_age_ms=NAN,primary_corrected=NAN,threshold=NAN,debounce_ms=NAN;
 std::uint64_t input_observed_us=0;
};
inline constexpr const char*value_names[]={"primary","primary_corrected","secondary","combined","coordinate","condition_value","input_age_ms","threshold","debounce_ms"};
inline constexpr const char*value_labels[]={"Primary","PrimaryCorrected","Secondary","Combined","Coordinate","ConditionValue","InputAgeMs","Threshold","DebounceMs"};
inline constexpr const char*code_labels[]={"Mode","Cells","Source","Reason","InputSource","Condition","Axis","InputChannel"};
inline constexpr const char*boolean_labels[]={"Available","Evaluated","Active","Clamped","Pending","InputQualified","InputLevel","PendingLevel","InputValid","InputRaw","ActiveHigh","Valid"};
inline constexpr float Observation::*value_members[]={&Observation::primary,&Observation::primary_corrected,&Observation::secondary,&Observation::combined,&Observation::coordinate,&Observation::condition_value,&Observation::input_age_ms,&Observation::threshold,&Observation::debounce_ms};
inline constexpr const char*boolean_names[]={"available","evaluated","active","clamped","pending","input_qualified","input_level","pending_level","input_valid","input_raw","active_high","valid"};
inline constexpr bool Observation::*boolean_members[]={&Observation::available,&Observation::evaluated,&Observation::active,&Observation::clamped,&Observation::pending,&Observation::input_qualified,&Observation::input_level,&Observation::pending_level,&Observation::input_valid,&Observation::input_raw,&Observation::active_high,&Observation::valid};
inline std::uint32_t flags(const Observation&o){
 const bool values[]={o.available,o.evaluated,o.active,o.clamped,o.pending,o.input_qualified,o.input_level,o.pending_level,o.input_valid,o.input_raw,o.active_high,o.valid};
 std::uint32_t result=0;for(unsigned n=0;n<12;++n)if(values[n])result|=1U<<n;
 return result|(std::uint32_t(o.input_channel)<<16)|(std::uint32_t(o.axis)<<20);
}
struct Selection {
 Observation observation;
 double coordinate=NAN;
 bool ok=false;
};
class Controller {
 std::array<SwitchFilter,2> filters_{};
 std::array<Rule,2> rules_{};
 std::array<bool,2> rule_seen_{};
public:
 void reset(){*this=Controller{};}
 Selection select(Kind kind,const Rule&r,const Input&i,std::uint64_t now,bool cranking){
  Selection result;auto&o=result.observation;o.available=true;o.mode=r.mode;o.cells=r.cells;o.source=r.source;
  o.condition=r.condition;o.axis=r.axis;o.input_channel=r.input_channel;o.active_high=r.active_high;o.threshold=r.threshold;o.debounce_ms=r.debounce_ms;
  const unsigned slot=kind==Kind::Fuel?0:1;auto&filter=filters_[slot];
  if(!rule_seen_[slot]||!same_rule(rules_[slot],r))filter.reset();
  rules_[slot]=r;rule_seen_[slot]=true;
  auto fail=[&](Reason reason){o.reason=reason;return result;};
  if(!valid(r)){filter.reset();return fail(Reason::InvalidConfig);}
  auto observe_input=[&](){
   const auto&sample=i.switches[r.input_channel];o.input_observed_us=sample.observed_us;o.input_raw=sample.level;o.input_valid=sample.valid;
   const auto state=filter.step(sample,r,now);
   o.input_source=state.source;o.input_age_ms=static_cast<float>(state.age_ms);o.input_qualified=state.valid;
   o.input_level=state.level;o.pending=state.pending;o.pending_level=state.pending_level;
   return state;
  };
  // Observe every configured input even when another required sensor fails.
  // A simultaneous load fault must not conceal a lost switch qualification.
  SwitchState input_state;
  if(r.mode==Mode::Input)input_state=observe_input();else filter.reset();
  if(r.mode==Mode::Off){result.ok=o.valid=true;return result;}
  if(kind==Kind::Spark&&cranking){
   // Observe the switch while the cranking angle bypasses secondary spark.
   // Crossing into running must not erase an already fresh qualification.
   // Invalid data resets the filter but never selects secondary spark here.
   result.ok=o.valid=true;o.reason=Reason::CrankingBypass;return result;
  }
  if(r.source==load::Source::Map||r.source==load::Source::PressureRatio){
   if(!i.map_qualified||!range(i.map_kpa,10,110))return fail(Reason::RequiredMap);
   result.coordinate=i.map_kpa;
  }else{
   if(!range(i.tps_pct,0,100))return fail(Reason::RequiredTps);
   result.coordinate=i.tps_pct;
  }
  if(r.source==load::Source::PressureRatio){
   if(!i.emap_qualified||!range(i.emap_kpa,20,500))return fail(Reason::RequiredEmap);
   result.coordinate=100*i.map_kpa/i.emap_kpa;
  }
  o.coordinate=static_cast<float>(result.coordinate);
  if(r.mode==Mode::Conditional){
   double value=NAN;
   switch(r.condition){
    case Condition::Rpm:if(range(i.rpm,0,12000))value=i.rpm;break;
    case Condition::Map:if(!i.map_qualified||!range(i.map_kpa,10,110))return fail(Reason::RequiredMap);value=i.map_kpa;break;
    case Condition::Tps:if(!range(i.tps_pct,0,100))return fail(Reason::RequiredTps);value=i.tps_pct;break;
    case Condition::Ethanol:if(!i.ethanol_qualified||!range(i.ethanol_pct,0,100))return fail(Reason::RequiredEthanol);value=i.ethanol_pct;break;
   }
   if(!std::isfinite(value))return fail(Reason::Arithmetic);
   o.condition_value=static_cast<float>(value);o.active=value>r.threshold;
   o.reason=o.active?Reason::ConditionSecondary:Reason::ConditionPrimary;
  }else if(r.mode==Mode::Input){
   const auto&state=input_state;
   if(!state.valid)return fail(state.reason);
   o.condition_value=state.level?1:0;o.active=state.level==r.active_high;
   o.reason=o.active?Reason::InputSecondary:Reason::InputPrimary;
  }else{o.active=true;o.reason=r.mode==Mode::Multiply?Reason::Multiply:Reason::Add;}
  result.ok=o.valid=true;return result;
 }
};
inline double record(Selection&s,double primary,double corrected,double secondary,double combined,double low,double high){
 auto&o=s.observation;
 const auto representable=[](double v){return std::isfinite(v)&&std::abs(v)<=std::numeric_limits<float>::max();};
 if(!s.ok||!representable(primary)||!representable(corrected)||(o.active&&!representable(secondary))||!std::isfinite(combined)){
  s.ok=o.valid=false;o.reason=Reason::Arithmetic;return NAN;
 }
 o.primary=static_cast<float>(primary);o.primary_corrected=static_cast<float>(corrected);
 if(o.active)o.secondary=static_cast<float>(secondary);
 // An inactive rule must preserve the exact historical F64 result, including
 // its old correction order. Diagnostics are never calculation inputs.
 const double bounded=o.active?std::clamp(combined,low,high):combined;
 o.clamped=bounded!=combined;o.combined=static_cast<float>(bounded);o.evaluated=true;return bounded;
}
inline double fuel(Selection&s,double primary,double secondary){
 double result=primary;
 if(s.observation.active){switch(s.observation.mode){
  case Mode::Multiply:result=primary*secondary/100;break;
  case Mode::Add:result=primary+secondary;break;
  case Mode::Conditional:case Mode::Input:result=secondary;break;
  default:s.ok=false;break;
 }}
 return record(s,primary,primary,secondary,result,0,255);
}
inline double spark(Selection&s,double primary_raw,double primary_corrected,double secondary_raw,double retard){
 double result=primary_corrected;
 if(s.observation.active){switch(s.observation.mode){
  case Mode::Multiply:result=primary_corrected*secondary_raw/100;break;
  case Mode::Add:result=primary_corrected+secondary_raw;break;
  case Mode::Conditional:case Mode::Input:result=secondary_raw-retard;break;
  default:s.ok=false;break;
 }}
 return record(s,primary_raw,primary_corrected,secondary_raw,result,-5,40);
}
} // namespace ecu::secondary
