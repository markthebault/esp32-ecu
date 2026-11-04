#include "ecu/flex_ingress.hpp"
#include "ecu/capture_clock.hpp"
#include "ecu/engine.hpp"
#include <cassert>
#include <deque>
#include <iostream>

using namespace ecu::flex;
using Result=Ingress::Result;
static unsigned checks=0;
static void verify(bool value,const char*expression,unsigned line){
 ++checks;if(!value)std::cerr<<"Failed line "<<line<<": "<<expression<<" (check "<<checks<<")\n";
 assert(value);
}
#define check(value) verify((value),#value,__LINE__)
static void near(double a,double b,double epsilon=1e-9){check(std::isfinite(a)&&std::abs(a-b)<=epsilon);}
static Ingress active(std::uint64_t now=100,std::uint64_t context=1){
 Ingress q;check(q.begin_context(context,now));check(q.arm(context,now));return q;
}
static void basic_and_ring(){
 Ingress q;auto s=q.snapshot();IngressEdge e;
 check(!s.armed&&!s.pending_fault&&s.context==0&&s.queued==0&&!q.pop(e));
 check(q.push(1,10,10,true)==Result::Ignored);
 check(q.begin_context(1,100)&&q.arm(1,100));
 check(q.push(1,99,101,false)==Result::Ignored);
 check(q.push(1,100,102,true)==Result::Ignored);
 check(q.push(1,101,103,true,true,0xaabbccdd)==Result::Accepted);
 check(q.begin_context(1,104));check(!q.arm(1,104));
 check(q.pop(e)&&e.captured_us==101&&e.observed_us==103&&e.context==1&&e.sequence==1&&e.high&&e.raw_capture==0xaabbccdd);
 check(!q.pop(e));
 check(q.push(2,200,200,false)==Result::Ignored);
 check(q.push(0,200,200,false)==Result::Ignored);
 s=q.snapshot();check(s.counters.accepted==1&&s.counters.dequeued==1&&s.counters.ignored_context==3&&s.counters.ignored_prearm==2&&s.armed);
 check(q.stop(200));check(q.push(1,201,201,false)==Result::Suppress);
 s=q.snapshot();check(!s.pending_fault&&s.counters.ignored_inactive==1);
 check(q.arm(1,202));
 std::deque<IngressEdge> expected;std::uint64_t sequence=1;
 for(unsigned n=1;n<=2048;++n){
  const auto captured=1000+n*1000ULL;
  check(q.push(1,captured,captured+500,n%2)==Result::Accepted);
  expected.push_back({captured,captured+500,1,++sequence,0,bool(n%2)});
  const auto count=n%5==0?3U:0U;
  for(unsigned i=0;i<count&&!expected.empty();++i){
   check(q.pop(e));const auto first=expected.front();expected.pop_front();
   check(e.sequence==first.sequence&&e.captured_us==first.captured_us&&e.observed_us==first.observed_us&&e.high==first.high);
  }
  // Keep a nonempty, wrapping queue without reaching capacity.
  if(expected.size()>50){check(q.pop(e));check(e.sequence==expected.front().sequence);expected.pop_front();}
  check(q.snapshot().queued==expected.size());
 }
 while(!expected.empty()){check(q.pop(e)&&e.sequence==expected.front().sequence);expected.pop_front();}
 s=q.snapshot();check(!q.pop(e)&&s.counters.accepted==sequence&&s.counters.dequeued==sequence&&s.counters.discarded==0&&s.armed);
}
static void ack_and_retry(Ingress&q,std::uint64_t now,IngressFault reason){
 auto s=q.snapshot();check(!s.armed&&s.pending_fault&&!s.terminal&&s.queued==0&&s.last_fault==reason);
 const IngressTicket guessed{s.context,s.fault_generation};
 // A diagnostic snapshot is not a completed control input offer.
 check(!q.acknowledge(guessed,now));check(!q.arm(s.context,now+1));
 const auto offered=q.offer_fault();check(bool(offered));
 check(!q.acknowledge({s.context+1,offered.generation},now+1));
 check(!q.acknowledge({s.context,offered.generation+1},now+1));
 check(q.acknowledge(offered,now+1));check(!q.acknowledge(offered,now+1));
 check(!q.snapshot().pending_fault&&!q.snapshot().armed);
 check(!q.arm(s.context,s.last_suppression_us+Ingress::retry_holdoff_us-1));
 check(q.arm(s.context,s.last_suppression_us+Ingress::retry_holdoff_us));
 check(!q.snapshot().retry_holdoff);
}
static void failures(){
 // Each invalid event discards the complete queue and requests local masking.
 for(unsigned kind=0;kind<8;++kind){
  auto q=active();check(q.push(1,1000,1100,true)==Result::Accepted);
  Result r;IngressFault expected=IngressFault::Clock;std::uint64_t now=2000;
  switch(kind){
   case 0:r=q.push(1,1200,1199,false);now=1199;break; // future capture
   case 1:r=q.push(1,1200,6201,false);now=6201;break; // stale latch
   case 2:r=q.push(1,1200,1200,false,false);now=1200;break;
   case 3:r=q.push(1,1200,1099,false);now=1100;break; // callback clock reversed
   case 4:r=q.push(1,1000,2000,false);break; // repeated timestamp
   case 5:r=q.push(1,999,2000,false);break;
   case 6:r=q.push(1,2000,2000,true);expected=IngressFault::RepeatedLevel;break;
   default:r=q.push(1,1049,2000,false);expected=IngressFault::ShortInterval;break;
  }
  check(r==Result::Suppress);check(q.snapshot().counters.discarded==1);
  check(q.snapshot().counters.faults[static_cast<unsigned>(expected)]==1);
  ack_and_retry(q,now,expected);
 }
 // Inclusive age/minimum-interval boundaries are accepted.
 auto q=active();check(q.push(1,1000,6000,true)==Result::Accepted);
 check(q.push(1,1050,6050,false)==Result::Accepted);
 // Overflow is independent of the callback budget for a slow undrained queue.
 q=active();for(unsigned n=1;n<=Ingress::capacity;++n)check(q.push(1,n*2000,n*2000,n%2)==Result::Accepted);
 check(q.snapshot().queued==Ingress::capacity);
 check(q.push(1,130000,130000,true)==Result::Suppress);
 check(q.snapshot().counters.discarded==64&&q.snapshot().counters.accepted==64);
 ack_and_retry(q,130000,IngressFault::Overflow);
 check(q.push(1,180001,180001,false)==Result::Accepted);
 IngressEdge e;check(q.pop(e)&&e.sequence==65); // no sequence reuse after loss
}
static void rate_and_persistent_noise(){
 auto q=active(0);
 for(unsigned n=1;n<=32;++n)check(q.push(1,n*50,n*50,n%2)==Result::Accepted);
 check(q.push(1,1650,1650,true)==Result::Suppress);
 check(q.snapshot().counters.discarded==32);
 ack_and_retry(q,1650,IngressFault::RateLimit);
 // Old pending timestamps also consume the callback budget.
 q=active(1000);
 for(unsigned n=0;n<32;++n)check(q.push(1,999,1001+n,false)==Result::Ignored);
 check(q.push(1,999,1033,false)==Result::Suppress);
 check(q.snapshot().last_fault==IngressFault::RateLimit&&q.snapshot().counters.ignored_prearm==32);
 // This is a FIXED window. Two adjacent windows can legitimately admit64
 // callbacks across the boundary; do not claim a sliding-window rate limit.
 q=active(0);IngressEdge edge;
 for(unsigned n=0;n<64;++n){
  const auto t=8400+n*50ULL;check(q.push(1,t,t,n%2)==Result::Accepted);check(q.pop(edge));
 }
 check(q.snapshot().armed&&q.snapshot().counters.accepted==64);
 check(q.push(1,11600,11600,false)==Result::Suppress);
 // Masked time cannot prove electrical quiet. A continuing noise source gets
 // another bounded attempt and is suppressed again, even after a valid ACK.
 q=active(0);std::uint64_t now=0;
 for(unsigned attempt=1;attempt<=1000;++attempt){
  for(unsigned n=1;n<=32;++n)check(q.push(1,now+n*50,now+n*50,n%2)==Result::Accepted);
  now+=1650;check(q.push(1,now,now,true)==Result::Suppress);
  auto s=q.snapshot();check(s.fault_generation==attempt&&s.pending_fault&&s.counters.discarded==attempt*32ULL);
  check(!q.arm(1,now));const auto offered=q.offer_fault();check(q.acknowledge(offered,now));
  check(!q.arm(1,now+Ingress::retry_holdoff_us-1));now+=Ingress::retry_holdoff_us;check(q.arm(1,now));
 }
}
static void contexts_and_clock_fences(){
 auto q=active();check(q.push(1,1000,1000,true)==Result::Accepted);
 check(q.begin_context(2,2000));auto s=q.snapshot();check(s.last_fault==IngressFault::ContextChanged&&s.pending_fault&&s.counters.discarded==1);
 const auto old=q.offer_fault();check(q.begin_context(3,3000));
 check(q.push(2,999999,999999,false)==Result::Ignored); // no old-context clock mutation
 check(q.snapshot().last_observed_us==3000);
 check(!q.acknowledge(old,3000));const auto current=q.offer_fault();
 check(q.begin_context(3,3000));check(q.acknowledge(current,3000));check(q.arm(3,53000));
 check(q.push(3,53000,53001,true)==Result::Ignored);check(q.push(3,53002,53002,true)==Result::Accepted);
 check(q.stop(53003));check(q.snapshot().counters.discarded==2&&!q.snapshot().pending_fault);
 check(q.arm(3,53004));check(q.push(3,53005,53005,false)==Result::Accepted);
 check(q.push(3,54000,54000,false)==Result::Suppress);
 const auto before=q.offer_fault();check(!q.stop(53999));const auto after=q.offer_fault();
 check(after.generation==before.generation+1&&!q.acknowledge(before,54000));
 check(q.acknowledge(after,54000));check(q.arm(3,104000));
 // Reusing/wrapping a context is terminal rather than an ABA acceptance path.
 for(auto invalid:{0ULL,2ULL}){
  q=active(100,3);check(!q.begin_context(invalid,101));s=q.snapshot();
  check(s.terminal&&!s.armed&&s.last_fault==IngressFault::InvalidContext);
  check(!q.acknowledge(q.offer_fault(),101));check(!q.begin_context(4,102));check(!q.arm(4,100000));
 }
 // Time near U64 max uses subtraction, never a wrapping retry deadline.
 const auto maximum=UINT64_MAX;q=active(maximum-60000,maximum);
 check(q.push(maximum,maximum-59000,maximum-59000,true)==Result::Accepted);
 check(q.push(maximum,maximum-58000,maximum-58000,true)==Result::Suppress);
 const auto ticket=q.offer_fault();check(q.acknowledge(ticket,maximum-58000));
 check(!q.arm(maximum,maximum-8001));check(q.arm(maximum,maximum-8000));
 check(q.push(maximum,maximum-7999,maximum-7999,false)==Result::Accepted);
 check(!q.begin_context(1,maximum-7998));check(q.snapshot().terminal);
 // A reversed ACK clock creates a newer fault that the offered ticket cannot clear.
 q=active();check(q.push(1,1000,1000,true)==Result::Accepted);
 check(q.push(1,2000,2000,true)==Result::Suppress);auto ticket2=q.offer_fault();
 check(!q.acknowledge(ticket2,1999));check(q.snapshot().last_fault==IngressFault::Clock&&q.snapshot().fault_generation==ticket2.generation+1);
}
static void capture_clock_and_core(){
 for(std::uint64_t base:{1000000ULL,54000000ULL,9007199254742016ULL})
 for(unsigned cycles:{2,8,32})for(std::uint64_t period:{6667ULL,10000ULL,20000ULL})
 for(std::uint64_t width:{1000ULL,3000ULL,5000ULL})for(std::uint64_t lag:{0ULL,5000ULL}){
  ecu::timing::CaptureClock clock;check(clock.sync(80000000,base,base+2));
  auto q=active(base+3,1);CaptureConfig config;config.cycles=cycles;Capture worker(config),direct(config);
  std::uint64_t last=base+4;
  auto inject=[&](std::uint64_t captured,bool level){
   const std::uint32_t raw=static_cast<std::uint32_t>(captured-clock.epoch_us())*80;
   const auto mapped=clock.map(raw,captured+lag);check(mapped.error==ecu::timing::CaptureClock::Error::None&&mapped.time_us==captured);
   check(q.push(1,mapped.time_us,captured+lag,level,true,raw)==Result::Accepted);
   direct.edge(captured,level,Source::TargetCapture);IngressEdge e;
   check(q.pop(e)&&e.context==1&&e.captured_us==captured&&e.raw_capture==raw);
   worker.edge(e.captured_us,e.high,Source::TargetCapture);last=captured;
  };
  inject(last,true);const auto first=last;
  for(unsigned n=1;n<=cycles;++n){inject(first+n*period-width,false);inject(first+n*period,true);}
  const auto o=worker.observe(last+lag),expected=direct.observe(last+lag);
  check(o.valid&&o.source==Source::TargetCapture&&o.sample_us==last&&o.window_start_us==first&&o.window_cycles==cycles);
  near(o.frequency_hz,expected.frequency_hz);near(o.low_pulse_us,expected.low_pulse_us);near(o.ethanol_pct,expected.ethanol_pct);near(o.fuel_temp_c,expected.fuel_temp_c);near(o.age_ms,double(lag)/1000);
 }
}
static void completed_control_fence(){
 // Owned native integration harness, not the as-yet unwired target producer.
 // Both the ingress ticket and the actual capture fault must be consumed by
 // the same completed control context before either ACK is forwarded.
 using namespace ecu::engine;
 Tune tune;tune.afterstart_pct=0;tune.dfco_enabled=false;tune.warmup_pct.fill(100);
 tune.flex_fuel.input_confirmed=tune.flex_fuel.correction.enabled=true;
 auto q=active(900000);Capture capture(tune.flex_fuel.capture);Inputs in;
 in.rpm=2000;in.map_kpa=50;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;
 in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;
 auto inject=[&](std::uint64_t t,bool high){
  check(q.push(1,t,t,high)==Result::Accepted);IngressEdge e;check(q.pop(e));capture.edge(e.captured_us,e.high,Source::TargetCapture);
 };
 auto control=[&](std::uint64_t now){
  in.sampled_us=now;in.flex_sample={capture.observe(now),tune.flex_fuel.capture,tune.revision};Controller c;return c.step(tune,in,now);
 };
 auto wave=[&](std::uint64_t start){inject(start,true);for(unsigned n=1;n<=8;++n){inject(start+n*10000-3000,false);inject(start+n*10000,true);}};
 wave(900001);auto output=control(980001);check(!output.faults&&output.flex_fuel.raw_qualified);
 check(q.push(1,981001,981001,true)==Result::Suppress);
 const auto offered=q.offer_fault();capture.capture_error(Reason::Unavailable);
 auto pending=capture.observe(981001);check(pending.pending_fault&&!pending.valid);
 output=control(981001);check((output.faults&BadSensor)&&output.fuel_cut&&output.spark_cut&&!output.flex_fuel.control_ok);
 check(capture.acknowledge(pending.fault_generation));check(q.acknowledge(offered,981001));
 check(!q.arm(1,1031000));check(q.arm(1,1031001));
 // ACK and unmask alone never make the old window valid.
 output=control(1031001);check((output.faults&BadSensor)&&output.fuel_cut&&output.spark_cut);
 wave(1031002);output=control(1111002);check(!output.faults&&output.flex_fuel.raw_qualified);
 // Staleness is based on the last completed waveform, not fresh control/ADC time.
 output=control(1361003);check((output.faults&BadSensor)&&output.fuel_cut&&output.spark_cut&&output.flex_fuel.reason==Reason::Stale);
 // A tune revision change cannot relabel the old producer's sample.
 ++tune.revision;in.sampled_us=1111002;Controller newer;
 output=newer.step(tune,in,1111002);check(output.faults&BadSensor);check(output.flex_fuel.reason==Reason::ConfigurationMismatch);
}
int main(){
 basic_and_ring();failures();rate_and_persistent_noise();contexts_and_clock_fences();
 capture_clock_and_core();completed_control_fence();
 std::cout<<"flex_ingress_checks "<<checks<<"\n";
 std::cout<<"ingress_bytes "<<sizeof(Ingress)<<" edge_bytes "<<sizeof(IngressEdge)<<"\n";
}
