#pragma once
#include "ecu/flex_engine.hpp"
#include <cfloat>

namespace ecu { namespace flex {
// Snapshot of a completed evaluation, never a second assessment using rounded
// logger values. Timestamp/counter integers remain lossless across transports.
enum RecordFlag:std::uint32_t {Required=1,ConfigurationMatch=2,ValueQualified=4,RawQualified=8,
 ControlOk=16,CaptureValid=32,SampleValueValid=64,PendingFault=128,FrequencyClamped=256,
 TemperatureClamped=512,InputConfirmed=1024,CorrectionsEnabled=2048,CorrectionsValid=4096,
 SparkBypassed=8192,SparkClamped=16384,ZeroFactor=32768,Available=65536};
inline constexpr const char* value_names[]={"frequency_hz","low_pulse_us","ethanol_pct","fuel_temp_c","unfiltered_ethanol_pct","unfiltered_fuel_temp_c","sample_age_ms","fuel_pct","spark_add_deg","temperature_pct"};
inline constexpr const char* value_labels[]={"FrequencyHz","LowPulseUs","EthanolPct","FuelTempC","UnfilteredEthanolPct","UnfilteredFuelTempC","SampleAgeMs","FuelPct","SparkAddDeg","TemperaturePct"};
inline constexpr const char* value_units[]={"Hz","us","% ethanol","C","% ethanol","C","ms","%","deg delta","%"};
inline constexpr const char* code_labels[]={"SourceCode","ReasonCode","CaptureReasonCode","LastFaultCode","CorrectionReasonCode","WindowCycles","ConfigurationRevision"};
inline constexpr const char* time_labels[]={"SampleUs","WindowStartUs","LastEdgeUs","RawEdges","FaultGeneration","AcknowledgedGeneration","ConfigEpoch"};
inline constexpr const char* flag_labels[]={"Required","ConfigurationMatch","ValueQualified","RawCaptureQualified","ControlOk","CaptureValid","SampleValueValid","PendingFault","FrequencyClamped","TemperatureClamped","InputConfirmed","CorrectionsEnabled","CorrectionsValid","SparkBypassed","SparkClamped","ZeroFactor","Available"};
struct Record {
 std::array<std::uint64_t,7> times{};
 std::array<float,10> values{NAN,NAN,NAN,NAN,NAN,NAN,NAN,NAN,NAN,NAN};
 std::array<float,6> calibration{};
 std::uint32_t flags=0,revision=0;
 std::uint8_t source=0,reason=0,capture_reason=0,last_fault=0,correction_reason=0,window_cycles=0,calibration_cycles=0;
 bool has(RecordFlag flag)const{return (flags&flag)!=0;}
 std::array<std::uint32_t,7> codes()const{return {source,reason,capture_reason,last_fault,correction_reason,window_cycles,revision};}
};
static_assert(sizeof(Record)<=136,"Flex diagnostic snapshot RAM budget");
inline Record record(const Evaluation&e){
 Record r;if(!e.available)return r;const auto&o=e.sample.observation;
 const double values[]={o.frequency_hz,o.low_pulse_us,o.ethanol_pct,o.fuel_temp_c,o.unfiltered_ethanol_pct,o.unfiltered_fuel_temp_c,o.age_ms,e.corrections.fuel_factor*100,e.corrections.spark_add_deg,e.corrections.temperature_factor*100};
 for(unsigned n=0;n<10;++n)r.values[n]=std::isfinite(values[n])&&std::abs(values[n])<=FLT_MAX?static_cast<float>(values[n]):NAN;
 const auto&c=e.sample.calibration;r.calibration={c.low_hz,c.high_hz,c.fault_hz,c.tolerance_hz,c.stale_ms,c.filter_ms};r.calibration_cycles=c.cycles;
 r.times={o.sample_us,o.window_start_us,o.last_edge_us,o.edges,o.fault_generation,o.acknowledged_generation,o.config_epoch};
 r.flags=(e.required?Required:0U)|(e.configuration_match?ConfigurationMatch:0U)|(e.value_qualified?ValueQualified:0U)|(e.raw_qualified?RawQualified:0U)|
  (e.control_ok?ControlOk:0U)|(o.valid&&(o.source==Source::TargetCapture||o.source==Source::Synthetic)?CaptureValid:0U)|(o.valid?SampleValueValid:0U)|
  (o.pending_fault?PendingFault:0U)|(o.frequency_clamped?FrequencyClamped:0U)|(o.temperature_clamped?TemperatureClamped:0U)|(e.input_confirmed?InputConfirmed:0U)|
  (e.corrections.enabled?CorrectionsEnabled:0U)|(e.corrections.valid?CorrectionsValid:0U)|(e.spark_bypassed?SparkBypassed:0U)|(e.spark_clamped?SparkClamped:0U)|(e.zero_factor?ZeroFactor:0U)|Available;
 r.revision=e.sample.tune_revision;r.source=static_cast<std::uint8_t>(o.source);r.reason=static_cast<std::uint8_t>(e.reason);r.capture_reason=static_cast<std::uint8_t>(o.capture_reason);r.last_fault=static_cast<std::uint8_t>(o.last_fault);r.correction_reason=static_cast<std::uint8_t>(e.corrections.reason);r.window_cycles=o.window_cycles;
 return r;
}
inline Evaluation expand(const Record&r){
 Evaluation e;e.available=r.has(Available);auto&o=e.sample.observation;
 o.source=static_cast<Source>(r.source);o.reason=e.reason=static_cast<Reason>(r.reason);o.capture_reason=static_cast<Reason>(r.capture_reason);o.last_fault=static_cast<Reason>(r.last_fault);o.window_cycles=r.window_cycles;
 o.sample_us=r.times[0];o.window_start_us=r.times[1];o.last_edge_us=r.times[2];o.edges=r.times[3];o.fault_generation=r.times[4];o.acknowledged_generation=r.times[5];o.config_epoch=r.times[6];
 o.frequency_hz=r.values[0];o.low_pulse_us=r.values[1];o.ethanol_pct=r.values[2];o.fuel_temp_c=r.values[3];o.unfiltered_ethanol_pct=r.values[4];o.unfiltered_fuel_temp_c=r.values[5];o.age_ms=r.values[6];
 e.corrections.fuel_factor=r.values[7]/100.;e.corrections.spark_add_deg=r.values[8];e.corrections.temperature_factor=r.values[9]/100.;e.corrections.reason=static_cast<Reason>(r.correction_reason);
 auto&c=e.sample.calibration;c.low_hz=r.calibration[0];c.high_hz=r.calibration[1];c.fault_hz=r.calibration[2];c.tolerance_hz=r.calibration[3];c.stale_ms=r.calibration[4];c.filter_ms=r.calibration[5];c.cycles=r.calibration_cycles;e.sample.tune_revision=r.revision;
 e.required=r.has(Required);e.configuration_match=r.has(ConfigurationMatch);e.value_qualified=r.has(ValueQualified);e.raw_qualified=r.has(RawQualified);e.control_ok=r.has(ControlOk);
 o.valid=r.has(SampleValueValid);o.pending_fault=r.has(PendingFault);o.frequency_clamped=r.has(FrequencyClamped);o.temperature_clamped=r.has(TemperatureClamped);e.input_confirmed=r.has(InputConfirmed);e.corrections.enabled=r.has(CorrectionsEnabled);e.corrections.valid=r.has(CorrectionsValid);e.spark_bypassed=r.has(SparkBypassed);e.spark_clamped=r.has(SparkClamped);e.zero_factor=r.has(ZeroFactor);
 return e;
}
}} // namespace ecu::flex
