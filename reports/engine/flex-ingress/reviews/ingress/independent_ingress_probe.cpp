#include <array>
#include <cstdint>
#include <limits>
// Reviewer-only state seeding makes U64 exhaustion reachable without changing
// the frozen implementation. No target code is built with this substitution.
#define private public
#include "ecu/flex_ingress.hpp"
#undef private
#include "ecu/capture_clock.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <random>
using ecu::flex::Ingress;
using ecu::flex::IngressFault;
using ecu::flex::IngressTicket;
using ecu::flex::IngressEdge;
using R=Ingress::Result;
static unsigned checks=0;
static void check(bool v,const char*label){++checks;if(!v){std::fprintf(stderr,"failed[%u]: %s\n",checks,label);std::exit(1);}}
static Ingress active(std::uint64_t ctx=1,std::uint64_t now=1000){Ingress q;check(q.begin_context(ctx,now),"begin");check(q.arm(ctx,now),"arm");return q;}
static void tickets_and_stop(){
 auto q=active();check(q.push(1,2000,2000,true)==R::Accepted,"initial edge");
 check(q.push(1,2100,2100,true)==R::Suppress,"duplicate level suppresses");auto initial=q.snapshot();
 const IngressTicket guessed{1,initial.fault_generation};
 for(unsigned n=0;n<10000;++n){const auto s=q.snapshot();check(s.pending_fault&&s.fault_generation==initial.fault_generation&&s.acknowledged_generation==0,"stats preserve pending");}
 check(!q.acknowledge(guessed,2100),"diagnostics did not offer");
 const auto offered=q.offer_fault();check(q.stop(2101),"stop pending");check(q.snapshot().pending_fault,"stop does not ACK");
 check(q.begin_context(1,2102),"same context idempotent");check(q.snapshot().pending_fault,"same context does not ACK");
 check(!q.arm(1,60000),"elapsed time does not ACK");
 check(!q.acknowledge({1,offered.generation-1},60001),"old generation reject");
 check(q.acknowledge(offered,60002),"offered context survives mechanical stop");
 check(!q.acknowledge(offered,60002),"ticket cannot ACK twice");check(q.arm(1,60003),"fresh arm after stop/ACK");
 check(q.push(1,60003,60004,true)==R::Ignored,"arm boundary ignored");
 check(q.push(1,60004,60004,false)==R::Accepted,"new first level independent");
 check(q.stop(60005),"normal stop");check(!q.snapshot().pending_fault,"stop alone is mechanical, no worker fault injection");
 check(q.push(1,UINT64_MAX,UINT64_MAX,true,false)==R::Suppress,"inactive callback suppresses without clock trust");
 check(q.snapshot().last_observed_us==60005&&!q.snapshot().pending_fault,"inactive ignored clock not a fabricated fault");
 check(q.arm(1,60006),"rearm mechanical stop");
 auto before=q.snapshot();check(q.push(999,UINT64_MAX,0,true,false)==R::Ignored,"foreign callback ignored");
 auto after=q.snapshot();check(after.last_observed_us==before.last_observed_us&&after.fault_generation==before.fault_generation&&after.armed,"foreign context cannot retag or poison current clock");
}
static void exhaustion(){
 {
  auto q=active();q.counters_.accepted=UINT64_MAX-1;
  check(q.push(1,1001,1001,true)==R::Accepted,"last sequence usable");IngressEdge e;
  check(q.pop(e)&&e.sequence==UINT64_MAX,"last sequence exact U64");
  check(q.push(1,1051,1051,false)==R::Suppress,"next sequence never wraps");auto s=q.snapshot();
  check(s.terminal&&s.pending_fault&&!s.armed&&s.last_fault==IngressFault::SequenceExhausted&&s.counters.accepted==UINT64_MAX,"sequence exhaustion terminal");
  check(!q.acknowledge(q.offer_fault(),1051),"terminal sequence cannot ACK");check(!q.arm(1,100000),"terminal cannot rearm");check(!q.begin_context(2,100001),"context cannot repair terminal");
 }
 {
  auto q=active();q.generation_=q.acknowledged_=UINT64_MAX-1;
  check(q.push(1,1001,1001,true)==R::Accepted,"last generation prelude");
  check(q.push(1,1051,1051,true)==R::Suppress,"last generation issued");auto s=q.snapshot();
  check(!s.terminal&&s.pending_fault&&s.fault_generation==UINT64_MAX,"last ticket nonzero");
  const auto t=q.offer_fault();check(q.acknowledge(t,1051),"last generation may complete");check(!q.snapshot().pending_fault,"last exact ACK clears current fault");
  check(q.arm(1,51051),"rearm after last ticket");check(q.push(1,51052,51052,true)==R::Accepted,"post last ACK first edge");
  check(q.push(1,51102,51102,true)==R::Suppress,"generation cannot wrap");s=q.snapshot();
  check(s.terminal&&s.pending_fault&&s.fault_generation==UINT64_MAX&&s.acknowledged_generation==UINT64_MAX,"terminal preserves pending even equal generations");
  check(!q.acknowledge(t,51102)&&!q.acknowledge(q.offer_fault(),51102),"old equal-valued ticket cannot clear terminal");
 }
 {
  auto q=active(UINT64_MAX);check(q.begin_context(UINT64_MAX,1001),"maximum context idempotent");
  check(!q.begin_context(0,1002),"context wrap zero terminal");check(q.snapshot().terminal,"context terminal sticky");
 }
 {
  auto q=active();q.counters_.callbacks=UINT64_MAX;q.counters_.dequeued=UINT64_MAX;
  q.counters_.discarded=UINT64_MAX;q.counters_.ignored_context=UINT64_MAX;
  q.counters_.ignored_inactive=UINT64_MAX;q.counters_.ignored_prearm=UINT64_MAX;
  q.counters_.suppressions=UINT64_MAX;q.counters_.rejected_ack=UINT64_MAX;
  q.counters_.faults.fill(UINT64_MAX);
  check(q.push(999,2000,2000,true)==R::Ignored,"ignored diagnostic saturation");
  check(q.push(1,1000,1001,true)==R::Ignored,"prearm diagnostic saturation");
  check(q.push(1,1001,1001,true)==R::Accepted,"saturated diagnostics do not block sequence");
  IngressEdge e;check(q.pop(e),"saturated dequeue");check(q.push(1,1051,1051,false)==R::Accepted,"accept after saturated dequeue");
  check(q.push(1,1101,1101,false)==R::Suppress,"saturated diagnostics still create fault");
  auto s=q.snapshot();check(s.pending_fault&&!s.terminal&&s.fault_generation==1&&s.counters.suppressions==UINT64_MAX&&s.counters.discarded==UINT64_MAX,"saturations do not wrap or consume pending");
  check(!q.acknowledge({1,1},1101),"saturated reject count still rejects");
  const auto t=q.offer_fault();check(q.acknowledge(t,1101),"diagnostics saturation does not prevent legal ACK");
  check(q.snapshot().counters.rejected_ack==UINT64_MAX,"reject counter sticky at max");
 }
}
static void boundary_and_clock(){
 for(std::uint64_t lag:{4999ULL,5000ULL,5001ULL}){
  auto q=active();const auto r=q.push(1,1001,1001+lag,true);
  check(r==(lag<=5000?R::Accepted:R::Suppress),"inclusive capture age");
 }
 for(std::uint64_t spacing:{49ULL,50ULL,51ULL}){
  auto q=active();check(q.push(1,1001,1001,true)==R::Accepted,"spacing first");
  check(q.push(1,1001+spacing,1001+spacing,false)==(spacing>=50?R::Accepted:R::Suppress),"inclusive minimum interval");
 }
 // Rate charge belongs to observed callback time, not queued sensor time.
 auto q=active(1,0);
 for(unsigned n=0;n<32;++n)check(q.push(1,n*50+1,5000+n*50,n%2)==R::Accepted,"bounded delayed burst");
 check(q.push(1,1601,6601,false)==R::Suppress,"33rd delayed callback suppressed");
 q=active(1,0);
 for(unsigned n=0;n<32;++n)check(q.push(1,8000+n*50,8000+n*50,n%2)==R::Accepted,"end first window");
 for(unsigned n=0;n<32;++n){const auto t=10000+n*50;check(q.push(1,t,t,n%2)==R::Accepted,"start second fixed window");}
 check(q.snapshot().queued==64,"adjacent fixed windows can fill ring");
 check(q.push(1,11600,11600,false)==R::Suppress,"fixed callback limit reached before queue mutation");
 check(q.snapshot().last_fault==IngressFault::RateLimit,"rate cause deterministic");
 q=active(1,UINT64_MAX-10000);
 check(q.push(1,UINT64_MAX-9999,UINT64_MAX-9999,true)==R::Accepted,"U64 near end accepts");
 check(q.push(1,UINT64_MAX-9949,UINT64_MAX-9949,true)==R::Suppress,"U64 near end fault");
 const auto t=q.offer_fault();check(q.acknowledge(t,UINT64_MAX),"latest U64 ACK legal");
 check(!q.arm(1,UINT64_MAX),"holdoff cannot wrap into a false deadline");
 // Owner calls all require a trusted monotonic clock, unlike foreign callbacks.
 q=active();check(q.push(1,2000,2000,true)==R::Accepted,"owner clock prelude");
 check(!q.arm(999,1999)&&q.snapshot().pending_fault&&q.snapshot().last_fault==IngressFault::Clock,"wrong-context owner arm still applies global clock fence");
}
static void randomized_conservation(){
 std::mt19937_64 random(0x9be26d);auto q=active(1,0);std::uint64_t now=0,ctx=1,last_popped=0;
 for(unsigned k=0;k<30000;++k){
  const auto prior=q.snapshot();now+=100+(random()%2000);const unsigned op=random()%11;
  if(op<6){const auto cap=now-(random()%70);const auto c=op==0?ctx+1:ctx;const auto r=q.push(c,cap,now,random()%2);(void)r;}
  else if(op==6){IngressEdge e;if(q.pop(e)){check(e.context==ctx&&e.sequence>last_popped&&e.captured_us<=e.observed_us&&e.observed_us-e.captured_us<=5000,"dequeued provenance/order");last_popped=e.sequence;}}
  else if(op==7){const auto t=q.offer_fault();check(!t||t.context==ctx,"offered context");if(t&&random()%2)q.acknowledge(t,now);}
  else if(op==8){q.stop(now);}
  else if(op==9){q.arm(ctx,now);}
  else{++ctx;q.begin_context(ctx,now);}
  const auto s=q.snapshot();
  check(s.queued<=Ingress::capacity,"ring bounded");
  check(s.counters.accepted==s.counters.dequeued+s.counters.discarded+s.queued,"accepted edge conservation");
  check(s.fault_generation>=prior.fault_generation&&s.acknowledged_generation<=s.fault_generation,"generations monotonic");
  check(!s.armed||(!s.pending_fault&&!s.terminal&&s.context==ctx),"armed invariant");
  if(op!=7)check(!(prior.pending_fault&&!s.pending_fault),"only a legal offered ACK can consume pending");
 }
}
int main(){tickets_and_stop();exhaustion();boundary_and_clock();randomized_conservation();
 std::printf("{\"passed\":true,\"checks\":%u,\"ingress_bytes\":%zu,\"edge_bytes\":%zu,\"scope\":\"Portable ingress only; reviewer state seeding for U64 exhaustion\"}\n",checks,sizeof(Ingress),sizeof(IngressEdge));}
