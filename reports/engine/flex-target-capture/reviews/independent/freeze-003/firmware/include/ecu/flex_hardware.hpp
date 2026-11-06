#pragma once
#ifndef ECU_FLEX_G38_DRAFT
#define ECU_FLEX_G38_DRAFT 0
#endif
#if ECU_FLEX_G38_DRAFT
#if !defined(ECU_COMPACT_A3) || !defined(ECU_SELECTED_N16R8)
#error GPIO38 flex draft requires the separate selected compact N16R8 carrier
#endif
#if (defined(ECU_ENGINE_DUMMY_LOADS) && ECU_ENGINE_DUMMY_LOADS) || (defined(ECU_BENCH_PULSES) && ECU_BENCH_PULSES)
#error GPIO38 flex draft keeps all physical engine outputs inhibited
#endif
#endif
namespace ecu::flex {constexpr unsigned gpio=38;}
