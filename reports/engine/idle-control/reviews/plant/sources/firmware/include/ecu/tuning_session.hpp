#pragma once
#include "ecu/tuning_layout.hpp"
#include <algorithm>
namespace ecu::tuning {
// All operations are task-side. No tuning/parser/CRC callback belongs in an ISR.
enum class Result {Ok,Conflict,StorageBlocked,Busy,NoMemory,Invalid};
enum class WriteState:std::uint32_t {Ready,Staged,Conflict,StorageBlocked,Busy,Invalid,Unavailable};
inline const char* state_name(WriteState s){switch(s){case WriteState::Staged:return "staged";case WriteState::Conflict:return "revision_conflict";case WriteState::StorageBlocked:return "storage_blocked";case WriteState::Busy:return "busy";case WriteState::Invalid:return "invalid_tune";case WriteState::Unavailable:return "unavailable";default:return "ready";}}
struct Backend {
 virtual ~Backend()=default;
 // A storage-blocked snapshot still supplies the retained active/default tune.
 virtual Result load(engine::Tune&)=0;
 virtual Result current(std::uint32_t&)=0;
 // Must compare candidate.revision and commit atomically. Return new revision
 // only after persistence/activation succeeds; failures retain active values.
 virtual Result commit(const engine::Tune&,std::uint32_t&)=0;
 virtual void sample(std::array<std::uint8_t,live_bytes>&)=0;
};
struct Stats {
 std::uint64_t commands=0,reads=0,writes=0,burns=0,rejected=0,resets=0;
 std::uint32_t origin_revision=0,base_revision=0,active_revision=0;
 WriteState state=WriteState::Unavailable;
 std::uint8_t last_code=0;
 bool initialized=false,dirty=false;
};
struct Reply {std::array<std::uint8_t,chunk_bytes+1> bytes{};std::size_t size=0;};
class Session {
 Backend& backend_;Page page_{};engine::Tune scratch_;Stats stats_;
 std::uint8_t result(Result r){
  switch(r){case Result::Conflict:stats_.state=WriteState::Conflict;return 0x84;
   case Result::StorageBlocked:stats_.state=WriteState::StorageBlocked;return 0x84;
   case Result::Busy:case Result::NoMemory:stats_.state=WriteState::Busy;return 0x85;
   case Result::Invalid:stats_.state=WriteState::Invalid;return 0x84;
   default:stats_.state=stats_.dirty?WriteState::Staged:WriteState::Ready;return 0;}
 }
 bool current(){
  std::uint32_t revision=0;const auto r=backend_.current(revision);stats_.active_revision=revision;
  if(r!=Result::Ok){stats_.last_code=result(r);return false;}
  if(revision!=stats_.base_revision){stats_.last_code=result(Result::Conflict);return false;}
  return true;
 }
 static unsigned u16(const std::uint8_t*p){return unsigned(p[0])|(unsigned(p[1])<<8);}
public:
 explicit Session(Backend&b):backend_(b){}
 void abandon(){stats_.initialized=stats_.dirty=false;stats_.origin_revision=stats_.base_revision=stats_.active_revision=0;stats_.state=WriteState::Unavailable;stats_.last_code=0;page_.fill(0);}
 Result open(){
  ++stats_.resets;abandon();
  const auto r=backend_.load(scratch_);
  if((r!=Result::Ok&&r!=Result::StorageBlocked)||engine::validate(scratch_)){result(r==Result::Ok?Result::Invalid:r);return r==Result::Ok?Result::Invalid:r;}
  stats_.origin_revision=stats_.base_revision=stats_.active_revision=scratch_.revision;
  encode_page(scratch_,stats_.origin_revision,page_);stats_.initialized=true;stats_.last_code=result(r);return r;
 }
 const Stats& stats()const{return stats_;}
 const Page& staged_page()const{return page_;}
 Reply command(const std::uint8_t*p,std::size_t n){
  Reply out;++stats_.commands;
  auto code=[&](std::uint8_t c){out.bytes[0]=c;out.size=1;stats_.last_code=c;if(c>=0x80)++stats_.rejected;return out;};
  auto text=[&](const char*s){out.bytes[0]=0;const auto count=std::strlen(s);std::memcpy(out.bytes.data()+1,s,count);out.size=count+1;stats_.last_code=0;return out;};
  if(n==1&&p[0]=='Q')return text(signature);
  if(n==1&&p[0]=='S')return text("ESP32ECU development; staged whole-tune burn; outputs inhibited");
  if(n==1&&p[0]=='F')return text(serial_protocol);
  if(n==1&&p[0]=='C'){out.bytes[0]=0;out.bytes[1]=0xff;out.size=2;stats_.last_code=0;return out;}
  if(n==1&&p[0]=='I'){out.bytes[0]=out.bytes[1]=0;out.size=2;stats_.last_code=0;return out;}
  if(n==2&&p[0]=='f'&&(p[1]==0||p[1]==255)){out.bytes={};out.bytes[1]=2;out.bytes[2]=out.bytes[4]=1;out.size=6;stats_.last_code=0;return out;}
  if(!n)return code(0x83);
  if(n==7&&p[0]=='r'){
   const auto offset=u16(p+3),count=u16(p+5);if(p[1]||p[2]!=0x30||!count||count>chunk_bytes||offset+count>live_bytes)return code(0x84);
   std::array<std::uint8_t,live_bytes> block{};backend_.sample(block);
   std::uint32_t revision=0;(void)backend_.current(revision);stats_.active_revision=revision;
   for(auto pair:{std::pair<unsigned,std::uint32_t>{184,revision},{188,stats_.origin_revision},{192,stats_.base_revision},{196,stats_.dirty},{200,std::uint32_t(stats_.state)},{204,stats_.last_code}})put_u32(block.data()+pair.first,pair.second);
   // Bytes208/212 carry backend input-valid bits and observation flags.
   out.bytes[0]=0;std::copy_n(block.data()+offset,count,out.bytes.data()+1);out.size=count+1;++stats_.reads;stats_.last_code=0;return out;
  }
  if(p[0]!='p'&&p[0]!='M'&&p[0]!='d'&&p[0]!='b')return code(0x83);
  if(!stats_.initialized){const auto r=open();if(r!=Result::Ok&&r!=Result::StorageBlocked)return code(result(r));}
  if(p[0]=='p'||p[0]=='M'){
   if(n<7){return code(0x84);}const auto offset=u16(p+3),count=u16(p+5);
   if(p[1]||p[2]!=1||!count||count>chunk_bytes||offset+count>page_bytes)return code(0x84);
   if(p[0]=='p'){
    if(n!=7){return code(0x84);}out.bytes[0]=0;std::copy_n(page_.data()+offset,count,out.bytes.data()+1);out.size=count+1;++stats_.reads;stats_.last_code=0;return out;
   }
   if(n!=7+count)return code(0x84);
   if(!current())return code(stats_.last_code);
   // Read-only/reserved violations reject the entire chunk before any writes.
   for(unsigned i=0;i<count;++i)if((revision_offset(offset+i)||reserved_offset(offset+i))&&p[7+i]!=page_[offset+i])return code(0x84);
   std::copy_n(p+7,count,page_.data()+offset);stats_.dirty=true;stats_.state=WriteState::Staged;++stats_.writes;return code(0);
  }
  if(n!=3||p[1]||p[2]!=1)return code(0x84);
  if(p[0]=='d'){
   const auto crc=crc32(page_.data(),page_.size());out.bytes[0]=0;for(unsigned i=0;i<4;++i)out.bytes[1+i]=std::uint8_t(crc>>(24-8*i));out.size=5;++stats_.reads;stats_.last_code=0;return out;
  }
  if(!current())return code(stats_.last_code);
  if(!stats_.dirty){stats_.state=WriteState::Ready;return code(4);} // A retried acknowledged burn is idempotent.
  if(stats_.base_revision==UINT32_MAX)return code(result(Result::Conflict));
  if(!decode_page(page_,stats_.origin_revision,scratch_))return code(result(Result::Invalid));
  scratch_.revision=stats_.base_revision;std::uint32_t saved=0;
  const auto r=backend_.commit(scratch_,saved);if(r!=Result::Ok)return code(result(r));
  if(!saved||saved<=stats_.base_revision){stats_.state=WriteState::Unavailable;return code(0x84);}
  stats_.base_revision=stats_.active_revision=saved;stats_.dirty=false;stats_.state=WriteState::Ready;++stats_.burns;
  // Preserve all mapped bytes, including the connection's origin revision.
  // Active/backend revision is separately observable in the runtime block.
  return code(4);
 }
 static std::uint32_t crc32(const std::uint8_t*p,std::size_t n){std::uint32_t crc=~0U;for(std::size_t i=0;i<n;++i){crc^=p[i];for(unsigned j=0;j<8;++j)crc=(crc>>1)^(0xedb88320U&std::uint32_t(-std::int32_t(crc&1)));}return ~crc;}
};
} // namespace ecu::tuning
