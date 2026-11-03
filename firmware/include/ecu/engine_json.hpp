#pragma once
#include "ecu/engine.hpp"
#include "ecu/json.hpp"
#include <string>
namespace ecu::engine {
// Strict engine schema shared by target and host. Sensor calibration has its
// own unrelated schema. Legacy engine v1 is accepted only as batch/wasted.
template<std::size_t N>bool float_array(const cJSON*j,std::array<float,N>&a){
 if(!cJSON_IsArray(j)||cJSON_GetArraySize(j)!=int(N))return false;
 for(unsigned i=0;i<N;++i){auto*v=cJSON_GetArrayItem(j,i);if(!cJSON_IsNumber(v)||!finite(v->valuedouble)||std::abs(v->valuedouble)>1e6)return false;a[i]=static_cast<float>(v->valuedouble);}return true;
}
template<class Grid>inline bool map_parse(const cJSON*j,Grid&m){return web::keys(j,"|rpm||load||cells|")&&float_array(cJSON_GetObjectItemCaseSensitive(j,"rpm"),m.rpm)&&float_array(cJSON_GetObjectItemCaseSensitive(j,"load"),m.load)&&float_array(cJSON_GetObjectItemCaseSensitive(j,"cells"),m.cells);}
inline bool parse_tune(const cJSON*j,Tune&t){
 using namespace web;unsigned schema;char strategy[32]{},physical[32]{};
 if(!integer(j,"schema_version",schema)||(schema<1||schema>3)||!keys(j,schema==1?"|schema_version||revision||strategy||physical_outputs||engine||settings||curves||maps|":schema==2?"|schema_version||revision||strategy||physical_outputs||engine||settings||curves||maps||timing|":"|schema_version||revision||strategy||physical_outputs||engine||settings||curves||maps||timing||cylinder_trims|")||!integer(j,"revision",t.revision)||!string(j,"strategy",strategy)||!string(j,"physical_outputs",physical)||std::strcmp(physical,"inhibited"))return false;
 if(!std::strcmp(strategy,"batch_wasted_4cyl"))t.strategy=Strategy::BatchWasted;
 else if(schema>=2&&!std::strcmp(strategy,"sequential_4cyl"))t.strategy=Strategy::Sequential;
 else return false;
 auto*e=cJSON_GetObjectItemCaseSensitive(j,"engine");
 if(!keys(e,"|cylinders||displacement_cc||injector_cc_min||fuel_density_g_cc||stoich_afr|")||!integer(e,"cylinders",t.cylinders))return false;
 auto number_float=[](const cJSON*o,const char*k,float&v){double n;if(!web::number(o,k,n)||std::abs(n)>1e6)return false;v=static_cast<float>(n);return true;};
 t.firing_order={1,3,4,2};t.injection_end_deg=540;t.cam_sync_deg=450;t.cam_window_deg=20;
 if(schema>=2){
  auto*timing=cJSON_GetObjectItemCaseSensitive(j,"timing");
  if(!keys(timing,"|firing_order||injection_end_deg||cam_sync_deg||cam_window_deg|")||!number_float(timing,"injection_end_deg",t.injection_end_deg)||!number_float(timing,"cam_sync_deg",t.cam_sync_deg)||!number_float(timing,"cam_window_deg",t.cam_window_deg))return false;
  auto*order=cJSON_GetObjectItemCaseSensitive(timing,"firing_order");if(!cJSON_IsArray(order)||cJSON_GetArraySize(order)!=4)return false;
  for(unsigned i=0;i<4;++i){auto*v=cJSON_GetArrayItem(order,i);if(!cJSON_IsNumber(v)||!range(v->valuedouble,1,4)||v->valuedouble!=std::floor(v->valuedouble))return false;t.firing_order[i]=unsigned(v->valuedouble);}
 }
 t.cylinder_trims_enabled=false;t.cylinder_spark_deg.fill(0);t.cylinder_fuel={};
 if(schema==3){
  auto*trims=cJSON_GetObjectItemCaseSensitive(j,"cylinder_trims");
  if(!keys(trims,"|enabled||spark_deg||fuel_maps|")||!boolean(trims,"enabled",t.cylinder_trims_enabled)||!float_array(cJSON_GetObjectItemCaseSensitive(trims,"spark_deg"),t.cylinder_spark_deg))return false;
  auto*maps=cJSON_GetObjectItemCaseSensitive(trims,"fuel_maps");if(!cJSON_IsArray(maps)||cJSON_GetArraySize(maps)!=4)return false;
  for(unsigned i=0;i<4;++i)if(!map_parse(cJSON_GetArrayItem(maps,i),t.cylinder_fuel[i]))return false;
 }
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
// Call only after parse_tune succeeds. Upgrade a private parsed tree, never a
// stored record. Failure discards that tree; no partial document is published.
inline bool upgrade_tune_document(cJSON*j){
 auto*schema=cJSON_GetObjectItemCaseSensitive(j,"schema_version");if(!cJSON_IsNumber(schema))return false;
 if(schema->valuedouble==3)return true;
 if(schema->valuedouble!=1&&schema->valuedouble!=2)return false;
 if(schema->valuedouble==1){
  auto*timing=cJSON_CreateObject();if(!timing)return false;
  const double order[]={1,3,4,2};auto*a=cJSON_CreateDoubleArray(order,4);
  if(!a||!cJSON_AddItemToObject(timing,"firing_order",a)){cJSON_Delete(a);cJSON_Delete(timing);return false;}
  if(!cJSON_AddNumberToObject(timing,"injection_end_deg",540)||!cJSON_AddNumberToObject(timing,"cam_sync_deg",450)||!cJSON_AddNumberToObject(timing,"cam_window_deg",20)||!cJSON_AddItemToObject(j,"timing",timing)){cJSON_Delete(timing);return false;}
 }
 auto*trims=cJSON_CreateObject();if(!trims)return false;
 const double zero[]={0,0,0,0};auto*spark=cJSON_CreateDoubleArray(zero,4);
 if(!spark||!cJSON_AddItemToObject(trims,"spark_deg",spark)){cJSON_Delete(spark);cJSON_Delete(trims);return false;}
 auto*maps=cJSON_AddArrayToObject(trims,"fuel_maps");bool ok=maps&&cJSON_AddBoolToObject(trims,"enabled",false);
 for(unsigned i=0;ok&&i<4;++i){
  const TrimMap neutral;auto*m=cJSON_CreateObject();if(!m){ok=false;break;}
  auto add=[&](const char*name,const auto&values){auto*a=cJSON_CreateFloatArray(values.data(),values.size());if(!a||!cJSON_AddItemToObject(m,name,a)){cJSON_Delete(a);return false;}return true;};
  ok=add("rpm",neutral.rpm)&&add("load",neutral.load)&&add("cells",neutral.cells)&&cJSON_AddItemToArray(maps,m);
  if(!ok)cJSON_Delete(m);
 }
 if(!ok||!cJSON_AddItemToObject(j,"cylinder_trims",trims)){cJSON_Delete(trims);return false;}
 cJSON_SetNumberValue(schema,3);return true;
}
inline bool canonical_tune(const char*text,Tune&t,std::string& document){
 if(!text||std::strlen(text)>tune_maximum||!web::safe_json(text,std::strlen(text),tune_maximum))return false;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);
 const bool ok=j&&parse_tune(j,t)&&upgrade_tune_document(j);
 char*encoded=ok?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);
 if(!encoded)return false;
 const bool fits=std::strlen(encoded)<=tune_maximum;if(fits)document=encoded;cJSON_free(encoded);return fits;
}
inline cJSON* output_json(const Output&o){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 auto number=[](cJSON*object,const char*name,double value){return finite(value)?cJSON_AddNumberToObject(object,name,value)!=nullptr:cJSON_AddNullToObject(object,name)!=nullptr;};
 bool ok=cJSON_AddStringToObject(j,"state",state_name(o.state))&&cJSON_AddNumberToObject(j,"faults",o.faults)&&
  cJSON_AddStringToObject(j,"execution","shadow / physical outputs inhibited")&&cJSON_AddBoolToObject(j,"physical_outputs_enabled",false);
#define OUT(name) ok=ok&&number(j,#name,o.name)
 OUT(rpm);OUT(ve_pct);OUT(target_lambda);OUT(advance_deg);OUT(pulse_ms);OUT(dwell_ms);OUT(deadtime_ms);OUT(air_mg);OUT(warmup);OUT(afterstart);OUT(accel);OUT(ego);OUT(duty_pct);OUT(idle_pct);
#undef OUT
 if(ok)ok=cJSON_AddBoolToObject(j,"fuel_cut",o.fuel_cut)&&cJSON_AddBoolToObject(j,"spark_cut",o.spark_cut)&&cJSON_AddBoolToObject(j,"proposed_pump",o.pump)&&cJSON_AddBoolToObject(j,"proposed_fan",o.fan)&&cJSON_AddStringToObject(j,"scalar_proposal_basis","untrimmed_base_demand");
 auto*cyl=ok?cJSON_AddObjectToObject(j,"cylinders"):nullptr;if(!cyl)ok=false;
 if(ok)ok=cJSON_AddBoolToObject(cyl,"available",o.cylinder_data)&&cJSON_AddBoolToObject(cyl,"enabled",o.cylinder_trims_enabled)&&
  cJSON_AddNumberToObject(cyl,"capacity_mask",o.cylinder_capacity_mask)&&cJSON_AddNumberToObject(cyl,"spark_clamp_mask",o.cylinder_spark_clamp_mask)&&cJSON_AddNumberToObject(cyl,"retard_floor_mask",o.cylinder_retard_floor_mask);
 auto*a=ok?cJSON_AddArrayToObject(cyl,"proposals"):nullptr;if(!a)ok=false;
 for(unsigned i=0;ok&&i<4;++i){
  auto*row=cJSON_CreateObject();if(!row){ok=false;break;}
  ok=cJSON_AddNumberToObject(row,"cylinder",i+1)&&number(row,"pulse_ms",o.cylinder_data?o.cylinder_pulse_ms[i]:NAN)&&number(row,"advance_deg",o.cylinder_data?o.cylinder_advance_deg[i]:NAN)&&number(row,"fuel_pct",o.cylinder_data?o.cylinder_fuel_pct[i]:NAN)&&number(row,"duty_pct",o.cylinder_data?o.cylinder_duty_pct[i]:NAN)&&cJSON_AddItemToArray(a,row);
  if(!ok)cJSON_Delete(row);
 }
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
