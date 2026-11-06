#pragma once
#include <cassert>
#include <cstdint>
constexpr int pdTRUE=1,pdFALSE=0;
constexpr std::uint32_t portMAX_DELAY=UINT32_MAX;
#define configASSERT(x) assert(x)
