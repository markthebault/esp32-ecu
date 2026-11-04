#pragma once
// All ISR helpers are forced into explicitly IRAM ISR roots. IRAM_ATTR on an
// outlined COMDAT member can leave its literal pool in flash on Xtensa; an
// attribute on a caller alone also does not move outlined callees. Audit ELF.
#if defined(ESP_PLATFORM)
#include "esp_attr.h"
#define ECU_ISR_CODE __attribute__((always_inline)) inline
#else
#define ECU_ISR_CODE
#endif
