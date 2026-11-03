#pragma once
#include "ecu/web_config.hpp"
#include "cJSON.h"
#include <string>
namespace ecu::engine_service {
void init();
void observe(const web::Sample&,const config::Config&,std::uint64_t now_us,std::uint64_t sampled_us);
std::string tune_json();
int save(const char* text,std::string& reason);
cJSON* snapshot();
}
