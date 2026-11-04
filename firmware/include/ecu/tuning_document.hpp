#pragma once
#include "ecu/tuning_layout.hpp"
#include "ecu/load_json.hpp"
#include "ecu/secondary_json.hpp"
#include "cJSON.h"
namespace ecu::tuning {
class Document {
 cJSON* root_;
 static cJSON* item(cJSON*j,const char*k){return cJSON_GetObjectItemCaseSensitive(j,k);}
 static bool set(cJSON*j,double v){if(!cJSON_IsNumber(j)||!engine::finite(v))return false;cJSON_SetNumberValue(j,v);return true;}
 template<class Values>static bool values(cJSON*j,const Values&v){if(!cJSON_IsArray(j)||cJSON_GetArraySize(j)!=int(v.size()))return false;for(unsigned i=0;i<v.size();++i)if(!set(cJSON_GetArrayItem(j,i),v[i]))return false;return true;}
 template<class Map>static bool grid(cJSON*j,const Map&m){return j&&values(item(j,"rpm"),m.rpm)&&values(item(j,"load"),m.load)&&values(item(j,"cells"),m.cells);}
public:
 explicit Document(cJSON*j):root_(j){}
 bool header(std::uint32_t revision,const char*strategy){return set(item(root_,"schema_version"),8)&&set(item(root_,"revision"),revision)&&cJSON_SetValuestring(item(root_,"strategy"),strategy);}
 bool number(const char*group,const char*key,double v){return set(item(item(root_,group),key),v);}
 bool boolean(const char*group,const char*key,bool v){auto*j=item(item(root_,group),key);if(!cJSON_IsBool(j))return false;j->type=(j->type&~0xff)|(v?cJSON_True:cJSON_False);return true;}
 template<class Values>bool array(const char*group,const char*key,const Values&v){return values(item(item(root_,group),key),v);}
 template<class Map>bool map(const char*key,const Map&m){return grid(item(item(root_,"maps"),key),m);}
 bool idle(const ecu::idle::Config&c){
  auto*j=item(root_,"idle_control");if(!j||!cJSON_SetValuestring(item(j,"algorithm"),ecu::idle::algorithm_name(c.algorithm)))return false;
  if(!number("idle_control","frequency_hz",c.frequency_hz))return false;
  if(!number("idle_control","control_period_ms",c.control_period_ms))return false;
  if(!number("idle_control","min_pct",c.min_pct))return false;
  if(!number("idle_control","max_pct",c.max_pct))return false;
  if(!number("idle_control","tps_closed_pct",c.tps_closed_pct))return false;
  if(!number("idle_control","tps_hysteresis_pct",c.tps_hysteresis_pct))return false;
  if(!number("idle_control","entry_rpm_above",c.entry_rpm_above))return false;
  if(!number("idle_control","exit_rpm_above",c.exit_rpm_above))return false;
  if(!number("idle_control","entry_delay_s",c.entry_delay_s))return false;
  if(!number("idle_control","afterstart_taper_s",c.afterstart_taper_s))return false;
  if(!number("idle_control","dashpot_pct",c.dashpot_pct))return false;
  if(!number("idle_control","dashpot_decay_pct_s",c.dashpot_decay_pct_s))return false;
  if(!number("idle_control","slew_pct_s",c.slew_pct_s))return false;
  if(!number("idle_control","integral_limit_pct",c.integral_limit_pct))return false;
  if(!number("idle_control","kd",c.kd))return false;
  if(!number("idle_control","derivative_filter_s",c.derivative_filter_s))return false;
  if(!number("idle_control","fast_idle_temp_c",c.fast_idle_temp_c))return false;
  if(!number("idle_control","fast_idle_hysteresis_c",c.fast_idle_hysteresis_c))return false;
  if(!array("idle_control","coolant_c",c.coolant_c))return false;
  if(!array("idle_control","run_pct",c.run_pct))return false;
  if(!array("idle_control","crank_pct",c.crank_pct))return false;
  if(!array("idle_control","target_add_rpm",c.target_add_rpm))return false;
  return true;
 }
 bool trim(unsigned index,const engine::TrimMap&m){return grid(cJSON_GetArrayItem(item(item(root_,"cylinder_trims"),"fuel_maps"),index),m);}
 bool transient_enrichment(const ecu::transient::Config&c){
  auto*j=item(root_,"transient_enrichment");if(!j||!cJSON_SetValuestring(item(j,"mode"),transient::mode_name(c.mode))||!cJSON_SetValuestring(item(j,"apply"),transient::apply_name(c.apply)))return false;
  for(auto field:transient::scalar_fields)if(!number("transient_enrichment",field.name,c.*(field.member)))return false;
  for(auto field:transient::array_fields)if(!array("transient_enrichment",field.name,c.*(field.member)))return false;
  return true;
 }
 bool load_model(const ecu::load::Config&c){
  auto*j=item(root_,"load_model");if(!j)return false;
  for(auto f:load::source_fields)if(!cJSON_SetValuestring(item(j,f.name),load::source_name(c.*(f.member))))return false;
  for(auto f:load::axis_fields)if(!cJSON_SetValuestring(item(j,f.name),load::axis_name(c.*(f.member))))return false;
  return cJSON_SetValuestring(item(j,"pressure"),load::pressure_name(c.pressure))&&cJSON_SetValuestring(item(j,"aux_role"),load::aux_name(c.aux_role))&&
   cJSON_SetValuestring(item(j,"baro_source"),load::baro_name(c.baro_source))&&cJSON_SetValuestring(item(j,"afr"),load::afr_name(c.afr))&&
   number("load_model","fixed_baro_kpa",c.fixed_baro_kpa)&&number("load_model","afr_delay_s",c.afr_delay_s);
 }
 bool secondary_tables(const ecu::secondary::Config&c,const engine::Map&fuel,const engine::Map&spark){
  auto*group=item(root_,"secondary_tables");if(!group)return false;
  auto update=[&](const char*name,const secondary::Rule&r,const engine::Map&m){auto*j=item(group,name);if(!j)return false;
   if(!cJSON_SetValuestring(item(j,"mode"),secondary::mode_name(r.mode))||!cJSON_SetValuestring(item(j,"source"),load::source_name(r.source))||!cJSON_SetValuestring(item(j,"axis"),load::axis_name(r.axis))||
      !cJSON_SetValuestring(item(j,"cells"),secondary::cells_name(r.cells))||!cJSON_SetValuestring(item(j,"condition"),secondary::condition_name(r.condition))||!set(item(j,"threshold"),r.threshold)||!set(item(j,"debounce_ms"),r.debounce_ms)||!set(item(j,"input_channel"),r.input_channel)||!grid(item(j,"map"),m))return false;
   auto*flag=item(j,"active_high");if(!cJSON_IsBool(flag))return false;flag->type=(flag->type&~0xff)|(r.active_high?cJSON_True:cJSON_False);return true;};
  return update("fuel",c.fuel,fuel)&&update("spark",c.spark,spark);
 }
};
} // namespace ecu::tuning
