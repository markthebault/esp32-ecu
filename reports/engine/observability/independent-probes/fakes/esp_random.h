#pragma once
#include <cstdint>
inline std::uint32_t esp_random(){static std::uint32_t state=0x13579bdf;state=state*1664525+1013904223;return state;}
