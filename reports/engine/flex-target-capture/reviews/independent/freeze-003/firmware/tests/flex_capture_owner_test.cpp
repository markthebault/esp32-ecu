#include "ecu/flex_capture_owner.hpp"
#include "ecu/engine.hpp"
#include "ecu/capture_clock.hpp"
#include <cassert>
#include <functional>
#include <iostream>
using namespace ecu::flex;
static unsigned checks=0;
static void verify(bool v,const char*expression,unsigned line){++checks;if(!v)std::cerr<<"Failed line "<<line<<": "<<expression<<" (check "<<checks<<")\n";assert(v);}
#define check(v) verify((v),#v,__LINE__)
struct Backend {
 CapturePort port;std::uint64_t now=1000;std::uint32_t epoch=1;
 bool bound=true,available=true;std::function<void()> before_publish,before_ack;
 CaptureWork configure(const CaptureRequest&r,bool valid,std::uint64_t stale){return port.configure(r,epoch,bound,available,valid,stale,now);}
 bool arm(CaptureVersion v){return port.arm(v,now);}
 CaptureWork work(){return port.work();}
 bool pop(CaptureVersion v,IngressEdge&e){return port.pop(v,e);}
 bool publish(CaptureVersion v,const Sample&s){if(before_publish){auto f=std::move(before_publish);before_publish={};f();}return port.publish(v,s,now);}
 CaptureView view(){return port.view(now);}
 bool acknowledge(const CaptureView&v){if(before_ack){auto f=std::move(before_ack);before_ack={};f();}return port.acknowledge(v,now);}
 std::uint64_t clock(){return now;}
 Ingress::Result edge(std::uint64_t t,bool high,bool good_clock=true){check(t>=now);now=t;return port.push(t,now,high,good_clock,static_cast<std::uint32_t>(t*80));}
};
static CaptureRequest requested(){CaptureRequest r;r.tune_revision=r.sensor_revision=1;r.required=r.confirmed=true;r.calibration.cycles=2;return r;}
static Evaluation evaluation(const CaptureRequest&r,const CaptureView&v,std::uint64_t now){Config c;c.capture=r.calibration;c.correction.enabled=r.required;c.input_confirmed=r.confirmed;return assess(c,v.sample,now,false,r.tune_revision,v.current);}
static std::uint64_t wave(Backend&b,std::uint64_t start,unsigned cycles=2,std::uint64_t period=10000,std::uint64_t width=3000){
 check(b.edge(start,true)==Ingress::Result::Accepted);
 for(unsigned n=1;n<=cycles;++n){check(b.edge(start+n*period-width,false)==Ingress::Result::Accepted);check(b.edge(start+n*period,true)==Ingress::Result::Accepted);}
 return b.now;
}
static ecu::engine::Output control(const CaptureRequest&r,const CaptureView&v,std::uint64_t now){
 using namespace ecu::engine;Tune t;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);t.flex_fuel.capture=r.calibration;t.flex_fuel.correction.enabled=r.required;t.flex_fuel.input_confirmed=r.confirmed;t.revision=r.tune_revision;
 Inputs in;in.rpm=2000;in.map_kpa=50;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;
 in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;in.sampled_us=now;in.flex_sample=v.sample;in.flex_context_match=v.current;
 Controller c;return c.step(t,in,now);
}
static void nominal_and_deadline(){
 Backend b;CaptureOwner owner;auto r=requested();auto v=owner.tick(b,r);
 check(v.current&&!v.sample.observation.valid&&!evaluation(r,v,b.now).control_ok&&b.port.armed());
 check(!owner.control_observed(b,v,evaluation(r,v,b.now),true));
 wave(b,2000);v=owner.tick(b,r);const auto&o=v.sample.observation;
 check(v.current&&o.valid&&o.source==Source::TargetCapture&&o.frequency_hz==100&&o.ethanol_pct==50&&o.fuel_temp_c==42.5);
 check(v.sample.tune_revision==1&&same(v.sample.calibration,r.calibration));check(evaluation(r,v,b.now).control_ok&&!control(r,v,b.now).faults);
 const auto old=v.ticket;check(old.sample_us==22000&&old.valid_until_us==272000&&b.port.can_issue(old,b.now,false));
 check(b.port.can_dispatch(old,272000,false)&&!b.port.can_dispatch(old,272001,false));
 check(b.edge(29000,false)==Ingress::Result::Accepted&&b.edge(32000,true)==Ingress::Result::Accepted);
 v=owner.tick(b,r);check(v.sample.observation.valid&&v.ticket.sample_us==32000&&v.ticket.valid_until_us==282000);
 check(!b.port.can_issue(old,b.now,false)&&b.port.can_dispatch(old,b.now,false));
 check(!b.port.can_dispatch(old,272001,false)&&b.port.can_dispatch(v.ticket,272001,false));
 auto forged=v.ticket;forged.valid_until_us+=1;check(!b.port.can_issue(forged,b.now,false));
 forged=v.ticket;forged.sample_us+=1;check(!b.port.can_issue(forged,b.now,false));
 // A current ADC/control timestamp never refreshes the raw capture window.
 b.now=282001;v=owner.tick(b,r);check(!v.sample.observation.valid&&v.sample.observation.reason==Reason::Stale);
 check(control(r,v,b.now).fuel_cut&&control(r,v,b.now).spark_cut);
 check(!b.port.can_dispatch(old,b.now,false));check(owner.control_observed(b,v,evaluation(r,v,b.now),true));
}
static void overflow_ack_and_rearm(){
 Backend b;CaptureOwner owner;auto r=requested();owner.tick(b,r);wave(b,2000);auto good=owner.tick(b,r);const auto command=good.ticket;
 for(unsigned n=1;n<=64;++n)check(b.edge(b.now+2000,n%2==0)==Ingress::Result::Accepted);
 check(b.edge(b.now+2000,false)==Ingress::Result::Suppress);check(!b.port.can_dispatch(command,b.now,false));
 auto v=owner.tick(b,r);auto e=evaluation(r,v,b.now);check(v.current&&v.ack_eligible&&!v.sample.observation.valid&&v.sample.observation.pending_fault);
 check(v.sample.observation.reason==Reason::Overflow&&v.ingress_ticket.generation==1);
 for(unsigned n=0;n<20;++n){const auto stats=b.port.snapshot(b.now);check(stats.work.ingress.pending_fault&&stats.view.ack_eligible);}
 check(!owner.control_observed(b,v,e,false));check(b.port.work().ingress.pending_fault);
 auto bad=e;++bad.sample.tune_revision;check(!owner.control_observed(b,v,bad,true));
 check(owner.control_observed(b,v,e,true));check(!owner.control_observed(b,v,e,true));
 const auto suppressed=b.port.work().ingress.last_suppression_us;
 b.now=suppressed+49999;v=owner.tick(b,r);check(!b.port.armed()&&!v.sample.observation.valid);
 b.now=suppressed+50000;v=owner.tick(b,r);check(b.port.armed()&&!v.sample.observation.valid);
 check(!b.port.can_dispatch(command,b.now,false));
 wave(b,b.now+1);v=owner.tick(b,r);check(v.sample.observation.valid&&evaluation(r,v,b.now).control_ok);
 check(v.sample.observation.edges>good.sample.observation.edges);check(b.port.work().ingress.counters.discarded==64);
}
static void publication_and_control_races(){
 Backend b;CaptureOwner owner;auto r=requested();owner.tick(b,r);wave(b,2000);auto good=owner.tick(b,r);
 check(b.edge(29000,false)==Ingress::Result::Accepted&&b.edge(32000,true)==Ingress::Result::Accepted);
 b.before_publish=[&](){b.port.fence(b.now);++b.epoch;};
 auto v=owner.tick(b,r);check(!v.current&&v.sample.observation.sample_us==good.sample.observation.sample_us);
 check(!evaluation(r,v,b.now).configuration_match&&!evaluation(r,v,b.now).control_ok&&control(r,v,b.now).fuel_cut);
 check(!owner.control_observed(b,v,evaluation(r,v,b.now),true));
 v=owner.tick(b,r);auto e=evaluation(r,v,b.now);check(v.current&&v.ack_eligible&&v.sample.observation.pending_fault&&!v.sample.observation.valid);
 check(v.sample.observation.window_cycles==0&&v.sample.observation.config_epoch>good.sample.observation.config_epoch);
 // A newer ISR-side clock fault between step completion and ACK invalidates
 // the publication ticket. The owner's old capture notification also stays.
 b.before_ack=[&](){const auto w=b.port.work();b.port.configure(r,b.epoch,true,true,true,250000,b.now-1);check(b.port.work().ingress.fault_generation>w.ingress.fault_generation);};
 check(!owner.control_observed(b,v,e,true));
 v=owner.tick(b,r);check(v.sample.observation.pending_fault);check(owner.control_observed(b,v,evaluation(r,v,b.now),true));
}
static void configuration_and_provenance(){
 Backend b;CaptureOwner owner;auto r=requested();owner.tick(b,r);wave(b,2000);auto old=owner.tick(b,r);
 b.port.fence(b.now);++b.epoch;check(!b.port.view(b.now).current);
 r.tune_revision=2;r.calibration.low_hz=40;r.calibration.high_hz=160;r.calibration.fault_hz=180;
 auto v=owner.tick(b,r);check(v.sample.tune_revision==2&&same(v.sample.calibration,r.calibration)&&!v.sample.observation.valid);
 check(v.sample.observation.config_epoch>old.sample.observation.config_epoch&&v.sample.observation.window_cycles==0);
 check(!b.port.can_dispatch(old.ticket,b.now,false));check(!owner.control_observed(b,old,evaluation(r,old,b.now),true));
 check(owner.control_observed(b,v,evaluation(r,v,b.now),true));
 b.now+=50000;owner.tick(b,r);wave(b,b.now+1);v=owner.tick(b,r);check(v.sample.observation.valid&&v.sample.observation.ethanol_pct==50);
 // Neither raw synthetic source nor relabeled calibration/revision may enter
 // the target publication, regardless of a numerically plausible waveform.
 auto forged=v.sample;forged.observation.source=Source::Synthetic;check(!b.port.publish(v.ticket.version,forged,b.now));
 forged=v.sample;forged.tune_revision=3;check(!b.port.publish(v.ticket.version,forged,b.now));
 forged=v.sample;forged.calibration.low_hz=41;check(!b.port.publish(v.ticket.version,forged,b.now));
 r.required=false;++r.tune_revision;v=owner.tick(b,r);check(!b.port.armed()&&v.sample.observation.pending_fault&&!v.sample.observation.valid);
 check(evaluation(r,v,b.now).control_ok&&!owner.control_observed(b,v,evaluation(r,v,b.now),true));
 check(b.port.work().ingress.pending_fault);r.required=true;++r.tune_revision;v=owner.tick(b,r);
 check(!evaluation(r,v,b.now).control_ok&&owner.control_observed(b,v,evaluation(r,v,b.now),true));
}
static void missing_and_unconfirmed(){
 for(unsigned mode=0;mode<3;++mode){Backend b;CaptureOwner owner;auto r=requested();
  if(mode==0)b.available=false;
  if(mode==1)r.confirmed=false;
  if(mode==2)b.bound=false;
  auto v=owner.tick(b,r);check(!b.port.armed()&&!v.sample.observation.valid&&!evaluation(r,v,b.now).control_ok);
  check(control(r,v,b.now).fuel_cut&&control(r,v,b.now).spark_cut);
  const auto before=b.port.work().ingress.counters.callbacks;check(b.edge(b.now+1,true)==Ingress::Result::Suppress);
  check(b.port.work().ingress.counters.callbacks==before+1);
 }
}
static void capture_fault_cancels_queued_command(){
 Backend b;CaptureOwner owner;auto r=requested();owner.tick(b,r);wave(b,2000);auto old=owner.tick(b,r);
 const auto version=old.ticket.version;
 check(b.edge(26000,false)==Ingress::Result::Accepted&&b.edge(32000,true)==Ingress::Result::Accepted);
 check(b.edge(36000,false)==Ingress::Result::Accepted&&b.edge(42000,true)==Ingress::Result::Accepted);
 auto bad=owner.tick(b,r);check(same(version,bad.ticket.version));
 check(!bad.sample.observation.valid&&bad.sample.observation.pending_fault&&bad.sample.observation.reason==Reason::PulseWidth);
 check(!b.port.can_dispatch(old.ticket,b.now,false)&&!b.port.can_issue(old.ticket,b.now,false));
 check(owner.control_observed(b,bad,evaluation(r,bad,b.now),true));
 check(b.edge(49000,false)==Ingress::Result::Accepted&&b.edge(52000,true)==Ingress::Result::Accepted);
 check(b.edge(59000,false)==Ingress::Result::Accepted&&b.edge(62000,true)==Ingress::Result::Accepted);
 auto recovered=owner.tick(b,r);check(recovered.sample.observation.valid&&recovered.ticket.capture_generation>old.ticket.capture_generation);
 check(b.port.can_dispatch(recovered.ticket,b.now,false)&&!b.port.can_dispatch(old.ticket,b.now,false));
 check(b.now<old.ticket.valid_until_us); // Old deadline alone would allow it.
}
static void interval_clock(){
 using Clock=ecu::timing::CaptureClock;
 for(unsigned bracket=0;bracket<=10;++bracket)for(unsigned epoch_offset=0;epoch_offset<=bracket;++epoch_offset)
 for(unsigned width:{1000U,3000U,5000U})for(unsigned lag:{0U,5U,100U})for(std::uint64_t wrap:{0ULL,53687091ULL,107374182ULL}){
  Clock clock;check(clock.sync(80000000,1000,1000+bracket));CaptureConfig config;config.cycles=2;Capture capture(config);
  for(unsigned cycle=0;cycle<3;++cycle){
   const std::uint64_t rise=10000+10000*cycle+wrap;
   auto stamp=clock.map_interval(static_cast<std::uint32_t>((rise-1000-epoch_offset)*80+17),rise+(cycle%2?lag:0));
   check(stamp.error==Clock::Error::None&&stamp.time_us==rise-epoch_offset);capture.edge(stamp.time_us,true,Source::TargetCapture);
   if(cycle==2)break;
   const auto fall=rise+10000-width;
   stamp=clock.map_interval(static_cast<std::uint32_t>((fall-1000-epoch_offset)*80+17),fall+(cycle%2?0:lag));
   check(stamp.error==Clock::Error::None&&stamp.time_us==fall-epoch_offset);capture.edge(stamp.time_us,false,Source::TargetCapture);
  }
  const auto value=capture.observe(30000+wrap+lag);
  check(value.valid&&value.low_pulse_us==width&&value.frequency_hz==100);
 }
 Clock c;check(c.sync(80000000,1000,1010));
 check(c.map_interval(0,999).error==Clock::Error::BeforeEpoch);
 check(c.map_interval(80000,1500).error==Clock::Error::Future);
 check(c.map_interval(80000,7001).error==Clock::Error::TooOld);
}
int main(){nominal_and_deadline();overflow_ack_and_rearm();publication_and_control_races();configuration_and_provenance();missing_and_unconfirmed();capture_fault_cancels_queued_command();interval_clock();std::cout<<"flex_capture_owner_checks "<<checks<<"\n";}
