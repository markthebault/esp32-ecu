#include "ecu/switch_transport.hpp"
#include "ecu/engine.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <limits>
using namespace ecu;
namespace si=ecu::switch_input;
static unsigned checks=0,reset_cases=0,mutation_cases=0,budget_cases=0;
static void need(bool ok,const char*why){++checks;if(!ok){std::fprintf(stderr,"FAIL%u %s\n",checks,why);std::abort();}}
// Independent register/pin device with sequential-pointer effects and reset
// injection at each wire byte boundary. This is an abstract digital model.
struct Device {
 std::array<unsigned char,11> reg{};unsigned char contacts=0;int reset_at=-1;bool reset_after_guard=false;
 unsigned bytes=0,writes=0;std::uint64_t*now=nullptr;std::vector<int>time_limits;
 Device(){reset();}
 void reset(){reg.fill(0);reg[0]=0xff;}
 unsigned char pins()const{
  unsigned raw=0x28|contacts;
  const bool loop=(reg[0]&0x80)==0&&(reg[10]&0x80);
  if(loop)raw|=0xc0;
  return static_cast<unsigned char>(((raw&reg[0])|(reg[10]&~reg[0]))^reg[1]);
 }
 si::Result prepare(){return si::Result::Ok;}
 si::Result write(unsigned char start,const unsigned char*p,std::size_t n,int timeout){
  need(timeout>0&&timeout<=3,"finite per-call timeout");time_limits.push_back(timeout);++writes;
  unsigned index=start;
  for(unsigned i=0;i<n;++i){if(index<reg.size())reg[index]=p[i];if(!(reg[5]&0x20))index=(index+1)%11;}
  if(now)*now+=100;
  return si::Result::Ok;
 }
 si::Result read(unsigned char start,unsigned char*p,std::size_t n,int timeout){
  need(timeout>0&&timeout<=3,"finite read timeout");time_limits.push_back(timeout);
  unsigned index=start;
  for(unsigned i=0;i<n;++i){
   if(reset_at>=0&&static_cast<int>(bytes)==reset_at){reset();reset_at=-1;}
   p[i]=index==9?pins():reg[index];++bytes;
   if(!(reg[5]&0x20))index=(index+1)%11;
  }
  if(n==1&&start==0&&reset_after_guard){reset();reset_after_guard=false;}
  if(now)*now+=n==11?1260:360;
  return si::Result::Ok;
 }
};
struct Rig {
 si::Acquisition a{secondary::InputSource::Synthetic};Device d;std::uint64_t now=100000;
 Rig(){d.now=&now;}
 void step(unsigned mask=3){
  const auto issued=now;auto op=a.next(mask,now);
  if(op){auto r=si::execute(op,d,[&](){return now;});need(a.complete(op.token,r.reply,r.started_us,r.ended_us),"owned completion");}
  now=issued+5000;
 }
 void ready(){for(unsigned i=0;i<100&&!a.snapshot().ready;++i)step();need(a.snapshot().ready,"ready reached");}
 void prepare_read(bool high){
  ready();
  while(a.snapshot().challenge_high!=high||a.snapshot().phase!=si::Phase::Read)step();
 }
};
static void resets(){
 for(bool high:{false,true})for(int boundary=0;boundary<=11;++boundary){
  Rig r;r.prepare_read(high);r.d.bytes=0;r.d.reset_at=boundary;r.step();auto s=r.a.snapshot();
  need(!s.ready&&s.fault_pending,"every reset before trailing guard blocks frame");++reset_cases;
 }
 for(bool high:{false,true}){
  Rig r;r.prepare_read(high);r.d.bytes=0;r.d.reset_after_guard=true;r.step();
  need(r.a.snapshot().ready,"reset after guard is later unobserved event, not fictitious instantaneous detection");
  r.step();r.step();need(!r.a.snapshot().ready,"next guarded read detects post-guard reset");++reset_cases;
 }
}
static void mutations(){
 const unsigned owned[]={0,1,2,3,4,5,6,7,10};
 for(bool high:{false,true})for(unsigned byte:owned)for(unsigned bit=0;bit<8;++bit){
  Rig r;r.prepare_read(high);r.d.reg[byte]^=1U<<bit;r.step();
  need(!r.a.snapshot().ready&&r.a.snapshot().fault_pending,"every owned-register mutation rejected");++mutation_cases;
 }
 for(unsigned contact=0;contact<4;++contact){Rig r;r.d.contacts=contact;r.ready();const auto s=r.a.snapshot();
  need(s.samples[0].level==bool(contact&1)&&s.samples[1].level==bool(contact&2),"pin data independent of configuration readback");}
}
struct TimedBus {
 std::uint64_t&now;unsigned prepare_us=0,first_us=0,guard_us=0,calls=0;std::vector<int>limits;
 si::Result prepare(){now+=prepare_us;return si::Result::Ok;}
 si::Result read(unsigned char,unsigned char*p,std::size_t n,int timeout){++calls;limits.push_back(timeout);now+=calls==1?first_us:guard_us;for(unsigned i=0;i<n;++i)p[i]=0;return si::Result::Ok;}
 si::Result write(unsigned char,const unsigned char*,std::size_t,int){return si::Result::BusError;}
};
static void transport(){
 si::Request op;op.kind=si::Kind::GuardedRead;op.issued_us=100000;op.read_size=12;
 const unsigned times[]={0,1,999,1000,1001,1999,2000,2001,2999,3000,3001,9000};
 for(unsigned prepare:times)for(unsigned first:times)for(unsigned guard:{0U,1U,999U,1000U,1001U}){
  std::uint64_t now=100000;TimedBus b{now,prepare,first,guard,0,{}};auto out=si::execute(op,b,[&](){return now;});
  const bool first_started=prepare<=2000;
  const bool guard_started=first_started&&prepare+first<=2000;
  const bool accepted=guard_started&&prepare+first+guard<=3000;
  need((b.calls>=1)==first_started,"read does not start without a whole SDK millisecond");
  need((b.calls==2)==guard_started,"guard receives remaining whole milliseconds only");
  need((out.reply.result==si::Result::Ok)==accepted,"whole-operation budget oracle");
  for(int limit:b.limits)need(limit>=1&&limit<=3,"timeout never zero, negative or unbounded");
  need(out.reply.size==(accepted?12:0),"only complete guarded frame has declared size");++budget_cases;
 }
 // Reverse each clock observation while outer endpoints can remain ordered.
 for(unsigned position=0;position<7;++position){
  std::uint64_t unused=100000;TimedBus b{unused,0,0,0,0,{}};unsigned call=0;
  auto out=si::execute(op,b,[&](){const auto index=call++;return index==position?99999ULL:100000ULL;});
  need(out.reply.result==si::Result::ClockError,"intermediate clock reversal retained even after endpoints recover");
 }
}
static secondary::Rule input_rule(double debounce){secondary::Rule r;r.mode=secondary::Mode::Input;r.debounce_ms=debounce;return r;}
static void qualification(){
 for(double debounce:{0.,20.,500.})for(bool level:{false,true})for(unsigned mask:{1U,3U}){
  Rig r;r.d.contacts=level?3:0;r.ready();secondary::SwitchFilter filter;auto rule=input_rule(debounce);rule.input_channel=mask==1?0:1;
  unsigned qualified=0;auto first=r.a.snapshot().observed_us;
  for(unsigned i=0;i<120;++i){
   r.step(mask);const auto s=r.a.snapshot().samples[rule.input_channel];const auto state=filter.step(s,rule,r.now);
   if(state.valid){++qualified;need(s.observed_us-first>=static_cast<unsigned>(debounce*1000),"qualification not earlier than independent source-time period");}
  }
  need(qualified>0,"all supported debounce periods eventually qualify");
  const auto stable=r.a.snapshot();const auto source=stable.samples[rule.input_channel];
  auto exact=filter.step(source,rule,source.observed_us+20000);need(exact.valid,"20ms freshness inclusive");
  auto stale=filter.step(source,rule,source.observed_us+20001);need(!stale.valid&&stale.reason==secondary::Reason::InputStale,"20ms+1 invalidates qualification");
 }
 // Successful recovery must not outrun delivery of an invalid source sample.
 Rig r;r.ready();auto op=r.a.next(3,r.now);si::Reply error;error.result=si::Result::Timeout;
 need(r.a.complete(op.token,error,r.now,r.now+10),"fault applied");r.now+=5000;const auto first=r.a.snapshot();
 for(unsigned i=0;i<40;++i)r.step();
 need(r.a.snapshot().reads>first.reads,"wire reads recovered");
 need(r.a.snapshot().fault_pending&&!r.a.snapshot().samples[0].valid,"unobserved fault remains invalid through recovery");
 op=r.a.next(3,r.now);need(bool(op),"new op for second failure");need(r.a.complete(op.token,error,r.now,r.now+10),"second fault applied");r.now+=5000;
 const auto second=r.a.snapshot();need(second.fault_id>first.fault_id,"new fault has new identity");
 need(!r.a.invalid_sample_consumed(first.fault_id)&&r.a.snapshot().fault_pending,"old ack cannot clear second fault");
 need(r.a.invalid_sample_consumed(second.fault_id),"matching observed invalid identity consumed");need(!r.a.snapshot().ready,"ACK itself never manufactures fresh data");
 r.ready();need(r.a.snapshot().ready,"fresh read after consumption recovers");
}
int main(){resets();mutations();transport();qualification();std::printf("{\"passed\":true,\"assertions\":%u,\"reset_cases\":%u,\"register_mutations\":%u,\"budget_cases\":%u,\"physical_qualification\":false}\n",checks,reset_cases,mutation_cases,budget_cases);}
