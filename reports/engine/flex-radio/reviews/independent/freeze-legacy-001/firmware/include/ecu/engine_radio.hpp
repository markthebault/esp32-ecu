#pragma once
#include "ecu/espnow_protocol.hpp"
#include "ecu/engine_data.hpp"
#include <limits>

namespace ecu::radio::wire {
constexpr unsigned capability_size=76,capability_reply_size=108,engine_size=250,engine_body_size=218,engine_ack_size=56;
constexpr std::uint32_t engine_feature=1,engine_schema=5;
inline bool engine_schema_valid(std::uint32_t schema){return schema>=1&&schema<=5;}
inline unsigned engine_frame_size(std::uint32_t schema){return engine_schema_valid(schema)?(schema<3?232:250):0;}
inline unsigned engine_frame_body_size(std::uint32_t schema){return engine_schema_valid(schema)?engine_frame_size(schema)-32:0;}
inline bool legacy_load_model(const engine::RuntimeSample&r){
 const auto&o=r.load_model;
 return !o.available||(o.fuel==load::Source::Map&&o.spark==load::Source::Map&&o.lambda==load::Source::Map&&o.trim==load::Source::Map&&o.pressure==load::Pressure::MapReference&&o.afr==load::Afr::Target&&o.aux_role==load::AuxRole::PostcatMonitor);
}
inline bool engine_schema_supports(std::uint32_t schema,const engine::RuntimeSample&r){
 // Schemas1..4 have no flex quality/factor block. Suppress engine telemetry
 // when it affects control rather than publish an incomplete legacy frame.
 if(schema<5&&(r.flex_fuel.has(flex::Required)||r.flex_fuel.has(flex::CorrectionsEnabled)))return false;
 if(schema>=5&&(!flex::valid_record(r.flex_fuel,r.has(engine::Present))||
    (r.source==engine::DataSource::Target&&r.flex_fuel.source>1)||
    (r.flex_fuel.has(flex::ConfigurationMatch)&&r.flex_fuel.revision!=r.tune_revision)))return false;
 const bool secondary_legacy=r.secondary_fuel.mode==secondary::Mode::Off&&r.secondary_spark.mode==secondary::Mode::Off;
 if(schema>=4)for(const secondary::Observation*o:{&r.secondary_fuel,&r.secondary_spark})if(o->available&&(static_cast<unsigned>(o->mode)>4||static_cast<unsigned>(o->source)>2||(o->evaluated&&!o->available)||(o->active&&o->mode==secondary::Mode::Off)))return false;
 return engine_schema_valid(schema)&&(schema>=4||secondary_legacy)&&r.strategy<=(schema==1?1:2)&&r.timing_fault<=(schema==1?16:17)&&r.last_timing_fault<=(schema==1?16:17)&&(schema>=3||legacy_load_model(r));
}
static_assert(engine_size<=max_packet&&capability_reply_size<=max_packet);
static_assert(engine::input_count==8&&engine::proposal_count==14,"Schema1 base frame must not grow into its HMAC");
// Only call after verifying the request's full HMAC with the saved peer LMK.
class PeerCapabilities {
 std::array<std::uint8_t,44> accepted_{};
 std::array<std::uint8_t,16> reply_nonce_{};
 std::uint32_t counter_=0,features_=0,schema_=0;
 bool reply_pending_=false;
public:
 void reset(){*this=PeerCapabilities{};}
 bool engine()const{return (features_&engine_feature)!=0;}
 std::uint32_t counter()const{return counter_;}
 std::uint32_t features()const{return features_;}
 std::uint32_t schema()const{return schema_;}
 bool pending()const{return reply_pending_;}
 void sent(){reply_pending_=false;}
 bool request(const std::uint8_t*p,unsigned length,std::uint32_t session){
  if(!session||!valid(p,length,Capabilities,capability_size)||read32(p+40)!=0)return false;
  const auto boot=read32(p+8),counter=read32(p+12),features=read32(p+32),schema=read32(p+36);
  if(!counter){
   if((boot&&boot!=session)||features||schema)return false;
  }else{
   if(boot!=session||(features&~engine_feature)||(features?!engine_schema_valid(schema):schema!=0)||counter<counter_)return false;
   if(counter==counter_){if(!same(p,accepted_.data(),accepted_.size()))return false;}
   else {counter_=counter;features_=features;schema_=schema;std::memcpy(accepted_.data(),p,accepted_.size());}
  }
  std::memcpy(reply_nonce_.data(),p+16,16);reply_pending_=true;return true;
 }
 // HMAC over the first76bytes is appended by the transport using the LMK.
 void reply(std::uint8_t*p,std::uint32_t session,const std::uint8_t*boot_nonce,std::uint64_t engine_sequence,std::uint64_t sent_esp_us)const{
  std::memset(p,0,capability_reply_size);header(p,CapabilitiesReply,capability_reply_size);
  u32(p+8,session);u32(p+12,counter_);std::memcpy(p+16,reply_nonce_.data(),16);
  u32(p+32,features_);u32(p+36,features_?schema_:0);u32(p+40,0);
  std::memcpy(p+44,boot_nonce,16);u64(p+60,engine_sequence);u64(p+68,sent_esp_us);
 }
};
// Exact byte transcript for deriving a32-byte per-boot engine data/ACK MAC key.
inline std::array<std::uint8_t,37> engine_key_transcript(const std::uint8_t*boot_nonce,std::uint32_t session){
 std::array<std::uint8_t,37> b{};std::memcpy(b.data(),"ECU-NOW-ENGINE-v1",17);std::memcpy(b.data()+17,boot_nonce,16);u32(b.data()+33,session);return b;
}
template<class Sequence,unsigned N=8>class SentWindow {
 struct Sent {Sequence sequence=0;std::uint64_t stamp_us=0;};
 std::array<Sent,N> sent_{};unsigned next_=0,count_=0;Sequence acknowledged_=0;bool seen_=false;
public:
 void reset(){*this=SentWindow{};}
 void submitted(Sequence seq,std::uint64_t now_us=0){sent_[next_]={seq,now_us};next_=(next_+1)%N;if(count_<N)++count_;}
 bool acknowledge(Sequence seq,std::uint64_t now_us=0){
  bool found=false;for(unsigned i=0;i<count_;++i)found|=sent_[i].sequence==seq&&now_us>=sent_[i].stamp_us&&now_us-sent_[i].stamp_us<=1000000;
  if(!found)return false;
  // Serial arithmetic keeps the legacy32-bit sequence usable through rollover.
  if(seen_){const auto delta=static_cast<Sequence>(seq-acknowledged_);if(!delta||delta>std::numeric_limits<Sequence>::max()/2)return false;}
  acknowledged_=seq;seen_=true;return true;
 }
};
// Different clocks are bridged by durations. Read ESP time BEFORE GP time at
// publication, then add only subsequent ESP elapsed time at transmission.
inline std::uint32_t transmitted_age(std::uint64_t gp_age_us,std::uint64_t published_esp_us,std::uint64_t now_esp_us){
 if(gp_age_us==UINT64_MAX||now_esp_us<published_esp_us)return UINT32_MAX;
 const auto elapsed=now_esp_us-published_esp_us;if(gp_age_us>UINT64_MAX-elapsed)return UINT32_MAX;
 return engine::data_age_ms(gp_age_us+elapsed);
}
inline bool engine_body(std::uint8_t*p,const engine::RuntimeSample&r,std::uint32_t session,std::uint64_t packet_sequence,std::uint32_t sample_age_ms,std::uint32_t control_age_ms,std::uint32_t worker_age_ms,std::uint64_t sent_esp_us,std::uint32_t schema=engine_schema){
 if(!session||!r.has(engine::Present)||!r.sequence||(r.source!=engine::DataSource::Target&&r.source!=engine::DataSource::Synthetic)||!packet_sequence||r.state>5||!engine_schema_supports(schema,r)||r.phase_reason>9||(r.board_flags&~15))return false;
 const auto size=engine_frame_size(schema);std::memset(p,0,size);header(p,EngineTelemetry,size);u32(p+8,session);u64(p+12,packet_sequence);u16(p+20,schema);
 auto flags=static_cast<std::uint16_t>(r.flags&~engine::DisplayFresh);
 if(sample_age_ms<=1000&&control_age_ms<=1000)flags|=engine::DisplayFresh;
 u16(p+22,flags);u32(p+24,sample_age_ms);u32(p+28,control_age_ms);u32(p+32,r.tune_revision);u32(p+36,r.sensor_revision);
 u64(p+40,r.sequence);u64(p+48,r.worker_sequence);u32(p+56,r.phase_epoch);u32(p+60,r.worker_epoch);u32(p+64,r.controller_faults);
 u32(p+68,r.phase_losses);u32(p+72,r.cam_rejected);f32(p+76,r.cam_error_deg);
 p[80]=r.state;p[81]=r.strategy;p[82]=static_cast<std::uint8_t>(r.source);p[83]=r.phase_reason;p[84]=r.input_valid;
 p[85]=r.timing_fault;p[86]=r.last_timing_fault;p[87]=r.virtual_high_mask;p[88]=r.physical_command_mask;p[89]=r.board_flags;
 if(schema>=4){
  const secondary::Observation empty;const auto&fuel=r.secondary_fuel.available?r.secondary_fuel:empty;const auto&spark=r.secondary_spark.available?r.secondary_spark:empty;
  p[90]=static_cast<unsigned>(fuel.mode)|(static_cast<unsigned>(spark.mode)<<3)|(unsigned(fuel.active)<<6)|(unsigned(spark.active)<<7);
  p[91]=static_cast<unsigned>(fuel.source)|(static_cast<unsigned>(spark.source)<<2)|(unsigned(fuel.available)<<4)|(unsigned(spark.available)<<5)|(unsigned(fuel.evaluated)<<6)|(unsigned(spark.evaluated)<<7);
 }
 u64(p+92,sent_esp_us);u32(p+100,r.worker_tune_revision);u32(p+104,r.worker_sensor_revision);u32(p+108,worker_age_ms);
 for(unsigned i=0;i<engine::input_count;++i)f32(p+112+i*4,(r.input_valid&(1U<<i))?r.inputs[i]:NAN);
 for(unsigned i=0;i<engine::proposal_count;++i)f32(p+144+i*4,r.proposals[i]);
 if(schema>=3){
  const auto&o=r.load_model;const bool known=o.available&&r.has(engine::Present);
  p[200]=static_cast<unsigned>(o.fuel)|(static_cast<unsigned>(o.spark)<<2)|(static_cast<unsigned>(o.lambda)<<4)|(static_cast<unsigned>(o.trim)<<6);
  p[201]=static_cast<unsigned>(o.pressure)|(static_cast<unsigned>(o.baro_source)<<2)|(unsigned(known)<<3)|(unsigned(known&&bool(o.flags&load::ArithmeticValid))<<4)|(static_cast<unsigned>(o.afr)<<5)|(unsigned(known&&bool(o.flags&load::PressureGuardAvailable))<<7);
  for(unsigned i=0;i<4;++i){constexpr unsigned values[]={load::FuelLoad,load::AfrFactor,load::BaroKpa,load::EmapKpa};f32(p+202+i*4,known?o.values[values[i]]:NAN);}
 }
 return true; // Caller appends32-byte HMAC at the selected schema's body end.
}
}
