#pragma once
#include "ecu/engine_radio_cylinders.hpp"

namespace ecu::radio::wire {
constexpr unsigned engine_flex_size=232,engine_flex_body_size=200;
constexpr std::uint64_t engine_pair_lifetime_us=250000;
static_assert(engine_flex_size<=max_packet,"Schema5 keeps ESP-NOW v1 datagrams");
inline std::uint64_t flex_sample_age(const engine::RuntimeSample&r,std::uint64_t gp_now){
 const auto&f=r.flex_fuel;
 return r.has(engine::Present)&&flex::sample_timestamp_known(f)&&gp_now>=f.times[0]?gp_now-f.times[0]:UINT64_MAX;
}
inline std::uint32_t flex_stale_limit(const flex::Record&r){
 if(!r.has(flex::Available)||!flex::valid_record(r))return 0;
 return static_cast<std::uint32_t>(std::llround(double(r.calibration[4])*1000.));
}
// The full base MAC binds every base byte (including source time, revisions
// and proposal sequence). Both bodies are prepared once from one snapshot.
// This function serializes a body; transport appends its full32-byte MAC.
inline bool engine_flex_body(std::uint8_t*p,const engine::RuntimeSample&r,std::uint32_t session,
                            std::uint64_t sequence,const std::uint8_t*base_mac,std::uint32_t raw_age_ms,std::uint32_t schema=5){
 if((schema<5||schema>7)||!session||!sequence||!r.sequence||!engine_schema_supports(schema,r))return false;
 if(raw_age_ms!=UINT32_MAX&&!flex::sample_timestamp_known(r.flex_fuel))return false;
 std::memset(p,0,engine_flex_size);header(p,EngineFlex,engine_flex_size);u32(p+8,session);u64(p+12,sequence);u16(p+20,schema);
 std::memcpy(p+24,base_mac,32);const auto&f=r.flex_fuel;
 for(unsigned n=0;n<7;++n)u64(p+56+8*n,f.times[n]);
 for(unsigned n=0;n<10;++n)f32(p+112+4*n,f.values[n]);
 for(unsigned n=0;n<6;++n)f32(p+152+4*n,f.calibration[n]);
 u32(p+176,f.flags);u32(p+180,f.revision);
 p[184]=f.source;p[185]=f.reason;p[186]=f.capture_reason;p[187]=f.last_fault;p[188]=f.correction_reason;p[189]=f.window_cycles;p[190]=f.calibration_cycles;
 u32(p+192,raw_age_ms);u32(p+196,flex_stale_limit(f));return true;
}

// One bounded pending observation per peer: two parts for schema5, three for
// schema6, four for schema7. A part is not an observation or ACK-window entry. The final
// successful submission returns its original base
// time so the recent-send window cannot be extended by fragment delay.
class EnginePair {
 std::array<std::uint8_t,engine_size> base_{};
 std::array<std::uint8_t,engine_flex_size> flex_{};
 std::array<std::uint8_t,engine_boost_size> boost_{};
 std::array<std::uint8_t,engine_cylinder_size> cylinders_{};
 std::uint64_t sequence_=0,prepared_us_=0;
 bool pending_=false;
 std::uint8_t part_=0,schema_=5;
public:
 bool pending()const{return pending_;}
 bool base_submitted()const{return pending_&&part_>0;}
 unsigned part_index()const{return part_;}
 unsigned parts()const{return schema_==7?4:schema_==6?3:2;}
 std::uint64_t sequence()const{return sequence_;}
 std::uint64_t prepared_us()const{return prepared_us_;}
 void cancel(){pending_=false;part_=0;}
 bool expired(std::uint64_t now)const{return pending_&&(now<prepared_us_||now-prepared_us_>engine_pair_lifetime_us);}
 template<class Mac>bool prepare(const engine::RuntimeSample&r,std::uint32_t session,std::uint64_t sequence,
    std::uint32_t sample_age,std::uint32_t control_age,std::uint32_t worker_age,std::uint32_t raw_age,
    std::uint64_t now,Mac mac,std::uint32_t schema=5){
  if(pending_||schema<5||schema>7)return false;
  if(!engine_body(base_.data(),r,session,sequence,sample_age,control_age,worker_age,now,schema)||
     !mac(base_.data(),engine_body_size,base_.data()+engine_body_size)||
     !engine_flex_body(flex_.data(),r,session,sequence,base_.data()+engine_body_size,raw_age,schema)||
     !mac(flex_.data(),engine_flex_body_size,flex_.data()+engine_flex_body_size))return false;
  if(schema>=6&&(!engine_boost_body(boost_.data(),r,session,sequence,base_.data()+engine_body_size,schema)||
     !mac(boost_.data(),engine_boost_body_size,boost_.data()+engine_boost_body_size)))return false;
  if(schema==7&&(!engine_cylinder_body(cylinders_.data(),r,session,sequence,base_.data()+engine_body_size)||
     !mac(cylinders_.data(),engine_cylinder_body_size,cylinders_.data()+engine_cylinder_body_size)))return false;
  sequence_=sequence;prepared_us_=now;pending_=true;part_=0;schema_=schema;return true;
 }
 const std::uint8_t*data()const{return !pending_?nullptr:part_==0?base_.data():part_==1?flex_.data():part_==2?boost_.data():cylinders_.data();}
 unsigned size()const{return !pending_?0:part_==0?engine_size:part_==1?engine_flex_size:part_==2?engine_boost_size:engine_cylinder_size;}
 // Call only for an SDK-accepted submission of the currently exposed bytes.
 bool submitted(){if(!pending_)return false;if(++part_<parts())return false;pending_=false;return true;}
};
} // namespace ecu::radio::wire
