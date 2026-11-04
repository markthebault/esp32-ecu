#include "ecu/flex_fuel.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace ecu::flex;
static unsigned checks=0;
static void verify(bool value,const char*expression,unsigned line){++checks;if(!value)std::cerr<<"Failed line "<<line<<": "<<expression<<" (check "<<checks<<")\n";assert(value);}
#define check(value) verify((value),#value,__LINE__)
static void near(double actual,double expected,double epsilon=1e-9){check(std::isfinite(actual)&&std::abs(actual-expected)<=epsilon);}
static CaptureConfig fast(){CaptureConfig c;c.cycles=2;return c;}
static std::uint64_t append(Capture&capture,std::uint64_t start,unsigned count,std::uint64_t period=10000,std::uint64_t low=3000,Source source=Source::Synthetic){
 for(unsigned n=0;n<count;++n){capture.edge(start+period-low,false,source);start+=period;capture.edge(start,true,source);}return start;
}
static Capture ready(std::uint64_t&now,const CaptureConfig&config=fast()){
 Capture c(config);c.edge(0,true);now=append(c,0,config.cycles);check(c.observe(now).valid);return c;
}
static void configuration(){
 CaptureConfig c;CorrectionConfig r;check(valid(c)&&valid(r));
 for(float CaptureConfig::*member:{&CaptureConfig::low_hz,&CaptureConfig::high_hz,&CaptureConfig::fault_hz,&CaptureConfig::tolerance_hz,&CaptureConfig::stale_ms,&CaptureConfig::filter_ms}){
  auto invalid=c;invalid.*member=NAN;check(!valid(invalid));Capture capture(invalid);check(capture.observe(0).reason==Reason::InvalidConfig);capture.edge(1,true);check(!capture.observe(1).valid);
  std::uint64_t time=0;capture=ready(time);check(capture.configure(invalid));check(capture.observe(time).reason==Reason::InvalidConfig);
 }
 for(unsigned cycles:{0,1,33,255}){c=CaptureConfig{};c.cycles=static_cast<std::uint8_t>(cycles);check(!valid(c));}
 c=CaptureConfig{};c.high_hz=c.low_hz;check(!valid(c));c=CaptureConfig{};c.fault_hz=c.high_hz;check(!valid(c));
 c=CaptureConfig{};c.low_hz=10;c.tolerance_hz=2;c.stale_ms=250;check(valid(c));c.stale_ms=249;check(!valid(c));
 for(unsigned n=0;n<6;++n){
  r=CorrectionConfig{};r.fuel_pct[n]=NAN;check(!valid(r));r=CorrectionConfig{};r.spark_deg[n]=41;check(!valid(r));r=CorrectionConfig{};r.temperature_pct[n]=-1;check(!valid(r));
 }
 r=CorrectionConfig{};r.ethanol_bins[1]=r.ethanol_bins[0];check(!valid(r));r=CorrectionConfig{};r.ethanol_bins.back()=99;check(!valid(r));
 r=CorrectionConfig{};r.temperature_c.front()=-39;check(!valid(r));r=CorrectionConfig{};r.temperature_enabled=true;check(!valid(r));
}
static void nominal(){
 for(unsigned cycles:{2,8,32})for(std::uint64_t period:{6667,10000,20000})for(std::uint64_t low:{1000,3000,5000}){
  CaptureConfig config;config.cycles=static_cast<std::uint8_t>(cycles);Capture c(config);c.edge(0,true);
  auto now=append(c,0,cycles-1,period,low);auto o=c.observe(now);check(!o.valid&&o.capture_reason==Reason::Acquiring);
  now=append(c,now,1,period,low);o=c.observe(now);check(o.valid&&o.reason==Reason::Ready&&o.source==Source::Synthetic);
  check(o.window_cycles==cycles&&o.window_start_us==0&&o.sample_us==now&&o.edges==2*cycles+1);
  near(o.frequency_hz,1000000./period);near(o.low_pulse_us,low);near(o.ethanol_pct,bounded(1000000./period-50,0,100));near(o.fuel_temp_c,.04125*low-81.25);near(o.age_ms,0);
  const auto sample=o.sample_us;for(unsigned n=0;n<5;++n){o=c.observe(now+1000);check(o.sample_us==sample&&o.valid);}
 }
 // A first rising edge and a previous unrelated low edge cannot supply a
 // complete period. Width and frequency must describe the same cycles.
 Capture c(fast());c.edge(1000,false);c.edge(4000,true);check(!c.observe(4000).valid);
 auto now=append(c,4000,1);check(!c.observe(now).valid);now=append(c,now,1);check(c.observe(now).valid);
 // No 8-bit pulse-counter wrap, even after thousands of real edges.
 std::uint64_t time=0;c=ready(time);time=append(c,time,2000);auto o=c.observe(time);check(o.valid&&o.edges>4000);near(o.ethanol_pct,50);
 // Custom span is calibrated as a ratio, not just frequency minus low.
 auto config=fast();config.low_hz=20;config.high_hz=120;config.fault_hz=170;c=Capture(config);c.edge(0,true);now=append(c,0,2,12500);o=c.observe(now);check(o.valid);near(o.ethanol_pct,60);
 config=fast();config.low_hz=40;config.high_hz=160;config.fault_hz=180;c=Capture(config);c.edge(0,true);now=append(c,0,2,10000);o=c.observe(now);check(o.valid);near(o.ethanol_pct,50);
}
static void faults(){
 std::uint64_t now=0;auto c=ready(now);const auto previous=c.observe(now);
 auto o=c.observe(now+250000);check(o.valid&&o.sample_us==previous.sample_us);
 o=c.observe(now+250001);check(!o.valid&&o.reason==Reason::Stale&&o.pending_fault);
 check(c.acknowledge(o.fault_generation));check(!c.observe(now+250001).valid);
 // An incomplete final cycle must not let a newer falling edge keep a stale
 // completed measurement in the Ready state.
 c=Capture{};c.edge(0,true);now=append(c,0,8,20000);check(c.observe(now).valid);c.edge(now+17000,false);
 o=c.observe(now+251000);check(!o.valid&&o.reason==Reason::Stale&&o.pending_fault);
 // Recovery before any consumer observes the fault must remain invalid.
 c=ready(now);c.edge(now+10,false);now+=10000;c.edge(now,true);now=append(c,now,8);o=c.observe(now);
 check(!o.valid&&o.pending_fault&&o.reason==Reason::Glitch&&o.capture_reason==Reason::Ready);
 check(c.acknowledge(o.fault_generation));check(c.observe(now).valid);
 check(!c.acknowledge(o.fault_generation));
 c=ready(now);c.edge(now+1000,true);now=append(c,now+1000,4);o=c.observe(now);check(!o.valid&&o.reason==Reason::RepeatedLevel);check(c.acknowledge(o.fault_generation));check(c.observe(now).valid);
 c=ready(now);c.edge(now-1,false);o=c.observe(now);check(!o.valid&&o.reason==Reason::TimeReversed);
 c=ready(now);c.edge(now,false);check(c.observe(now).reason==Reason::TimeReversed);
 c=ready(now);c.edge(now+1000,false);o=c.observe(now);check(!o.valid&&o.reason==Reason::Future);
 c=ready(now);o=c.observe(now-1);check(!o.valid&&o.reason==Reason::TimeReversed);
 c=ready(now);c.edge(now+250001,false);o=c.observe(now+250001);check(!o.valid&&o.reason==Reason::Gap);
 c=ready(now);c.edge(now+1000,false,static_cast<Source>(99));o=c.observe(now+1000);check(!o.valid&&o.reason==Reason::Unavailable);
 c=ready(now);now=append(c,now,8,10000,3000,Source::TargetCapture);o=c.observe(now);check(!o.valid&&o.reason==Reason::SourceChanged&&o.source==Source::TargetCapture);check(c.acknowledge(o.fault_generation));check(c.observe(now).valid);
 c=ready(now);auto config=fast();config.filter_ms=100;check(c.configure(config));check(!c.configure(config));now=append(c,now,5);o=c.observe(now);check(!o.valid&&o.reason==Reason::ConfigurationChanged&&o.config_epoch==2);check(c.acknowledge(o.fault_generation));check(c.observe(now).valid);
 // Consumer cannot acknowledge an unobserved fault or a newer fault using
 // the ticket from an earlier control observation.
 c=ready(now);c.overflow();check(!c.acknowledge(1));o=c.observe(now);c.overflow();check(!c.acknowledge(o.fault_generation));now=append(c,now,5);o=c.observe(now);check(o.reason==Reason::Overflow&&o.pending_fault);check(c.acknowledge(o.fault_generation));check(c.observe(now).valid);
 for(std::uint64_t period:{5000,4000,2000}){
  c=Capture(fast());c.edge(0,true);now=append(c,0,5,period,1000);o=c.observe(now);check(!o.valid&&o.reason==Reason::SensorFault);
 }
 for(std::uint64_t period:{6452,25000}){
  c=Capture(fast());c.edge(0,true);now=append(c,0,5,period,1000);o=c.observe(now);check(!o.valid&&o.reason==Reason::Frequency);
 }
 for(std::uint64_t low:{500,5500}){
  c=Capture(fast());c.edge(0,true);now=append(c,0,5,10000,low);o=c.observe(now);check(!o.valid&&o.reason==Reason::PulseWidth);
 }
 c=Capture(fast());const auto max=std::numeric_limits<std::uint64_t>::max();c.edge(max-1,true);c.edge(max,false);o=c.observe(max);check(!o.valid&&o.reason==Reason::Glitch);c.edge(0,true);check(c.observe(max).reason==Reason::TimeReversed);
}
static void filtering_and_corrections(){
 auto config=fast();config.filter_ms=200;Capture a(config),b(config);a.edge(0,true);b.edge(0,true);std::uint64_t now=0;
 for(unsigned n=0;n<60;++n){const std::uint64_t period=n<20?10000:6667;
  a.edge(now+period-3000,false);a.observe(now+period-3000);a.edge(now+period,true);a.observe(now+period);
  b.edge(now+period-3000,false);b.edge(now+period,true);now+=period;
 }
 auto oa=a.observe(now),ob=b.observe(now);check(oa.valid&&ob.valid&&oa.sample_us==ob.sample_us);near(oa.ethanol_pct,ob.ethanol_pct);near(oa.fuel_temp_c,ob.fuel_temp_c);check(oa.ethanol_pct>50&&oa.ethanol_pct<100);
 config=fast();auto c=ready(now,config);auto sample=c.observe(now);CorrectionConfig r;
 auto result=evaluate(r,config,Observation{},now);check(result.valid&&result.reason==Reason::Disabled);near(result.fuel_factor,1);near(result.spark_add_deg,0);near(result.temperature_factor,1);
 r.enabled=true;result=evaluate(r,config,sample,now);check(result.valid);near(result.fuel_factor,1);near(result.spark_add_deg,0);near(result.temperature_factor,1);
 r.fuel_pct={{100,110,120,130,140,150}};r.spark_deg={{-10,-6,-2,2,6,10}};r.temperature_pct={{80,90,95,100,110,120}};r.temperature_enabled=true;
 result=evaluate(r,config,sample,now);check(result.valid);near(result.fuel_factor,1.25);near(result.spark_add_deg,0);near(result.temperature_factor,1.00625);
 result=evaluate(r,config,sample,now-1);check(!result.valid&&result.reason==Reason::Future&&std::isnan(result.fuel_factor));
 result=evaluate(r,config,sample,now+250001);check(!result.valid&&result.reason==Reason::Stale);
 sample.ethanol_pct=NAN;check(!evaluate(r,config,sample,now).valid);sample=c.observe(now);sample.source=Source::Unavailable;check(!evaluate(r,config,sample,now).valid);
 c.overflow();sample=c.observe(now);check(!evaluate(r,config,sample,now).valid);
 r.fuel_pct.fill(0);sample.valid=true;sample.pending_fault=false;sample.reason=Reason::Ready;sample.ethanol_pct=50;sample.fuel_temp_c=42.5;sample.source=Source::Synthetic;result=evaluate(r,config,sample,now);check(result.valid&&result.fuel_factor==0);
 r.enabled=false;r.temperature_enabled=false;check(evaluate(r,config,Observation{},now).valid);
}
int main(){configuration();nominal();faults();filtering_and_corrections();std::cout<<"flex_fuel_checks "<<checks<<"\n";}
