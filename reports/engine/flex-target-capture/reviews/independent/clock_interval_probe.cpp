#include "ecu/capture_clock.hpp"
#include "ecu/flex_fuel.hpp"
#define ecu old_ecu
#include "freeze-001/firmware/include/ecu/capture_clock.hpp"
#undef ecu
#include <cstdio>
#include <cstdlib>
static unsigned checks=0,waves=0;
static void check(bool v,const char*label){++checks;if(!v){std::fprintf(stderr,"check%u %s\n",checks,label);std::abort();}}
int main(){
 using Clock=ecu::timing::CaptureClock;
 constexpr std::uint64_t before=1000;
 for(unsigned bracket=0;bracket<=10;++bracket)for(unsigned offset=0;offset<=bracket;++offset)
 for(unsigned event_phase:{0U,79U})for(unsigned sync_phase:{0U,79U})
 for(unsigned width:{1000U,3000U,5000U})for(unsigned lag:{0U,5U,100U})
 for(std::uint64_t wrap:{0ULL,53687091ULL,107374182ULL}){
  Clock clock;check(clock.sync(80000000,before,before+bracket),"valid bracket");ecu::flex::CaptureConfig config;config.cycles=2;ecu::flex::Capture capture(config);
  const auto raw=[&](std::uint64_t t){return static_cast<std::uint32_t>((t-before-offset)*80+event_phase-sync_phase);};
  std::uint64_t query=0;
  for(unsigned cycle=0;cycle<3;++cycle){
   const auto rise=10000+wrap+cycle*10000;const auto delivered=rise+(cycle%2?lag:0);
   const auto stamp=clock.map_interval(raw(rise),delivered);check(stamp.error==Clock::Error::None,"rise mapping accepted");check(stamp.time_us<=delivered&&stamp.time_us>=rise-offset-1&&stamp.time_us<=rise-offset,"fixed conservative rise timestamp");
   check(clock.map_interval(raw(rise),rise+200).time_us==stamp.time_us,"rise timestamp independent of callback lag");capture.edge(stamp.time_us,true,ecu::flex::Source::TargetCapture);query=delivered;
   if(cycle==2)break;
   const auto fall=rise+10000-width;const auto observed=fall+(cycle%2?0:lag);
   const auto f=clock.map_interval(raw(fall),observed);check(f.error==Clock::Error::None,"fall mapping accepted");check(f.time_us<=observed&&clock.map_interval(raw(fall),fall+200).time_us==f.time_us,"fall timestamp independent of lag");capture.edge(f.time_us,false,ecu::flex::Source::TargetCapture);query=observed;
  }
  const auto s=capture.observe(query);check(s.valid&&s.low_pulse_us==width&&s.frequency_hz==100,"raw capture width preserved at endpoints and wraps");++waves;
 }
 Clock current;old_ecu::timing::CaptureClock old;
 for(unsigned bracket=0;bracket<=10;++bracket){check(current.sync(80000000,1000,1000+bracket)&&old.sync(80000000,1000,1000+bracket),"legacy bracket setup");
  for(unsigned n=0;n<1000;++n){const std::uint64_t observed=1100+std::uint64_t(n)*53687;const auto raw=static_cast<std::uint32_t>((observed-1000)*80+static_cast<std::uint32_t>(n*9973));const auto a=current.map(raw,observed);const auto b=old.map(raw,observed);check(static_cast<unsigned>(a.error)==static_cast<unsigned>(b.error)&&a.time_us==b.time_us&&a.age_us==b.age_us,"old crank mapping behavior unchanged");}}
 Clock bounded;check(bounded.sync(80000000,1000,1010),"bounded clock init");check(bounded.map_interval(0,999).error==Clock::Error::BeforeEpoch,"before epoch rejected");check(bounded.map_interval(80000,1500).error==Clock::Error::Future,"whole-us future rejected");check(bounded.map_interval(0,6001).error==Clock::Error::TooOld,"old capture rejected");
 check(bounded.sync(80000000,UINT64_MAX-10,UINT64_MAX),"near U64 sync safe");check(bounded.map_interval(0,UINT64_MAX-10).time_us==UINT64_MAX-10,"near U64 map safe");
 std::printf("independent_interval_checks %u waves %u\n",checks,waves);
}
