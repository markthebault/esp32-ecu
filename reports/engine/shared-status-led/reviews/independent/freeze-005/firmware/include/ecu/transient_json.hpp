#pragma once
#include "ecu/transient_enrichment.hpp"
#include "cJSON.h"
#include "ecu/json.hpp"
namespace ecu::transient {
inline bool parse_config(const cJSON*j,Config&c){
 if(!web::keys(j,"|mode||apply||sample_period_ms||tps_threshold_pct_s||map_threshold_kpa_s||tps_min_change_pct||map_min_change_kpa||duration_ms||max_enrichment_pct||decel_fuel_pct||rpm_taper_start||rpm_taper_end||cold_multiplier_pct||cold_taper_start_c||cold_taper_end_c||tps_rates||tps_added_pct||map_rates||map_added_pct|"))return false;
 char mode[24]{},apply[24]{};if(!web::string(j,"mode",mode)||!web::string(j,"apply",apply))return false;
 bool found=false;for(unsigned i=0;i<4;++i)if(!std::strcmp(mode,mode_name(static_cast<Mode>(i)))){c.mode=static_cast<Mode>(i);found=true;}if(!found)return false;
 found=false;for(unsigned i=0;i<2;++i)if(!std::strcmp(apply,apply_name(static_cast<Apply>(i)))){c.apply=static_cast<Apply>(i);found=true;}if(!found)return false;
 for(auto field:scalar_fields){double value;if(!web::number(j,field.name,value)||std::abs(value)>1e6)return false;c.*(field.member)=static_cast<float>(value);}
 for(auto field:array_fields){const auto*a=cJSON_GetObjectItemCaseSensitive(j,field.name);if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)!=4)return false;
  for(unsigned i=0;i<4;++i){const auto*v=cJSON_GetArrayItem(a,i);if(!cJSON_IsNumber(v)||!std::isfinite(v->valuedouble)||std::abs(v->valuedouble)>1e6)return false;(c.*(field.member))[i]=static_cast<float>(v->valuedouble);}}
 return valid(c);
}
inline cJSON* config_document(const Config&c){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;bool ok=cJSON_AddStringToObject(j,"mode",mode_name(c.mode))&&cJSON_AddStringToObject(j,"apply",apply_name(c.apply));
 for(auto field:scalar_fields)if(ok)ok=cJSON_AddNumberToObject(j,field.name,c.*(field.member));
 for(auto field:array_fields)if(ok){const auto&values=c.*(field.member);auto*a=cJSON_CreateFloatArray(values.data(),values.size());if(!a||!cJSON_AddItemToObject(j,field.name,a)){cJSON_Delete(a);ok=false;}}
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* observation_json(const Output&o,bool present=true){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 const bool known=present&&o.available;
 bool ok=cJSON_AddBoolToObject(j,"available",known)&&cJSON_AddStringToObject(j,"mode",mode_name(o.mode))&&
  cJSON_AddStringToObject(j,"apply",apply_name(o.apply))&&cJSON_AddNumberToObject(j,"mode_code",static_cast<unsigned>(o.mode))&&
  cJSON_AddNumberToObject(j,"apply_code",static_cast<unsigned>(o.apply))&&cJSON_AddNumberToObject(j,"phase_code",static_cast<unsigned>(o.phase))&&
  cJSON_AddStringToObject(j,"reason",reason_name(o.reason))&&cJSON_AddNumberToObject(j,"reason_code",static_cast<unsigned>(o.reason))&&
  cJSON_AddNumberToObject(j,"flags",o.flags)&&cJSON_AddStringToObject(j,"rate_clock",o.mode==Mode::LegacyTps?"control_evaluation":"sensor_acquisition_window")&&
  cJSON_AddStringToObject(j,"meaning","Proposed transient dose terms; effective total dose ratio is proposals.accel. No electrical measurement.");
 for(unsigned i=0;ok&&i<value_count;++i)ok=known&&std::isfinite(o.values[i])?cJSON_AddNumberToObject(j,value_names[i],o.values[i])!=nullptr:cJSON_AddNullToObject(j,value_names[i])!=nullptr;
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
