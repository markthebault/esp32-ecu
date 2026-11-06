#pragma once
#include <cassert>
#include <cstdint>
constexpr unsigned portMAX_DELAY=UINT32_MAX;
constexpr int pdTRUE=1;
#define configASSERT(value) assert(value)
