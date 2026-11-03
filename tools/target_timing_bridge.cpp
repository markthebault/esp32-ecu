// Native execution of the same fixed-storage dispatcher used by GPTimer ISR.
// CPU execution cost is zero here. Peripheral/CPU latency needs target/HIL tests.
#include "ecu/engine_json.hpp"
#include "ecu/control.hpp"
#include "ecu/timing_executor.hpp"
#include <string>

namespace {
struct Context;
struct Event {std::uint64_t time=0,dwell=0;unsigned ch=0;bool high=false,cut=false;double advance=0;};
struct IO {
 Context* owner=nullptr;std::uint8_t mask=0;bool dispatching=false;
 void all_low();bool write(unsigned ch,bool high);
};
struct Context {
 ecu::engine::Tune tune;ecu::engine::Controller controller;ecu::MissingTooth decoder{{60,2,8000}};
 ecu::timing::Executor core;ecu::engine::Output last;IO io;
 std::array<Event,32> events{};unsigned event_begin=0,event_count=0;
 Event popped;std::uint64_t now=0,command_us=0,sampled_us=0,gap=0,sequence=0;
 unsigned slots=60,missing=2,max_rpm=8000;bool have_control=false;
 Context(){io.owner=this;}
 void enqueue(Event e){if(event_count<events.size()){events[(event_begin+event_count)%events.size()]=e;++event_count;}}
};
void IO::all_low(){mask=0;if(dispatching)owner->enqueue({owner->now,0,0,false,true,0});}
bool IO::write(unsigned ch,bool high){
 if(high)mask|=1U<<ch;else mask&=~(1U<<ch);
 owner->enqueue({owner->now,owner->core.event_requested_dwell_us(),ch,high,false,owner->core.event_advance()});return true;
}
thread_local std::string reply;
const char* encode(cJSON*j){char*s=cJSON_PrintUnformatted(j);cJSON_Delete(j);reply=s?s:"{}";cJSON_free(s);return reply.c_str();}
ecu::timing::Command command(Context& c){
 ecu::timing::Command cmd;cmd.angle={c.tune.tooth1_btdc_deg,c.tune.max_dwell_ms};cmd.output=c.last;
 cmd.command_us=c.command_us;cmd.sampled_us=c.sampled_us;cmd.sequence=++c.sequence;
 cmd.tune_revision=c.tune.revision;cmd.sensor_revision=1;cmd.slots=c.slots;cmd.missing=c.missing;cmd.max_rpm=c.max_rpm;
 cmd.max_injector_high_us=std::llround(c.tune.max_injection_ms*1000);cmd.max_coil_high_us=std::llround(c.tune.max_dwell_ms*1000);return cmd;
}
}
extern "C" int engine_validate(const char* text){
 if(!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto* j=cJSON_ParseWithOpts(text,nullptr,true);ecu::engine::Tune tune;
 const bool ok=j&&ecu::engine::parse_tune(j,tune);cJSON_Delete(j);return ok;
}
extern "C" void* engine_create(){return new Context;}
extern "C" void engine_destroy(void*p){delete static_cast<Context*>(p);}
extern "C" int engine_configure(void*p,const char* text){
 if(!engine_validate(text))return 0;
 auto&c=*static_cast<Context*>(p);auto*j=cJSON_Parse(text);
 const bool ok=ecu::engine::parse_tune(j,c.tune);cJSON_Delete(j);c.controller.reset();c.core=ecu::timing::Executor{};
 c.decoder.reset();c.last={};c.io.mask=0;c.event_count=0;c.event_begin=0;c.now=c.command_us=c.sampled_us=c.sequence=0;c.have_control=false;return ok;
}
extern "C" int engine_wheel(void*p,unsigned slots,unsigned missing,unsigned max_rpm){
 ecu::MissingTooth decoder({slots,missing,max_rpm});if(!decoder.valid())return 0;
 auto&c=*static_cast<Context*>(p);c.decoder=decoder;c.slots=slots;c.missing=missing;c.max_rpm=max_rpm;
 c.core.stop(c.now,ecu::timing::Cause::Configuration,c.io);return 1;
}
extern "C" int engine_trigger(void*p,std::uint64_t time){
 auto&c=*static_cast<Context*>(p);c.now=time;c.core.progress(time,c.io);c.core.raw_capture(time);
 const bool before=c.decoder.synced();c.decoder.edge(time);
 if(!c.decoder.synced()){if(before)c.core.stop(time,ecu::timing::Cause::Control,c.io);return before?2:0;}
 if(!c.have_control||time<c.command_us||time<c.sampled_us)return 0;
 const auto& stats=c.core.stats();if(stats.fault!=ecu::timing::Cause::None)return 2;
 ecu::timing::Executor::Candidate candidate;c.core.prepare(candidate,time,c.decoder.stall_timeout());
 candidate.calculate(c.decoder.tooth(),c.decoder.rpm());
 if(c.core.commit(candidate,time,c.io)!=ecu::timing::Executor::Commit::Accepted)return 3;
 if(c.decoder.tooth()==0){c.gap=time;return 1;}return 0;
}
extern "C" void engine_cut(void*p){auto&c=*static_cast<Context*>(p);c.core.stop(c.now,ecu::timing::Cause::Control,c.io);c.event_count=0;}
extern "C" void engine_progress(void*p,std::uint64_t now){auto&c=*static_cast<Context*>(p);c.now=now;c.core.progress(now,c.io);}
extern "C" const char* engine_timing_reason(void*p){return ecu::timing::cause_name(static_cast<Context*>(p)->core.stats().last_fault);}
extern "C" std::uint64_t engine_next_time(void*p){auto&c=*static_cast<Context*>(p);return c.event_count?c.events[c.event_begin].time:c.core.next_alarm();}
extern "C" unsigned engine_pop(void*p){
 auto&c=*static_cast<Context*>(p);
 if(!c.event_count){const auto due=c.core.next_alarm();if(due==UINT64_MAX)return 0;c.now=due;c.io.dispatching=true;c.core.dispatch(due,c.io);c.io.dispatching=false;}
 if(!c.event_count)return 0;
 c.popped=c.events[c.event_begin];c.event_begin=(c.event_begin+1)%c.events.size();--c.event_count;
 return c.popped.cut?0x30000:0x10000|c.popped.ch|(c.popped.high?0x100:0);
}
extern "C" double engine_event_advance(void*p){return static_cast<Context*>(p)->popped.advance;}
extern "C" std::uint64_t engine_event_dwell(void*p){return static_cast<Context*>(p)->popped.dwell;}
extern "C" const char* engine_step(void*p,const char*text,std::uint64_t now,std::uint64_t sampled){
 auto&c=*static_cast<Context*>(p);auto*j=cJSON_Parse(text);ecu::engine::Inputs in;bool wheel=false;
 bool ok=j&&ecu::web::keys(j,"|rpm||map_kpa||tps_pct||clt_c||iat_c||lambda||battery_v||sensor_v||synced||sensors_valid||lambda_ready||use_decoder|");
#define FIELD(k) ok=ok&&ecu::web::number(j,#k,in.k)
 FIELD(rpm);FIELD(map_kpa);FIELD(tps_pct);FIELD(clt_c);FIELD(iat_c);FIELD(lambda);FIELD(battery_v);FIELD(sensor_v);
#undef FIELD
 ok=ok&&ecu::web::boolean(j,"synced",in.synced)&&ecu::web::boolean(j,"sensors_valid",in.sensors_valid)&&
  ecu::web::boolean(j,"lambda_ready",in.lambda_ready)&&ecu::web::boolean(j,"use_decoder",wheel);cJSON_Delete(j);
 c.now=now;
 if(!ok){c.core.trip(now,ecu::timing::Cause::Control,c.io);j=cJSON_CreateObject();cJSON_AddStringToObject(j,"error","Invalid native timing input");return encode(j);}
 c.decoder.tick(now);if(wheel){in.rpm=c.decoder.rpm();in.synced=c.decoder.synced();}in.sampled_us=sampled;
 c.last=c.controller.step(c.tune,in,now);c.command_us=now;c.sampled_us=sampled;c.have_control=true;
 c.core.progress(now,c.io);c.core.command(command(c),now,c.io);
 c.core.recover(now,wheel&&!in.synced&&c.last.state==ecu::engine::State::Stopped&&!c.last.faults);
 const auto& stats=c.core.stats();
 if(stats.fault!=ecu::timing::Cause::None){c.last.faults|=ecu::engine::Timing;c.last.state=ecu::engine::State::Faulted;c.last.fuel_cut=c.last.spark_cut=true;}
 j=ecu::engine::output_json(c.last);cJSON_AddBoolToObject(j,"synced",in.synced);cJSON_AddNumberToObject(j,"time_us",now);cJSON_AddNumberToObject(j,"gap_us",c.gap);
 cJSON_AddNumberToObject(j,"timing_stops",stats.faults);cJSON_AddNumberToObject(j,"timing_recoveries",stats.recoveries);
 cJSON_AddNumberToObject(j,"executor_high_mask",c.io.mask);cJSON_AddStringToObject(j,"timing_stop_reason",ecu::timing::cause_name(stats.last_fault));return encode(j);
}
extern "C" const char* engine_plan(void*){return "{\"valid\":false,\"edges\":[]}";}
