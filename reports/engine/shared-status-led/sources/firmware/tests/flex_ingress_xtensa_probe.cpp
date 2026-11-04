// Static placement probe only. Never flashed or substituted for a real SDK
// capture callback, interrupt mask, lock, owning worker or hardware measurement.
#include "ecu/flex_ingress.hpp"
#include "ecu/capture_clock.hpp"
#include "esp_attr.h"
DRAM_ATTR ecu::flex::Ingress probe_ingress;
DRAM_ATTR ecu::timing::CaptureClock probe_clock;
#if FLEX_PROBE_NEGATIVE_MODE == 1
// An owned negative control must be rejected by the placement audit.
__attribute__((section(".probe_flash"))) const volatile unsigned probe_flash=7;
#endif
#if FLEX_PROBE_NEGATIVE_MODE == 2
extern "C" __attribute__((noinline)) unsigned probe_flash_helper(unsigned value){
 asm volatile("" ::: "memory");return value+1;
}
#endif
extern "C" __attribute__((used,noinline)) unsigned IRAM_ATTR
flex_ingress_isr_probe(std::uint64_t context,std::uint32_t captured,
                       std::uint64_t observed,bool high){
 const auto mapped=probe_clock.map(captured,observed);
 auto result=static_cast<unsigned>(probe_ingress.push(context,mapped.time_us,observed,high,
  mapped.error==ecu::timing::CaptureClock::Error::None,captured));
#if FLEX_PROBE_NEGATIVE_MODE == 1
 result^=probe_flash;
#endif
#if FLEX_PROBE_NEGATIVE_MODE == 2
 result=probe_flash_helper(result);
#endif
 return result;
}
// Include the owning-worker methods in the object, but outside the ISR root.
extern "C" __attribute__((used,noinline)) bool
flex_ingress_worker_probe(std::uint64_t context,std::uint64_t now){
 if(!probe_clock.sync(80000000,now,now+2))return false;
 if(!probe_ingress.begin_context(context,now+3))return false;
 return probe_ingress.arm(context,now+3);
}
