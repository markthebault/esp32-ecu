#pragma once
#include "ecu/status_led.hpp"
#include "cJSON.h"
namespace ecu::board_status {
// Radio only queues/coalesces desired policy. The monitor's single shared I2C
// owner performs bounded work through switch_service::tick, never this call.
void request(status_led::Pattern);
cJSON* snapshot();
}
