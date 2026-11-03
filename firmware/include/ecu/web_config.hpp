#pragma once
#include "ecu/config.hpp"
#include <array>
#include <cstdint>
namespace ecu::web {
struct Sample {std::array<unsigned,8> raw{};bool adc_ok{},safe{},interlock{},overflow{},synced{},timing_fault{},phase_synced{};double rpm{};std::uint64_t can_frames{},cam_edges{},crank_edges{};int crank_level{},cam_level{};std::uint32_t phase_tune_revision{},phase_sensor_revision{},phase_epoch{};};
void init(); // Load NVS before the monitor loop; never enables outputs.
void start_service(); // AP only in the dedicated web build, with J3 open at startup.
bool try_config(config::Config& out);
void publish(const Sample& sample);
}
