#pragma once
#include "ecu/tuning_session.hpp"
namespace ecu::tuning {
struct StreamStats {std::uint64_t received=0,transmitted=0,frames=0,crc_errors=0,timeouts=0,framing_errors=0,tx_errors=0;};
class Stream {
 Session& session_;std::array<std::uint8_t,chunk_bytes+13> rx_{};std::size_t used_=0;std::uint64_t last_us_=0,last_rx_us_=0;bool seen_=false,tx_fault_=false;StreamStats stats_;
 template<class Send>void send(const std::uint8_t*p,std::size_t n,Send&fn){if(fn(p,n))stats_.transmitted+=n;else{++stats_.tx_errors;tx_fault_=true;}}
 template<class Send>void framed(const Reply&r,Send&fn){
  std::array<std::uint8_t,live_bytes+7> wire{};wire[0]=std::uint8_t(r.size>>8);wire[1]=std::uint8_t(r.size);std::copy_n(r.bytes.data(),r.size,wire.data()+2);
  const auto crc=Session::crc32(r.bytes.data(),r.size);for(unsigned i=0;i<4;++i)wire[2+r.size+i]=std::uint8_t(crc>>(24-8*i));send(wire.data(),r.size+6,fn);
 }
 template<class Send>void error(std::uint8_t code,Send&fn){Reply r;r.bytes[0]=code;r.size=1;framed(r,fn);}
public:
 static constexpr std::uint64_t character_timeout_us=25000;
 explicit Stream(Session&s):session_(s){}
 const StreamStats& stats()const{return stats_;}
 std::size_t buffered()const{return used_;}
 bool transmit_fault()const{return tx_fault_;}
 void disconnect(){used_=0;last_us_=last_rx_us_=0;seen_=tx_fault_=false;session_.abandon();}
 template<class Send>void expire(std::uint64_t now,Send&&fn){
  if(used_&&(now<last_us_||now-last_us_>=character_timeout_us)){used_=0;++stats_.timeouts;error(0x80,fn);}
 }
 template<class Send>void feed(const std::uint8_t*p,std::size_t n,std::uint64_t now,Send&&fn){
  expire(now,fn);
  for(std::size_t i=0;i<n;++i){
   ++stats_.received;const auto byte=p[i];
   const bool idle=!seen_||now<last_rx_us_||now-last_rx_us_>=character_timeout_us;
   // The documented serial reset prefix is outside envelopes. Preserve the
   // idle boundary for a following raw F in this same USB read slice.
   if(!used_&&idle&&byte==0xf0)continue;
   last_rx_us_=now;seen_=true;
   // After a failed transmission, do not execute further buffered commands.
   // A fresh idle rawF discovery is the explicit reconnect boundary.
   if(tx_fault_){if(!idle||byte!='F')continue;tx_fault_=false;used_=0;}
   if(!used_&&(byte=='F'||byte=='Q'||byte=='S')){
    if(byte=='F'&&idle)session_.open();
    const auto r=session_.command(&byte,1);send(r.bytes.data()+1,r.size-1,fn);continue;
   }
   if(used_==rx_.size()){used_=0;++stats_.framing_errors;error(0x84,fn);}
   rx_[used_++]=byte;last_us_=now;
   if(used_<2)continue;
   const auto size=(unsigned(rx_[0])<<8)|rx_[1];
   if(!size||size>chunk_bytes+7){used_=0;++stats_.framing_errors;error(0x84,fn);continue;}
   if(used_<size+6)continue;
   std::uint32_t expected=0;for(unsigned j=0;j<4;++j)expected=(expected<<8)|rx_[size+2+j];
   if(Session::crc32(rx_.data()+2,size)!=expected){++stats_.crc_errors;error(0x82,fn);}
   else{++stats_.frames;framed(session_.command(rx_.data()+2,size),fn);}
   used_=0;
  }
 }
};
} // namespace ecu::tuning
