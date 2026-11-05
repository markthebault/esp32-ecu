#pragma once
#include "ecu/boost_runtime.hpp"
#include "ecu/json.hpp"
#include <cstdio>

namespace ecu::boost {
inline cJSON* record_json(const Record&r,bool present=true){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;const bool known=present&&r.available;
 bool ok=cJSON_AddBoolToObject(j,"available",known)&&cJSON_AddBoolToObject(j,"pressure_enabled",present&&r.pressure_enabled)&&cJSON_AddBoolToObject(j,"inhibit_engine",known&&r.inhibit_engine)&&
  cJSON_AddNumberToObject(j,"flags",known?r.flags:0)&&cJSON_AddNumberToObject(j,"reason_code",known?r.reason:0)&&cJSON_AddStringToObject(j,"reason",reason_name(static_cast<Reason>(known?r.reason:0)))&&
  cJSON_AddNumberToObject(j,"mode_code",present?r.mode:0)&&cJSON_AddStringToObject(j,"mode",mode_name(static_cast<Mode>(present?r.mode:0)))&&
  cJSON_AddStringToObject(j,"meaning","Controller proposal and pressure protection decision; no electrical valve measurement");
 for(unsigned n=0;ok&&n<8;++n)ok=known&&std::isfinite(r.values[n])?cJSON_AddNumberToObject(j,value_names[n],r.values[n])!=nullptr:cJSON_AddNullToObject(j,value_names[n])!=nullptr;
 const char*names[]={"pid_updates","overboost_events"};
 for(unsigned n=0;ok&&n<2;++n){char text[24];std::snprintf(text,sizeof(text),"%llu",static_cast<unsigned long long>(known?r.counters[n]:0));ok=cJSON_AddStringToObject(j,names[n],text)!=nullptr;}
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline bool parse_record(const cJSON*j,Record&r,bool present){
 if(!web::keys(j,"|available||pressure_enabled||inhibit_engine||flags||reason_code||reason||mode_code||mode||meaning||duty_pct||demand_pct||target_kpa||feedforward_pct||error_kpa||p_term||i_term||d_term||pid_updates||overboost_events|"))return false;
 Record result;unsigned flags=0,reason=0,mode=0;char text[64];
 if(!web::boolean(j,"available",result.available)||!web::boolean(j,"pressure_enabled",result.pressure_enabled)||!web::boolean(j,"inhibit_engine",result.inhibit_engine)||
    !web::integer(j,"flags",flags)||flags>2047||!web::integer(j,"reason_code",reason)||reason>16||!web::integer(j,"mode_code",mode)||mode>2)return false;
 result.flags=flags;result.reason=static_cast<std::uint8_t>(reason);result.mode=static_cast<std::uint8_t>(mode);
 if(!web::string(j,"reason",text)||std::strcmp(text,reason_name(static_cast<Reason>(reason)))||!web::string(j,"mode",text)||std::strcmp(text,mode_name(static_cast<Mode>(mode))))return false;
 for(unsigned n=0;n<8;++n){const auto*v=cJSON_GetObjectItemCaseSensitive(j,value_names[n]);
  if(cJSON_IsNull(v))result.values[n]=NAN;
  else if(cJSON_IsNumber(v)&&std::isfinite(v->valuedouble)&&std::abs(v->valuedouble)<=FLT_MAX)result.values[n]=static_cast<float>(v->valuedouble);
  else return false;
 }
 const char*names[]={"pid_updates","overboost_events"};
 for(unsigned n=0;n<2;++n){char digits[24];if(!web::string(j,names[n],digits)||!digits[0])return false;std::uint64_t value=0;unsigned count=0;
  for(const char*p=digits;*p;++p){if(*p<'0'||*p>'9'||++count>20||value>(UINT64_MAX-unsigned(*p-'0'))/10)return false;value=value*10+unsigned(*p-'0');}
  result.counters[n]=value;
 }
 if(!valid_record(result,present))return false;
 r=result;return true;
}
} // namespace ecu::boost
