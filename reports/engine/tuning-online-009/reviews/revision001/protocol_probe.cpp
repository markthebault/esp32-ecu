#include "ecu/tuning_stream.hpp"
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>

using Bytes=std::vector<std::uint8_t>;
using namespace ecu::tuning;
static std::uint32_t reference_crc(const Bytes& b) {
  std::uint32_t r=0xffffffff;
  for(auto c:b) { r^=c; for(unsigned i=0;i<8;i++) r=(r&1)?(r>>1)^0xedb88320:(r>>1); }
  return r^0xffffffff;
}
static Bytes frame(const Bytes& p) {
  Bytes b{std::uint8_t(p.size()>>8),std::uint8_t(p.size())};
  b.insert(b.end(),p.begin(),p.end());const auto c=reference_crc(p);
  for(int s=24;s>=0;s-=8)b.push_back(c>>s);
  return b;
}
static Bytes unframe(const Bytes& b) {
  assert(b.size()>=7);const auto n=unsigned(b[0])*256+b[1];assert(b.size()==n+6);
  Bytes p(b.begin()+2,b.begin()+2+n);std::uint32_t c=0;
  for(unsigned i=0;i<4;i++)c=c*256+b[2+n+i];
  assert(c==reference_crc(p));return p;
}
static Bytes request(char kind,unsigned offset,unsigned n,const Bytes& data={}) {
  Bytes b{std::uint8_t(kind),0,1,std::uint8_t(offset),std::uint8_t(offset>>8),std::uint8_t(n),std::uint8_t(n>>8)};
  b.insert(b.end(),data.begin(),data.end());return b;
}
static Bytes number(unsigned offset,float value) {
  Bytes data(4);std::uint32_t word;std::memcpy(&word,&value,4);
  for(unsigned i=0;i<4;i++)data[i]=word>>(8*i);
  return request('M',offset,4,data);
}
struct Store:Backend {
  ecu::engine::Tune tune;Result storage=Result::Ok,next=Result::Ok;unsigned saves=0;
  Result load(ecu::engine::Tune& t)override { t=tune;return storage; }
  Result current(std::uint32_t& r)override { r=tune.revision;return storage; }
  Result commit(const ecu::engine::Tune& t,std::uint32_t& r)override {
    if(storage!=Result::Ok)return storage;
    if(t.revision!=tune.revision)return Result::Conflict;
    if(next!=Result::Ok)return next;
    tune=t;r=++tune.revision;++saves;return Result::Ok;
  }
  void sample(std::array<std::uint8_t,live_bytes>& b)override { b.fill(0); }
};
struct Fixture {
  Store store;Session session;Stream stream;std::vector<Bytes> replies;
  Fixture():session(store),stream(session){assert(session.open()==Result::Ok);}
  void feed(const Bytes& b,std::uint64_t now) {
    stream.feed(b.data(),b.size(),now,[&](const std::uint8_t* p,std::size_t n){replies.emplace_back(p,p+n);return true;});
  }
  Bytes cmd(const Bytes& p,std::uint64_t now=1000){const auto n=replies.size();feed(frame(p),now);assert(replies.size()==n+1);return unframe(replies.back());}
};
int main() {
  assert(reference_crc(Bytes{'1','2','3','4','5','6','7','8','9'})==0xcbf43926);
  assert(Session::crc32(reinterpret_cast<const std::uint8_t*>("123456789"),9)==0xcbf43926);
  Fixture f;
  Bytes discovery{0xf0,'F'};
  for(Bytes p:std::vector<Bytes>{{'I'},{'f',0},{'f',255},{'Q'},{'F'},{'C'}}){const auto q=frame(p);discovery.insert(discovery.end(),q.begin(),q.end());}
  f.feed(discovery,1000);assert(f.replies.size()==7);
  assert(f.replies[0]==Bytes({'0','0','2'}));assert(unframe(f.replies[1])==Bytes({0,0}));
  assert(unframe(f.replies[2])==Bytes({0,2,1,0,1,0}));assert(f.replies[2]==f.replies[3]);
  assert(unframe(f.replies[4])==Bytes({0,'E','S','P','3','2','E','C','U',' ','D','E','V',' ','0','0','9',' ','I','N','H','I','B','I','T','E','D'}));
  assert(unframe(f.replies[5])==Bytes({0,'0','0','2'}));assert(unframe(f.replies[6])==Bytes({0,255}));
  Bytes all;
  for(unsigned o=0;o<8192;o+=256){const auto b=f.cmd(request('p',o,256),2000+o);assert(b.size()==257&&b[0]==0);all.insert(all.end(),b.begin()+1,b.end());}
  assert(std::equal(all.begin(),all.end(),f.session.staged_page().begin()));
  const auto crc=f.cmd({'d',0,1},11000);assert(crc.size()==5&&crc[0]==0);std::uint32_t wire_crc=0;
  for(unsigned i=1;i<5;i++)wire_crc=wire_crc*256+crc[i];
  assert(wire_crc==reference_crc(all));
  assert(f.cmd({'r',0,0x30,0,0,0x80,2},12000).size()==641);assert(f.replies.back().size()==647);
  assert(f.cmd({'r',0,0x30,0x7f,2,2,0},13000)==Bytes({0x84}));
  assert(f.cmd(request('p',8191,2),14000)==Bytes({0x84}));
  assert(f.cmd(number(640,86),15000)==Bytes({0}));assert(f.store.tune.ve.cells[0]==85);
  const auto staged=f.session.staged_page();const auto staged_crc=f.cmd({'d',0,1},16000);
  assert(f.cmd({'b',0,1},17000)==Bytes({4}));assert(f.store.saves==1&&f.store.tune.ve.cells[0]==86);
  assert(f.session.stats().origin_revision==1&&f.session.stats().base_revision==2);
  assert(f.session.staged_page()==staged&&f.cmd({'d',0,1},18000)==staged_crc);
  assert(f.cmd({'b',0,1},19000)==Bytes({4})&&f.store.saves==1);
  ++f.store.tune.revision;assert(f.cmd({'b',0,1},20000)==Bytes({0x84}));
  assert(f.cmd(number(640,90),21000)==Bytes({0x84}));assert(f.store.tune.ve.cells[0]==86);
  // Exhaustively split a maximum-size frame, with every possible octet in data.
  Bytes octets;for(unsigned i=0;i<256;i++)octets.push_back(i);const auto max=frame(request('M',512,256,octets));assert(max.size()==269);
  for(unsigned split=1;split<max.size();split++){
    Fixture t;t.feed(Bytes(max.begin(),max.begin()+split),1000);assert(t.replies.empty());
    t.feed(Bytes(max.begin()+split,max.end()),25999);assert(t.replies.size()==1&&unframe(t.replies[0])==Bytes({0}));
    assert(t.store.saves==0&&t.session.stats().writes==1);
  }
  Fixture timeout;timeout.feed(Bytes(max.begin(),max.begin()+20),1000);timeout.feed({},26000);
  assert(timeout.replies.size()==1&&unframe(timeout.replies[0])==Bytes({0x80}));assert(timeout.session.stats().writes==0);
  timeout.feed({'F'},27000);assert(timeout.replies.back()==Bytes({'0','0','2'}));
  Fixture corrupt;auto bad=max;bad.back()^=1;corrupt.feed(bad,1000);assert(unframe(corrupt.replies[0])==Bytes({0x82}));assert(corrupt.session.stats().writes==0);
  Fixture tx;Bytes coalesced=frame(number(640,87));auto burn=frame({'b',0,1}),extra=frame(number(640,90));
  coalesced.insert(coalesced.end(),burn.begin(),burn.end());coalesced.insert(coalesced.end(),extra.begin(),extra.end());unsigned sends=0;
  tx.stream.feed(coalesced.data(),coalesced.size(),1000,[&](const std::uint8_t*,std::size_t){return ++sends!=2;});
  assert(tx.store.saves==1&&tx.store.tune.ve.cells[0]==87&&tx.session.stats().commands==2&&tx.stream.transmit_fault());
  tx.feed(extra,2000);assert(tx.session.stats().commands==2);tx.feed({'F'},27000);
  assert(!tx.stream.transmit_fault()&&!tx.session.stats().dirty&&tx.store.tune.ve.cells[0]==87);
  Fixture persistence;assert(persistence.cmd(number(640,88))==Bytes({0}));persistence.store.next=Result::StorageBlocked;
  assert(persistence.cmd({'b',0,1},2000)==Bytes({0x84}));assert(persistence.store.saves==0&&persistence.store.tune.ve.cells[0]==85&&persistence.session.stats().dirty);
  persistence.store.storage=Result::StorageBlocked;assert(persistence.cmd(number(640,89),3000)==Bytes({0x84}));
  // Record lazy-open behavior after a bus disconnect as an explicit boundary.
  Fixture reconnect;assert(reconnect.cmd(number(640,89))==Bytes({0}));reconnect.stream.disconnect();
  assert(!reconnect.session.stats().initialized&&!reconnect.session.stats().dirty);++reconnect.store.tune.revision;
  assert(reconnect.cmd(number(640,90),2000)==Bytes({0}));assert(reconnect.session.stats().origin_revision==2);
  std::cout<<"{\"passed\":true,\"discovery_responses\":7,\"page_read_bytes\":8192,\"maximum_M_frame_bytes\":269,\"split_boundaries\":268,\"full_runtime_wire_bytes\":647,\"crc_fixture\":\"cbf43926\",\"burn_origin_stable\":true,\"external_save_conflict\":true,\"timeout_crc_no_execution\":true,\"failed_burn_reply_stops_following_commands\":true,\"storage_rejection_retains_active_tune\":true,\"disconnect_drops_stage_but_next_M_lazy_opens\":true}\n";
}
