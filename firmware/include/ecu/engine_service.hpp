#pragma once
#include "ecu/web_config.hpp"
#include "cJSON.h"
#include "ecu/tuning_session.hpp"
#include <string>
namespace ecu::engine_service {
void init();
// Fills published only after a completed step. A skipped call preserves it.
bool observe(const web::Sample&,const config::Config&,std::uint64_t now_us,std::uint64_t sampled_us,engine::RuntimeSample& published);
std::string tune_json();
int save(const char* text,std::string& reason);
cJSON* snapshot();
cJSON* sample();
// Task-only typed backend for the dedicated tuning transport. Mutations retain
// the same validation, revision CAS, persistence and configuration fences.
tuning::Result tuning_load(engine::Tune&);
tuning::Result tuning_current(std::uint32_t&);
tuning::Result tuning_commit(const engine::Tune&,std::uint32_t& saved_revision);
bool tuning_sample(engine::RuntimeSample&);
}
