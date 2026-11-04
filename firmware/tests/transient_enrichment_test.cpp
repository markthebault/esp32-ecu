#include "ecu/transient_enrichment.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::transient;
Input sample(std::uint64_t time,double tps=10,double map=40){return {tps,map,1000,85,time,true};}
Config rate_mode(Mode mode=Mode::TpsRate){Config c;c.mode=mode;return c;}
Output ramp(Controller&controller,const Config&c,std::uint64_t start=0,double tps_rate=100,double map_rate=200){
 Output out;for(unsigned n=0;n<=4;++n){auto i=sample(start+n*5000,10+tps_rate*n*.005,40+map_rate*n*.005);out=controller.step(c,i,i.sampled_us);}return out;
}
void acquisitions(){
 for(auto mode:{Mode::TpsRate,Mode::MapRate}){
  Controller controller;auto c=rate_mode(mode);auto out=ramp(controller,c);
  assert(out.active()&&out.values[TpsDot]==100&&out.values[MapDot]==200&&out.values[WindowMs]==20);
  assert(std::abs(out.correction()-(mode==Mode::TpsRate?1.1:1.15))<1e-6);
 }
 Controller delayed;auto c=rate_mode();Output out;
 for(unsigned n=0;n<=4;++n){auto i=sample(n*5000,10+n*.5);out=delayed.step(c,i,i.sampled_us+15000);}
 assert(out.values[TpsDot]==100&&out.values[RemainingMs]==185);
 out=delayed.step(c,sample(20000,12),40000);assert(out.values[TpsDot]==100&&out.values[RemainingMs]==180);
}
void expiry_and_retrigger(){
 auto c=rate_mode();c.sample_period_ms=100;c.duration_ms=10;Controller controller;Output out;
 for(unsigned n=0;n<=20;++n){auto i=sample(n*5000,10+n*.5);out=controller.step(c,i,i.sampled_us);}
 assert(out.active()&&out.values[RemainingMs]==10);
 out=controller.step(c,sample(105000,20),105000);assert(out.active());
 out=controller.step(c,sample(105000,20),110000);assert(!out.active()&&out.reason==Reason::Expired&&out.correction()==1);
 c=rate_mode();Controller strong;ramp(strong,c);
 for(unsigned n=1;n<=4;++n)out=strong.step(c,sample(20000+n*5000,12+n),20000+n*5000);
 assert(out.values[TriggerDot]==200&&out.flags&Retriggered&&out.values[RemainingMs]==200);
 // A sample arriving exactly when the old hold expires is still an event.
 c.duration_ms=20;Controller coincident,polled;ramp(coincident,c);ramp(polled,c);
 for(unsigned n=1;n<=3;++n){const auto i=sample(20000+n*5000,12+n);coincident.step(c,i,i.sampled_us);polled.step(c,i,i.sampled_us);}
 auto fresh=coincident.step(c,sample(40000,16),40000);
 auto neutral=polled.step(c,sample(35000,15),40000);assert(!neutral.active());
 auto late=polled.step(c,sample(40000,16),41000);
 assert(fresh.active()&&late.active()&&fresh.values[TriggerDot]==200&&late.values[TriggerDot]==200);
 assert(fresh.correction()==late.correction()&&fresh.values[RemainingMs]==20&&late.values[RemainingMs]==19);
 c.duration_ms=0;Controller zero;out=ramp(zero,c);assert(!out.active()&&out.correction()==1);
}
void reversal(){
 for(double fall:{-50.,-20.}){
  Controller controller;auto c=rate_mode();c.tps_min_change_pct=0;c.decel_fuel_pct=80;ramp(controller,c);Output out;
  for(unsigned n=1;n<=4;++n)out=controller.step(c,sample(20000+n*5000,12+fall*n*.005),20000+n*5000);
  assert(out.flags&Reversed);
  if(fall== -50)assert(out.phase==Phase::Deceleration&&std::abs(out.correction()-.8)<1e-6);
  else assert(!out.active()&&out.correction()==1&&out.reason==Reason::Reversed);
 }
}
void tapers_and_resets(){
 auto c=rate_mode();c.cold_multiplier_pct=200;Controller controller;Output out;
 for(unsigned n=0;n<=4;++n){auto i=sample(n*5000,10+n);i.rpm=4500;i.clt_c=35;out=controller.step(c,i,i.sampled_us);}
 assert(std::abs(out.correction()-1.1125)<1e-6);
 for(unsigned n=1;n<=4;++n){auto i=sample(20000+n*5000,14);i.rpm=5500;i.clt_c=100;out=controller.step(c,i,i.sampled_us);}
 assert(std::abs(out.correction()-1.1125)<1e-6); // Tapers latch with the event.
 c.max_enrichment_pct=5;out=controller.step(c,sample(45000,90),45000);assert(!out.active());
 for(unsigned n=1;n<=4;++n){auto i=sample(45000+n*5000,90+n);i.rpm=4500;i.clt_c=35;out=controller.step(c,i,i.sampled_us);}
 assert(std::abs(out.correction()-1.05)<1e-6&&out.flags&Clamped);
 out=controller.step(c,sample(90000,95),90000);assert(out.reason==Reason::AcquisitionGap&&!out.active());
 out=controller.step(c,sample(85000,90),95000);assert(out.reason==Reason::AcquisitionClock&&!out.active());
 auto bad=sample(100000,90);bad.eligible=false;out=controller.step(c,bad,100000);assert(!out.active()&&std::isnan(out.values[TpsDot]));
 out=controller.step(c,sample(105000,10),105000);assert(!out.active());
 out=controller.step(c,sample(104000,80),104000);assert(!out.active()&&out.reason==Reason::ControlClock);
}
int main(){assert(valid(Config{}));acquisitions();expiry_and_retrigger();reversal();tapers_and_resets();std::cout<<"Acquisition-time rate windows, hold/expiry, retrigger/reversal, tapered/clamped demand and recovery history passed\n";}
