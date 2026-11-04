#include "ecu/status_led.hpp"
#include "ecu/switch_transport.hpp"
#include <cassert>
#include <iostream>
#include <vector>
namespace sl=ecu::status_led;
namespace si=ecu::switch_input;
static unsigned checks=0;
static void verify(bool v,const char*expression,unsigned line){++checks;if(!v)std::cerr<<"Failed line "<<line<<": "<<expression<<" (check "<<checks<<")\n";assert(v);}
#define check(value) verify((value),#value,__LINE__)
struct Device {
 std::uint64_t now=100000,prepare_us=0,read_us=1200,guard_us=400,write_us=200;
 std::array<std::uint8_t,11> registers{0xff,0,0,0,0,0,0,0,0,0,0};
 si::Result error=si::Result::Ok;
 bool underfill=false,reset_guard=false;
 unsigned reads=0,writes=0;
 std::vector<std::pair<unsigned,unsigned>> written;
 si::Result prepare(){now+=prepare_us;return error;}
 si::Result read(std::uint8_t reg,std::uint8_t*bytes,std::size_t n,int timeout){
  check(timeout>=1&&timeout<=3);++reads;now+=n==11?read_us:guard_us;
  if(error!=si::Result::Ok)return error;
  if(underfill)return si::Result::Ok;
  if(reset_guard&&reg==0&&n==1){registers.fill(0);registers[0]=0xff;reset_guard=false;}
  for(unsigned i=0;i<n;++i){const auto index=reg+((registers[5]&0x20)?0:i);bytes[i]=index==9?std::uint8_t(registers[10]&~registers[0]):registers[index];}
  if(reg==0&&n==11)registers[7]=0; // GPIO/INTCAP read clears latched INTF.
  return si::Result::Ok;
 }
 si::Result write(std::uint8_t reg,const std::uint8_t*bytes,std::size_t n,int timeout){
  check(timeout>=1&&timeout<=3);++writes;now+=write_us;
  if(error!=si::Result::Ok)return error;
  for(unsigned i=0;i<n;++i){written.push_back({reg+i,bytes[i]});registers[reg+i]=bytes[i];}
  return si::Result::Ok;
 }
};
static sl::Snapshot tick(sl::Acquisition&a,Device&d,sl::Pattern p=sl::Pattern::Normal,unsigned used_us=0){
 const auto start=d.now;d.now+=used_us;const auto op=a.next(p,d.now,start);
 if(op){const auto done=si::execute(op,d,[&](){return d.now;});check(a.complete(op.token,done.reply,done.started_us,done.ended_us));}
 const auto sample=a.snapshot(d.now);d.now=std::max(d.now,start+5000);return sample;
}
static sl::Snapshot ready(sl::Acquisition&a,Device&d,sl::Pattern p=sl::Pattern::Normal){
 sl::Snapshot s;for(unsigned n=0;n<100;++n){s=tick(a,d,p);if(s.ready)return s;}
 std::cerr<<"LED not ready: phase="<<sl::phase_name(s.phase)<<" fault="<<si::fault_name(s.fault)<<" writes="<<d.writes<<" reads="<<d.reads<<"\n";check(false);return s;
}
static void policy(){
 for(std::uint64_t t:std::array<std::uint64_t,6>{{0,249999,250000,499999,500000,UINT64_MAX}}){
  check(sl::color(sl::Pattern::Normal,t)==2&&sl::color(sl::Pattern::Off,t)==0);
  check(sl::color(sl::Pattern::Pairing,t)==((t/250000)%2?4:0));
  check(sl::color(sl::Pattern::Problem,t)==((t/250000)%2?1:0));
 }
}
static void initialization_and_change(){
 sl::Acquisition a;Device d;
 auto s=ready(a,d);check(s.configured&&s.known&&s.verified_latch==2&&s.fresh&&s.desired_rgb==2);
 check(!a.snapshot(s.completed_us-1).fresh&&!a.snapshot(s.completed_us-1).ready);
 check(d.written.size()>=10&&d.written[0]==std::make_pair(10U,0U));
 check(d.written[1]==std::make_pair(5U,4U));
 for(unsigned n=0;n<7;++n)check(d.written[n+2]==std::make_pair(n,unsigned(sl::configuration[n])));
 check(d.written[9]==std::make_pair(10U,2U)); // only after configuration readback
 const auto first=s.observed_us;d.now+=sl::fresh_us+1;
 check(!a.snapshot(d.now).fresh&&!a.snapshot(d.now).ready&&a.snapshot(d.now).observed_us==first);
 s=ready(a,d,sl::Pattern::Off);check(s.verified_latch==0&&s.desired==sl::Pattern::Off);
 s=tick(a,d,sl::Pattern::Normal);check(s.known&&s.verified_latch==0&&s.written_rgb==2&&!s.ready);
 s=ready(a,d);check(s.ready&&s.verified_latch==2&&s.observed_us>first);
 // Policy changes coalesce while a prior write is waiting for verification.
 s=tick(a,d,sl::Pattern::Off);check(s.written_rgb==0&&!s.ready);
 s=tick(a,d,sl::Pattern::Normal);check(s.verified_latch==0&&!s.ready);
 s=ready(a,d);check(s.verified_latch==2&&s.ready);
}
static void shared_budget(){
 sl::Acquisition a;Device d;
 for(unsigned n=0;n<3;++n)tick(a,d);
 check(a.snapshot(d.now).phase==sl::Phase::Verify);
 auto reads=d.reads;auto attempts=a.snapshot(d.now).attempts;
 auto s=tick(a,d,sl::Pattern::Normal,1600);
 check(d.reads==reads&&s.attempts==attempts&&s.budget_skips==1&&!s.ready);
 // Two transactions run in the remaining budget on the switch-write tick.
 s=tick(a,d,sl::Pattern::Normal,200);check(s.known&&s.verified_latch==0&&d.reads==reads+2);
 s=ready(a,d);check(s.verified_latch==2);
 for(unsigned used:{0U,999U,1000U,1001U,1600U,1999U,2000U,2001U,2999U,3000U,3001U}){
  sl::Acquisition probe;Device backend;
  auto before=backend.now;const auto op=probe.next(sl::Pattern::Normal,before+used,before);
  check(bool(op)==(used<=2000));
  if(op){backend.now+=used;const auto done=si::execute(op,backend,[&](){return backend.now;});check(probe.complete(op.token,done.reply,done.started_us,done.ended_us));check(done.ended_us-before<=3000);}
 }
 // Preparation and SDK overruns count against the original shared deadline.
 a=sl::Acquisition{};d=Device{};d.prepare_us=1500;d.write_us=501;
 s=tick(a,d,sl::Pattern::Normal,1000);check(s.fault==si::Fault::Budget&&!s.ready);
 a=sl::Acquisition{};d=Device{};d.prepare_us=2001;
 s=tick(a,d);check(s.fault==si::Fault::Budget&&d.writes==0);
 a=sl::Acquisition{};d=Device{};d.write_us=1001;
 s=tick(a,d,sl::Pattern::Normal,2000);check(s.fault==si::Fault::Budget&&d.writes==1);
}
static void invalid_readback_and_recovery(){
 {
  sl::Acquisition a;Device d;ready(a,d,sl::Pattern::Off);d.registers[5]|=0x20;d.now+=sl::verify_us;
  const auto s=tick(a,d,sl::Pattern::Off);check(!s.ready&&!s.configured&&s.fault==si::Fault::Configuration);
 }
 for(unsigned reg:{0U,1U,2U,3U,4U,5U,6U,7U,10U}){
  sl::Acquisition a;Device d;ready(a,d);d.registers[reg]=reg==0?0xff:1;
  d.now+=sl::verify_us;auto s=tick(a,d);check(!s.ready&&!s.configured&&s.known&&s.last_fault==si::Fault::Configuration);
  s=ready(a,d);check(s.ready&&s.fault==si::Fault::None&&s.last_fault==si::Fault::Configuration&&s.failures==1);
 }
 sl::Acquisition a;Device d;auto s=ready(a,d);const auto stamp=s.observed_us;
 d.reset_guard=true;d.now+=sl::verify_us;s=tick(a,d);check(s.fault==si::Fault::Configuration&&!s.fresh&&s.observed_us==stamp);
 s=ready(a,d);d.underfill=true;d.now+=sl::verify_us;s=tick(a,d);check(s.fault==si::Fault::Configuration&&!s.ready);d.underfill=false;
 s=ready(a,d);d.error=si::Result::Timeout;d.now+=sl::verify_us;s=tick(a,d);check(s.fault==si::Fault::Timeout&&!s.fresh&&s.verified_latch==2);
 const auto traffic=d.reads+d.writes;for(unsigned n=0;n<19;++n)s=tick(a,d);check(traffic==d.reads+d.writes);d.error=si::Result::Ok;s=ready(a,d);check(s.fault==si::Fault::None&&s.last_fault==si::Fault::Timeout);
}
static void clock_and_tokens(){
 sl::Acquisition a;Device d;
 auto op=a.next(sl::Pattern::Normal,d.now,d.now);auto done=si::execute(op,d,[&](){return d.now;});
 check(!a.complete(op.token+1,done.reply,done.started_us,done.ended_us));
 check(a.complete(op.token,done.reply,done.started_us,done.ended_us));check(!a.complete(op.token,done.reply,done.started_us,done.ended_us));
 check(!a.next(sl::Pattern::Normal,done.ended_us-1,done.started_us));check(a.snapshot(d.now).phase==sl::Phase::Fatal);
 a=sl::Acquisition{};check(!a.next(sl::Pattern::Normal,100,101));check(a.snapshot(100).phase==sl::Phase::Fatal);
 a=sl::Acquisition{};check(!a.next(static_cast<sl::Pattern>(255),100,100));check(a.snapshot(100).fault==si::Fault::Internal);
 a=sl::Acquisition{};check(!a.next(sl::Pattern::Off,UINT64_MAX,UINT64_MAX));check(a.snapshot(UINT64_MAX).phase==sl::Phase::Fatal);
}
int main(){policy();initialization_and_change();shared_budget();invalid_readback_and_recovery();clock_and_tokens();std::cout<<"status_led_checks "<<checks<<"\n";}
