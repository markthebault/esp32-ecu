#pragma once
#include "ecu/engine_radio.hpp"

namespace ecu::radio::wire {
constexpr unsigned engine_boost_size=144,engine_boost_body_size=112;
static_assert(engine_boost_size<=max_packet,"Schema6 keeps ESP-NOW v1 datagrams");
// The extension binds the entire BASE, including its source ages, revisions
// and sequence. No new time anchor is introduced when sending later parts.
inline bool engine_boost_body(std::uint8_t*p,const engine::RuntimeSample&r,std::uint32_t session,
                              std::uint64_t sequence,const std::uint8_t*base_mac){
 if(!session||!sequence||!r.sequence||!engine_schema_supports(6,r))return false;
 std::memset(p,0,engine_boost_size);header(p,EngineBoost,engine_boost_size);
 u32(p+8,session);u64(p+12,sequence);u16(p+20,6);std::memcpy(p+24,base_mac,32);
 const auto&b=r.boost_control;
 for(unsigned n=0;n<8;++n)f32(p+56+4*n,b.values[n]);
 u64(p+88,b.counters[0]);u64(p+96,b.counters[1]);u32(p+104,b.flags);
 p[108]=b.reason;p[109]=b.mode;p[110]=unsigned(b.available)|(unsigned(b.pressure_enabled)<<1)|(unsigned(b.inhibit_engine)<<2);
 return true; // Caller appends the full32-byte engine-key HMAC.
}
} // namespace ecu::radio::wire
