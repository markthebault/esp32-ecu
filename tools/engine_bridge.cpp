// Native SIL adapter: compiles the same engine and decoder headers as ESP-IDF.
#include "ecu/engine_json.hpp"
#include "ecu/engine_data_json.hpp"
#include "ecu/engine_phase.hpp"
#include "ecu/engine_scheduler.hpp"
#include <string>
struct EngineContext {ecu::engine::RuntimeSample data;std::uint64_t data_sequence=0;ecu::engine::Tune tune;ecu::engine::Controller controller;ecu::engine::PhaseDecoder decoder{{60,2,8000}};ecu::engine::Output last;ecu::engine::AngleScheduler scheduler;unsigned slots=60,missing=2,max_rpm=8000;std::uint64_t gap=0,control_us=0,sampled_us=0,last_trigger_us=UINT64_MAX;bool have_control=false;std::uint8_t virtual_high_mask=0;std::uint64_t stopped_since=UINT64_MAX;unsigned timing_recoveries=0,timing_stops=0;ecu::engine::AngleScheduler::StopReason last_timing_reason=ecu::engine::AngleScheduler::StopReason::None;};
thread_local std::string engine_reply;
static const char* encode(cJSON*j){char*s=cJSON_PrintUnformatted(j);cJSON_Delete(j);engine_reply=s?s:"{}";cJSON_free(s);return engine_reply.c_str();}
#include "trigger_capture_bridge.hpp"
extern "C" void* engine_create(){return new EngineContext{};}
extern "C" void engine_destroy(void*p){delete static_cast<EngineContext*>(p);}
extern "C" const char* engine_canonicalize(const char*text){ecu::engine::Tune tune;static thread_local std::string canonical;if(!ecu::engine::canonical_tune(text,tune,canonical))return nullptr;return canonical.c_str();}
extern "C" int engine_validate(const char*text){if(!ecu::web::safe_json(text,std::strlen(text)))return 0;auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::engine::Tune t;bool ok=j&&ecu::engine::parse_tune(j,t);cJSON_Delete(j);return ok;}
extern "C" int engine_configure(void*p,const char*text){
 if(!text||!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::engine::Tune candidate;
 const bool ok=j&&ecu::engine::parse_tune(j,candidate);cJSON_Delete(j);if(!ok)return 0;
 auto*c=static_cast<EngineContext*>(p);c->tune=candidate;c->decoder=ecu::engine::PhaseDecoder({c->slots,c->missing,c->max_rpm},ecu::engine::angle_config(c->tune));
 c->controller.reset();c->scheduler.reset();c->last={};c->data={};c->data_sequence=0;c->have_control=false;c->virtual_high_mask=0;c->stopped_since=UINT64_MAX;c->timing_recoveries=0;c->timing_stops=0;c->last_timing_reason=ecu::engine::AngleScheduler::StopReason::None;return 1;
}
extern "C" int engine_wheel(void*p,unsigned slots,unsigned missing,unsigned max_rpm){
 auto*c=static_cast<EngineContext*>(p);ecu::engine::PhaseDecoder d({slots,missing,max_rpm},ecu::engine::angle_config(c->tune));if(!d.valid())return 0;c->decoder=d;c->gap=0;c->slots=slots;c->missing=missing;c->max_rpm=max_rpm;c->scheduler.reset();return 1;
}
static bool phase_fault(EngineContext*c){
 if(!c->decoder.faulted())return false;
 if(!c->scheduler.failed()){c->scheduler.fail_phase();++c->timing_stops;c->last_timing_reason=c->scheduler.stop_reason();}
 return true;
}
extern "C" int engine_cam(void*p,std::uint64_t time){auto*c=static_cast<EngineContext*>(p);c->last_trigger_us=std::max(c->last_trigger_us==UINT64_MAX?0:c->last_trigger_us,time);c->decoder.cam(time);return phase_fault(c)?3:0;}
extern "C" int engine_trigger(void*p,std::uint64_t time){
 auto*c=static_cast<EngineContext*>(p);const bool before=c->decoder.synced();c->stopped_since=UINT64_MAX;c->last_trigger_us=time;c->decoder.edge(time);
 if(phase_fault(c))return 3;
 if(c->decoder.synced()){
  if(!c->have_control||time<c->control_us||time-c->control_us>20000||time<c->sampled_us||time-c->sampled_us>20000){c->scheduler.cut();c->last.faults|=ecu::engine::Stale;c->last.state=ecu::engine::State::Faulted;c->last.fuel_cut=c->last.spark_cut=true;return 2;}
  auto output=c->last;output.rpm=c->decoder.rpm();
  const bool failed_before=c->scheduler.failed();
  if(!c->scheduler.tooth(c->tune,output,time,c->decoder.required()?c->decoder.phase_tooth():c->decoder.tooth(),c->slots,c->control_us,c->sampled_us)){
   if(!failed_before&&c->scheduler.failed()){++c->timing_stops;c->last_timing_reason=c->scheduler.stop_reason();}
   return 3;
  }
  if(c->decoder.tooth()==0){c->gap=time;return 1;}
 }else c->scheduler.cut();
 return before&&!c->decoder.synced()?2:0;
}
extern "C" void engine_cut(void*p){auto*c=static_cast<EngineContext*>(p);c->scheduler.cut();c->virtual_high_mask=0;}
extern "C" const char* engine_timing_reason(void*p){return ecu::engine::AngleScheduler::reason_name(static_cast<EngineContext*>(p)->last_timing_reason);}
extern "C" std::uint64_t engine_next_time(void*p){auto*c=static_cast<EngineContext*>(p);return c->decoder.faulted()?c->scheduler.next_time():std::min(c->scheduler.next_time(),c->decoder.deadline());}
extern "C" unsigned engine_pop(void*p){auto*c=static_cast<EngineContext*>(p);ecu::engine::Edge e;if(c->decoder.deadline()<=c->scheduler.next_time()&&c->decoder.deadline()!=UINT64_MAX){c->decoder.tick(c->decoder.deadline());phase_fault(c);return 0x30000;}if(!c->scheduler.pop(e))return 0;if(c->scheduler.event_forced_cut()){c->last.faults|=ecu::engine::Stale;c->last.state=ecu::engine::State::Faulted;c->last.fuel_cut=c->last.spark_cut=true;return 0x30000;}if(e.high)c->virtual_high_mask|=1U<<e.channel;else c->virtual_high_mask&=~(1U<<e.channel);return 0x10000|e.channel|(e.high?0x100:0);}
extern "C" std::uint64_t engine_event_dwell(void*p){return static_cast<EngineContext*>(p)->scheduler.event_requested_dwell_us();}
extern "C" double engine_event_advance(void*p){return static_cast<EngineContext*>(p)->scheduler.event_advance();}
extern "C" const char* engine_step(void*p,const char*text,std::uint64_t now,std::uint64_t sampled){
 auto*c=static_cast<EngineContext*>(p);ecu::engine::Inputs s;auto*j=cJSON_Parse(text);bool wheel=false;
 bool ok=j&&ecu::web::keys(j,"|rpm||map_kpa||tps_pct||clt_c||iat_c||lambda||battery_v||sensor_v||synced||sensors_valid||lambda_ready||use_decoder||phase_synced|");
#define INPUT(name) ok=ok&&ecu::web::number(j,#name,s.name)
 INPUT(rpm);INPUT(map_kpa);INPUT(tps_pct);INPUT(clt_c);INPUT(iat_c);INPUT(lambda);INPUT(battery_v);INPUT(sensor_v);
#undef INPUT
 ok=ok&&ecu::web::boolean(j,"synced",s.synced)&&ecu::web::boolean(j,"sensors_valid",s.sensors_valid)&&ecu::web::boolean(j,"lambda_ready",s.lambda_ready)&&ecu::web::boolean(j,"use_decoder",wheel);if(cJSON_GetObjectItemCaseSensitive(j,"phase_synced"))ok=ok&&ecu::web::boolean(j,"phase_synced",s.phase_synced);cJSON_Delete(j);
 if(!ok){c->last={};c->last.faults=ecu::engine::BadSensor;c->last.state=ecu::engine::State::Faulted;c->last.fuel_cut=c->last.spark_cut=true;c->scheduler.cut();c->have_control=false;c->stopped_since=UINT64_MAX;j=cJSON_CreateObject();cJSON_AddStringToObject(j,"error","Invalid native engine input");return encode(j);}
 c->decoder.tick(now);phase_fault(c);if(wheel){s.rpm=c->decoder.rpm();s.synced=c->decoder.crank_synced();s.phase_synced=c->decoder.phase_synced();}s.sampled_us=sampled;
 const bool continuous=c->have_control&&now>c->control_us&&now-c->control_us<=20000;
 c->control_us=now;c->sampled_us=sampled;c->have_control=true;c->last=c->controller.step(c->tune,s,now);
 // A protected stall may recover only after fresh decoder-derived stopped
 // samples and explicit executor all-low acknowledgment persist for 20 ms.
 // Ordinary cuts, transient sync loss and runtime polling do not clear faults.
 const bool quiet=c->last_trigger_us==UINT64_MAX||(now>=c->last_trigger_us&&now-c->last_trigger_us>150000);
 const bool stopped_safe=quiet&&wheel&&!s.synced&&c->last.state==ecu::engine::State::Stopped&&!c->last.faults&&!c->virtual_high_mask;
 if(c->scheduler.failed()&&stopped_safe){
  if(!continuous||c->stopped_since==UINT64_MAX||now<c->stopped_since)c->stopped_since=now;
  if(now>=c->stopped_since&&now-c->stopped_since>=20000){c->scheduler.reset();c->decoder.reset();++c->timing_recoveries;c->stopped_since=UINT64_MAX;}
 }else c->stopped_since=UINT64_MAX;
 if(c->last.faults||c->last.state==ecu::engine::State::Stopped)c->scheduler.cut();else c->scheduler.refresh_control(now,sampled);if(c->scheduler.failed()){c->last.faults|=ecu::engine::Timing;c->last.state=ecu::engine::State::Faulted;c->last.fuel_cut=c->last.spark_cut=true;}c->data=ecu::engine::synthetic_data(c->tune,s,c->last,++c->data_sequence,now);c->data.phase_reason=static_cast<std::uint8_t>(c->decoder.reason());c->data.phase_losses=c->decoder.losses();c->data.cam_rejected=c->decoder.rejected();c->data.cam_error_deg=c->decoder.cam_error_deg();c->data.virtual_high_mask=c->virtual_high_mask;
 j=ecu::engine::output_json(c->last);cJSON_AddBoolToObject(j,"synced",s.synced&&(!c->decoder.required()||s.phase_synced));cJSON_AddBoolToObject(j,"crank_synced",s.synced);cJSON_AddBoolToObject(j,"phase_synced",s.phase_synced);cJSON_AddBoolToObject(j,"phase_required",c->decoder.required());cJSON_AddStringToObject(j,"phase_reason",ecu::engine::PhaseDecoder::reason_name(c->decoder.reason()));cJSON_AddNumberToObject(j,"phase_losses",c->decoder.losses());cJSON_AddNumberToObject(j,"cam_rejected",c->decoder.rejected());cJSON_AddNumberToObject(j,"cam_error_deg",c->decoder.cam_error_deg());cJSON_AddNumberToObject(j,"gap_us",c->gap);cJSON_AddNumberToObject(j,"time_us",now);cJSON_AddNumberToObject(j,"timing_recoveries",c->timing_recoveries);cJSON_AddNumberToObject(j,"timing_stops",c->timing_stops);cJSON_AddNumberToObject(j,"executor_high_mask",c->virtual_high_mask);cJSON_AddStringToObject(j,"timing_stop_reason",ecu::engine::AngleScheduler::reason_name(c->last_timing_reason));return encode(j);
}
extern "C" const char* engine_plan(void*p){auto*c=static_cast<EngineContext*>(p);auto output=c->last;output.rpm=c->decoder.rpm();auto plan=ecu::engine::plan_revolution(c->tune,output,c->gap);auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"valid",plan.valid);auto*a=cJSON_AddArrayToObject(j,"edges");for(unsigned i=0;i<plan.count;++i){auto*e=cJSON_CreateArray();cJSON_AddItemToArray(e,cJSON_CreateNumber(plan.edges[i].time_us));cJSON_AddItemToArray(e,cJSON_CreateNumber(plan.edges[i].channel));cJSON_AddItemToArray(e,cJSON_CreateBool(plan.edges[i].high));cJSON_AddItemToArray(a,e);}return encode(j);}

extern "C" const char* engine_data_json(void*p){auto*c=static_cast<EngineContext*>(p);return encode(ecu::engine::data_json(c->data,c->control_us));}
