#include "ecu/tuning_stream.hpp"
#include "ecu/tuning_live.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace ecu::tuning;
struct Store:Backend {
 ecu::engine::Tune tune;Result state=Result::Ok,write_result=Result::Ok;unsigned saves=0;
 Result load(ecu::engine::Tune&t)override{t=tune;return state;}
 Result current(std::uint32_t&r)override{r=tune.revision;return state;}
 Result commit(const ecu::engine::Tune&t,std::uint32_t&r)override{
  if(t.revision!=tune.revision)return Result::Conflict;
  if(write_result!=Result::Ok)return write_result;
  tune=t;++tune.revision;r=tune.revision;++saves;return Result::Ok;
 }
 void sample(std::array<std::uint8_t,live_bytes>&b)override{b.fill(0);put_u32(b.data()+52,1);}
};
Reply command(Session&s,std::vector<std::uint8_t>p){return s.command(p.data(),p.size());}
std::vector<std::uint8_t> write(unsigned offset,const std::uint8_t*p,unsigned n){std::vector<std::uint8_t>v={'M',0,1,std::uint8_t(offset),std::uint8_t(offset>>8),std::uint8_t(n),std::uint8_t(n>>8)};v.insert(v.end(),p,p+n);return v;}
void floating(Session&s,unsigned offset,float v){std::uint8_t bytes[4];put_float(bytes,v);assert(command(s,write(offset,bytes,4)).bytes[0]==0);}
std::vector<std::uint8_t> frame(std::vector<std::uint8_t>p){const auto crc=Session::crc32(p.data(),p.size());std::vector<std::uint8_t>v={std::uint8_t(p.size()>>8),std::uint8_t(p.size())};v.insert(v.end(),p.begin(),p.end());for(unsigned i=0;i<4;++i)v.push_back(std::uint8_t(crc>>(24-8*i)));return v;}
int main(){
 // Invalid/absent inputs remain visibly unavailable; source and age are not
 // inferred from an open tuning session or the active calibration revision.
 std::array<std::uint8_t,live_bytes> live;ecu::engine::RuntimeSample sample;
 live_block(sample,1000,live);assert(get_u32(live.data()+52)==1&&get_u32(live.data()+64)==UINT32_MAX&&get_u32(live.data()+72)==0);
 sample.sequence=7;sample.flags=ecu::engine::Present|ecu::engine::CrankSynced|ecu::engine::PhaseRequired;
 sample.control_us=sample.sampled_us=1000;sample.tune_revision=9;sample.source=ecu::engine::DataSource::Target;
 sample.inputs[ecu::engine::MapKpa]=80;sample.proposals[ecu::engine::PulseMs]=3;sample.cylinder_valid=1;sample.cylinder_pulse_ms={3,4,5,6};
 live_block(sample,2000,live);assert(get_float(live.data()+8)==0&&get_float(live.data()+20)==3&&get_u32(live.data()+56)==9&&get_u32(live.data()+60)==2&&get_u32(live.data()+48)==0);
 assert(get_float(live.data()+100)==3&&get_float(live.data()+116)==0&&get_u32(live.data()+212)&ecu::engine::DisplayFresh);
 sample.input_valid=1U<<ecu::engine::MapKpa;sample.flags|=ecu::engine::PhaseSynced;live_block(sample,1001001,live);
 assert(get_float(live.data()+8)==80&&get_u32(live.data()+48)==1&&get_u32(live.data()+208)==sample.input_valid&&!(get_u32(live.data()+212)&ecu::engine::DisplayFresh));
 Store store;Session s(store);assert(s.open()==Result::Ok);assert(sizeof(Session)<10000);
 const auto original=s.staged_page();ecu::engine::Tune decoded;assert(decode_page(original,1,decoded));Page again;encode_page(decoded,1,again);assert(again==original);
 floating(s,512+128,86);assert(store.tune.ve.cells[0]==85);const auto pending=s.staged_page();const auto crc=Session::crc32(pending.data(),pending.size());
 assert(command(s,{'b',0,1}).bytes[0]==4);assert(store.tune.ve.cells[0]==86&&store.tune.revision==2&&s.stats().base_revision==2&&s.stats().origin_revision==1);
 assert(s.staged_page()==pending&&Session::crc32(s.staged_page().data(),page_bytes)==crc);
 assert(command(s,{'b',0,1}).bytes[0]==4&&store.saves==1);
 floating(s,512+128,87);assert(command(s,{'b',0,1}).bytes[0]==4&&store.tune.revision==3&&store.saves==2);
 std::uint8_t changed_revision[4];put_u32(changed_revision,3);const auto before=s.staged_page();assert(command(s,write(268,changed_revision,4)).bytes[0]==0x84&&s.staged_page()==before);
 std::uint8_t bad_chunk[8]{};bad_chunk[7]=1;assert(command(s,write(285,bad_chunk,8)).bytes[0]==0x84&&s.staged_page()==before);
 ++store.tune.revision;assert(command(s,{'b',0,1}).bytes[0]==0x84&&s.stats().state==WriteState::Conflict);assert(store.saves==2);
 assert(s.open()==Result::Ok&&s.stats().origin_revision==4);floating(s,512+128,88);store.write_result=Result::NoMemory;assert(command(s,{'b',0,1}).bytes[0]==0x85&&s.stats().dirty&&store.tune.ve.cells[0]==87);
 store.write_result=Result::StorageBlocked;assert(command(s,{'b',0,1}).bytes[0]==0x84&&s.stats().dirty&&store.tune.ve.cells[0]==87);
 store.write_result=Result::Ok;assert(command(s,{'b',0,1}).bytes[0]==4&&store.tune.ve.cells[0]==88);
 // A valid multi-field strategy transition is staged inside the same page.
 store.tune.strategy=ecu::engine::Strategy::Sequential;store.tune.cylinder_trims_enabled=true;++store.tune.revision;s.open();
 std::uint8_t zero[4]{};assert(command(s,write(272,zero,4)).bytes[0]==0);assert(command(s,{'b',0,1}).bytes[0]==0x84);assert(store.tune.strategy==ecu::engine::Strategy::Sequential);
 assert(command(s,write(4752,zero,4)).bytes[0]==0);assert(command(s,{'b',0,1}).bytes[0]==4&&store.tune.strategy==ecu::engine::Strategy::BatchWasted&&!store.tune.cylinder_trims_enabled);
 // One maximum-size M frame is269 bytes; TX for a256-byte read is263.
 Stream stream(s);std::vector<std::vector<std::uint8_t>> replies;auto send=[&](const std::uint8_t*p,std::size_t n){replies.emplace_back(p,p+n);return true;};
 const auto q=frame({'Q'});for(std::size_t i=0;i<q.size();++i)stream.feed(q.data()+i,1,1000+i,send);assert(replies.size()==1&&replies[0]==frame(std::vector<std::uint8_t>({'\0','E','S','P','3','2','E','C','U',' ','D','E','V',' ','0','0','6',' ','I','N','H','I','B','I','T','E','D'})));
 auto corrupt=q;corrupt.back()^=1;stream.feed(corrupt.data(),corrupt.size(),2000,send);assert(replies.back()==frame({0x82}));
 std::uint8_t chunk[256];std::copy_n(s.staged_page().data()+512,256,chunk);const auto max=frame(write(512,chunk,256));assert(max.size()==269);stream.feed(max.data(),max.size(),3000,send);assert(replies.back()==frame({0}));
 const auto r=frame({'p',0,1,0,2,0,1});stream.feed(r.data(),r.size(),4000,send);assert(replies.back().size()==263);
 const auto resets=s.stats().resets;const std::uint8_t f='F';stream.feed(&f,1,5000,send);assert(s.stats().resets==resets&&s.stats().dirty);
 stream.feed(&f,1,30000,send);assert(s.stats().resets==resets+1&&!s.stats().dirty&&replies.back()==std::vector<std::uint8_t>({'0','0','2'}));
 stream.feed(max.data(),5,31000,send);const auto writes=s.stats().writes;stream.feed(&f,1,56000,send);assert(stream.stats().timeouts==1&&s.stats().writes==writes&&replies[replies.size()-2]==frame({0x80}));
 const auto buried=frame(write(640,reinterpret_cast<const std::uint8_t*>("FQSF"),4));const auto resets2=s.stats().resets;stream.feed(buried.data(),buried.size(),57000,send);assert(s.stats().resets==resets2&&s.stats().dirty);
 auto reject=[](const std::uint8_t*,std::size_t){return false;};stream.feed(q.data(),q.size(),58000,reject);assert(stream.transmit_fault());const auto commands=s.stats().commands;stream.feed(max.data(),max.size(),59000,send);assert(s.stats().commands==commands);
 stream.feed(&f,1,84000,send);assert(!stream.transmit_fault()&&!s.stats().dirty);
 const auto bad=frame({'M',0,1,0,2,1,0,1});stream.feed(bad.data(),bad.size(),85000,send);assert(s.stats().dirty);const auto dirty=s.staged_page();++store.tune.revision;
 stream.feed(q.data(),q.size(),86000,send);assert(s.staged_page()==dirty);assert(command(s,{'b',0,1}).bytes[0]==0x84);
 const std::uint8_t reset[] = {0xf0,'F'};const auto reply_count=replies.size(),reset_count=s.stats().resets;
 stream.feed(reset,2,111000,send);assert(replies.size()==reply_count+1&&s.stats().resets==reset_count+1&&!s.stats().dirty);
 assert(replies.back()==std::vector<std::uint8_t>({'0','0','2'}));
 const std::uint8_t embedded[]={0xf0,'F',0,0};const auto f0=frame(write(640,embedded,4));stream.feed(f0.data(),f0.size(),112000,send);assert(s.stats().resets==reset_count+1&&s.stats().dirty);
 stream.disconnect();assert(!s.stats().initialized&&!s.stats().dirty&&s.stats().origin_revision==0&&stream.buffered()==0);
 store.tune.revision=UINT32_MAX;s.open();floating(s,640,89);assert(command(s,{'b',0,1}).bytes[0]==0x84&&store.tune.ve.cells[0]==88);
 std::cout<<"Single-page typed tuning, stable origin/CAS, whole-tune burns, rejection, framing bounds, timeout and TX recovery tests passed\n";
}
