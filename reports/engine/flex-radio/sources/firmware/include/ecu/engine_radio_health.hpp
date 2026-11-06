#pragma once
#include "ecu/engine_radio_flex.hpp"

namespace ecu::radio {
// Advisory requested policy only. This does not measure the physical LED or
// establish engine/CPU health. Required flex faults apply at zero RPM too.
inline bool required_flex_problem(const engine::RuntimeSample&r,std::uint64_t raw_age_us,std::uint64_t control_age_us){
 const auto&f=r.flex_fuel;if(!f.has(flex::Required)&&!f.has(flex::CorrectionsEnabled))return false;
 if(!r.has(engine::Present)||!f.has(flex::Available)||!f.has(flex::ControlOk)||!f.has(flex::ValueQualified)||
    !f.has(flex::ConfigurationMatch)||f.has(flex::PendingFault)||f.times[4]!=f.times[5]||
    !flex::valid_record(f)||f.revision!=r.tune_revision||
    (r.source==engine::DataSource::Target&&f.source!=static_cast<unsigned>(flex::Source::TargetCapture))||
    raw_age_us==UINT64_MAX||control_age_us==UINT64_MAX||control_age_us>1000000)return true;
 const auto stale=wire::flex_stale_limit(f);return !stale||raw_age_us>stale;
}
} // namespace ecu::radio
