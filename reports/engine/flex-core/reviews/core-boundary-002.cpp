#include "ecu/flex_fuel.hpp"
#include <iostream>
#include <stdexcept>
using namespace ecu::flex;
static unsigned checks=0;
static void ck(bool value,const char*message){++checks;if(!value)throw std::runtime_error(message);}
static void quantized(const CaptureConfig&cfg,double hz,double phase,bool accepted,Reason why){
 Capture c(cfg);auto start=static_cast<std::uint64_t>(std::llround(phase));c.edge(start,true);
 for(unsigned n=1;n<=65;++n){const auto now=static_cast<std::uint64_t>(std::llround(n*1000000./hz+phase));c.edge(now-3000,false);c.edge(now,true);const auto o=c.observe(now);
  if(accepted){ck(o.fault_generation==0&&!o.pending_fault,"quantized endpoint must never fault");ck(o.valid==(n>=cfg.cycles),"endpoint full-window readiness");if(o.valid){ck(o.frequency_hz>0&&o.ethanol_pct>=0&&o.ethanol_pct<=100,"endpoint finite percent");}}
  else ck(!o.valid&&o.pending_fault&&o.reason==why,"outside interval must fault with expected class");
 }
}
static void period(std::uint64_t p,bool accepted,Reason why){CaptureConfig cfg;cfg.cycles=2;Capture c(cfg);c.edge(0,true);for(unsigned n=1;n<=4;++n){const auto t=n*p;c.edge(t-3000,false);c.edge(t,true);}const auto o=c.observe(4*p);ck(o.valid==accepted,"integer-period acceptance");if(!accepted)ck(o.reason==why,"integer-period fault class");}
int main(){try{
 for(unsigned count:{2,8,32})for(double phase:{0.,.1,.49,.75}){
  CaptureConfig cfg;cfg.cycles=static_cast<std::uint8_t>(count);
  quantized(cfg,49,phase,true,Reason::Ready);quantized(cfg,151,phase,true,Reason::Ready);
  quantized(cfg,48.9,phase,false,Reason::Frequency);quantized(cfg,151.1,phase,false,Reason::Frequency);
  quantized(cfg,169.8,phase,false,Reason::Frequency);quantized(cfg,170,phase,false,Reason::SensorFault);quantized(cfg,170.2,phase,false,Reason::SensorFault);
  cfg.tolerance_hz=0;quantized(cfg,50,phase,true,Reason::Ready);quantized(cfg,150,phase,true,Reason::Ready);
  cfg.low_hz=10;cfg.high_hz=20;cfg.fault_hz=25;cfg.tolerance_hz=2;quantized(cfg,8,phase,true,Reason::Ready);quantized(cfg,22,phase,true,Reason::Ready);
  cfg.low_hz=180;cfg.high_hz=200;cfg.fault_hz=205;quantized(cfg,178,phase,true,Reason::Ready);quantized(cfg,202,phase,true,Reason::Ready);
 }
 // At default tolerance boundaries,1us intervals that overlap the boundary
 // are admitted; periods beyond the overlap are rejected.
 period(6622,true,Reason::Ready);period(6621,false,Reason::Frequency);
 period(20409,true,Reason::Ready);period(20410,false,Reason::Frequency);
 // Sensor-fault threshold is deliberately conservative for quantized periods.
 period(5883,false,Reason::SensorFault);period(5884,false,Reason::Frequency);
 std::cout<<"independent_boundary_checks "<<checks<<"\n";return 0;
}catch(const std::exception&e){std::cerr<<"failure after "<<checks<<": "<<e.what()<<"\n";return 1;}}
