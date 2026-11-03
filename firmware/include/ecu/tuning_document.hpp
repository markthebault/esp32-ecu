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
 bool header(std::uint32_t revision,const char*strategy){return set(item(root_,"schema_version"),3)&&set(item(root_,"revision"),revision)&&cJSON_SetValuestring(item(root_,"strategy"),strategy);}
 bool number(const char*group,const char*key,double v){return set(item(item(root_,group),key),v);}
 bool boolean(const char*group,const char*key,bool v){auto*j=item(item(root_,group),key);if(!cJSON_IsBool(j))return false;j->type=(j->type&~0xff)|(v?cJSON_True:cJSON_False);return true;}
 template<class Values>bool array(const char*group,const char*key,const Values&v){return values(item(item(root_,group),key),v);}
 template<class Map>bool map(const char*key,const Map&m){return grid(item(item(root_,"maps"),key),m);}
 bool trim(unsigned index,const engine::TrimMap&m){return grid(cJSON_GetArrayItem(item(item(root_,"cylinder_trims"),"fuel_maps"),index),m);}
};
} // namespace ecu::tuning
