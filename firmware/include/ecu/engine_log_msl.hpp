#pragma once
#include "ecu/engine_log.hpp"
#include "ecu/engine_data_json.hpp"
#include <cstdarg>

namespace ecu::engine_log {
inline constexpr unsigned text_capacity=6144; //188-column header and bounded numeric row.
class Text {
 char* text_;unsigned size_,used_=0;bool ok_=true;
public:
 Text(char*text,unsigned size):text_(text),size_(size){if(size)text[0]=0;}
 void add(const char*format,...){
  if(!ok_)return;
  va_list args;va_start(args,format);const int n=std::vsnprintf(text_+used_,size_-used_,format,args);va_end(args);
  if(n<0||static_cast<unsigned>(n)>=size_-used_){ok_=false;return;}used_+=static_cast<unsigned>(n);
 }
 bool ok()const{return ok_;}unsigned size()const{return used_;}
};
inline constexpr const char* input_msl[]={"RPM","MAP","TPS","CLT","IAT","Lambda","Battery","Sensor5V"};
inline constexpr const char* proposal_msl[]={"ProposedRPM","VE","LambdaTarget","ProposedAdvance","ProposedPW","ProposedDwell","DeadTime","AirMass","Warmup","Afterstart","Accel","EGO","Duty","IdleProposal"};
inline bool msl_header(const Header&h,char*buffer,unsigned size,const char*boot="not_recorded"){
 Text t(buffer,size);t.add("\"ESP32ECU ENGINE LOG 006\"\n\"%s / boot %s / log %u / period_ms=%u duration_s=%u / retained rows %u..%u of %u / overwritten=%u missed_periods=%u repeated=%u invalid=%u / PhaseEpoch=configuration context; WorkerEpoch=executor generation / proposals and masks; Load*=source-tagged fuel model; Sec*=secondary values/units/selection/raw-input diagnostics; check availability/source/validity; no electrical execution measurement\"\n",
  h.source==engine::DataSource::Target?"TARGET CONTROL/SENSOR OBSERVATIONS":"SYNTHETIC ENGINE REPLAY",boot,h.log_id,h.period_ms,h.duration_s,h.retained?h.first_sequence():0,h.total,h.total,h.overwritten,h.missed_periods,h.repeated,h.invalid);
 t.add("Time\tRowSequence\tSnapshotSequence\tControlAge\tSensorAge\tSource\tTuneRevision\tSensorRevision\tPhaseEpoch\tFlags\tFaults\tState\tStrategy\tPhaseReason\tPhaseLosses\tCamRejected\tCamError\tWorkerCommand\tWorkerAge\tWorkerEpoch\tWorkerTuneRevision\tWorkerSensorRevision\tTimingFault\tLastTimingFault\tVirtualMask\tPhysicalCommandMask\tBoardFlags");
 t.add("\tInputValidMask");for(auto name:input_msl)t.add("\t%s",name);
 for(auto name:proposal_msl)t.add("\t%s",name);
 for(unsigned i=0;i<8;++i)t.add("\tADC%u",i);
 t.add("\tCylinderValidMask\tCylinderTrimsEnabled\tCylinderCapacityMask\tCylinderSparkClampMask\tCylinderRetardFloorMask");
 for(unsigned i=1;i<=4;++i)t.add("\tC%uPW\tC%uAdvance\tC%uFuelTrim\tC%uDuty",i,i,i,i);
 t.add("\tIdleTarget\tIdleDuty\tIdleFeedforward\tIdleP\tIdleI\tIdleD\tIdleFlags\tIdleState\tIdleReason\tIdleAlgorithm\tIdlePidUpdates\tIdleAvailable");
 t.add("\tAeTpsDot\tAeMapDot\tAeWindowMs\tAeTriggerDot\tAeCorrectionPct\tAeUnclampedPct\tAeRemainingAtSampleMs\tAeAddedFuelMg\tAeFlags\tAeMode\tAeApply\tAePhase\tAeReason\tAeAvailable");
 t.add("\tLoadFuel\tLoadSpark\tLoadLambda\tLoadTrim\tLoadPressureFactor\tLoadBaro\tLoadEmap\tLoadAux\tLoadAfrFactor\tLoadFlags\tLoadFuelSource\tLoadSparkSource\tLoadLambdaSource\tLoadTrimSource\tLoadPressure\tLoadAuxRole\tLoadBaroSource\tLoadAfr\tLoadReason\tLoadAfrState\tLoadAvailable");
 for(const char*kind:{"Fuel","Spark"}){
  for(auto name:secondary::value_labels)t.add("\tSec%s%s",kind,name);
  t.add("\tSec%sFlags",kind);
  for(auto name:secondary::code_labels)t.add("\tSec%s%s",kind,name);
  t.add("\tSec%sObservedUs",kind);
  for(auto name:secondary::boolean_labels)t.add("\tSec%s%s",kind,name);
 }
 t.add("\ns\tcount\tcount\tms\tms\tcode\tcount\tcount\tcount\tbitfield\tbitfield\tcode\tcode\tcode\tcount\tcount\tdeg\tcount\tms\tcount\tcount\tcount\tcode\tcode\tbitfield\tbitfield\tbitfield");
 t.add("\tbitfield");for(auto unit:engine::input_units)t.add("\t%s",unit);
 for(auto unit:engine::proposal_units)t.add("\t%s",unit);
 for(unsigned i=0;i<8;++i)t.add("\tcount");
 t.add("\tbitfield\tbool\tbitfield\tbitfield\tbitfield");
 for(unsigned i=0;i<4;++i)t.add("\tms\tdeg\t%%\t%%");
 t.add("\tRPM\t%%\t%%\t%%\t%%\t%%\tbitfield\tcode\tcode\tcode\tcount\tbool");
 t.add("\t%%/s\tkPa/s\tms\tsource_units/s\t%%\t%%\tms\tmg\tbitfield\tcode\tcode\tcode\tcode\tbool");
 t.add("\tsource_units\tsource_units\tsource_units\tsource_units\tratio\tkPa\tkPa\tkPa\tratio\tbitfield\tcode\tcode\tcode\tcode\tcode\tcode\tcode\tcode\tcode\tcode\tbool");
 for(unsigned kind=0;kind<2;++kind){const char*unit=kind==0?"%":"deg";
  t.add("\t%s\t%s\tcell_units\t%s\tsource_units\tcondition_units\tms\tcondition_units\tms\tbitfield",unit,unit,unit);
  for(unsigned n=0;n<8;++n)t.add("\tcode");
  t.add("\tus");for(unsigned n=0;n<12;++n)t.add("\tbool");
 }
 t.add("\n");return t.ok();
}
inline bool msl_row(const Header&h,const Row&row,char*buffer,unsigned size){
 const auto&r=row.sample;Text t(buffer,size);
 const double elapsed=row.recorded_us>=h.started_us?double(row.recorded_us-h.started_us)/1e6:-double(h.started_us-row.recorded_us)/1e6;
 t.add("%.6f\t%u\t%llu",elapsed,row.sequence,static_cast<unsigned long long>(r.sequence));
 auto age=[&](std::uint64_t value){if(value==UINT64_MAX)t.add("\tNaN");else t.add("\t%u",engine::data_age_ms(value));};
 age(engine::data_age_us(r,r.control_us,row.recorded_us));age(engine::data_age_us(r,r.sampled_us,row.recorded_us));
 t.add("\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u",static_cast<unsigned>(r.source),r.tune_revision,r.sensor_revision,r.phase_epoch,r.flags,r.controller_faults,r.state,r.strategy,r.phase_reason,r.phase_losses,r.cam_rejected);
 if(engine::finite(r.cam_error_deg))t.add("\t%.9g",double(r.cam_error_deg));else t.add("\tNaN");
 t.add("\t%llu",static_cast<unsigned long long>(r.worker_sequence));age((r.worker_sequence||r.worker_observed_us)&&row.recorded_us>=r.worker_observed_us?row.recorded_us-r.worker_observed_us:UINT64_MAX);
 t.add("\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u",r.worker_epoch,r.worker_tune_revision,r.worker_sensor_revision,r.timing_fault,r.last_timing_fault,r.virtual_high_mask,r.physical_command_mask,r.board_flags);
 t.add("\t%u",r.input_valid);for(unsigned i=0;i<engine::input_count;++i){if((r.input_valid&(1U<<i))&&engine::finite(r.inputs[i]))t.add("\t%.9g",double(r.inputs[i]));else t.add("\tNaN");}
 for(auto value:r.proposals){if(engine::finite(value))t.add("\t%.9g",double(value));else t.add("\tNaN");}
 for(auto value:r.raw_adc){if(r.board_flags&1)t.add("\t%u",value);else t.add("\tNaN");}
 t.add("\t%u\t%u\t%u\t%u\t%u",r.cylinder_valid,r.cylinder_enabled,r.cylinder_capacity_mask,r.cylinder_spark_clamp_mask,r.cylinder_retard_floor_mask);
 for(unsigned i=0;i<4;++i)for(auto value:{r.cylinder_pulse_ms[i],r.cylinder_advance_deg[i],r.cylinder_fuel_pct[i],r.cylinder_duty_pct[i]}){if((r.cylinder_valid&(1U<<i))&&engine::finite(value))t.add("\t%.9g",double(value));else t.add("\tNaN");}
 for(auto value:r.idle_proposals){if(engine::finite(value)&&r.has(engine::Present)&&r.idle_available)t.add("\t%.9g",double(value));else t.add("\tNaN");}
 t.add("\t%u\t%u\t%u\t%u\t%llu",r.idle_flags,r.idle_state,r.idle_reason,r.idle_algorithm,static_cast<unsigned long long>(r.idle_pid_updates));
 t.add("\t%u",unsigned(r.idle_available&&r.has(engine::Present)));
 const auto&ae=r.transient_enrichment;const bool known=ae.available&&r.has(engine::Present);
 for(auto value:ae.values){if(known&&engine::finite(value))t.add("\t%.9g",double(value));else t.add("\tNaN");}
 t.add("\t%u\t%u\t%u\t%u\t%u\t%u",ae.flags,static_cast<unsigned>(ae.mode),static_cast<unsigned>(ae.apply),static_cast<unsigned>(ae.phase),static_cast<unsigned>(ae.reason),unsigned(known));
 const auto&model=r.load_model;const bool model_known=model.available&&r.has(engine::Present);
 for(auto value:model.values){if(model_known&&engine::finite(value))t.add("\t%.9g",double(value));else t.add("\tNaN");}
 t.add("\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u",model.flags,static_cast<unsigned>(model.fuel),static_cast<unsigned>(model.spark),static_cast<unsigned>(model.lambda),static_cast<unsigned>(model.trim),static_cast<unsigned>(model.pressure),static_cast<unsigned>(model.aux_role),static_cast<unsigned>(model.baro_source),static_cast<unsigned>(model.afr),static_cast<unsigned>(model.reason),model_known&&engine::finite(model.values[load::AfrFactor])?static_cast<unsigned>(model.afr_state()):255,unsigned(model_known));
 for(const secondary::Observation*raw:{&r.secondary_fuel,&r.secondary_spark}){const secondary::Observation empty;const auto&o=r.has(engine::Present)&&raw->available?*raw:empty;
  for(auto member:secondary::value_members){const float value=o.*member;if(o.available&&engine::finite(value))t.add("\t%.9g",double(value));else t.add("\tNaN");}
  t.add("\t%u",secondary::flags(o));
  for(unsigned code:{static_cast<unsigned>(o.mode),static_cast<unsigned>(o.cells),static_cast<unsigned>(o.source),static_cast<unsigned>(o.reason),static_cast<unsigned>(o.input_source),static_cast<unsigned>(o.condition),static_cast<unsigned>(o.axis),unsigned(o.input_channel)})t.add("\t%u",code);
  if(o.available&&o.mode==secondary::Mode::Input&&o.input_source!=secondary::InputSource::Unavailable)t.add("\t%llu",static_cast<unsigned long long>(o.input_observed_us));else t.add("\tNaN");
  for(auto member:secondary::boolean_members)t.add("\t%u",unsigned(o.*member));
 }
 t.add("\n");return t.ok();
}
}
