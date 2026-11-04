// Native adapter for the same bounded recorder and packet bodies as the target.
// JSON input is an observation fixture only. It cannot apply ECU commands.
#include "ecu/engine_log_json.hpp"
#include "ecu/flex_runtime_json.hpp"
#include "ecu/engine_log_msl.hpp"
#include "ecu/engine_radio.hpp"
#include <openssl/hmac.h>
#include <cctype>
#include <string>

namespace {
struct Context {ecu::engine_log::Recorder recorder;ecu::radio::wire::PeerCapabilities capabilities;};
thread_local std::string response;
const char* encode(cJSON*j){
 if(!j)return nullptr;
 char*s=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!s)return nullptr;
 response=s;cJSON_free(s);return response.c_str();
}
bool u64(const cJSON*j,const char*key,std::uint64_t&out){
 auto*v=cJSON_GetObjectItemCaseSensitive(j,key);
 if(!cJSON_IsString(v)||!v->valuestring[0])return false;
 std::uint64_t n=0;unsigned digits=0;
 for(const char*p=v->valuestring;*p;++p){
  if(*p<'0'||*p>'9'||++digits>20||n>(UINT64_MAX-unsigned(*p-'0'))/10)return false;
  n=n*10+unsigned(*p-'0');
 }
 out=n;return true;
}
template<class T>bool integer(const cJSON*j,const char*key,T&out,std::uint32_t max=UINT32_MAX){
 std::uint32_t n=0;if(!ecu::web::integer(j,key,n)||n>max)return false;out=static_cast<T>(n);return true;
}
bool value(const cJSON*j,const char*key,float&out){
 auto*v=cJSON_GetObjectItemCaseSensitive(j,key);if(cJSON_IsNull(v)){out=NAN;return true;}
 if(!cJSON_IsNumber(v)||!std::isfinite(v->valuedouble)||std::abs(v->valuedouble)>FLT_MAX)return false;
 out=static_cast<float>(v->valuedouble);return true;
}
bool sample(const char*text,ecu::engine::RuntimeSample&out){
 if(!text||!ecu::web::safe_json(text,std::strlen(text)))return false;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);if(!j)return false;
 ecu::engine::RuntimeSample r;std::uint32_t source=0,schema=0;bool available=false;
 bool ok=integer(j,"schema_version",schema)&&schema==1&&ecu::web::boolean(j,"available",available)&&
  integer(j,"source_code",source,2)&&u64(j,"sequence",r.sequence)&&u64(j,"control_us",r.control_us)&&u64(j,"sampled_us",r.sampled_us)&&
  integer(j,"tune_revision",r.tune_revision)&&integer(j,"sensor_revision",r.sensor_revision)&&integer(j,"phase_epoch",r.phase_epoch)&&
  integer(j,"flags",r.flags,UINT16_MAX)&&integer(j,"input_valid_mask",r.input_valid,255)&&integer(j,"board_flags",r.board_flags,15)&&
  integer(j,"controller_faults",r.controller_faults)&&integer(j,"state_code",r.state,5)&&integer(j,"strategy_code",r.strategy,2)&&
  integer(j,"phase_reason_code",r.phase_reason,9)&&integer(j,"phase_losses",r.phase_losses)&&integer(j,"cam_rejected",r.cam_rejected)&&value(j,"cam_error_deg",r.cam_error_deg);
 r.source=static_cast<ecu::engine::DataSource>(source);
 ok=ok&&(available==(r.has(ecu::engine::Present)&&r.sequence!=0))&&(!available||source);
 const auto*cyl=cJSON_GetObjectItemCaseSensitive(j,"cylinders");
 if(cyl){
  bool enabled=false;ok=ok&&cJSON_IsObject(cyl)&&integer(cyl,"valid_mask",r.cylinder_valid,15)&&ecu::web::boolean(cyl,"enabled",enabled)&&
   integer(cyl,"capacity_mask",r.cylinder_capacity_mask,15)&&integer(cyl,"spark_clamp_mask",r.cylinder_spark_clamp_mask,15)&&integer(cyl,"retard_floor_mask",r.cylinder_retard_floor_mask,15);
  r.cylinder_enabled=enabled;const auto*channels=cJSON_GetObjectItemCaseSensitive(cyl,"proposals");ok=ok&&cJSON_IsArray(channels)&&cJSON_GetArraySize(channels)==4;
  for(unsigned i=0;ok&&i<4;++i){
   const auto*row=cJSON_GetArrayItem(channels,i);unsigned id=0;
   ok=integer(row,"cylinder",id,4)&&id==i+1&&value(row,"pulse_ms",r.cylinder_pulse_ms[i])&&value(row,"advance_deg",r.cylinder_advance_deg[i])&&value(row,"fuel_pct",r.cylinder_fuel_pct[i])&&value(row,"duty_pct",r.cylinder_duty_pct[i]);
   if(ok&&(r.cylinder_valid&(1U<<i)))ok=std::isfinite(r.cylinder_pulse_ms[i])&&std::isfinite(r.cylinder_advance_deg[i])&&std::isfinite(r.cylinder_fuel_pct[i])&&std::isfinite(r.cylinder_duty_pct[i]);
  }
 }
 const auto*idle=cJSON_GetObjectItemCaseSensitive(j,"idle");
 if(idle){bool known=false;ok=ok&&cJSON_IsObject(idle)&&ecu::web::boolean(idle,"available",known)&&(!known||available)&&integer(idle,"state_code",r.idle_state,10)&&integer(idle,"reason_code",r.idle_reason,12)&&integer(idle,"algorithm_code",r.idle_algorithm,2)&&integer(idle,"flags",r.idle_flags,255)&&u64(idle,"pid_updates",r.idle_pid_updates);
  for(unsigned i=0;ok&&i<6;++i)ok=value(idle,ecu::engine::idle_names[i],r.idle_proposals[i])&&(known?std::isfinite(r.idle_proposals[i]):cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(idle,ecu::engine::idle_names[i])));
  r.idle_available=known;
 }
 const auto*inputs=cJSON_GetObjectItemCaseSensitive(j,"inputs");const auto*proposals=cJSON_GetObjectItemCaseSensitive(j,"proposals");
 const auto*second=cJSON_GetObjectItemCaseSensitive(j,"secondary_tables");
 if(second)ok=ok&&ecu::secondary::parse_observations(second,r.secondary_fuel,r.secondary_spark,available);
 const auto*flex=cJSON_GetObjectItemCaseSensitive(j,"flex_fuel");if(flex)ok=ok&&ecu::flex::parse_record(flex,r.flex_fuel,available);
 const auto*model=cJSON_GetObjectItemCaseSensitive(j,"load_model");
 if(model)ok=ok&&ecu::load::parse_observation(model,r.load_model,available);
 const auto*ae=cJSON_GetObjectItemCaseSensitive(j,"transient_enrichment");
 if(ae){
  auto&d=r.transient_enrichment;bool known=false;std::uint8_t mode=0,apply=0,phase=0,reason=0;
  ok=ok&&cJSON_IsObject(ae)&&ecu::web::boolean(ae,"available",known)&&(!known||available)&&
   integer(ae,"mode_code",mode,3)&&integer(ae,"apply_code",apply,1)&&integer(ae,"phase_code",phase,2)&&integer(ae,"reason_code",reason,11)&&integer(ae,"flags",d.flags,31);
  d.available=known;d.mode=static_cast<ecu::transient::Mode>(mode);d.apply=static_cast<ecu::transient::Apply>(apply);d.phase=static_cast<ecu::transient::Phase>(phase);d.reason=static_cast<ecu::transient::Reason>(reason);
  for(unsigned i=0;ok&&i<ecu::transient::value_count;++i)ok=value(ae,ecu::transient::value_names[i],d.values[i])&&(known||cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(ae,ecu::transient::value_names[i])));
  if(ok&&known){
   ok=bool(d.flags&ecu::transient::Active)==d.active()&&std::isfinite(d.values[ecu::transient::CorrectionPct])&&d.values[ecu::transient::CorrectionPct]>=0&&d.values[ecu::transient::CorrectionPct]<=750&&
    std::isfinite(d.values[ecu::transient::RemainingMs])&&d.values[ecu::transient::RemainingMs]>=0&&d.values[ecu::transient::RemainingMs]<=2000&&
    std::isfinite(d.values[ecu::transient::AddedFuelMg])&&d.values[ecu::transient::AddedFuelMg]>=0;
   if(d.flags&ecu::transient::RateValid)ok=ok&&std::isfinite(d.values[d.mode==ecu::transient::Mode::MapRate?ecu::transient::MapDot:ecu::transient::TpsDot])&&std::isfinite(d.values[ecu::transient::WindowMs])&&d.values[ecu::transient::WindowMs]>0;
  }
 }
 ok=ok&&cJSON_IsObject(inputs)&&cJSON_IsObject(proposals);
 for(unsigned i=0;ok&&i<ecu::engine::input_count;++i)ok=value(inputs,ecu::engine::input_names[i],r.inputs[i])&&(!(r.input_valid&(1U<<i))||std::isfinite(r.inputs[i]));
 for(unsigned i=0;ok&&i<ecu::engine::proposal_count;++i)ok=value(proposals,ecu::engine::proposal_names[i],r.proposals[i]);
 const auto*worker=cJSON_GetObjectItemCaseSensitive(j,"worker_observation");
 ok=ok&&cJSON_IsObject(worker)&&u64(worker,"command_sequence",r.worker_sequence)&&u64(worker,"observed_us",r.worker_observed_us)&&
  integer(worker,"epoch",r.worker_epoch)&&integer(worker,"tune_revision",r.worker_tune_revision)&&integer(worker,"sensor_revision",r.worker_sensor_revision)&&
  integer(worker,"timing_fault_code",r.timing_fault,17)&&integer(worker,"last_timing_fault_code",r.last_timing_fault,17)&&
  integer(worker,"virtual_high_mask",r.virtual_high_mask,255)&&integer(worker,"physical_command_mask",r.physical_command_mask,255);
 const auto*raw=cJSON_GetObjectItemCaseSensitive(j,"raw_adc");ok=ok&&cJSON_IsArray(raw)&&cJSON_GetArraySize(raw)==8;
 for(unsigned i=0;ok&&i<8;++i){
  const auto*v=cJSON_GetArrayItem(raw,i);
  if(!(r.board_flags&1))ok=cJSON_IsNull(v);
  else {ok=cJSON_IsNumber(v)&&v->valuedouble>=0&&v->valuedouble<=4095&&std::floor(v->valuedouble)==v->valuedouble;if(ok)r.raw_adc[i]=static_cast<std::uint16_t>(v->valuedouble);}
 }
 cJSON_Delete(j);if(ok)out=r;return ok;
}
bool mac(const std::uint8_t*key,unsigned key_size,const std::uint8_t*body,unsigned size,std::uint8_t*out){
 unsigned result=0;return HMAC(EVP_sha256(),key,key_size,body,size,out,&result)&&result==32;
}
}
extern "C" void* data_create(){return new Context{};}
extern "C" void data_destroy(void*p){delete static_cast<Context*>(p);}
extern "C" int data_validate(const char*text){ecu::engine::RuntimeSample r;return sample(text,r);}
extern "C" int data_log_command(void*p,const char*body,unsigned length,std::uint64_t now,unsigned source){
 ecu::engine_log::Request request;if(!ecu::engine_log::parse_request(body,length,request))return 422;
 auto&recorder=static_cast<Context*>(p)->recorder;
 const bool ok=request.start?recorder.start(request.period_ms,request.duration_s,static_cast<ecu::engine::DataSource>(source),now):recorder.stop(request.log_id,now);
 return ok?200:409;
}
extern "C" int data_log_append(void*p,const char*text,std::uint64_t now){
 ecu::engine::RuntimeSample r;if(!sample(text,r))return -1;return static_cast<Context*>(p)->recorder.append(r,now);
}
extern "C" void data_log_expire(void*p,std::uint64_t now){static_cast<Context*>(p)->recorder.expire(now);}
extern "C" const char* data_log_header(void*p){return encode(ecu::engine_log::header_json(static_cast<Context*>(p)->recorder.header()));}
extern "C" const char* data_log_page(void*p,std::uint32_t id,std::uint32_t after){
 ecu::engine_log::Page page;static_cast<Context*>(p)->recorder.page(id,after,page);return encode(ecu::engine_log::page_json(page));
}
extern "C" const char* data_log_msl(void*p,std::uint32_t id,const char*boot){
 const auto&recorder=static_cast<Context*>(p)->recorder;const auto h=recorder.header();
 if(!recorder.current(id)||h.state==ecu::engine_log::State::Recording||!h.retained)return nullptr;
 if(!boot||std::strlen(boot)>32)return nullptr;
 for(const char*cursor=boot;*cursor;++cursor)if(!std::isxdigit(static_cast<unsigned char>(*cursor)))return nullptr;
 char buffer[ecu::engine_log::text_capacity];if(!ecu::engine_log::msl_header(h,buffer,sizeof(buffer),boot))return nullptr;
 response=buffer;ecu::engine_log::Row row;
 for(std::uint64_t seq=h.first_sequence();seq<=h.total;++seq){
  if(!recorder.read(id,static_cast<std::uint32_t>(seq),row)||!ecu::engine_log::msl_row(h,row,buffer,sizeof(buffer)))return nullptr;
  response+=buffer;
 }
 return response.c_str();
}
extern "C" void data_capability_reset(void*p){static_cast<Context*>(p)->capabilities.reset();}
extern "C" int data_capability_reply(void*p,const std::uint8_t*request,unsigned length,const std::uint8_t*key,std::uint32_t session,const std::uint8_t*nonce,std::uint64_t floor,std::uint64_t sent,std::uint8_t*out){
 std::uint8_t proof[32];
 if(length!=ecu::radio::wire::capability_size||!mac(key,16,request,44,proof)||!ecu::radio::wire::same(proof,request+44,32))return 0;
 auto&cap=static_cast<Context*>(p)->capabilities;if(!cap.request(request,length,session))return 0;
 cap.reply(out,session,nonce,floor,sent);return mac(key,16,out,76,out+76);
}
extern "C" int data_radio_frame(const char*text,const std::uint8_t*lmk,const std::uint8_t*nonce,std::uint32_t session,std::uint64_t seq,std::uint32_t sample_age,std::uint32_t control_age,std::uint32_t worker_age,std::uint64_t sent,std::uint32_t schema,std::uint8_t*out){
 ecu::engine::RuntimeSample r;if(!sample(text,r))return 0;
 const auto transcript=ecu::radio::wire::engine_key_transcript(nonce,session);std::uint8_t key[32];
 const auto body_size=ecu::radio::wire::engine_frame_body_size(schema);
 return mac(lmk,16,transcript.data(),transcript.size(),key)&&ecu::radio::wire::engine_body(out,r,session,seq,sample_age,control_age,worker_age,sent,schema)&&mac(key,32,out,body_size,out+body_size);
}
