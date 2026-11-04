#pragma once
#include "ecu/flex_engine.hpp"
#include "ecu/json.hpp"
#include <cstdio>
namespace ecu { namespace flex {
struct CaptureField {const char*name;float CaptureConfig::*member;};
static constexpr CaptureField capture_fields[]={{"low_hz",&CaptureConfig::low_hz},{"high_hz",&CaptureConfig::high_hz},{"fault_hz",&CaptureConfig::fault_hz},{"tolerance_hz",&CaptureConfig::tolerance_hz},{"stale_ms",&CaptureConfig::stale_ms},{"filter_ms",&CaptureConfig::filter_ms}};
struct CorrectionArray {const char*name;std::array<float,6> CorrectionConfig::*member;};
static constexpr CorrectionArray correction_arrays[]={{"ethanol_bins",&CorrectionConfig::ethanol_bins},{"fuel_pct",&CorrectionConfig::fuel_pct},{"spark_deg",&CorrectionConfig::spark_deg},{"temperature_c",&CorrectionConfig::temperature_c},{"temperature_pct",&CorrectionConfig::temperature_pct}};
inline bool parse_config(const cJSON*j,Config&c){
 if(!web::keys(j,"|input_confirmed||capture||correction|")||!web::boolean(j,"input_confirmed",c.input_confirmed))return false;
 const auto*a=cJSON_GetObjectItemCaseSensitive(j,"capture");unsigned cycles=0;
 if(!web::keys(a,"|low_hz||high_hz||fault_hz||tolerance_hz||stale_ms||filter_ms||cycles|")||!web::integer(a,"cycles",cycles)||cycles>255)return false;
 c.capture.cycles=static_cast<std::uint8_t>(cycles);
 for(auto field:capture_fields){double value;if(!web::number(a,field.name,value)||std::abs(value)>1e6)return false;c.capture.*field.member=static_cast<float>(value);}
 const auto*r=cJSON_GetObjectItemCaseSensitive(j,"correction");
 if(!web::keys(r,"|enabled||temperature_enabled||ethanol_bins||fuel_pct||spark_deg||temperature_c||temperature_pct|")||!web::boolean(r,"enabled",c.correction.enabled)||!web::boolean(r,"temperature_enabled",c.correction.temperature_enabled))return false;
 for(auto field:correction_arrays){const auto*array=cJSON_GetObjectItemCaseSensitive(r,field.name);if(!cJSON_IsArray(array)||cJSON_GetArraySize(array)!=6)return false;
  for(unsigned n=0;n<6;++n){auto*value=cJSON_GetArrayItem(array,n);if(!cJSON_IsNumber(value)||!range(value->valuedouble,-1e6,1e6))return false;(c.correction.*field.member)[n]=static_cast<float>(value->valuedouble);}
 }
 return valid(c);
}
inline cJSON* config_document(const Config&c){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 bool ok=cJSON_AddBoolToObject(j,"input_confirmed",c.input_confirmed);auto*a=ok?cJSON_AddObjectToObject(j,"capture"):nullptr;if(!a)ok=false;
 for(auto field:capture_fields)ok=ok&&cJSON_AddNumberToObject(a,field.name,c.capture.*field.member);
 ok=ok&&cJSON_AddNumberToObject(a,"cycles",c.capture.cycles);auto*r=ok?cJSON_AddObjectToObject(j,"correction"):nullptr;if(!r)ok=false;
 ok=ok&&cJSON_AddBoolToObject(r,"enabled",c.correction.enabled)&&cJSON_AddBoolToObject(r,"temperature_enabled",c.correction.temperature_enabled);
 for(auto field:correction_arrays)if(ok){const auto&values=c.correction.*field.member;auto*array=cJSON_CreateFloatArray(values.data(),6);if(!array||!cJSON_AddItemToObject(r,field.name,array)){cJSON_Delete(array);ok=false;}}
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* evaluation_json(const Evaluation&e){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;const auto&o=e.sample.observation;
 auto value=[&](const char*name,double n){return std::isfinite(n)?cJSON_AddNumberToObject(j,name,n)!=nullptr:cJSON_AddNullToObject(j,name)!=nullptr;};
 auto u64=[&](const char*name,std::uint64_t n){char text[24];std::snprintf(text,sizeof(text),"%llu",static_cast<unsigned long long>(n));return cJSON_AddStringToObject(j,name,text)!=nullptr;};
 bool ok=cJSON_AddStringToObject(j,"source",source_name(o.source))&&cJSON_AddNumberToObject(j,"source_code",static_cast<unsigned>(o.source))&&
  cJSON_AddStringToObject(j,"reason",reason_name(e.reason))&&cJSON_AddNumberToObject(j,"reason_code",static_cast<unsigned>(e.reason))&&
  cJSON_AddStringToObject(j,"capture_reason",reason_name(o.capture_reason))&&cJSON_AddNumberToObject(j,"capture_reason_code",static_cast<unsigned>(o.capture_reason))&&
  cJSON_AddStringToObject(j,"last_fault",reason_name(o.last_fault))&&cJSON_AddNumberToObject(j,"last_fault_code",static_cast<unsigned>(o.last_fault))&&
  cJSON_AddStringToObject(j,"correction_reason",reason_name(e.corrections.reason))&&cJSON_AddNumberToObject(j,"correction_reason_code",static_cast<unsigned>(e.corrections.reason));
#define FB(name,v) ok=ok&&cJSON_AddBoolToObject(j,name,v)
 FB("available",e.available);FB("required",e.required);FB("configuration_match",e.configuration_match);FB("value_qualified",e.value_qualified);FB("raw_capture_qualified",e.raw_qualified);FB("control_ok",e.control_ok);
 FB("capture_valid",o.valid&&(o.source==Source::TargetCapture||o.source==Source::Synthetic));FB("sample_value_valid",o.valid);FB("pending_fault",o.pending_fault);FB("frequency_clamped",o.frequency_clamped);FB("temperature_clamped",o.temperature_clamped);FB("input_confirmed",e.input_confirmed);
 FB("corrections_enabled",e.corrections.enabled);FB("corrections_valid",e.corrections.valid);FB("spark_bypassed",e.spark_bypassed);FB("spark_clamped",e.spark_clamped);FB("zero_factor",e.zero_factor);
#undef FB
 ok=ok&&cJSON_AddNumberToObject(j,"window_cycles",o.window_cycles)&&u64("sample_us",o.sample_us)&&u64("window_start_us",o.window_start_us)&&u64("last_edge_us",o.last_edge_us)&&u64("raw_edges",o.edges)&&u64("fault_generation",o.fault_generation)&&u64("acknowledged_generation",o.acknowledged_generation)&&u64("config_epoch",o.config_epoch);
 ok=ok&&cJSON_AddNumberToObject(j,"configuration_revision",e.sample.tune_revision);
 auto*cal=ok?cJSON_AddObjectToObject(j,"capture_calibration"):nullptr;if(!cal)ok=false;
 for(auto field:capture_fields)ok=ok&&cJSON_AddNumberToObject(cal,field.name,e.sample.calibration.*field.member);
 ok=ok&&cJSON_AddNumberToObject(cal,"cycles",e.sample.calibration.cycles);
 ok=ok&&value("frequency_hz",o.frequency_hz)&&value("low_pulse_us",o.low_pulse_us)&&value("ethanol_pct",o.ethanol_pct)&&value("fuel_temp_c",o.fuel_temp_c)&&
  value("unfiltered_ethanol_pct",o.unfiltered_ethanol_pct)&&value("unfiltered_fuel_temp_c",o.unfiltered_fuel_temp_c)&&value("sample_age_ms",o.age_ms)&&
  value("fuel_pct",e.corrections.fuel_factor*100)&&value("spark_add_deg",e.corrections.spark_add_deg)&&value("temperature_pct",e.corrections.temperature_factor*100);
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}} // namespace ecu::flex
