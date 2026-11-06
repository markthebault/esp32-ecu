#pragma once
#include "cJSON.h"
namespace ecu::engine_tuning {
void start(bool interlock_at_boot);
cJSON* snapshot();
}
