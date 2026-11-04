#pragma once
#include <mutex>
#include <cassert>
#include <cstdint>
using portMUX_TYPE=std::mutex;
#define portMUX_INITIALIZER_UNLOCKED {}
#define portENTER_CRITICAL(mux) (mux)->lock()
#define portEXIT_CRITICAL(mux) (mux)->unlock()
constexpr unsigned portMAX_DELAY=UINT32_MAX;
constexpr int pdTRUE=1;
#define configASSERT(value) assert(value)
