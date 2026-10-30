#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include <cmath>
namespace ecu::radio::wire {
constexpr unsigned max_peers=4, channel=6, header_size=8, max_packet=250;
enum Type : std::uint8_t { Beacon=1, Request=2, Accepted=3, Telemetry=4, Metadata=5, Ack=6 };
inline void u16(std::uint8_t*p,std::uint16_t v){p[0]=v;p[1]=v>>8;}
inline void u32(std::uint8_t*p,std::uint32_t v){for(unsigned i=0;i<4;++i)p[i]=v>>(i*8);}
inline std::uint32_t read32(const std::uint8_t*p){return p[0]|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
inline void f32(std::uint8_t*p,double v){float f=std::isfinite(v)?static_cast<float>(v):NAN;std::uint32_t n;static_assert(sizeof(f)==4);std::memcpy(&n,&f,4);u32(p,n);}
inline void header(std::uint8_t*p,Type type,unsigned size){std::memcpy(p,"ECN1",4);p[4]=1;p[5]=type;u16(p+6,size);}
inline bool valid(const std::uint8_t*p,unsigned n,Type type,unsigned size){return n==size&&n>=8&&!std::memcmp(p,"ECN1",4)&&p[4]==1&&p[5]==type&&(p[6]|(unsigned(p[7])<<8))==n;}
inline bool unicast(const std::uint8_t*p){unsigned n=0;for(unsigned i=0;i<6;++i)n|=p[i];return n&&!(p[0]&1);}
inline bool same(const std::uint8_t*a,const std::uint8_t*b,unsigned n){unsigned diff=0;for(unsigned i=0;i<n;++i)diff|=a[i]^b[i];return diff==0;}
// Authenticated transcript: label, window, ECU STA MAC, screen MAC, nonce, name.
constexpr unsigned transcript_size=15+16+6+6+16+24;
inline std::array<std::uint8_t,transcript_size> transcript(const std::uint8_t*window,const std::uint8_t*ecu,const std::uint8_t*screen,const std::uint8_t*nonce,const std::uint8_t*name){
 std::array<std::uint8_t,transcript_size> b{};unsigned o=0;
 auto add=[&](const void*p,unsigned n){std::memcpy(b.data()+o,p,n);o+=n;};
 add("ECU-NOW-PAIR-v1",15);add(window,16);add(ecu,6);add(screen,6);add(nonce,16);add(name,24);return b;
}
// Poll at <=10 ms. Ignore a button held at startup until released.
class Button {
 bool armed=false,last=false,stable=false,fired=false;std::uint64_t changed=0,pressed=0;
public:
 enum Action { None, Open, Confirm };
 Action poll(bool down,std::uint64_t ms){
  if(down!=last){last=down;changed=ms;}
  if(ms-changed<30)return None;
  if(!armed){if(!down)armed=true;return None;}
  if(down!=stable){stable=down;if(down){pressed=ms;fired=false;}else if(!fired&&ms-pressed>=50&&ms-pressed<1000)return Confirm;}
  if(stable&&!fired&&ms-pressed>=3000){fired=true;return Open;}
  return None;
 }
};
}
