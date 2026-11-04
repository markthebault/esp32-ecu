#pragma once
#include "ecu/idle_pwm.hpp"
#include "ecu/engine_data_json.hpp"
namespace ecu::idle {
inline cJSON* pwm_json(const PwmStats&s,bool physical_policy,bool physical_high){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 bool ok=cJSON_AddStringToObject(j,"basis","dispatcher_observation")&&cJSON_AddBoolToObject(j,"active",s.active)&&
  cJSON_AddBoolToObject(j,"virtual_high",s.high)&&cJSON_AddBoolToObject(j,"physical_policy_enabled",physical_policy)&&
  cJSON_AddBoolToObject(j,"physical_command_high",physical_high)&&cJSON_AddStringToObject(j,"fault",pwm_cause_name(s.fault))&&
  cJSON_AddStringToObject(j,"last_cause",pwm_cause_name(s.last_cause));
#define U64(k) ok=ok&&engine::json_u64(j,#k,s.k)
 U64(sequence);U64(pending_sequence);U64(observed_us);U64(accepted);U64(rejected);U64(cycles);U64(rises);U64(falls);U64(faults);U64(cuts);U64(recoveries);U64(max_lateness_us);
#undef U64
#define NUM(k) ok=ok&&cJSON_AddNumberToObject(j,#k,s.k)
 NUM(tune_revision);NUM(sensor_revision);NUM(pending_tune_revision);NUM(pending_sensor_revision);NUM(period_us);NUM(high_us);
#undef NUM
 ok=ok&&cJSON_AddStringToObject(j,"qualification","Integer PWM dispatcher state. Pending identities may differ from the cycle-latched command. GPIO voltage, valve position and target timing are unmeasured; physical policy remains inhibited on selected N16R8.");
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
} // namespace ecu::idle
