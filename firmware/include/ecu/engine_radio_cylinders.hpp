#pragma once
#include "ecu/engine_radio_boost.hpp"

namespace ecu::radio::wire {
constexpr unsigned engine_cylinder_size=236,engine_cylinder_body_size=204;
static_assert(engine_cylinder_size<=max_packet,"Schema7 keeps ESP-NOW v1 datagrams");
// All eight rows belong to the same source snapshot as BASE/FLEX/BOOST. The
// full BASE MAC binds revisions, source time, scalar proposals and sequences.
inline bool engine_cylinder_body(std::uint8_t*p,const engine::RuntimeSample&r,std::uint32_t session,
                                 std::uint64_t sequence,const std::uint8_t*base_mac){
 if(!session||!sequence||!r.sequence||!engine_schema_supports(7,r))return false;
 std::memset(p,0,engine_cylinder_size);header(p,EngineCylinders,engine_cylinder_size);
 u32(p+8,session);u64(p+12,sequence);u16(p+20,7);std::memcpy(p+24,base_mac,32);
 p[56]=r.cylinder_count;p[57]=r.worker_cylinder_count;
 p[58]=engine::channels::board_injector_commands;p[59]=engine::channels::board_coil_commands;
 p[60]=r.cylinder_valid;p[61]=r.cylinder_enabled;p[62]=r.cylinder_capacity_mask;
 p[63]=r.cylinder_spark_clamp_mask;p[64]=r.cylinder_retard_floor_mask;
 u32(p+68,r.virtual_high_mask);u32(p+72,r.physical_command_mask);
 for(unsigned i=0;i<8;++i){
  const bool known=r.has(engine::Present)&&(r.cylinder_valid&(1U<<i));
  f32(p+76+16*i,known?r.cylinder_pulse_ms[i]:NAN);
  f32(p+80+16*i,known?r.cylinder_advance_deg[i]:NAN);
  f32(p+84+16*i,known?r.cylinder_fuel_pct[i]:NAN);
  f32(p+88+16*i,known?r.cylinder_duty_pct[i]:NAN);
 }
 return true;
}
} // namespace ecu::radio::wire
