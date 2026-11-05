#pragma once
#include "ecu/boost_pwm.hpp"
#include "ecu/idle_pwm_json.hpp"
namespace ecu::boost {
inline cJSON* pwm_json(const PwmStats&s){
 auto*j=idle::pwm_json(s,false,false);if(!j)return nullptr;
 auto*meaning=cJSON_GetObjectItemCaseSensitive(j,"qualification");
 if(!cJSON_SetValuestring(meaning,"Virtual boost dispatcher only. No boost GPIO or physical valve driver is allocated in any build. Cycle-latched commands and timer observations do not establish electrical or mechanical execution.")){cJSON_Delete(j);return nullptr;}
 return j;
}
}
