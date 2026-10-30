#pragma once
#include "ecu/config.hpp"
#include "cJSON.h"
#include <cstdio>
#include <cstring>
namespace ecu::web {
// Bound parser recursion before cJSON sees any untrusted body.
inline bool safe_json(const char*text,std::size_t length){
 if(!text||!length||length>16384)return false;
 unsigned depth=0;bool quoted=false,escaped=false;
 for(std::size_t i=0;i<length;++i){const char c=text[i];if(!c)return false;
  if(quoted){if(escaped){escaped=false;continue;}if(c=='\\'){escaped=true;continue;}if(c=='"')quoted=false;}
  else if(c=='"')quoted=true;
  else if(c=='{'||c=='['){if(++depth>8)return false;}
  else if(c=='}'||c==']'){if(!depth)return false;--depth;}
 }
 return !quoted&&!escaped&&!depth;
}
inline bool keys(const cJSON*o,const char*allowed){if(!cJSON_IsObject(o))return false;for(auto*x=o->child;x;x=x->next){char token[96];if(!x->string||std::snprintf(token,sizeof(token),"|%s|",x->string)>=static_cast<int>(sizeof(token))||!std::strstr(allowed,token))return false;for(auto*y=x->next;y;y=y->next)if(y->string&&!std::strcmp(x->string,y->string))return false;}return true;}
inline bool number(const cJSON*o,const char*k,double&v){auto*x=cJSON_GetObjectItemCaseSensitive(o,k);if(!cJSON_IsNumber(x)||!config::finite(x->valuedouble))return false;v=x->valuedouble;return true;}
inline bool integer(const cJSON*o,const char*k,unsigned&v){double n;if(!number(o,k,n)||n<0||n>4294967295.0||std::floor(n)!=n)return false;v=static_cast<unsigned>(n);return true;}
inline bool boolean(const cJSON*o,const char*k,bool&v){auto*x=cJSON_GetObjectItemCaseSensitive(o,k);if(!cJSON_IsBool(x))return false;v=cJSON_IsTrue(x);return true;}
template<unsigned N>bool string(const cJSON*o,const char*k,char(&v)[N]){auto*x=cJSON_GetObjectItemCaseSensitive(o,k);if(!cJSON_IsString(x)||!x->valuestring)return false;auto n=std::strlen(x->valuestring);if(n==0||n>=N)return false;for(unsigned i=0;i<n;++i)if(static_cast<unsigned char>(x->valuestring[i])<32)return false;std::memcpy(v,x->valuestring,n+1);return true;}
inline bool parse(const cJSON*j,config::Config&c){
 unsigned schema=0,revision=0;
 if(!keys(j,"|schema_version||revision||name||adc_reference_v||ui_poll_ms||trigger||sensors|")||!integer(j,"schema_version",schema)||schema!=1||!integer(j,"revision",revision)||revision==0||!string(j,"name",c.name)||!number(j,"adc_reference_v",c.adc_reference_v)||!integer(j,"ui_poll_ms",c.ui_poll_ms))return false;
 c.revision=revision;
 auto*t=cJSON_GetObjectItemCaseSensitive(j,"trigger");if(!keys(t,"|slots||missing||max_rpm|")||!integer(t,"slots",c.slots)||!integer(t,"missing",c.missing)||!integer(t,"max_rpm",c.max_rpm))return false;
 auto*a=cJSON_GetObjectItemCaseSensitive(j,"sensors");if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)!=6)return false;
 for(unsigned i=0;i<6;++i){auto*o=cJSON_GetArrayItem(a,i);auto&s=c.sensors[i];char mode[16];
  if(!keys(o,"|id||label||mode||unit||confirmed||fault_low_v||fault_high_v||filter_ms||v0||y0||v1||y1||points||ntc_r0_ohm||ntc_t0_c||ntc_beta_k||pullup_ohm||pullup_fitted|")||!string(o,"id",s.id)||!string(o,"label",s.label)||!string(o,"unit",s.unit)||!string(o,"mode",mode)||!boolean(o,"confirmed",s.confirmed)||!boolean(o,"pullup_fitted",s.pullup_fitted))return false;
  if(!std::strcmp(mode,"voltage"))s.mode=config::Mode::Voltage;else if(!std::strcmp(mode,"linear"))s.mode=config::Mode::Linear;else if(!std::strcmp(mode,"table"))s.mode=config::Mode::Table;else if(!std::strcmp(mode,"ntc_beta"))s.mode=config::Mode::Ntc;else return false;
  if(!number(o,"fault_low_v",s.fault_low_v)||!number(o,"fault_high_v",s.fault_high_v)||!number(o,"filter_ms",s.filter_ms)||!number(o,"v0",s.v0)||!number(o,"y0",s.y0)||!number(o,"v1",s.v1)||!number(o,"y1",s.y1)||!number(o,"ntc_r0_ohm",s.ntc_r0_ohm)||!number(o,"ntc_t0_c",s.ntc_t0_c)||!number(o,"ntc_beta_k",s.ntc_beta_k)||!number(o,"pullup_ohm",s.pullup_ohm))return false;
  auto*p=cJSON_GetObjectItemCaseSensitive(o,"points");int n=cJSON_GetArraySize(p);if(!cJSON_IsArray(p)||n<2||n>16)return false;s.point_count=n;for(int z=0;z<n;++z){auto*q=cJSON_GetArrayItem(p,z);if(!keys(q,"|v||value|")||!number(q,"v",s.points[z].v)||!number(q,"value",s.points[z].value))return false;}
 }
 return config::valid(c);
}
}
