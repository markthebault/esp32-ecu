#pragma once
// Accessory draft GPIO3 is U3/JMOD socket pad13. This is not a routing or
// physical module qualification. No peripheral PWM ownership is used.
#ifndef ECU_IDLE_DUMMY_LOADS
#define ECU_IDLE_DUMMY_LOADS 0
#endif
#if ECU_IDLE_DUMMY_LOADS && !(defined(ECU_ENGINE_DUMMY_LOADS) && ECU_ENGINE_DUMMY_LOADS)
#error Idle physical policy requires the explicit engine dummy-load policy
#endif
#if ECU_IDLE_DUMMY_LOADS && defined(ECU_SELECTED_N16R8)
#error Selected N16R8 GPIO3/eFuse routing, module fit and accessory qualification remain unverified
#endif
namespace ecu::idle {inline constexpr unsigned gpio=3;}
