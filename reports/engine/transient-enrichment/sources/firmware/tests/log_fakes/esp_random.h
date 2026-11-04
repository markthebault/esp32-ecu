#pragma once
#include <cstdint>
// Deterministic test fixture only. Production builds use ESP-IDF's RNG.
inline std::uint32_t esp_random(){static std::uint32_t value=0x12345678;return ++value;}
