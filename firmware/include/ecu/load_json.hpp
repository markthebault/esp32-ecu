#pragma once
#include "ecu/load_model.hpp"
#include "ecu/json.hpp"
#include <utility>
#include <initializer_list>
#include <cfloat>
#include <type_traits>
namespace ecu::load {
struct SourceField {const char* name;Source Config::*member;};
struct AxisField {const char* name;Axis Config::*member;};
inline constexpr SourceField source_fields[]={{"fuel_source",&Config::fuel_source},{"spark_source",&Config::spark_source},{"lambda_source",&Config::lambda_source},{"trim_source",&Config::trim_source}};
inline constexpr AxisField axis_fields[]={{"ve_axis",&Config::ve_axis},{"spark_axis",&Config::spark_axis},{"lambda_axis",&Config::lambda_axis},{"trim_axis",&Config::trim_axis}};
template<class E>bool parse_enum(const cJSON*j,const char*name,E&value,std::initializer_list<std::pair<const char*,E>> allowed){
 char text[32]{};if(!web::string(j,name,text))return false;
 for(const auto&v:allowed)if(!std::strcmp(text,v.first)){value=v.second;return true;}
 return false;
}
inline bool parse_config(const cJSON*j,Config&c,bool trims_enabled=false){
 if(!web::keys(j,"|fuel_source||spark_source||lambda_source||trim_source||pressure||aux_role||baro_source||ve_axis||spark_axis||lambda_axis||trim_axis||afr||fixed_baro_kpa||afr_delay_s|"))return false;
 for(const auto&f:source_fields)if(!parse_enum(j,f.name,c.*(f.member),{{"map",Source::Map},{"tps",Source::Tps},{"imap_emap",Source::PressureRatio},{"follow_fuel",Source::FollowFuel}}))return false;
 for(const auto&f:axis_fields)if(!parse_enum(j,f.name,c.*(f.member),{{"map_kpa",Axis::MapKpa},{"tps_pct",Axis::TpsPercent},{"imap_emap_pct",Axis::PressureRatioPercent}}))return false;
 if(!parse_enum(j,"pressure",c.pressure,{{"none",Pressure::None},{"map_100kpa",Pressure::MapReference},{"map_baro",Pressure::MapBaro}})||
    !parse_enum(j,"aux_role",c.aux_role,{{"postcat_monitor",AuxRole::PostcatMonitor},{"emap",AuxRole::Emap},{"baro",AuxRole::Baro}})||
    !parse_enum(j,"baro_source",c.baro_source,{{"fixed",BaroSource::Fixed},{"aux",BaroSource::Aux}})||
    !parse_enum(j,"afr",c.afr,{{"off",Afr::Off},{"target",Afr::Target},{"measured",Afr::Measured}}))return false;
 double baro,delay;if(!web::number(j,"fixed_baro_kpa",baro)||!web::number(j,"afr_delay_s",delay)||!in_range(baro,50,110)||!in_range(delay,0,120))return false;
 c.fixed_baro_kpa=static_cast<float>(baro);c.afr_delay_s=static_cast<float>(delay);return valid(c,trims_enabled);
}
inline cJSON* config_document(const Config&c){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;bool ok=true;
 for(const auto&f:source_fields)if(ok)ok=cJSON_AddStringToObject(j,f.name,source_name(c.*(f.member)))!=nullptr;
 for(const auto&f:axis_fields)if(ok)ok=cJSON_AddStringToObject(j,f.name,axis_name(c.*(f.member)))!=nullptr;
 ok=ok&&cJSON_AddStringToObject(j,"pressure",pressure_name(c.pressure))&&cJSON_AddStringToObject(j,"aux_role",aux_name(c.aux_role))&&
    cJSON_AddStringToObject(j,"baro_source",baro_name(c.baro_source))&&cJSON_AddStringToObject(j,"afr",afr_name(c.afr))&&
    cJSON_AddNumberToObject(j,"fixed_baro_kpa",c.fixed_baro_kpa)&&cJSON_AddNumberToObject(j,"afr_delay_s",c.afr_delay_s);
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* observation_json(const Observation&o,bool present=true){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;const bool known=present&&o.available;
 const bool afr_known=known&&std::isfinite(o.values[AfrFactor]);
 bool ok=cJSON_AddBoolToObject(j,"available",known)&&cJSON_AddNumberToObject(j,"flags",o.flags)&&
  cJSON_AddStringToObject(j,"reason",reason_name(o.reason))&&cJSON_AddNumberToObject(j,"reason_code",static_cast<unsigned>(o.reason))&&
  cJSON_AddStringToObject(j,"afr_state",afr_known?afr_state_name(o.afr_state()):"not_evaluated")&&cJSON_AddNumberToObject(j,"afr_state_code",afr_known?static_cast<unsigned>(o.afr_state()):255);
 const Source sources[]={o.fuel,o.spark,o.lambda,o.trim};const char*names[]={"fuel_source","spark_source","lambda_source","trim_source"};
 const char*codes[]={"fuel_source_code","spark_source_code","lambda_source_code","trim_source_code"};
 for(unsigned i=0;ok&&i<4;++i)ok=cJSON_AddStringToObject(j,names[i],source_name(sources[i]))&&cJSON_AddNumberToObject(j,codes[i],static_cast<unsigned>(sources[i]));
 ok=ok&&cJSON_AddStringToObject(j,"pressure",pressure_name(o.pressure))&&cJSON_AddNumberToObject(j,"pressure_code",static_cast<unsigned>(o.pressure))&&
  cJSON_AddStringToObject(j,"aux_role",aux_name(o.aux_role))&&cJSON_AddNumberToObject(j,"aux_role_code",static_cast<unsigned>(o.aux_role))&&
  cJSON_AddStringToObject(j,"baro_source",baro_name(o.baro_source))&&cJSON_AddNumberToObject(j,"baro_source_code",static_cast<unsigned>(o.baro_source))&&
  cJSON_AddStringToObject(j,"afr",afr_name(o.afr))&&cJSON_AddNumberToObject(j,"afr_code",static_cast<unsigned>(o.afr))&&
  cJSON_AddStringToObject(j,"meaning","Table coordinates and modeled fuel basis, not measured air mass. Fixed baro is manual. Undefined effective ratios remain unknown.");
 for(unsigned i=0;ok&&i<value_count;++i)ok=known&&std::isfinite(o.values[i])?cJSON_AddNumberToObject(j,value_names[i],o.values[i])!=nullptr:cJSON_AddNullToObject(j,value_names[i])!=nullptr;
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
// Strict observation-fixture boundary. This never applies configuration or
// produces control inputs; absent legacy observations stay unavailable.
inline bool parse_observation(const cJSON*j,Observation&o,bool present){
 if(!web::keys(j,"|available||flags||reason||reason_code||afr_state||afr_state_code||fuel_source||fuel_source_code||spark_source||spark_source_code||lambda_source||lambda_source_code||trim_source||trim_source_code||pressure||pressure_code||aux_role||aux_role_code||baro_source||baro_source_code||afr||afr_code||meaning||fuel_load||spark_load||lambda_load||trim_load||pressure_factor||baro_kpa||emap_kpa||aux_kpa||afr_factor|"))return false;
 Observation r;unsigned flags=0,reason=0,state=0;
 if(!web::boolean(j,"available",r.available)||(r.available&&!present)||!web::integer(j,"flags",flags)||flags>UINT16_MAX||!web::integer(j,"reason_code",reason)||reason>8||!web::integer(j,"afr_state_code",state))return false;
 r.flags=static_cast<std::uint16_t>(flags);r.reason=static_cast<Reason>(reason);
 auto code=[&](const char*key,const char*name,unsigned max,auto&field,auto label){
  unsigned n=0;char text[48]{};if(!web::integer(j,key,n)||n>max||!web::string(j,name,text))return false;
  using E=std::decay_t<decltype(field)>;field=static_cast<E>(n);return !std::strcmp(text,label(field));
 };
 if(!code("fuel_source_code","fuel_source",2,r.fuel,source_name)||!code("spark_source_code","spark_source",2,r.spark,source_name)||
    !code("lambda_source_code","lambda_source",2,r.lambda,source_name)||!code("trim_source_code","trim_source",2,r.trim,source_name)||
    !code("pressure_code","pressure",2,r.pressure,pressure_name)||!code("aux_role_code","aux_role",2,r.aux_role,aux_name)||
    !code("baro_source_code","baro_source",1,r.baro_source,baro_name)||!code("afr_code","afr",2,r.afr,afr_name))return false;
 char text[48]{};if(!web::string(j,"reason",text)||std::strcmp(text,reason_name(r.reason)))return false;
 for(unsigned i=0;i<value_count;++i){
  const auto*v=cJSON_GetObjectItemCaseSensitive(j,value_names[i]);
  if(cJSON_IsNull(v))r.values[i]=NAN;
  else if(r.available&&cJSON_IsNumber(v)&&std::isfinite(v->valuedouble)&&std::abs(v->valuedouble)<=FLT_MAX)r.values[i]=static_cast<float>(v->valuedouble);
  else return false;
 }
 const bool evaluated=r.available&&std::isfinite(r.values[AfrFactor]);
 if(state!=(evaluated?static_cast<unsigned>(r.afr_state()):255)||!web::string(j,"afr_state",text)||std::strcmp(text,evaluated?afr_state_name(r.afr_state()):"not_evaluated"))return false;
 if(evaluated&&r.values[AfrFactor]<0)return false;
 if((r.flags&ArithmeticValid)&&r.available&&(!std::isfinite(r.values[FuelLoad])||!std::isfinite(r.values[SparkLoad])||!std::isfinite(r.values[PressureFactor])||r.values[PressureFactor]<=0))return false;
 o=r;return true;
}
} // namespace ecu::load
