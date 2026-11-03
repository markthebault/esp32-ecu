#pragma once
#include "ecu/engine.hpp"
#include "ecu/json.hpp"
namespace ecu::engine {
// Strict schema shared by target service and host SIL; separate from sensor
// calibration schema v1 to preserve existing saved profiles without migration.
template<std::size_t N>bool float_array(const cJSON*j,std::array<float,N>&a){
 if(!cJSON_IsArray(j)||cJSON_GetArraySize(j)!=int(N))return false;
 for(unsigned i=0;i<N;++i){auto*v=cJSON_GetArrayItem(j,i);if(!cJSON_IsNumber(v)||!finite(v->valuedouble)||std::abs(v->valuedouble)>1e6)return false;a[i]=static_cast<float>(v->valuedouble);}return true;
}
inline bool map_parse(const cJSON*j,Map&m){return web::keys(j,"|rpm||load||cells|")&&float_array(cJSON_GetObjectItemCaseSensitive(j,"rpm"),m.rpm)&&float_array(cJSON_GetObjectItemCaseSensitive(j,"load"),m.load)&&float_array(cJSON_GetObjectItemCaseSensitive(j,"cells"),m.cells);}
inline bool parse_tune(const cJSON*j,Tune&t){
 using namespace web;unsigned schema;char strategy[32]{},physical[32]{};
 if(!keys(j,"|schema_version||revision||strategy||physical_outputs||engine||settings||curves||maps|")||!integer(j,"schema_version",schema)||schema!=1||!integer(j,"revision",t.revision)||!string(j,"strategy",strategy)||std::strcmp(strategy,"batch_wasted_4cyl")||!string(j,"physical_outputs",physical)||std::strcmp(physical,"inhibited"))return false;
 auto*e=cJSON_GetObjectItemCaseSensitive(j,"engine");
 if(!keys(e,"|cylinders||displacement_cc||injector_cc_min||fuel_density_g_cc||stoich_afr|")||!integer(e,"cylinders",t.cylinders))return false;
 auto number_float=[](const cJSON*o,const char*k,float&v){double n;if(!web::number(o,k,n)||std::abs(n)>1e6)return false;v=static_cast<float>(n);return true;};
 if(!number_float(e,"displacement_cc",t.displacement_cc)||!number_float(e,"injector_cc_min",t.injector_cc_min)||!number_float(e,"fuel_density_g_cc",t.fuel_density_g_cc)||!number_float(e,"stoich_afr",t.stoich_afr))return false;
 auto*s=cJSON_GetObjectItemCaseSensitive(j,"settings");
 if(!keys(s,"|cranking_rpm||crank_advance_deg||rpm_limit||rpm_hysteresis||soft_limit_band||max_duty||max_injection_ms||max_dwell_ms||tooth1_btdc_deg||afterstart_pct||afterstart_s||accel_threshold_pct_s||accel_gain||accel_decay_s||ego_enabled||ego_kp||ego_ki||ego_limit||ego_min_clt||dfco_enabled||dfco_rpm||dfco_hysteresis||dfco_tps||dfco_delay_s||idle_enabled||idle_target_rpm||idle_kp||idle_ki||fan_on_c||fan_off_c||pump_prime_s|"))return false;
#define FIELD(name) if(!number_float(s,#name,t.name))return false
 FIELD(cranking_rpm);FIELD(crank_advance_deg);FIELD(rpm_limit);FIELD(rpm_hysteresis);FIELD(soft_limit_band);FIELD(max_duty);FIELD(max_injection_ms);FIELD(max_dwell_ms);FIELD(tooth1_btdc_deg);FIELD(afterstart_pct);FIELD(afterstart_s);FIELD(accel_threshold_pct_s);FIELD(accel_gain);FIELD(accel_decay_s);FIELD(ego_kp);FIELD(ego_ki);FIELD(ego_limit);FIELD(ego_min_clt);FIELD(dfco_rpm);FIELD(dfco_hysteresis);FIELD(dfco_tps);FIELD(dfco_delay_s);FIELD(idle_target_rpm);FIELD(idle_kp);FIELD(idle_ki);FIELD(fan_on_c);FIELD(fan_off_c);FIELD(pump_prime_s);
#undef FIELD
 if(!boolean(s,"ego_enabled",t.ego_enabled)||!boolean(s,"dfco_enabled",t.dfco_enabled)||!boolean(s,"idle_enabled",t.idle_enabled))return false;
 auto*c=cJSON_GetObjectItemCaseSensitive(j,"curves");
 if(!keys(c,"|coolant_c||warmup_pct||crank_pct||battery_v||deadtime_ms||dwell_ms|")||!float_array(cJSON_GetObjectItemCaseSensitive(c,"coolant_c"),t.coolant_c)||!float_array(cJSON_GetObjectItemCaseSensitive(c,"warmup_pct"),t.warmup_pct)||!float_array(cJSON_GetObjectItemCaseSensitive(c,"crank_pct"),t.crank_pct)||!float_array(cJSON_GetObjectItemCaseSensitive(c,"battery_v"),t.battery_v)||!float_array(cJSON_GetObjectItemCaseSensitive(c,"deadtime_ms"),t.deadtime_ms)||!float_array(cJSON_GetObjectItemCaseSensitive(c,"dwell_ms"),t.dwell_ms))return false;
 auto*m=cJSON_GetObjectItemCaseSensitive(j,"maps");return keys(m,"|ve||spark||lambda|")&&map_parse(cJSON_GetObjectItemCaseSensitive(m,"ve"),t.ve)&&map_parse(cJSON_GetObjectItemCaseSensitive(m,"spark"),t.spark)&&map_parse(cJSON_GetObjectItemCaseSensitive(m,"lambda"),t.lambda)&&!validate(t);
}
inline cJSON* output_json(const Output&o){
 auto*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"state",state_name(o.state));cJSON_AddNumberToObject(j,"faults",o.faults);
 cJSON_AddStringToObject(j,"execution","shadow / physical outputs inhibited");cJSON_AddBoolToObject(j,"physical_outputs_enabled",false);
#define OUT(name) if(finite(o.name))cJSON_AddNumberToObject(j,#name,o.name);else cJSON_AddNullToObject(j,#name)
 OUT(rpm);OUT(ve_pct);OUT(target_lambda);OUT(advance_deg);OUT(pulse_ms);OUT(dwell_ms);OUT(deadtime_ms);OUT(air_mg);OUT(warmup);OUT(afterstart);OUT(accel);OUT(ego);OUT(duty_pct);OUT(idle_pct);
#undef OUT
 cJSON_AddBoolToObject(j,"fuel_cut",o.fuel_cut);cJSON_AddBoolToObject(j,"spark_cut",o.spark_cut);cJSON_AddBoolToObject(j,"proposed_pump",o.pump);cJSON_AddBoolToObject(j,"proposed_fan",o.fan);
 return j;
}
}
