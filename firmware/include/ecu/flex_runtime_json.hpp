#pragma once
#include "ecu/flex_json.hpp"
#include "ecu/flex_runtime.hpp"
#include <cstring>

namespace ecu { namespace flex {
inline constexpr const char* flag_names[]={"required","configuration_match","value_qualified","raw_capture_qualified","control_ok","capture_valid","sample_value_valid","pending_fault","frequency_clamped","temperature_clamped","input_confirmed","corrections_enabled","corrections_valid","spark_bypassed","spark_clamped","zero_factor","available"};
inline constexpr const char* time_names[]={"sample_us","window_start_us","last_edge_us","raw_edges","fault_generation","acknowledged_generation","config_epoch"};
inline bool json_counter(const cJSON*j,const char*key,std::uint64_t&out){
 const auto*v=cJSON_GetObjectItemCaseSensitive(j,key);if(!cJSON_IsString(v)||!v->valuestring||!v->valuestring[0]||(v->valuestring[0]=='0'&&v->valuestring[1]))return false;
 std::uint64_t n=0;unsigned count=0;for(auto*p=v->valuestring;*p;++p){if(*p<'0'||*p>'9'||++count>20||n>(UINT64_MAX-unsigned(*p-'0'))/10)return false;n=n*10+unsigned(*p-'0');}out=n;return true;
}
inline bool parse_record(const cJSON*j,Record&out,bool present){
 if(!web::keys(j,"|source||source_code||reason||reason_code||capture_reason||capture_reason_code||last_fault||last_fault_code||correction_reason||correction_reason_code||required||configuration_match||value_qualified||raw_capture_qualified||control_ok||capture_valid||sample_value_valid||pending_fault||frequency_clamped||temperature_clamped||input_confirmed||corrections_enabled||corrections_valid||spark_bypassed||spark_clamped||zero_factor||available||window_cycles||sample_us||window_start_us||last_edge_us||raw_edges||fault_generation||acknowledged_generation||config_epoch||configuration_revision||capture_calibration||frequency_hz||low_pulse_us||ethanol_pct||fuel_temp_c||unfiltered_ethanol_pct||unfiltered_fuel_temp_c||sample_age_ms||fuel_pct||spark_add_deg||temperature_pct||read_age_ms|"))return false;
 Record r;
 for(unsigned n=0;n<17;++n){bool v=false;if(!web::boolean(j,flag_names[n],v))return false;if(v)r.flags|=1U<<n;}
 if(r.has(Available)&&!present)return false;
 const char*code_names[]={"source","reason","capture_reason","last_fault","correction_reason"};
 std::uint8_t*codes[]={&r.source,&r.reason,&r.capture_reason,&r.last_fault,&r.correction_reason};
 for(unsigned n=0;n<5;++n){char key[32];std::snprintf(key,sizeof(key),"%s_code",code_names[n]);unsigned v=0;if(!web::integer(j,key,v)||v>(n?22U:3U))return false;*codes[n]=static_cast<std::uint8_t>(v);const auto*s=cJSON_GetObjectItemCaseSensitive(j,code_names[n]);if(!cJSON_IsString(s)||std::strcmp(s->valuestring,n?reason_name(static_cast<Reason>(v)):source_name(static_cast<Source>(v))))return false;}
 unsigned cycles=0;if(!web::integer(j,"window_cycles",cycles)||cycles>32||!web::integer(j,"configuration_revision",r.revision))return false;r.window_cycles=static_cast<std::uint8_t>(cycles);
 for(unsigned n=0;n<7;++n)if(!json_counter(j,time_names[n],r.times[n]))return false;
 for(unsigned n=0;n<10;++n){const auto*v=cJSON_GetObjectItemCaseSensitive(j,value_names[n]);if(cJSON_IsNull(v))r.values[n]=NAN;else {if(!cJSON_IsNumber(v)||!range(v->valuedouble,-FLT_MAX,FLT_MAX))return false;r.values[n]=static_cast<float>(v->valuedouble);}}
 const auto*cal=cJSON_GetObjectItemCaseSensitive(j,"capture_calibration");if(!web::keys(cal,"|low_hz||high_hz||fault_hz||tolerance_hz||stale_ms||filter_ms||cycles|")||!web::integer(cal,"cycles",cycles)||cycles>32)return false;r.calibration_cycles=static_cast<std::uint8_t>(cycles);
 for(unsigned n=0;n<6;++n){double v=0;if(!web::number(cal,capture_fields[n].name,v)||!range(v,-FLT_MAX,FLT_MAX))return false;r.calibration[n]=static_cast<float>(v);}
 if(const auto*age=cJSON_GetObjectItemCaseSensitive(j,"read_age_ms")){if(!cJSON_IsNull(age)&&(!cJSON_IsNumber(age)||!range(age->valuedouble,0,UINT32_MAX-1)||std::floor(age->valuedouble)!=age->valuedouble))return false;}
 if(!valid_record(r,present))return false;
 out=r;return true;
}
}} // namespace ecu::flex
