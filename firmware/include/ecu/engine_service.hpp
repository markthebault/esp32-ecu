#pragma once
#include "ecu/web_config.hpp"
#include "cJSON.h"
#include <string>
namespace ecu::engine_service {
void init();
// Fills published only after a completed step. A skipped call preserves it.
bool observe(const web::Sample&,const config::Config&,std::uint64_t now_us,std::uint64_t sampled_us,engine::RuntimeSample& published);
std::string tune_json();
int save(const char* text,std::string& reason);
cJSON* snapshot();
cJSON* sample();
}
