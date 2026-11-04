#pragma once
#include "ecu/tuning_layout.hpp"
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
 bool header(std::uint32_t revision,const char*strategy){return set(item(root_,"schema_version"),6)&&set(item(root_,"revision"),revision)&&cJSON_SetValuestring(item(root_,"strategy"),strategy);}
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
};
} // namespace ecu::tuning
