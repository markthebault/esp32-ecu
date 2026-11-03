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
}
