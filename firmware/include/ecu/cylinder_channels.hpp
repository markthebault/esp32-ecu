#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace ecu::engine::channels {
// Preserve the published four-cylinder channel IDs and the two auxiliary
// channels. Expanded engine channels require a separate explicit board map.
// These are logical IDs. They never authorize a pin or a driver connection.
inline constexpr unsigned maximum_cylinders=8,invalid=255,idle=8,boost=9;
enum class Kind : std::uint8_t {Injector,Coil,Idle,Boost,Invalid};
constexpr unsigned injector(unsigned cylinder){return cylinder<4?cylinder:cylinder<8?cylinder+6:invalid;}
constexpr unsigned coil(unsigned cylinder){return cylinder<4?cylinder+4:cylinder<8?cylinder+10:invalid;}
constexpr Kind kind(unsigned channel){
 return channel<4||(channel>=10&&channel<14)?Kind::Injector:
  (channel>=4&&channel<8)||(channel>=14&&channel<18)?Kind::Coil:
  channel==idle?Kind::Idle:channel==boost?Kind::Boost:Kind::Invalid;
}
constexpr unsigned cylinder(unsigned channel){
 return channel<4?channel:channel<8?channel-4:
  channel>=10&&channel<14?channel-6:channel>=14&&channel<18?channel-10:invalid;
}
template<std::size_t CylinderCapacity>inline constexpr unsigned extent=CylinderCapacity<=4?8:18;
template<std::size_t CylinderCapacity>bool order_valid(const std::array<unsigned,CylinderCapacity>&order,unsigned count){
 static_assert(CylinderCapacity==4||CylinderCapacity==8,"Only the existing and expanded fixed capacities are defined");
 if(!count||count>CylinderCapacity||order[0]!=1)return false;
 unsigned seen=0;
 for(unsigned i=0;i<CylinderCapacity;++i){
  const auto c=order[i];
  if(i>=count){if(c)return false;continue;}
  if(!c||c>count||(seen&(1U<<(c-1))))return false;
  seen|=1U<<(c-1);
 }
 return true;
}
template<std::size_t CylinderCapacity>std::array<double,CylinderCapacity> compression_phases(const std::array<unsigned,CylinderCapacity>&order,unsigned count){
 std::array<double,CylinderCapacity> result{};
 // The caller must reject an invalid profile. This bounded fallback does not
 // divide by zero or index through an invalid cylinder identifier.
 if(!order_valid(order,count))return result;
 for(unsigned i=0;i<count;++i)result[order[i]-1]=(720.0/count)*i;
 return result;
}
}
