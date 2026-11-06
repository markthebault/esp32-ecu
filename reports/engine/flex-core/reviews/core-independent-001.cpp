#include "ecu/flex_fuel.hpp"
#include <iostream>
#include <vector>
#include <numeric>
#include <stdexcept>
#include <limits>
using namespace ecu::flex;
static unsigned checks=0;
static void ck(bool b,const char*m){++checks;if(!b)throw std::runtime_error(m);}
static void eq(double a,double b,const char*m){ck(std::isfinite(a)&&std::abs(a-b)<1e-9,m);}
static std::uint64_t cycle(Capture&c,std::uint64_t now,std::uint64_t p,std::uint64_t w,Source s=Source::Synthetic){c.edge(now+p-w,false,s);c.edge(now+p,true,s);return now+p;}
static Capture seed(std::uint64_t&now,Source s=Source::Synthetic){Capture c;c.edge(now,true,s);for(unsigned n=0;n<8;++n)now=cycle(c,now,10000,3000,s);ck(c.observe(now).valid,"seed ready");return c;}
int main(){try{
 // Independent rolling-window oracle with unequal periods and low widths.
 for(unsigned size:{2,8,32}){
  CaptureConfig cfg;cfg.cycles=static_cast<std::uint8_t>(size);Capture c(cfg);std::uint64_t now=500000;const auto origin=now;c.edge(now,true);
  std::vector<std::uint64_t> periods,widths;
  for(unsigned n=0;n<100;++n){
   const auto period=std::uint64_t(7000+(n*7919)%13000),width=std::uint64_t(1000+(n*1031)%4001);
   now=cycle(c,now,period,width);periods.push_back(period);widths.push_back(width);
   auto o=c.observe(now);const unsigned count=std::min(n+1,size);
   const auto sp=std::accumulate(periods.end()-count,periods.end(),std::uint64_t(0));
   const auto sw=std::accumulate(widths.end()-count,widths.end(),std::uint64_t(0));
   ck(o.window_cycles==count,"bounded window count");ck(o.window_start_us==now-sp&&o.window_start_us>=origin,"coherent window start");
   eq(o.frequency_hz,1000000.*count/sp,"frequency oracle");eq(o.low_pulse_us,double(sw)/count,"width oracle");
   ck(o.valid==(count==size),"full window validity");
   if(o.valid){eq(o.ethanol_pct,bounded(1000000.*count/sp-50,0,100),"calibration oracle");eq(o.fuel_temp_c,.04125*sw/count-81.25,"temperature oracle");}
  }
 }
 // Unknown/malformed sources must invalidate and cannot be repaired with ACK alone.
 for(Source bad:{Source::Unavailable,static_cast<Source>(255)}){
  std::uint64_t now=0;auto c=seed(now);c.edge(now+7000,false,bad);auto o=c.observe(now+7000);
  ck(!o.valid&&o.reason==Reason::Unavailable&&o.pending_fault,"malformed source invalid");
  ck(c.acknowledge(o.fault_generation),"source fault acknowledged");ck(!c.observe(now+7000).valid,"ACK cannot recreate series");
  now+=10000;c.edge(now,true);for(unsigned n=0;n<7;++n)now=cycle(c,now,10000,3000);
  ck(!c.observe(now).valid,"recovery needs all cycles");now=cycle(c,now,10000,3000);ck(c.observe(now).valid,"full recovery");
 }
 // Source changes discard all previous periods and LPF history; pending faults survive reacquisition.
 {
  CaptureConfig cfg;cfg.filter_ms=5000;Capture c(cfg);std::uint64_t now=0;c.edge(now,true);
  for(unsigned n=0;n<8;++n)now=cycle(c,now,20000,1000);
  auto o=c.observe(now);eq(o.ethanol_pct,0,"initial fuel0");eq(o.fuel_temp_c,-40,"initial temperature");
  now=cycle(c,now,10000,5000,Source::TargetCapture);o=c.observe(now);
  ck(o.pending_fault&&!o.valid&&o.reason==Reason::SourceChanged&&o.window_cycles==0,"source change drops cross-source cycle");
  const auto source_seed=now;
  for(unsigned n=0;n<7;++n)now=cycle(c,now,10000,5000,Source::TargetCapture);
  o=c.observe(now);ck(o.window_cycles==7&&!o.valid,"new source full window");
  now=cycle(c,now,10000,5000,Source::TargetCapture);o=c.observe(now);
  ck(o.pending_fault&&!o.valid&&o.capture_reason==Reason::Ready,"source pending survives readiness");
  ck(o.window_start_us==source_seed,"source coherent origin");eq(o.ethanol_pct,50,"source LPF reset");eq(o.fuel_temp_c,125,"source temp LPF reset");
  ck(c.acknowledge(o.fault_generation),"source fault ACK");ck(c.observe(now).valid,"source valid after observation ACK");
  const auto epoch=o.config_epoch;cfg.low_hz=40;cfg.high_hz=160;cfg.fault_hz=180;ck(c.configure(cfg),"new calibration applied");
  o=c.observe(now);ck(o.config_epoch==epoch+1&&o.window_cycles==0&&std::isnan(o.ethanol_pct),"config resets series");
  ck(!c.configure(cfg),"same config no epoch change");
 }
 // Unobserved or superseded generations cannot be ACKed, even after recovery.
 {
  std::uint64_t now=0;auto c=seed(now);c.overflow();ck(!c.acknowledge(1),"unobserved overflow ACK denied");
  auto o=c.observe(now);const auto old=o.fault_generation;c.overflow();
  ck(!c.acknowledge(old),"old generation denied");
  for(unsigned n=0;n<10;++n)now=cycle(c,now,10000,3000);
  ck(!c.acknowledge(old+1),"new but unobserved generation denied");
  o=c.observe(now);ck(!o.valid&&o.pending_fault&&o.capture_reason==Reason::Ready,"hidden recovery still pending");
  ck(c.acknowledge(o.fault_generation)&&!c.acknowledge(o.fault_generation),"single successful ACK");ck(c.observe(now).valid,"acknowledged recovered series ready");
 }
 // Strict timestamp ordering and arithmetic remain valid beyond32-bit wrap and near UINT64_MAX.
 for(std::uint64_t start:{std::uint64_t(0xffffffffULL-20000),std::numeric_limits<std::uint64_t>::max()-80000}){
  auto now=start;auto c=seed(now);auto o=c.observe(now);ck(o.valid&&o.window_start_us==start&&o.sample_us==now,"large64 origin");
  eq(o.ethanol_pct,50,"large64 calibration");c.edge(now,false);o=c.observe(now);ck(o.reason==Reason::TimeReversed&&!o.valid,"duplicate timestamp invalid");
 }
 // Completed-sample staleness cannot be postponed by an incomplete last low pulse.
 {
  std::uint64_t now=0;auto c=seed(now);c.edge(now+7000,false);auto o=c.observe(now+250000);ck(o.valid,"inclusive stale boundary");
  o=c.observe(now+250001);ck(!o.valid&&o.reason==Reason::Stale&&o.pending_fault,"completed sample stale reason");
  const auto generation=o.fault_generation;for(unsigned n=0;n<4;++n){o=c.observe(now+250001+n);ck(o.fault_generation==generation,"held stale one generation");}
  ck(c.acknowledge(generation),"stale ACK");ck(!c.observe(now+250005).valid,"stale ACK not valid");
 }
 // Whole correction validation and finite factors across all segment boundaries.
 {
  CorrectionConfig cfg;cfg.enabled=cfg.temperature_enabled=true;cfg.fuel_pct={{0,25,100,150,200,255}};cfg.spark_deg={{-40,-20,-1,1,20,40}};cfg.temperature_pct={{255,200,150,100,25,0}};
  Observation o;o.source=Source::Synthetic;o.valid=true;o.reason=Reason::Ready;o.sample_us=12345;
  for(unsigned n=0;n<6;++n){o.ethanol_pct=cfg.ethanol_bins[n];o.fuel_temp_c=cfg.temperature_c[n];const auto x=evaluate(cfg,CaptureConfig{},o,o.sample_us);ck(x.valid,"curve boundary valid");eq(x.fuel_factor,cfg.fuel_pct[n]/100.,"fuel endpoint");eq(x.spark_add_deg,cfg.spark_deg[n],"spark endpoint");eq(x.temperature_factor,cfg.temperature_pct[n]/100.,"temperature endpoint");}
  for(double v:{-1.,101.,std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()}){o.ethanol_pct=v;ck(!evaluate(cfg,CaptureConfig{},o,o.sample_us).valid,"unbounded sample denied");}
  cfg.enabled=cfg.temperature_enabled=false;const auto off=evaluate(cfg,CaptureConfig{},Observation{},0);ck(off.valid&&off.reason==Reason::Disabled,"Off preserves neutral");eq(off.fuel_factor,1,"Off factor");
 }
 std::cout<<"independent_core_checks "<<checks<<"\n";return 0;
}catch(const std::exception&e){std::cerr<<"failure after "<<checks<<": "<<e.what()<<"\n";return 1;}}
