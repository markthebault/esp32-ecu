#pragma once
#include "ecu/flex_fuel.hpp"

namespace ecu { namespace flex {
struct Config {CaptureConfig capture;CorrectionConfig correction;bool input_confirmed=false;};
inline bool valid(const Config&c){return valid(c.capture)&&valid(c.correction);}
// Calibration travels with the immutable observation. A local epoch counter
// alone cannot prove that an asynchronous sample belongs to the current tune.
struct Sample {Observation observation;CaptureConfig calibration;std::uint32_t tune_revision=0;};
struct Evaluation {
 Sample sample;Corrections corrections;
 Reason reason=Reason::Disabled;
 bool required=false,configuration_match=false,value_qualified=false,raw_qualified=false,control_ok=true;
 bool spark_bypassed=false,spark_clamped=false,zero_factor=false;
 bool input_confirmed=false,available=false;
};
inline Evaluation assess(const Config&c,const Sample&s,std::uint64_t now,bool ethanol_required,std::uint32_t tune_revision){
 Evaluation e;e.available=true;e.sample=s;e.required=c.correction.enabled||ethanol_required;e.input_confirmed=c.input_confirmed;e.configuration_match=tune_revision&&s.tune_revision==tune_revision&&same(c.capture,s.calibration);
 if(s.observation.source!=Source::Unavailable&&now>=s.observation.sample_us)e.sample.observation.age_ms=double(now-s.observation.sample_us)/1000;
 e.corrections=evaluate(c.correction,c.capture,s.observation,now);
 auto fail=[&](Reason reason){e.reason=reason;e.control_ok=!e.required;if(c.correction.enabled){e.corrections.valid=false;e.corrections.reason=reason;e.corrections.fuel_factor=e.corrections.spark_add_deg=e.corrections.temperature_factor=NAN;}return e;};
 if(!valid(c)){e.corrections.valid=false;return fail(Reason::InvalidConfig);}
 if(!e.configuration_match)return fail(Reason::ConfigurationMismatch);
 const auto&o=s.observation;
 if(o.source!=Source::TargetCapture&&o.source!=Source::Synthetic&&o.source!=Source::SyntheticValue)return fail(Reason::Unavailable);
 if(o.source==Source::TargetCapture&&!c.input_confirmed)return fail(Reason::Unconfirmed);
 if(!o.valid||o.pending_fault||o.fault_generation!=o.acknowledged_generation)return fail(o.reason==Reason::Ready?Reason::MalformedSample:o.reason);
 if(now<o.sample_us||now<o.last_edge_us)return fail(Reason::Future);
 if(now-o.sample_us>std::uint64_t(std::llround(c.capture.stale_ms*1000.)))return fail(Reason::Stale);
 if(!range(o.ethanol_pct,0,100)||!o.config_epoch)return fail(Reason::MalformedSample);
 if(o.source==Source::SyntheticValue){
  // Explicit host-only legacy ETH selection. Never invent frequency, width,
  // temperature or a completed capture window from a scalar percentage.
  if(o.reason!=Reason::ValueOnly||o.capture_reason!=Reason::Unavailable||o.window_cycles||std::isfinite(o.frequency_hz)||std::isfinite(o.low_pulse_us)||std::isfinite(o.fuel_temp_c))return fail(Reason::MalformedSample);
  if(c.correction.enabled)return fail(Reason::RawCaptureRequired);
  e.value_qualified=true;e.reason=Reason::ValueOnly;e.control_ok=true;return e;
 }
 if(o.reason!=Reason::Ready||o.capture_reason!=Reason::Ready||o.window_cycles!=c.capture.cycles||
  o.window_start_us>=o.sample_us||o.sample_us>o.last_edge_us||!range(o.fuel_temp_c,-40,125)||
  !range(o.low_pulse_us,998,5002)||!range(o.frequency_hz,1,500))return fail(Reason::MalformedSample);
 const double hz=1000000.*o.window_cycles/double(o.sample_us-o.window_start_us);
 if(std::abs(hz-o.frequency_hz)>1e-8*std::max(1.,hz))return fail(Reason::MalformedSample);
 // Recheck the complete F64 capture contract at the controller boundary.
 // Range checks alone could accept a forged percentage, temperature or a
 // geometrically consistent window outside the active sensor calibration.
 const double period=double(o.sample_us-o.window_start_us)/o.window_cycles;
 const auto&cal=c.capture;
 if(period<=std::ceil(1000000./cal.fault_hz)||period+1<1000000./(cal.high_hz+cal.tolerance_hz)||
  period-1>1000000./(cal.low_hz-cal.tolerance_hz)||o.low_pulse_us>=period||o.edges<2U*cal.cycles+1)return fail(Reason::MalformedSample);
 const double raw_ethanol=100*(hz-cal.low_hz)/(cal.high_hz-cal.low_hz),raw_temperature=.04125*o.low_pulse_us-81.25;
 auto equal=[](double a,double b){return std::isfinite(a)&&std::abs(a-b)<=1e-8*std::max(1.,std::abs(b));};
 if(!equal(o.unfiltered_ethanol_pct,bounded(raw_ethanol,0,100))||!equal(o.unfiltered_fuel_temp_c,bounded(raw_temperature,-40,125))||
  o.frequency_clamped!=(raw_ethanol<0||raw_ethanol>100)||o.temperature_clamped!=(raw_temperature< -40||raw_temperature>125)||
  (cal.filter_ms==0&&(!equal(o.ethanol_pct,o.unfiltered_ethanol_pct)||!equal(o.fuel_temp_c,o.unfiltered_fuel_temp_c))))return fail(Reason::MalformedSample);
 e.value_qualified=e.raw_qualified=true;e.reason=Reason::Ready;e.control_ok=!e.required||e.corrections.valid;
 if(!e.control_ok)e.reason=e.corrections.reason;
 e.zero_factor=c.correction.enabled&&e.corrections.valid&&(e.corrections.fuel_factor==0||e.corrections.temperature_factor==0);
 return e;
}
inline Sample synthetic_value(double ethanol,bool qualified,std::uint64_t sampled,const CaptureConfig&calibration,std::uint32_t revision){
 Sample s;s.calibration=calibration;s.tune_revision=revision;auto&o=s.observation;o.source=Source::SyntheticValue;
 o.valid=qualified&&range(ethanol,0,100);o.ethanol_pct=ethanol;o.sample_us=sampled;o.reason=Reason::ValueOnly;o.capture_reason=Reason::Unavailable;
 return s;
}
}} // namespace ecu::flex
