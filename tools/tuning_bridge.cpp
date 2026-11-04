#include "ecu/tuning_stream.hpp"
#include "ecu/tuning_document.hpp"
#include "ecu/engine_json.hpp"
#include <cstdio>
#include <cstdlib>
#include <new>
using namespace ecu::tuning;
namespace {
using Load=int(*)(void*,char*,std::size_t);
using Current=int(*)(void*,std::uint32_t*);
using Commit=int(*)(void*,const char*,std::size_t,std::uint32_t*);
using Sample=int(*)(void*,std::uint8_t*,std::size_t);
Result status(int n){return n>=0&&n<=int(Result::Invalid)?Result(n):Result::Invalid;}
struct Host:Backend {
 void*opaque;Load load_fn;Current current_fn;Commit commit_fn;Sample sample_fn;
 std::array<char,ecu::engine::tune_maximum+1> document{};
 Host(void*o,Load l,Current r,Commit c,Sample s):opaque(o),load_fn(l),current_fn(r),commit_fn(c),sample_fn(s){}
 Result load(ecu::engine::Tune&t)override{
  document.fill(0);const auto r=status(load_fn(opaque,document.data(),document.size()));
  if(r!=Result::Ok&&r!=Result::StorageBlocked)return r;
  const auto*end=static_cast<const char*>(std::memchr(document.data(),0,document.size()));
  if(!end||!ecu::web::safe_json(document.data(),std::size_t(end-document.data()),ecu::engine::tune_maximum))return Result::Invalid;
  auto*j=cJSON_ParseWithOpts(document.data(),nullptr,true);if(!j)return Result::NoMemory;
  const bool ok=ecu::engine::parse_tune(j,t)&&ecu::engine::upgrade_tune_document(j);
  // Canonicalize the retained template once; commits update all known fields.
  char*encoded=ok?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);if(!encoded)return ok?Result::NoMemory:Result::Invalid;
  const auto n=std::strlen(encoded);if(n>=document.size()){cJSON_free(encoded);return Result::Invalid;}
  std::memcpy(document.data(),encoded,n+1);cJSON_free(encoded);return r;
 }
 Result current(std::uint32_t&r)override{return status(current_fn(opaque,&r));}
 Result commit(const ecu::engine::Tune&t,std::uint32_t&r)override{
  auto*j=cJSON_ParseWithOpts(document.data(),nullptr,true);if(!j)return Result::NoMemory;
  Document doc(j);const bool ok=update_document(doc,t);char*encoded=ok?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);
  if(!encoded)return Result::NoMemory;
  const auto n=std::strlen(encoded);const auto result=n<=ecu::engine::tune_maximum?status(commit_fn(opaque,encoded,n,&r)):Result::Invalid;cJSON_free(encoded);return result;
 }
 void sample(std::array<std::uint8_t,live_bytes>&b)override{
  b.fill(0);if(sample_fn(opaque,b.data(),b.size())!=0){
   b.fill(0);put_u32(b.data()+52,1);put_u32(b.data()+64,UINT32_MAX);
  }
 }
};
struct Context {
 Host backend;Session session;Stream stream;
 std::array<std::uint8_t,16384> outgoing{};std::size_t outgoing_size=0;
 std::array<char,2048> info{};
 Context(void*o,Load l,Current r,Commit c,Sample s):backend(o,l,r,c,s),session(backend),stream(session){session.open();}
 bool capture(const std::uint8_t*p,std::size_t n){if(n+2>outgoing.size()-outgoing_size)return false;outgoing[outgoing_size++]=std::uint8_t(n);outgoing[outgoing_size++]=std::uint8_t(n>>8);std::copy_n(p,n,outgoing.data()+outgoing_size);outgoing_size+=n;return true;}
};
}
extern "C" {
void* tuning_create(void*opaque,Load l,Current r,Commit c,Sample s){if(!l||!r||!c||!s)return nullptr;void*p=std::malloc(sizeof(Context));return p?new(p)Context(opaque,l,r,c,s):nullptr;}
void tuning_destroy(void*p){if(p){auto*c=static_cast<Context*>(p);c->~Context();std::free(c);}}
const std::uint8_t* tuning_command(void*p,const std::uint8_t*data,std::size_t n,std::size_t*size){if(!p||!size||(!data&&n)||n>chunk_bytes+7)return nullptr;auto&c=*static_cast<Context*>(p);const auto r=c.session.command(data,n);c.outgoing_size=r.size;std::copy_n(r.bytes.data(),r.size,c.outgoing.data());*size=r.size;return c.outgoing.data();}
const std::uint8_t* tuning_feed(void*p,const std::uint8_t*data,std::size_t n,std::uint64_t now,std::size_t*size){if(!p||!size||n>4096||(!data&&n))return nullptr;auto&c=*static_cast<Context*>(p);c.outgoing_size=0;auto send=[&](const std::uint8_t*b,std::size_t count){return c.capture(b,count);};c.stream.feed(data,n,now,send);*size=c.outgoing_size;return c.outgoing.data();}
const std::uint8_t* tuning_page(void*p){return p?static_cast<Context*>(p)->session.staged_page().data():nullptr;}
std::size_t tuning_buffered(void*p){return p?static_cast<Context*>(p)->stream.buffered():0;}
void tuning_disconnect(void*p){if(p)static_cast<Context*>(p)->stream.disconnect();}
const char* tuning_status(void*p){
 if(!p){return nullptr;}auto&c=*static_cast<Context*>(p);const auto&s=c.session.stats();const auto&w=c.stream.stats();
 const int n=std::snprintf(c.info.data(),c.info.size(),"{\"schema_version\":1,\"identity\":\"%s\",\"serial_protocol\":\"002\",\"page_bytes\":8192,\"live_bytes\":832,\"state\":\"%s\",\"initialized\":%s,\"dirty\":%s,\"origin_revision\":%u,\"base_revision\":%u,\"observed_active_revision\":%u,\"last_code\":%u,\"commands\":\"%llu\",\"reads\":\"%llu\",\"writes\":\"%llu\",\"burns\":\"%llu\",\"rejected\":\"%llu\",\"resets\":\"%llu\",\"received_bytes\":\"%llu\",\"fully_queued_reply_bytes\":\"%llu\",\"frames\":\"%llu\",\"crc_errors\":\"%llu\",\"timeouts\":\"%llu\",\"framing_errors\":\"%llu\",\"tx_errors\":\"%llu\",\"tx_fault\":%s,\"buffered_bytes\":%u}",signature,state_name(s.state),s.initialized?"true":"false",s.dirty?"true":"false",s.origin_revision,s.base_revision,s.active_revision,s.last_code,
  (unsigned long long)s.commands,(unsigned long long)s.reads,(unsigned long long)s.writes,(unsigned long long)s.burns,(unsigned long long)s.rejected,(unsigned long long)s.resets,(unsigned long long)w.received,(unsigned long long)w.transmitted,(unsigned long long)w.frames,(unsigned long long)w.crc_errors,(unsigned long long)w.timeouts,(unsigned long long)w.framing_errors,(unsigned long long)w.tx_errors,c.stream.transmit_fault()?"true":"false",unsigned(c.stream.buffered()));
 return n>0&&std::size_t(n)<c.info.size()?c.info.data():nullptr;
}
}
