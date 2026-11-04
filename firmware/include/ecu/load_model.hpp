#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

// Independent table coordinates and pressure normalization. No actuator code.
namespace ecu::load {
enum class Source:std::uint8_t {Map,Tps,PressureRatio,FollowFuel};
enum class Axis:std::uint8_t {MapKpa,TpsPercent,PressureRatioPercent};
enum class Pressure:std::uint8_t {None,MapReference,MapBaro};
enum class AuxRole:std::uint8_t {PostcatMonitor,Emap,Baro};
enum class BaroSource:std::uint8_t {Fixed,Aux};
enum class Afr:std::uint8_t {Off,Target,Measured};
enum class AfrState:std::uint8_t {Off,Target,StartDelay,Cranking,WidebandUnavailable,Measured,InvalidTarget,ClockUnavailable};
enum class Reason:std::uint8_t {Unavailable,Ready,InvalidConfig,RequiredMap,RequiredTps,RequiredEmap,RequiredBaro,KnownOverpressure};
struct Config {
 Source fuel_source=Source::Map,spark_source=Source::Map,lambda_source=Source::FollowFuel,trim_source=Source::FollowFuel;
 Pressure pressure=Pressure::MapReference;AuxRole aux_role=AuxRole::PostcatMonitor;BaroSource baro_source=BaroSource::Fixed;
 Axis ve_axis=Axis::MapKpa,spark_axis=Axis::MapKpa,lambda_axis=Axis::MapKpa,trim_axis=Axis::MapKpa;
 Afr afr=Afr::Target;float fixed_baro_kpa=100,afr_delay_s=10;
};
inline Source resolve(Source s,const Config&c){return s==Source::FollowFuel?c.fuel_source:s;}
inline Axis axis(Source s,const Config&c){return static_cast<Axis>(resolve(s,c));}
inline const char* source_name(Source s){switch(s){case Source::Map:return "map";case Source::Tps:return "tps";case Source::PressureRatio:return "imap_emap";case Source::FollowFuel:return "follow_fuel";default:return "unknown";}}
inline const char* axis_name(Axis a){switch(a){case Axis::MapKpa:return "map_kpa";case Axis::TpsPercent:return "tps_pct";case Axis::PressureRatioPercent:return "imap_emap_pct";default:return "unknown";}}
inline const char* axis_unit(Axis a){return a==Axis::MapKpa?"kPa":a==Axis::TpsPercent?"% TPS":a==Axis::PressureRatioPercent?"% IMAP/EMAP":"unknown";}
inline const char* pressure_name(Pressure p){switch(p){case Pressure::None:return "none";case Pressure::MapReference:return "map_100kpa";case Pressure::MapBaro:return "map_baro";default:return "unknown";}}
inline const char* aux_name(AuxRole r){switch(r){case AuxRole::PostcatMonitor:return "postcat_monitor";case AuxRole::Emap:return "emap";case AuxRole::Baro:return "baro";default:return "unknown";}}
inline const char* baro_name(BaroSource s){return s==BaroSource::Fixed?"fixed":s==BaroSource::Aux?"aux":"unknown";}
inline const char* afr_name(Afr a){return a==Afr::Off?"off":a==Afr::Target?"target":a==Afr::Measured?"measured":"unknown";}
inline const char* afr_state_name(AfrState s){switch(s){case AfrState::Off:return "off";case AfrState::Target:return "target_incorporation";case AfrState::StartDelay:return "running_delay";case AfrState::Cranking:return "cranking_neutral";case AfrState::WidebandUnavailable:return "wideband_unavailable";case AfrState::Measured:return "measured_ratio";case AfrState::InvalidTarget:return "invalid_target";case AfrState::ClockUnavailable:return "running_clock_unavailable";default:return "unknown";}}
inline const char* reason_name(Reason r){switch(r){case Reason::Unavailable:return "unavailable";case Reason::Ready:return "ready";case Reason::InvalidConfig:return "invalid_configuration";case Reason::RequiredMap:return "required_map_unavailable";case Reason::RequiredTps:return "required_tps_unavailable";case Reason::RequiredEmap:return "required_emap_unavailable";case Reason::RequiredBaro:return "required_baro_unavailable";case Reason::KnownOverpressure:return "known_map_above_na_limit";default:return "unknown";}}
struct Requirements {bool map=false,emap=false,baro=false;bool aux()const{return emap||baro;}};
inline Requirements requirements(const Config&c,bool trims_enabled,bool map_transient=false,bool ego_enabled=false){
 Requirements r;r.map=c.pressure!=Pressure::None||map_transient;
 const Source sources[]={c.fuel_source,c.spark_source,c.lambda_source,c.trim_source};
 for(unsigned i=0;i<4;++i){if((i==3&&!trims_enabled)||(i==2&&c.afr==Afr::Off&&!ego_enabled))continue;const auto s=resolve(sources[i],c);r.map|=s==Source::Map||s==Source::PressureRatio;r.emap|=s==Source::PressureRatio;}
 r.baro=c.pressure==Pressure::MapBaro&&c.baro_source==BaroSource::Aux;return r;
}
inline bool valid(const Config&c,bool trims_enabled=false,bool ego_enabled=false){
 if(static_cast<unsigned>(c.fuel_source)>2||static_cast<unsigned>(c.spark_source)>2||static_cast<unsigned>(c.lambda_source)>3||static_cast<unsigned>(c.trim_source)>3||
    static_cast<unsigned>(c.pressure)>2||static_cast<unsigned>(c.aux_role)>2||static_cast<unsigned>(c.baro_source)>1||static_cast<unsigned>(c.afr)>2||!std::isfinite(c.fixed_baro_kpa)||c.fixed_baro_kpa<50||c.fixed_baro_kpa>110||!std::isfinite(c.afr_delay_s)||c.afr_delay_s<0||c.afr_delay_s>120)return false;
 if(c.ve_axis!=axis(c.fuel_source,c)||c.spark_axis!=axis(c.spark_source,c)||c.lambda_axis!=axis(c.lambda_source,c)||c.trim_axis!=axis(c.trim_source,c))return false;
 const auto r=requirements(c,trims_enabled,false,ego_enabled);
 return !(r.emap&&c.aux_role!=AuxRole::Emap)&&!(r.baro&&c.aux_role!=AuxRole::Baro);
}
inline double axis_min(Axis a){return a==Axis::MapKpa?5:0;}
inline double axis_max(Axis a){return a==Axis::MapKpa?110:a==Axis::TpsPercent?100:600;}
enum Value:unsigned {FuelLoad,SparkLoad,LambdaLoad,TrimLoad,PressureFactor,BaroKpa,EmapKpa,AuxKpa,AfrFactor,value_count};
inline constexpr const char*value_names[]={"fuel_load","spark_load","lambda_load","trim_load","pressure_factor","baro_kpa","emap_kpa","aux_kpa","afr_factor"};
enum Flag:std::uint16_t {ArithmeticValid=1,MapRequired=2,AuxRequired=4,MapCalibrated=8,MapInRange=16,AuxCalibrated=32,AuxInRange=64,ManualBaro=128,PressureGuardAvailable=256,ZeroBaseFuel=512,AccelRatioUnavailable=1024,AfrWaiting=2048,MeasuredAfrActive=4096};
constexpr unsigned afr_state_shift=13;constexpr std::uint16_t afr_state_mask=0xe000;
struct Observation {
 std::array<float,value_count> values{NAN,NAN,NAN,NAN,NAN,NAN,NAN,NAN,NAN};
 std::uint16_t flags=0;Source fuel=Source::Map,spark=Source::Map,lambda=Source::Map,trim=Source::Map;
 Pressure pressure=Pressure::MapReference;AuxRole aux_role=AuxRole::PostcatMonitor;BaroSource baro_source=BaroSource::Fixed;
 Afr afr=Afr::Target;Reason reason=Reason::Unavailable;bool available=false;
 AfrState afr_state()const{return static_cast<AfrState>((flags>>afr_state_shift)&7);}
};
static_assert(sizeof(Observation)<=48,"Load observation exceeds its explicit RAM budget");
struct Input {double map_kpa=NAN,tps_pct=NAN,aux_kpa=NAN;bool map_qualified=false,aux_qualified=false,trims_enabled=false,map_transient=false,ego_enabled=false,extra_map=false,extra_emap=false;};
struct Evaluation {
 Observation observation;
 // Calculations retain double input precision; F32 diagnostics are not used
 // as lookup coordinates. This preserves the original MAP arithmetic.
 std::array<double,4> coordinates{NAN,NAN,NAN,NAN};double fuel_pressure_kpa=NAN;
 bool ok()const{return observation.reason==Reason::Ready;}
};
inline bool in_range(double v,double lo,double hi){return std::isfinite(v)&&v>=lo&&v<=hi;}
inline Evaluation evaluate(const Config&c,const Input&i){
 Evaluation e;auto&o=e.observation;o.available=true;o.fuel=c.fuel_source;o.spark=c.spark_source;o.lambda=resolve(c.lambda_source,c);o.trim=resolve(c.trim_source,c);o.pressure=c.pressure;o.aux_role=c.aux_role;o.baro_source=c.baro_source;o.afr=c.afr;
 if(!valid(c,i.trims_enabled,i.ego_enabled)){o.reason=Reason::InvalidConfig;return e;}
 auto needs=requirements(c,i.trims_enabled,i.map_transient,i.ego_enabled);
 needs.map|=i.extra_map||i.extra_emap;needs.emap|=i.extra_emap;
 if(needs.map)o.flags|=MapRequired;
 if(needs.aux())o.flags|=AuxRequired;
 const bool map_known=i.map_qualified&&std::isfinite(i.map_kpa),map_valid=map_known&&in_range(i.map_kpa,10,110),tps_valid=in_range(i.tps_pct,0,100);
 const bool aux_known=i.aux_qualified&&std::isfinite(i.aux_kpa)&&c.aux_role!=AuxRole::PostcatMonitor;
 const bool aux_valid=aux_known&&in_range(i.aux_kpa,c.aux_role==AuxRole::Emap?20:50,c.aux_role==AuxRole::Emap?500:110);
 if(map_known)o.flags|=MapCalibrated;
 if(map_valid)o.flags|=MapInRange;
 if(map_valid||(map_known&&i.map_kpa>110))o.flags|=PressureGuardAvailable;
 if(aux_known){o.flags|=AuxCalibrated;o.values[AuxKpa]=static_cast<float>(i.aux_kpa);}if(aux_valid)o.flags|=AuxInRange;
 if(aux_valid&&c.aux_role==AuxRole::Emap)o.values[EmapKpa]=static_cast<float>(i.aux_kpa);
 double baro=NAN;
 if(c.pressure==Pressure::MapBaro){
  if(c.baro_source==BaroSource::Fixed){baro=c.fixed_baro_kpa;o.flags|=ManualBaro;}
  else if(aux_valid&&c.aux_role==AuxRole::Baro)baro=i.aux_kpa;
  o.values[BaroKpa]=static_cast<float>(baro);
 }
 // Even optional MAP cannot hide a confirmed pressure above the NA limit.
 if(map_known&&i.map_kpa>110){o.reason=Reason::KnownOverpressure;return e;}
 if(needs.map&&!map_valid){o.reason=Reason::RequiredMap;return e;}
 if(needs.emap&&!(aux_valid&&c.aux_role==AuxRole::Emap)){o.reason=Reason::RequiredEmap;return e;}
 if(needs.baro&&!std::isfinite(baro)){o.reason=Reason::RequiredBaro;return e;}
 const Source sources[]={o.fuel,o.spark,o.lambda,o.trim};
 for(unsigned n=0;n<4;++n){
  if(sources[n]==Source::Map&&map_valid)e.coordinates[n]=i.map_kpa;
  else if(sources[n]==Source::Tps&&tps_valid)e.coordinates[n]=i.tps_pct;
  else if(sources[n]==Source::PressureRatio&&map_valid&&aux_valid&&c.aux_role==AuxRole::Emap)e.coordinates[n]=100*i.map_kpa/i.aux_kpa;
  const bool active=n==3?i.trims_enabled:n==2?(c.afr!=Afr::Off||i.ego_enabled):true;
  if(!std::isfinite(e.coordinates[n])&&active){o.reason=sources[n]==Source::Tps?Reason::RequiredTps:Reason::RequiredMap;return e;}
  o.values[n]=static_cast<float>(e.coordinates[n]);
 }
 e.fuel_pressure_kpa=c.pressure==Pressure::None?100:c.pressure==Pressure::MapReference?i.map_kpa:100*i.map_kpa/baro;
 o.values[PressureFactor]=static_cast<float>(e.fuel_pressure_kpa/100);o.flags|=ArithmeticValid;o.reason=Reason::Ready;return e;
}
inline double afr_factor(Observation&o,const Config&c,double target,double measured,bool ready,bool cranking,double running_s){
 o.flags&=~(AfrWaiting|MeasuredAfrActive|afr_state_mask);double factor=1;auto state=AfrState::Off;
 if(c.afr==Afr::Off){o.values[AfrFactor]=1;return 1;}
 // Tables carry F32 cells; bilinear interpolation retains F64 precision and
 // can exceed a constant endpoint by an F64 rounding residue. Qualify at the
 // declared F32 precision without changing the value used in fuel arithmetic.
 const bool target_ok=std::isfinite(target)&&target>0&&target<2&&static_cast<float>(target)>=.75f&&static_cast<float>(target)<=1.2f;
 if(!target_ok){o.flags&=~ArithmeticValid;o.flags|=static_cast<unsigned>(AfrState::InvalidTarget)<<afr_state_shift;o.reason=Reason::InvalidConfig;o.values[AfrFactor]=NAN;return NAN;}
 if(c.afr==Afr::Target){factor=1/target;state=AfrState::Target;}
 if(c.afr==Afr::Measured){
  if(cranking)state=AfrState::Cranking;
  else if(!std::isfinite(running_s)||running_s<0)state=AfrState::ClockUnavailable;
  else if(running_s<std::llround(double(c.afr_delay_s)*1e6)/1e6)state=AfrState::StartDelay;
  else if(!ready||!in_range(measured,.65,1.5))state=AfrState::WidebandUnavailable;
  else{factor=measured/target;o.flags|=MeasuredAfrActive;state=AfrState::Measured;}
  if(state!=AfrState::Measured)o.flags|=AfrWaiting;
 }
 o.flags|=static_cast<unsigned>(state)<<afr_state_shift;
 o.values[AfrFactor]=static_cast<float>(factor);return factor;
}
} // namespace ecu::load
