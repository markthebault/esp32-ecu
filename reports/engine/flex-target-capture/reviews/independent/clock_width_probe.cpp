#include "ecu/capture_clock.hpp"
#include "ecu/flex_fuel.hpp"
#include <cstdio>
int main(){
 for(const unsigned width:{1000U,5000U}){
  ecu::timing::CaptureClock clock;if(!clock.sync(80000000,1000,1010))return 1;
  ecu::flex::CaptureConfig cfg;cfg.cycles=2;ecu::flex::Capture capture(cfg);
  unsigned errors=0;std::uint64_t now=0;
  for(unsigned cycle=0;cycle<3;++cycle){
   const std::uint64_t rise=10000+10000*cycle;
   const auto rise_delay=width==5000?5U:0U;
   auto r=clock.map(static_cast<std::uint32_t>((rise-1000)*80),rise+rise_delay);
   errors+=r.error!=ecu::timing::CaptureClock::Error::None;capture.edge(r.time_us,true,ecu::flex::Source::TargetCapture);now=rise+rise_delay;
   if(cycle==2)break;
   const auto fall=rise+10000-width;const auto fall_delay=width==1000?5U:0U;
   r=clock.map(static_cast<std::uint32_t>((fall-1000)*80),fall+fall_delay);
   errors+=r.error!=ecu::timing::CaptureClock::Error::None;capture.edge(r.time_us,false,ecu::flex::Source::TargetCapture);now=fall+fall_delay;
  }
  const auto s=capture.observe(now);
  std::printf("{\"physical_low_us\":%u,\"epoch_bracket_us\":10,\"clock_uncertainty_us\":%u,\"clock_errors\":%u,\"latency_options_us\":[0,5],\"measured_low_us\":%.1f,\"reason\":\"%s\",\"valid\":%s}\n",width,clock.uncertainty_us(),errors,s.low_pulse_us,ecu::flex::reason_name(s.reason),s.valid?"true":"false");
 }
}
