#pragma once
#include "ecu/json.hpp"
namespace ecu::web {
inline bool parse(const cJSON*j,config::Config&c){
 unsigned schema=0,revision=0;
 if(!keys(j,"|schema_version||revision||name||adc_reference_v||ui_poll_ms||trigger||sensors|")||!integer(j,"schema_version",schema)||(schema!=1&&schema!=2)||!integer(j,"revision",revision)||revision==0||!string(j,"name",c.name)||!number(j,"adc_reference_v",c.adc_reference_v)||!integer(j,"ui_poll_ms",c.ui_poll_ms))return false;
 c.revision=revision;
 auto*t=cJSON_GetObjectItemCaseSensitive(j,"trigger");if(!keys(t,"|slots||missing||max_rpm|")||!integer(t,"slots",c.slots)||!integer(t,"missing",c.missing)||!integer(t,"max_rpm",c.max_rpm))return false;
 auto*a=cJSON_GetObjectItemCaseSensitive(j,"sensors");if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)!=6)return false;
 for(unsigned i=0;i<6;++i){auto*o=cJSON_GetArrayItem(a,i);auto&s=c.sensors[i];char mode[16];
  const char*allowed=schema==1?"|id||label||mode||unit||confirmed||fault_low_v||fault_high_v||filter_ms||v0||y0||v1||y1||points||ntc_r0_ohm||ntc_t0_c||ntc_beta_k||pullup_ohm||pullup_fitted|":"|id||label||mode||unit||confirmed||fault_low_v||fault_high_v||filter_ms||v0||y0||v1||y1||points||ntc_r0_ohm||ntc_t0_c||ntc_beta_k||pullup_ohm||pullup_fitted||ratiometric||reference_supply_v|";
  if(!keys(o,allowed)||!string(o,"id",s.id)||!string(o,"label",s.label)||!string(o,"unit",s.unit)||!string(o,"mode",mode)||!boolean(o,"confirmed",s.confirmed)||!boolean(o,"pullup_fitted",s.pullup_fitted))return false;
  s.ratiometric=false;s.reference_supply_v=5;
  if(schema==2&&(!boolean(o,"ratiometric",s.ratiometric)||!number(o,"reference_supply_v",s.reference_supply_v)))return false;
  if(!std::strcmp(mode,"voltage"))s.mode=config::Mode::Voltage;else if(!std::strcmp(mode,"linear"))s.mode=config::Mode::Linear;else if(!std::strcmp(mode,"table"))s.mode=config::Mode::Table;else if(!std::strcmp(mode,"ntc_beta"))s.mode=config::Mode::Ntc;else return false;
  if(!number(o,"fault_low_v",s.fault_low_v)||!number(o,"fault_high_v",s.fault_high_v)||!number(o,"filter_ms",s.filter_ms)||!number(o,"v0",s.v0)||!number(o,"y0",s.y0)||!number(o,"v1",s.v1)||!number(o,"y1",s.y1)||!number(o,"ntc_r0_ohm",s.ntc_r0_ohm)||!number(o,"ntc_t0_c",s.ntc_t0_c)||!number(o,"ntc_beta_k",s.ntc_beta_k)||!number(o,"pullup_ohm",s.pullup_ohm))return false;
  auto*p=cJSON_GetObjectItemCaseSensitive(o,"points");int n=cJSON_GetArraySize(p);if(!cJSON_IsArray(p)||n<2||n>16)return false;s.point_count=n;for(int z=0;z<n;++z){auto*q=cJSON_GetArrayItem(p,z);if(!keys(q,"|v||value|")||!number(q,"v",s.points[z].v)||!number(q,"value",s.points[z].value))return false;}
 }
 return config::valid(c);
}
// Upgrade only an owned, already validated document. A failed allocation is
// discarded by the caller before any runtime or persistent profile changes.
inline bool upgrade_profile_document(cJSON*j){
 unsigned schema=0;if(!integer(j,"schema_version",schema))return false;
 if(schema==2)return true;
 if(schema!=1)return false;
 auto*a=cJSON_GetObjectItemCaseSensitive(j,"sensors");
 if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)!=6)return false;
 for(unsigned i=0;i<6;++i){auto*s=cJSON_GetArrayItem(a,i);
  if(!cJSON_AddBoolToObject(s,"ratiometric",false)||!cJSON_AddNumberToObject(s,"reference_supply_v",5))return false;
 }
 cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"schema_version"),2);return true;
}
}
