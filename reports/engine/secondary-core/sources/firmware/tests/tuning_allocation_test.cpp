#include "ecu/tuning_session.hpp"
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <vector>
using namespace ecu::tuning;
static bool fail_tune=false;
static unsigned allocations=0,failures=0;
extern "C" void* __real_malloc(std::size_t);
extern "C" void* __wrap_malloc(std::size_t n){
 if(n==sizeof(ecu::engine::Tune)){++allocations;if(fail_tune){++failures;return nullptr;}}
 return __real_malloc(n);
}
struct Store:Backend {
 ecu::engine::Tune tune;unsigned loads=0,saves=0;
 Result load(ecu::engine::Tune&t)override{++loads;t=tune;return Result::Ok;}
 Result current(std::uint32_t&r)override{r=tune.revision;return Result::Ok;}
 Result commit(const ecu::engine::Tune&t,std::uint32_t&r)override{
  if(t.revision!=tune.revision)return Result::Conflict;
  ++saves;tune=t;r=++tune.revision;return Result::Ok;
 }
 void sample(std::array<std::uint8_t,live_bytes>&b)override{b.fill(0);}
};
static Reply command(Session&s,std::initializer_list<std::uint8_t>v){return s.command(v.begin(),v.size());}
int main(){
 Store store;Session session(store);
 static_assert(sizeof(Session)<11*1024,"Resident tuning session exceeded its pre-secondary budget");
 fail_tune=true;assert(session.open()==Result::NoMemory);
 assert(!session.stats().initialized&&!session.stats().dirty&&session.stats().state==WriteState::Busy&&session.stats().last_code==0x85);
 assert(store.loads==0&&store.saves==0&&store.tune.revision==1);
 assert(command(session,{'p',0,1,0,0,4,0}).bytes[0]==0x85);
 assert(!session.stats().initialized&&store.loads==0);
 fail_tune=false;assert(session.open()==Result::Ok&&session.stats().initialized);
 const auto original=session.staged_page();std::uint8_t value[4];put_float(value,90);
 std::vector<std::uint8_t>write={'M',0,1,128,2,4,0};write.insert(write.end(),value,value+4);
 assert(session.command(write.data(),write.size()).bytes[0]==0&&session.stats().dirty);
 const auto staged=session.staged_page();assert(staged!=original);
 fail_tune=true;assert(command(session,{'b',0,1}).bytes[0]==0x85);
 assert(session.stats().dirty&&session.stats().base_revision==1&&session.staged_page()==staged);
 assert(store.saves==0&&store.tune.revision==1&&store.tune.ve.cells[0]==85);
 // A failed allocation does not bypass a later independent editor's revision.
 ++store.tune.revision;fail_tune=false;assert(command(session,{'b',0,1}).bytes[0]==0x84);
 assert(session.stats().state==WriteState::Conflict&&session.staged_page()==staged&&store.saves==0);
 assert(session.open()==Result::Ok);assert(session.command(write.data(),write.size()).bytes[0]==0);
 fail_tune=true;assert(command(session,{'b',0,1}).bytes[0]==0x85);fail_tune=false;
 assert(command(session,{'b',0,1}).bytes[0]==4&&store.saves==1&&store.tune.ve.cells[0]==90&&store.tune.revision==3);
 const auto after_success=allocations;assert(command(session,{'b',0,1}).bytes[0]==4&&allocations==after_success&&store.saves==1);
 assert(failures==4);
 // A programmatic model newer than own008 is unavailable through that ABI;
 // opening the editor must not silently discard its unrepresented fields.
 store.tune.secondary_tables.fuel.mode=ecu::secondary::Mode::Multiply;
 store.tune.secondary_tables.fuel.cells=ecu::secondary::Cells::Multiplier;
 assert(session.open()==Result::Invalid&&!session.stats().initialized&&session.stats().state==WriteState::Invalid);
 assert(store.tune.secondary_tables.fuel.mode==ecu::secondary::Mode::Multiply&&store.saves==1);
 ecu::engine::reset_secondary_tables(store.tune);store.tune.secondary_ve.cells[0]=100;
 assert(session.open()==Result::Invalid&&!session.stats().initialized&&store.tune.secondary_ve.cells[0]==100);
 ecu::engine::reset_secondary_tables(store.tune);assert(session.open()==Result::Ok);
 std::cout<<"{\"passed\":true,\"allocation_failures\":"<<failures<<",\"session_bytes\":"<<sizeof(Session)<<",\"temporary_tune_bytes\":"<<sizeof(ecu::engine::Tune)<<"}\n";
}
