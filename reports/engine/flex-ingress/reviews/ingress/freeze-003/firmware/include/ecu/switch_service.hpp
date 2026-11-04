#pragma once
#include "ecu/switch_acquisition.hpp"
#include "cJSON.h"

namespace ecu::switch_service {
// Call after engine_target::init starts the shared GP timer. Only the monitor
// task may tick or acknowledge. JSON readers receive a copied snapshot.
void init();
switch_input::Snapshot tick(std::uint8_t requested_mask);
void control_observed(const switch_input::Snapshot&,bool completed);
cJSON* snapshot();
}
