#include "ecu/tuning_session.hpp"
#include <array>
#include <cstring>
#include <iostream>
namespace tun=ecu::tuning;
static bool watch=false,deny=false;
static unsigned allocations=0,live=0,maximum=0,freed=0;
static std::array<void*,16> pointers{};
extern "C" void*__real_malloc(std::size_t);
extern "C" void __real_free(void*);
extern "C" void*__wrap_malloc(std::size_t n){
 if(watch&&n==sizeof(ecu::engine::Tune)){
  ++allocations;if(deny)return nullptr;void*p=__real_malloc(n);
  if(p){for(auto&v:pointers)if(!v){v=p;break;}++live;maximum=std::max(maximum,live);}return p;
 }
 return __real_malloc(n);
}
extern "C" void __wrap_free(void*p){
 for(auto&v:pointers)if(v==p&&p){v=nullptr;--live;++freed;break;}
 __real_free(p);
}
static unsigned checks=0,failures=0;
static void check(bool okay,const char*what){++checks;if(!okay){++failures;std::cout<<"FAIL,"<<what<<'\n';}}
struct Store:tun::Backend {
 ecu::engine::Tune active;
 unsigned loads=0,commits=0,successful=0,live_at_load=0,live_at_commit=0;
 tun::Result load_result=tun::Result::Ok,current_result=tun::Result::Ok,commit_result=tun::Result::Ok;
 bool race=false;
 tun::Result load(ecu::engine::Tune&t)override{++loads;live_at_load=live;t=active;return load_result;}
 tun::Result current(std::uint32_t&r)override{r=active.revision;return current_result;}
 tun::Result commit(const ecu::engine::Tune&t,std::uint32_t&saved)override{
  ++commits;live_at_commit=live;if(race)++active.revision;
  if(t.revision!=active.revision)return tun::Result::Conflict;
  if(commit_result!=tun::Result::Ok)return commit_result;
  active=t;saved=++active.revision;++successful;return tun::Result::Ok;
 }
 void sample(std::array<std::uint8_t,tun::live_bytes>&a)override{a.fill(0);}
};
static tun::Reply command(tun::Session&s,std::initializer_list<std::uint8_t>p){return s.command(p.begin(),p.size());}
static void stage(tun::Session&s,float value){std::array<std::uint8_t,11>p{'M',0,1,128,2,4,0};tun::put_float(p.data()+7,value);check(s.command(p.data(),p.size()).bytes[0]==0,"stage succeeds");}
int main(){
 Store b;tun::Session s(b);watch=true;deny=true;
 check(s.open()==tun::Result::NoMemory,"initial open allocation returns NoMemory");
 check(!s.stats().initialized&&s.stats().state==tun::WriteState::Busy&&s.stats().last_code==0x85,"initial open busy state");
 check(b.loads==0&&b.commits==0&&live==0,"no backend calls or live allocation after denied open");
 const auto before=allocations;check(command(s,{'p',0,1,0,0,4,0}).bytes[0]==0x85,"implicit open read returns busy");
 check(allocations==before+1&&!s.stats().initialized,"read retry attempted one allocation");
 check(command(s,{'Q'}).bytes[0]==0&&live==0,"discovery independent of failed open");
 deny=false;check(s.open()==tun::Result::Ok,"open retry succeeds");
 check(live==0&&b.live_at_load==1&&s.stats().initialized,"temporary freed before open returns");
 check(sizeof(s)<11*1024,"session steady RAM bound");
 stage(s,86);const auto staged=s.staged_page();const auto base=s.stats().base_revision,origin=s.stats().origin_revision;
 const auto writes=s.stats().writes;deny=true;auto reply=command(s,{'b',0,1});
 check(reply.bytes[0]==0x85&&reply.size==1&&s.stats().state==tun::WriteState::Busy,"burn denied allocation busy reply");
 check(s.staged_page()==staged&&s.stats().dirty&&s.stats().base_revision==base&&s.stats().origin_revision==origin&&s.stats().writes==writes,"denied burn preserves staged data");
 check(b.active.ve.cells[0]==85&&b.active.revision==1&&b.commits==0&&live==0,"denied burn preserves active data");
 deny=false;reply=command(s,{'b',0,1});
 check(reply.bytes[0]==4&&b.active.ve.cells[0]==86&&b.active.revision==2&&b.successful==1,"burn allocation retry commits once");
 check(!s.stats().dirty&&s.staged_page()==staged&&s.stats().origin_revision==origin&&s.stats().base_revision==2,"origin stable after retry");
 check(live==0&&b.live_at_commit==1,"scratch lifetime covers commit only");
 const auto noalloc=allocations;reply=command(s,{'b',0,1});check(reply.bytes[0]==4&&allocations==noalloc&&b.successful==1,"acknowledged burn retry idempotent allocation free");
 // Backend failure after a successful scratch allocation also frees it and
 // preserves exactly the same staged bytes for a later retry.
 stage(s,87);const auto failed=s.staged_page();b.commit_result=tun::Result::NoMemory;reply=command(s,{'b',0,1});
 check(reply.bytes[0]==0x85&&live==0&&s.staged_page()==failed&&s.stats().dirty,"backend NoMemory retains staging and frees temporary");
 check(b.active.ve.cells[0]==86&&b.active.revision==2,"backend NoMemory no activation");
 b.commit_result=tun::Result::StorageBlocked;reply=command(s,{'b',0,1});check(reply.bytes[0]==0x84&&live==0&&s.staged_page()==failed&&s.stats().dirty,"blocked storage releases scratch preserves stage");
 b.commit_result=tun::Result::Ok;reply=command(s,{'b',0,1});check(reply.bytes[0]==4&&live==0&&b.active.ve.cells[0]==87&&b.active.revision==3,"backend retry succeeds");
 stage(s,88);const auto conflict=s.staged_page();b.race=true;reply=command(s,{'b',0,1});
 check(reply.bytes[0]==0x84&&s.stats().state==tun::WriteState::Conflict&&s.staged_page()==conflict&&live==0,"commit race retains origin/base/stage");
 check(b.active.ve.cells[0]==87&&b.active.revision==4,"race only external revision advanced");b.race=false;
 const auto before_conflict=allocations;reply=command(s,{'b',0,1});check(reply.bytes[0]==0x84&&allocations==before_conflict,"stale retry rejects before allocating");
 check(s.open()==tun::Result::Ok&&live==0&&s.stats().origin_revision==4,"conflict reopens current backend");
 stage(s,NAN);const auto invalid=s.staged_page();const auto commits=b.commits;reply=command(s,{'b',0,1});
 check(reply.bytes[0]==0x84&&s.stats().state==tun::WriteState::Invalid&&s.staged_page()==invalid&&b.commits==commits&&live==0,"invalid staged tune releases scratch without commit");
 // Explicit reconnect continues to discard staged edits even if allocating
 // its new snapshot fails. This differs intentionally from a failed burn.
 deny=true;check(s.open()==tun::Result::NoMemory,"explicit reopen may fail allocation");
 check(!s.stats().dirty&&!s.stats().initialized&&s.stats().origin_revision==0&&s.stats().base_revision==0,"explicit reconnect abandons staging before attempting new snapshot");
 deny=false;b.load_result=tun::Result::NoMemory;check(s.open()==tun::Result::NoMemory&&live==0,"backend load NoMemory releases scratch");
 b.load_result=tun::Result::StorageBlocked;check(s.open()==tun::Result::StorageBlocked&&s.stats().initialized&&live==0,"blocked snapshot remains readable");
 check(command(s,{'p',0,1,0,0,4,0}).bytes[0]==0,"blocked snapshot read");
 b.load_result=tun::Result::Ok;b.current_result=tun::Result::StorageBlocked;const auto before_blocked=allocations;
 check(command(s,{'b',0,1}).bytes[0]==0x84&&allocations==before_blocked,"storage-blocked burn rejects before allocation");
 b.current_result=tun::Result::Ok;b.active.revision=UINT32_MAX;s.open();stage(s,88);const auto before_max=allocations;
 check(command(s,{'b',0,1}).bytes[0]==0x84&&allocations==before_max&&live==0,"revision overflow rejects before allocation");
 for(unsigned change=0;change<9;++change){
  b.active=ecu::engine::Tune{};
  if(change==0){b.active.secondary_tables.fuel.mode=ecu::secondary::Mode::Multiply;b.active.secondary_tables.fuel.cells=ecu::secondary::Cells::Multiplier;}
  else if(change==1)b.active.secondary_tables.fuel.threshold=3001;
  else if(change==2)b.active.secondary_tables.spark.active_high=false;
  else if(change==3)b.active.secondary_tables.spark.input_channel=0;
  else if(change==4)b.active.secondary_ve.rpm[0]=81;
  else if(change==5)b.active.secondary_spark.load[0]=11;
  else if(change==6)b.active.secondary_ve.cells[125]=86;
  else if(change==7)b.active.secondary_spark.cells[193]=16;
  else b.active.secondary_tables.fuel.cells=ecu::secondary::Cells::Multiplier;
  check(!ecu::engine::validate(b.active),"unrepresented backend fixture otherwise valid");
  std::array<unsigned char,sizeof(ecu::engine::Tune)> original;std::memcpy(original.data(),&b.active,sizeof(b.active));
  const auto before_commit=b.commits;
  check(s.open()==tun::Result::Invalid&&!s.stats().initialized&&s.stats().last_code==0x84&&live==0,"own008 rejects enabled or edited secondary state");
  check(std::memcmp(original.data(),&b.active,sizeof(b.active))==0&&b.commits==before_commit,"unrepresented open does not mutate backend");
 }
 b.active=ecu::engine::Tune{};check(s.open()==tun::Result::Ok&&live==0,"canonical own008 reopens after rejection");
 check(maximum==1,"one scratch allocation maximum in session");
 std::cout<<"TOTAL,"<<checks<<",FAILURES,"<<failures<<",ALLOCATIONS,"<<allocations<<",FREED,"<<freed<<",LIVE,"<<live<<",MAXIMUM,"<<maximum<<",SESSION_BYTES,"<<sizeof(s)<<",TUNE_BYTES,"<<sizeof(ecu::engine::Tune)<<'\n';
 return failures?1:0;
}
