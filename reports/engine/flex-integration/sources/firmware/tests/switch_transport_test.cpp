#include "ecu/switch_transport.hpp"
#include <cstdio>
#include <cstdlib>
#include <vector>
namespace si=ecu::switch_input;
unsigned checks=0;
void check(bool ok,const char*why){++checks;if(!ok){std::fprintf(stderr,"Check%u failed: %s\n",checks,why);std::abort();}}
struct Backend {
 std::uint64_t now=100000;unsigned prepares=0,reads=0,writes=0;
 std::uint64_t setup_us=0,first_us=0,guard_us=0;
 si::Result setup=si::Result::Ok,transfer=si::Result::Ok;
 bool reverse_first=false,underfill=false;
 std::vector<int> timeouts;
 si::Result prepare(){++prepares;now+=setup_us;return setup;}
 si::Result read(std::uint8_t reg,std::uint8_t*data,std::size_t n,int timeout){
  ++reads;timeouts.push_back(timeout);check(reg==0||reg==9,"Only contract registers read");
  if(!underfill)for(std::size_t i=0;i<n;++i)data[i]=static_cast<std::uint8_t>(i+1);
  now+=reads==1?first_us:guard_us;if(reverse_first&&reads==1)now-=10000;return transfer;
 }
 si::Result write(std::uint8_t,const std::uint8_t*,std::size_t,int timeout){++writes;timeouts.push_back(timeout);now+=first_us;return transfer;}
};
si::Request read_request(){si::Request op;op.kind=si::Kind::GuardedRead;op.token=1;op.issued_us=100000;op.read_size=12;return op;}
int main(){
 const std::uint64_t delays[]={0,900,1000,1700,2000,3001};unsigned combinations=0;
 for(auto setup:delays)for(auto first:delays)for(auto guard:delays){
  Backend b;b.setup_us=setup;b.first_us=first;b.guard_us=guard;auto op=read_request();
  const auto out=si::execute(op,b,[&]{return b.now;});++combinations;
  const bool start_read=setup<=2000;
  const bool start_guard=start_read&&setup+first<=2000;
  check(b.prepares==1&&b.reads==unsigned(start_read)+unsigned(start_guard),"No further call after exhausted integer-ms budget");
  check((out.reply.result==si::Result::Ok)==(start_guard&&setup+first+guard<=3000),"Actual whole-operation duration governs acceptance");
  check(out.started_us==100000&&out.ended_us==b.now,"Source start and completion preserved");
  check(out.reply.size==(out.reply.result==si::Result::Ok?12:0),"Failed operation never supplies a valid length");
  for(auto timeout:b.timeouts)check(timeout>=1&&timeout<=3,"Never pass zero, infinite or rounded-up timeout");
  if(start_read)check(b.timeouts[0]==int((3000-setup)/1000),"First call gets remaining floor budget");
  if(start_guard)check(b.timeouts[1]==int((3000-setup-first)/1000),"Guard gets new remaining floor budget");
 }
 for(auto error:{si::Result::Unavailable,si::Result::Timeout,si::Result::BusError}){
  Backend b;b.setup=error;auto out=si::execute(read_request(),b,[&]{return b.now;});
  check(out.reply.result==error&&!b.reads,"Setup failure does not start I2C traffic");
  Backend c;c.transfer=error;out=si::execute(read_request(),c,[&]{return c.now;});
  check(out.reply.result==error&&c.reads==1,"First-read error prevents guard read");
 }
 {
  Backend b;b.reverse_first=true;auto out=si::execute(read_request(),b,[&]{return b.now;});
  check(out.reply.result==si::Result::ClockError&&b.reads==1,"Intermediate clock reversal prevents more traffic");
  Backend c;c.now=99999;out=si::execute(read_request(),c,[&]{return c.now;});
  check(out.reply.result==si::Result::ClockError&&!c.prepares,"Late callback cannot mask initial reversed clock");
 }
 {
  Backend b;b.underfill=true;auto out=si::execute(read_request(),b,[&]{return b.now;});
  check(out.reply.data[0]==0xa5&&out.reply.data[11]==0xa5,"SDK success without filled bytes leaves poison, never prior frame data");
  Backend c;auto op=read_request();op.issued_us=1;out=si::execute(op,c,[&]{return c.now;});
  check(out.reply.result==si::Result::NoBudget&&!c.prepares,"Stale issued request cannot start setup");
 }
 {
  Backend b;si::Request op;op.kind=si::Kind::Configure;op.token=2;op.issued_us=b.now;op.write_size=7;
  const auto out=si::execute(op,b,[&]{return b.now;});check(out.reply.result==si::Result::Ok&&out.reply.size==0&&b.writes==1&&!b.reads,"Write returns no invented GPIO bytes");
  op.read_size=1;const auto invalid=si::execute(op,b,[&]{return b.now;});check(invalid.reply.result==si::Result::BusError&&b.writes==1,"Malformed request cannot mutate device");
 }
 std::printf("{\"passed\":true,\"transport_checks\":%u,\"delay_combinations\":%u,\"target_timing_qualified\":false}\n",checks,combinations);
}
