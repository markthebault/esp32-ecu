#include "ecu/flex_capture_owner.hpp"
#include "ecu/engine.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
namespace f=ecu::flex;
static unsigned checks=0;
static void check(bool ok,const char*label){++checks;if(!ok){std::fprintf(stderr,"check%u: %s\n",checks,label);std::abort();}}
struct Bus {
 f::CapturePort port;std::uint64_t now=1000;std::uint32_t epoch=1;bool binding=true,available=true;
 std::function<void()> after_pop,before_publish,before_ack;
 static void once(std::function<void()>&hook){if(hook){auto h=std::move(hook);hook={};h();}}
 f::CaptureWork configure(const f::CaptureRequest&r,bool v,std::uint64_t stale){return port.configure(r,epoch,binding,available,v,stale,now);}
 bool arm(f::CaptureVersion v){return port.arm(v,now);}
 f::CaptureWork work(){return port.work();}
 bool pop(f::CaptureVersion v,f::IngressEdge&e){const bool ok=port.pop(v,e);if(ok)once(after_pop);return ok;}
 bool publish(f::CaptureVersion v,const f::Sample&s){once(before_publish);return port.publish(v,s,now);}
 f::CaptureView view(){return port.view(now);}
 bool acknowledge(const f::CaptureView&v){once(before_ack);return port.acknowledge(v,now);}
 std::uint64_t clock(){return now;}
 f::Ingress::Result edge(std::uint64_t t,bool high){check(t>=now,"test time monotonic");now=t;return port.push(t,t,high,true,static_cast<std::uint32_t>(t));}
};
struct Harness {
 Bus b;f::CaptureOwner owner;f::CaptureRequest r;
 Harness(){r.required=r.confirmed=true;r.tune_revision=r.sensor_revision=1;r.calibration.cycles=2;}
 f::CaptureView tick(){return owner.tick(b,r);}
 ecu::engine::Output step(const f::CaptureView&v){
  ecu::engine::Tune t;t.revision=r.tune_revision;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);t.flex_fuel.capture=r.calibration;t.flex_fuel.input_confirmed=r.confirmed;t.flex_fuel.correction.enabled=r.required;
  ecu::engine::Inputs in;in.rpm=2000;in.map_kpa=50;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;in.sampled_us=b.now;in.flex_sample=v.sample;in.flex_context_match=v.current;
  ecu::engine::Controller controller;return controller.step(t,in,b.now);
 }
 bool ack(const f::CaptureView&v,bool done=true){return owner.control_observed(b,v,step(v).flex_fuel,done);}
 f::CaptureView ready(std::uint64_t start=2000){tick();wave(start);auto v=tick();check(v.current&&v.sample.observation.valid,"raw target ready");check(v.sample.observation.source==f::Source::TargetCapture,"actual raw source tag");return v;}
 void wave(std::uint64_t start){check(b.edge(start,true)==f::Ingress::Result::Accepted,"wave rising seed");for(unsigned k=1;k<=r.calibration.cycles;++k){check(b.edge(start+k*10000-3000,false)==f::Ingress::Result::Accepted,"wave falling");check(b.edge(start+k*10000,true)==f::Ingress::Result::Accepted,"wave rising");}}
};
static void deadlines_and_origin(){
 Harness h;auto v=h.ready();check(!h.step(v).fuel_cut&&!h.step(v).spark_cut,"qualified actual controller demands");const auto first=v.ticket;
 check(h.b.port.can_issue(first,h.b.now,false),"genuine publication admission");
 for(unsigned k=0;k<4;++k){auto t=first;if(k==0)++t.publication;if(k==1)++t.sample_us;if(k==2)++t.valid_until_us;if(k==3)++t.version.armed_after_us;check(!h.b.port.can_issue(t,h.b.now,false),"forged admission rejected");}
 check(h.b.edge(29000,false)==f::Ingress::Result::Accepted&&h.b.edge(32000,true)==f::Ingress::Result::Accepted,"new cycle queued");v=h.tick();
 check(!h.b.port.can_issue(first,h.b.now,false)&&h.b.port.can_dispatch(first,h.b.now,false),"admitted old command distinct from new admission");
 check(h.b.port.can_dispatch(first,first.valid_until_us,false)&&!h.b.port.can_dispatch(first,first.valid_until_us+1,false),"old own deadline inclusive");
 check(h.b.port.can_dispatch(v.ticket,first.valid_until_us+1,false),"new sample deadline independent");
 for(auto source:{f::Source::Synthetic,f::Source::SyntheticValue,f::Source::Unavailable,static_cast<f::Source>(255)}){auto s=v.sample;s.observation.source=source;check(!h.b.port.publish(v.ticket.version,s,h.b.now),"no synthetic/unavailable valid publication");}
 auto s=v.sample;++s.tune_revision;check(!h.b.port.publish(v.ticket.version,s,h.b.now),"wrong producer revision rejected");s=v.sample;s.calibration.high_hz+=1;check(!h.b.port.publish(v.ticket.version,s,h.b.now),"wrong calibration rejected");
 h.b.now=v.ticket.valid_until_us+1;const auto stale=h.tick();check(!stale.sample.observation.valid&&h.step(stale).fuel_cut&&h.step(stale).spark_cut,"stale completed sample cuts both");check(h.ack(stale),"completed stale fault ACK");
}
static void same_context_ack_rearm(){
 Harness h;const auto good=h.ready();for(unsigned k=0;k<64;++k)check(h.b.edge(h.b.now+2000,k%2!=0)==f::Ingress::Result::Accepted,"fill ring slowly below fixed storm limit");
 check(h.b.edge(h.b.now+2000,false)==f::Ingress::Result::Suppress,"overflow suppression");const auto context=h.b.work().version.context;auto bad=h.tick();check(bad.current&&bad.ack_eligible&&bad.sample.observation.pending_fault&&!bad.sample.observation.valid,"invalid observed fault offered");
 const auto generation=h.b.work().ingress.fault_generation;for(unsigned k=0;k<50;++k){auto x=h.b.port.snapshot(h.b.now);check(x.work.ingress.pending_fault&&x.work.ingress.fault_generation==generation,"diagnostic never ACKs");}
 check(!h.ack(bad,false)&&h.b.work().ingress.pending_fault,"incomplete control not consumed");
 auto e=h.step(bad).flex_fuel;++e.sample.observation.config_epoch;check(!h.owner.control_observed(h.b,bad,e,true),"wrong consumed epoch rejected");
 const auto newer=h.tick();check(!h.ack(bad)&&!h.b.port.acknowledge(bad,h.b.now),"stale publication ticket cannot ACK");check(h.ack(newer),"matching completed invalid ACK");check(!h.ack(newer),"single consumption only");
 const auto suppressed=h.b.work().ingress.last_suppression_us;h.b.now=suppressed+49999;h.tick();check(!h.b.port.armed(),"strict retry holdoff");h.b.now=suppressed+50000;h.tick();check(h.b.port.armed()&&h.b.work().version.context==context,"same context rearm allowed");
 check(!h.b.port.can_dispatch(good.ticket,h.b.now,false),"pre-suppression command never resumes");h.wave(h.b.now+1);const auto fresh=h.tick();check(fresh.sample.observation.valid&&fresh.sample.observation.window_cycles==2,"full fresh window after rearm");
}
static void publication_races(){
 for(unsigned mode=0;mode<3;++mode){Harness h;const auto old=h.ready();h.b.edge(29000,false);h.b.edge(32000,true);
  auto fault=[&](){h.b.now+=100;check(h.b.port.push(h.b.now,h.b.now,true,true,0)==f::Ingress::Result::Suppress,"same-context IRQ fault during worker");};
  if(mode==0)h.b.after_pop=fault;
  else if(mode==1)h.b.before_publish=fault;
  else h.b.after_pop=[&](){h.b.port.fence(h.b.now);++h.b.epoch;};
  const auto raced=h.tick();check(!raced.current,"popped/processed old publication rejected atomically");const auto output=h.step(raced);check(output.fuel_cut&&output.spark_cut&&!output.flex_fuel.configuration_match,"held valid data never substitutes for current context");check(!h.ack(old)&&!h.ack(raced),"no stale result consumes new notification");
  const auto invalid=h.tick();check(invalid.current&&invalid.ack_eligible&&!invalid.sample.observation.valid&&invalid.sample.observation.window_cycles==0,"next worker offers invalid cleared series");check(h.ack(invalid),"new invalid completed control owns ACK");
 }
}
static void binding_changes(){
 for(unsigned mode=0;mode<4;++mode){Harness h;const auto old=h.ready();if(mode==0)++h.r.tune_revision;if(mode==1)++h.r.sensor_revision;if(mode==2)h.r.calibration.cycles=4;if(mode==3)h.r.confirmed=false;
  const auto v=h.tick();check(!v.sample.observation.valid&&v.sample.observation.window_cycles==0,"producer binding change clears old window");check(!h.b.port.can_dispatch(old.ticket,h.b.now,false),"old command invalidated by all binding kinds");check(v.sample.tune_revision==h.r.tune_revision&&f::same(v.sample.calibration,h.r.calibration),"new binding labels only invalid reacquisition");check(h.ack(v),"new binding fault completed ACK");
  const auto context=h.b.work().version.context;h.tick();check(h.b.work().version.context==context,"same effective binding stays idempotent");if(mode==3)check(!h.b.port.armed(),"unconfirmed never arms after ACK");
 }
}
static void restart_and_bounds(){
 f::CaptureConfig cfg;cfg.cycles=2;f::Capture c(cfg);for(unsigned n=0;n<5;++n)c.edge(2000+n*5000,n%2==0,f::Source::TargetCapture);
 auto x=c.observe(22000);c.overflow();x=c.observe(22001);const auto old=x.fault_generation;c.restart();auto y=c.observe(22002);check(y.pending_fault&&y.fault_generation==old&&y.edges==x.edges&&y.last_edge_us==x.last_edge_us,"restart preserves fault/counter/clock history");
 c.edge(21999,false,f::Source::TargetCapture);y=c.observe(22003);check(y.fault_generation>old&&y.reason==f::Reason::TimeReversed&&!c.acknowledge(old),"restart cannot hide reversed edge or old ACK");check(c.acknowledge(y.fault_generation),"current observed capture fault ACK");c.restart();y=c.observe(22002);check(y.pending_fault&&y.reason==f::Reason::TimeReversed,"restart preserves query clock");
 Harness h;h.b.now=UINT64_MAX-280002;const auto v=h.ready(h.b.now+1);check(h.b.port.can_dispatch(v.ticket,v.ticket.valid_until_us,false)&&!h.b.port.can_dispatch(v.ticket,v.ticket.valid_until_us+1,false),"near-U64 deadline does not wrap");
 f::CapturePort p;f::CaptureRequest r;r.required=r.confirmed=true;r.tune_revision=r.sensor_revision=1;r.calibration.low_hz=1;const auto a=p.configure(r,1,true,true,false,0,1000);const auto b=p.configure(r,1,true,true,false,0,2000);check(a.version.context==b.version.context&&!b.binding&&!b.active,"unchanged invalid effective binding idempotent");
}
static void exact_off(){
 ecu::engine::Tune t;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);ecu::engine::Controller a,b;
 for(unsigned n=0;n<1000;++n){ecu::engine::Inputs in;in.rpm=600+n%4700;in.map_kpa=30+n%70;in.tps_pct=n%70;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;in.sampled_us=1000000+n*5000;
  const auto x=a.step(t,in,in.sampled_us);in.flex_context_match=false;const auto y=b.step(t,in,in.sampled_us);check(x.faults==y.faults&&x.state==y.state&&x.fuel_cut==y.fuel_cut&&x.spark_cut==y.spark_cut,"Off context mismatch leaves decisions exact");
  check(std::memcmp(&x.pulse_ms,&y.pulse_ms,sizeof(double))==0&&std::memcmp(&x.advance_deg,&y.advance_deg,sizeof(double))==0&&std::memcmp(&x.dwell_ms,&y.dwell_ms,sizeof(double))==0,"Off context mismatch leaves fuel/spark bits exact");
 }
}
int main(){deadlines_and_origin();same_context_ack_rearm();publication_races();binding_changes();restart_and_bounds();exact_off();std::printf("independent_flex_owner_checks %u\n",checks);}
