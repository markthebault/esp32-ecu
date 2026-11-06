#pragma once
#include "ecu/timing_executor.hpp"
#include "ecu/engine_phase.hpp"
#include "ecu/trigger_log.hpp"
#include "ecu/flex_capture_owner.hpp"
#include "cJSON.h"
namespace ecu::engine_target {
struct Wheel {unsigned slots=60,missing=2,max_rpm=8000;};
struct Measurement {
 double rpm=0;bool synced=false,overflow=false,ready=false,timing_fault=false;
 bool phase_synced=false,phase_required=false;double cam_error_deg=0;
 engine::PhaseDecoder::Reason phase_reason=engine::PhaseDecoder::Reason::AwaitingCrank;
 std::uint64_t phase_losses=0,cam_rejected=0;
 std::uint32_t tune_revision=0,sensor_revision=0,phase_epoch=0;
 std::uint64_t worker_sequence=0,worker_observed_us=0;
 std::uint32_t worker_epoch=0,worker_tune_revision=0,worker_sensor_revision=0;
 std::uint8_t timing_cause=0,last_timing_cause=0,worker_cylinder_count=0;
 std::uint32_t virtual_high_mask=0,physical_command_mask=0;
 std::uint64_t crank_edges=0,cam_edges=0;
};
void init(Wheel wheel,bool interlock_at_boot);
std::uint64_t clock_us();
Measurement measurement();
bool submit(const timing::Command&);
bool submit_capture(const timing::Command&,const flex::CaptureTicket&);
flex::CaptureWork flex_configure(const flex::CaptureRequest&,bool valid,std::uint64_t stale_us);
bool flex_arm(flex::CaptureVersion);
flex::CaptureWork flex_work();
bool flex_pop(flex::CaptureVersion,flex::IngressEdge&);
bool flex_publish(flex::CaptureVersion,const flex::Sample&);
flex::CaptureView flex_view();
bool flex_acknowledge(const flex::CaptureView&);
cJSON* flex_snapshot();
struct FlexBackend {
 flex::CaptureWork configure(const flex::CaptureRequest&r,bool valid,std::uint64_t stale){return flex_configure(r,valid,stale);}
 bool arm(flex::CaptureVersion v){return flex_arm(v);}
 flex::CaptureWork work(){return flex_work();}
 bool pop(flex::CaptureVersion v,flex::IngressEdge&e){return flex_pop(v,e);}
 bool publish(flex::CaptureVersion v,const flex::Sample&s){return flex_publish(v,s);}
 flex::CaptureView view(){return flex_view();}
 bool acknowledge(const flex::CaptureView&v){return flex_acknowledge(v);}
 std::uint64_t clock(){return clock_us();}
};
void inhibit(timing::Cause);
void begin_configuration();
void finish_configuration(std::uint32_t tune_revision,std::uint32_t sensor_revision);
cJSON* snapshot();
cJSON* trace_json();
cJSON* trigger_json(std::uint32_t expected_frame=0,unsigned offset=0,bool records=false);
bool trigger_start(unsigned samples,unsigned timeout_ms);
bool trigger_stop(std::uint32_t frame_id);
}
