// Native execution of the same fixed-storage dispatcher used by GPTimer ISR.
// CPU execution cost is zero here. Peripheral/CPU latency needs target/HIL tests.
#include "ecu/engine_json.hpp"
#include "ecu/engine_data_json.hpp"
#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include "ecu/idle_command.hpp"
#include "ecu/idle_pwm_json.hpp"
#include <string>

namespace {
struct Context;
struct Event {std::uint64_t time=0,dwell=0;unsigned ch=0;bool high=false,cut=false;double advance=0;};
struct IO {
 Context* owner=nullptr;std::uint8_t mask=0;bool dispatching=false;
 void all_low();bool write(unsigned ch,bool high);
};
struct IdleIO {Context*owner=nullptr;bool high=false;void all_low();bool write(bool value);};
struct Context {
 ecu::engine::RuntimeSample data;std::uint64_t data_sequence=0;
 ecu::engine::Tune tune;ecu::engine::Controller controller;ecu::engine::PhaseDecoder decoder{{60,2,8000}};
 ecu::timing::Executor core;ecu::idle::PwmExecutor pwm;ecu::engine::Output last;IO io;IdleIO idle_io;
 std::array<Event,32> events{};unsigned event_begin=0,event_count=0;
 Event popped;std::uint64_t now=0,command_us=0,sampled_us=0,gap=0,sequence=0;
 unsigned slots=60,missing=2,max_rpm=8000;bool have_control=false;
 Context(){io.owner=this;idle_io.owner=this;}
 void enqueue(Event e){if(event_count<events.size()){events[(event_begin+event_count)%events.size()]=e;++event_count;}}
};
void IdleIO::all_low(){if(high)write(false);}
bool IdleIO::write(bool value){if(high==value)return true;high=value;owner->enqueue({owner->now,0,8,value,false,0});return true;}
void IO::all_low(){mask=0;if(owner->pwm.stats().active||owner->pwm.stats().high)owner->pwm.stop(owner->now,ecu::idle::PwmCause::EngineFault,owner->idle_io);else owner->idle_io.all_low();if(dispatching)owner->enqueue({owner->now,0,0,false,true,0});}
bool IO::write(unsigned ch,bool high){
 if(high)mask|=1U<<ch;else mask&=~(1U<<ch);
 owner->enqueue({owner->now,owner->core.event_requested_dwell_us(),ch,high,false,owner->core.event_advance()});return true;
}
thread_local std::string reply;
const char* encode(cJSON*j){char*s=cJSON_PrintUnformatted(j);cJSON_Delete(j);reply=s?s:"{}";cJSON_free(s);return reply.c_str();}
ecu::timing::Command command(Context& c){
 ecu::timing::Command cmd;cmd.angle=ecu::engine::angle_config(c.tune);cmd.output=c.last;
 cmd.command_us=c.command_us;cmd.sampled_us=c.sampled_us;cmd.sequence=++c.sequence;
 cmd.tune_revision=c.tune.revision;cmd.sensor_revision=1;cmd.slots=c.slots;cmd.missing=c.missing;cmd.max_rpm=c.max_rpm;
 cmd.max_injector_high_us=std::llround(c.tune.max_injection_ms*1000);cmd.max_coil_high_us=std::llround(c.tune.max_dwell_ms*1000);ecu::idle::prepare_pwm(cmd,c.tune);return cmd;
}
void idle_fault(Context&c){if(c.pwm.stats().fault!=ecu::idle::PwmCause::None&&c.core.stats().fault==ecu::timing::Cause::None)c.core.trip(c.now,ecu::timing::Cause::IdlePwm,c.io);}
void dispatch(Context&c){c.core.dispatch(c.now,c.io);c.pwm.dispatch(c.now,c.idle_io);idle_fault(c);}
}
extern "C" const char* engine_canonicalize(const char*text){ecu::engine::Tune tune;static thread_local std::string canonical;if(!ecu::engine::canonical_tune(text,tune,canonical))return nullptr;return canonical.c_str();}
extern "C" int engine_validate(const char* text){
 if(!ecu::web::safe_json(text,std::strlen(text),ecu::engine::tune_maximum))return 0;
 auto* j=cJSON_ParseWithOpts(text,nullptr,true);ecu::engine::Tune tune;
 const bool ok=j&&ecu::engine::parse_tune(j,tune);cJSON_Delete(j);return ok;
}
extern "C" void* engine_create(){return new Context;}
extern "C" void engine_destroy(void*p){delete static_cast<Context*>(p);}
extern "C" int engine_configure(void*p,const char* text){
 if(!text||!ecu::web::safe_json(text,std::strlen(text),ecu::engine::tune_maximum))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::engine::Tune candidate;
 const bool ok=j&&ecu::engine::parse_tune(j,candidate);cJSON_Delete(j);if(!ok)return 0;
 auto&c=*static_cast<Context*>(p);c.tune=candidate;c.controller.reset();c.core=ecu::timing::Executor{};c.pwm=ecu::idle::PwmExecutor{};c.idle_io.high=false;
 c.decoder=ecu::engine::PhaseDecoder({c.slots,c.missing,c.max_rpm},ecu::engine::angle_config(c.tune));c.last={};c.data={};c.data_sequence=0;c.io.mask=0;c.event_count=0;c.event_begin=0;c.now=c.command_us=c.sampled_us=c.sequence=0;c.have_control=false;return 1;
}
extern "C" int engine_wheel(void*p,unsigned slots,unsigned missing,unsigned max_rpm){
 auto&c=*static_cast<Context*>(p);ecu::engine::PhaseDecoder decoder({slots,missing,max_rpm},ecu::engine::angle_config(c.tune));if(!decoder.valid())return 0;
 c.decoder=decoder;c.slots=slots;c.missing=missing;c.max_rpm=max_rpm;
 c.core.stop(c.now,ecu::timing::Cause::Configuration,c.io);return 1;
}
static void update_phase(Context&c){
 if(!c.decoder.required())return;
 c.core.phase(c.decoder.phase_synced(),c.decoder.deadline(),c.now,c.io);
 if(c.core.stats().fault==ecu::timing::Cause::CamPhase&&!c.decoder.faulted())c.decoder.invalidate(ecu::engine::PhaseDecoder::Reason::Timeout);
}
extern "C" int engine_cam(void*p,std::uint64_t time){auto&c=*static_cast<Context*>(p);c.now=time;c.core.progress(time,c.io);c.core.raw_capture(time);c.decoder.cam(time);update_phase(c);return c.core.stats().fault==ecu::timing::Cause::None?0:3;}
extern "C" int engine_trigger(void*p,std::uint64_t time){
 auto&c=*static_cast<Context*>(p);c.now=time;c.core.progress(time,c.io);c.core.raw_capture(time);
 const bool before=c.decoder.synced();c.decoder.edge(time);update_phase(c);
 if(!c.decoder.synced()){if(before)c.core.stop(time,ecu::timing::Cause::Control,c.io);return before?2:0;}
 if(!c.have_control||time<c.command_us||time<c.sampled_us)return 0;
 const auto& stats=c.core.stats();if(stats.fault!=ecu::timing::Cause::None)return 2;
 ecu::timing::Executor::Candidate candidate;c.core.prepare(candidate,time,c.decoder.stall_timeout());
 candidate.calculate(c.decoder.required()?c.decoder.phase_tooth():c.decoder.tooth(),c.decoder.rpm());
 if(c.core.commit(candidate,time,c.io)!=ecu::timing::Executor::Commit::Accepted)return 3;
 if(c.decoder.tooth()==0){c.gap=time;return 1;}return 0;
}
extern "C" void engine_cut(void*p){auto&c=*static_cast<Context*>(p);c.core.stop(c.now,ecu::timing::Cause::Control,c.io);c.event_count=0;}
extern "C" void engine_progress(void*p,std::uint64_t now){auto&c=*static_cast<Context*>(p);c.now=now;c.io.dispatching=true;c.core.progress(now,c.io);c.pwm.dispatch(now,c.idle_io);idle_fault(c);c.io.dispatching=false;}
extern "C" const char* engine_timing_reason(void*p){return ecu::timing::cause_name(static_cast<Context*>(p)->core.stats().last_fault);}
extern "C" std::uint64_t engine_next_time(void*p){auto&c=*static_cast<Context*>(p);return c.event_count?c.events[c.event_begin].time:std::min(c.core.next_alarm(),c.pwm.next_alarm());}
extern "C" unsigned engine_pop(void*p){
 auto&c=*static_cast<Context*>(p);
 if(!c.event_count){const auto due=std::min(c.core.next_alarm(),c.pwm.next_alarm());if(due==UINT64_MAX)return 0;c.now=due;c.io.dispatching=true;dispatch(c);c.io.dispatching=false;}
 if(!c.event_count)return 0x40000; // Timer advanced with a constant GPIO level; no fabricated edge.
 c.popped=c.events[c.event_begin];c.event_begin=(c.event_begin+1)%c.events.size();--c.event_count;
 return c.popped.cut?0x30000:0x10000|c.popped.ch|(c.popped.high?0x100:0);
}
extern "C" double engine_event_advance(void*p){return static_cast<Context*>(p)->popped.advance;}
extern "C" std::uint64_t engine_event_dwell(void*p){return static_cast<Context*>(p)->popped.dwell;}
extern "C" const char* engine_step(void*p,const char*text,std::uint64_t now,std::uint64_t sampled){
 auto&c=*static_cast<Context*>(p);auto*j=cJSON_Parse(text);ecu::engine::Inputs in;bool wheel=false;
 bool ok=j&&ecu::web::keys(j,"|rpm||map_kpa||tps_pct||clt_c||iat_c||lambda||battery_v||sensor_v||synced||sensors_valid||lambda_ready||use_decoder||phase_synced|");
#define FIELD(k) ok=ok&&ecu::web::number(j,#k,in.k)
 FIELD(rpm);FIELD(map_kpa);FIELD(tps_pct);FIELD(clt_c);FIELD(iat_c);FIELD(lambda);FIELD(battery_v);FIELD(sensor_v);
#undef FIELD
 ok=ok&&ecu::web::boolean(j,"synced",in.synced)&&ecu::web::boolean(j,"sensors_valid",in.sensors_valid)&&
  ecu::web::boolean(j,"lambda_ready",in.lambda_ready)&&ecu::web::boolean(j,"use_decoder",wheel);
 if(cJSON_GetObjectItemCaseSensitive(j,"phase_synced"))ok=ok&&ecu::web::boolean(j,"phase_synced",in.phase_synced);
 cJSON_Delete(j);
 c.now=now;
 if(!ok){c.core.trip(now,ecu::timing::Cause::Control,c.io);j=cJSON_CreateObject();cJSON_AddStringToObject(j,"error","Invalid native timing input");return encode(j);}
 c.decoder.tick(now);update_phase(c);if(wheel){in.rpm=c.decoder.rpm();in.synced=c.decoder.crank_synced();in.phase_synced=c.decoder.phase_synced();}in.sampled_us=sampled;
 c.last=c.controller.step(c.tune,in,now);c.command_us=now;c.sampled_us=sampled;c.have_control=true;
 c.core.progress(now,c.io);const auto cmd=command(c);c.core.command(cmd,now,c.io);
 c.pwm.submit(ecu::idle::pwm_command(cmd,c.core.current_command(),now,c.core.stats()),now,c.idle_io);idle_fault(c);
 if(c.core.recover(now,wheel&&!in.synced&&c.last.state==ecu::engine::State::Stopped&&!c.last.faults))c.decoder.reset();
 const auto& stats=c.core.stats();
 if(stats.fault!=ecu::timing::Cause::None){c.last.faults|=ecu::engine::Timing;c.last.state=ecu::engine::State::Faulted;c.last.fuel_cut=c.last.spark_cut=true;}
 c.data=ecu::engine::synthetic_data(c.tune,in,c.last,++c.data_sequence,now);c.data.phase_reason=static_cast<std::uint8_t>(c.decoder.reason());c.data.phase_losses=c.decoder.losses();c.data.cam_rejected=c.decoder.rejected();c.data.cam_error_deg=c.decoder.cam_error_deg();c.data.virtual_high_mask=c.io.mask;
 c.data.worker_sequence=c.core.current_command().sequence;c.data.worker_observed_us=now;c.data.worker_epoch=stats.epoch;c.data.worker_tune_revision=c.core.current_command().tune_revision;c.data.worker_sensor_revision=c.core.current_command().sensor_revision;c.data.timing_fault=static_cast<std::uint8_t>(stats.fault);c.data.last_timing_fault=static_cast<std::uint8_t>(stats.last_fault);
 j=ecu::engine::output_json(c.last);cJSON_AddStringToObject(j,"angle_stop_reason",ecu::engine::AngleScheduler::reason_name(stats.angle_reason));cJSON_AddBoolToObject(j,"synced",in.synced&&(!c.decoder.required()||in.phase_synced));cJSON_AddBoolToObject(j,"crank_synced",in.synced);cJSON_AddBoolToObject(j,"phase_synced",in.phase_synced);cJSON_AddBoolToObject(j,"phase_required",c.decoder.required());cJSON_AddStringToObject(j,"phase_reason",ecu::engine::PhaseDecoder::reason_name(c.decoder.reason()));cJSON_AddNumberToObject(j,"phase_losses",c.decoder.losses());cJSON_AddNumberToObject(j,"cam_rejected",c.decoder.rejected());cJSON_AddNumberToObject(j,"cam_error_deg",c.decoder.cam_error_deg());cJSON_AddNumberToObject(j,"time_us",now);cJSON_AddNumberToObject(j,"gap_us",c.gap);
 cJSON_AddNumberToObject(j,"timing_stops",stats.faults);cJSON_AddNumberToObject(j,"timing_recoveries",stats.recoveries);
 cJSON_AddNumberToObject(j,"executor_high_mask",c.io.mask);cJSON_AddStringToObject(j,"timing_stop_reason",ecu::timing::cause_name(stats.last_fault));return encode(j);
}
extern "C" const char* engine_plan(void*){return "{\"valid\":false,\"edges\":[]}";}

extern "C" const char* engine_data_json(void*p){auto&c=*static_cast<Context*>(p);return encode(ecu::engine::data_json(c.data,c.now));}
extern "C" const char* engine_idle_json(void*p){return encode(ecu::idle::pwm_json(static_cast<Context*>(p)->pwm.stats(),false,false));}
