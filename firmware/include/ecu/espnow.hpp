#pragma once
#include "ecu/web_config.hpp"
#include "cJSON.h"
namespace ecu::radio {
void start();
void publish(const web::Sample&,const config::Config&,const std::array<double,6>&);
cJSON* status(); // No secrets unless called through authenticated service route.
bool command(const char* action,const char* mac,const char* window);
}
