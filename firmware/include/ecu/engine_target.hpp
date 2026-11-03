#pragma once
#include "ecu/timing_executor.hpp"
#include "ecu/engine_phase.hpp"
#include "ecu/trigger_log.hpp"
#include "cJSON.h"
namespace ecu::engine_target {
struct Wheel {unsigned slots=60,missing=2,max_rpm=8000;};
struct Measurement {
 double rpm=0;bool synced=false,overflow=false,ready=false,timing_fault=false;
 bool phase_synced=false,phase_required=false;double cam_error_deg=0;
 engine::PhaseDecoder::Reason phase_reason=engine::PhaseDecoder::Reason::AwaitingCrank;
 std::uint64_t phase_losses=0,cam_rejected=0;
 std::uint32_t tune_revision=0,sensor_revision=0,phase_epoch=0;
 std::uint64_t crank_edges=0,cam_edges=0;
};
void init(Wheel wheel,bool interlock_at_boot);
std::uint64_t clock_us();
Measurement measurement();
bool submit(const timing::Command&);
void inhibit(timing::Cause);
void begin_configuration();
void finish_configuration(std::uint32_t tune_revision,std::uint32_t sensor_revision);
cJSON* snapshot();
cJSON* trace_json();
cJSON* trigger_json(std::uint32_t expected_frame=0,unsigned offset=0,bool records=false);
bool trigger_start(unsigned samples,unsigned timeout_ms);
bool trigger_stop(std::uint32_t frame_id);
}
