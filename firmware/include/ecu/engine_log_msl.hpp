#pragma once
#include "ecu/engine_log.hpp"
#include "ecu/engine_data_json.hpp"
#include <cstdarg>

namespace ecu::engine_log {
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
 Text t(buffer,size);t.add("\"ESP32ECU ENGINE LOG 002\"\n\"%s / boot %s / log %u / period_ms=%u duration_s=%u / retained rows %u..%u of %u / overwritten=%u missed_periods=%u repeated=%u invalid=%u / PhaseEpoch=configuration context; WorkerEpoch=executor generation / base scalars plus physical-cylinder proposals and software masks; no electrical execution measurement\"\n",
  h.source==engine::DataSource::Target?"TARGET CONTROL/SENSOR OBSERVATIONS":"SYNTHETIC ENGINE REPLAY",boot,h.log_id,h.period_ms,h.duration_s,h.retained?h.first_sequence():0,h.total,h.total,h.overwritten,h.missed_periods,h.repeated,h.invalid);
 t.add("Time\tRowSequence\tSnapshotSequence\tControlAge\tSensorAge\tSource\tTuneRevision\tSensorRevision\tPhaseEpoch\tFlags\tFaults\tState\tStrategy\tPhaseReason\tPhaseLosses\tCamRejected\tCamError\tWorkerCommand\tWorkerAge\tWorkerEpoch\tWorkerTuneRevision\tWorkerSensorRevision\tTimingFault\tLastTimingFault\tVirtualMask\tPhysicalCommandMask\tBoardFlags");
 t.add("\tInputValidMask");for(auto name:input_msl)t.add("\t%s",name);
 for(auto name:proposal_msl)t.add("\t%s",name);
 for(unsigned i=0;i<8;++i)t.add("\tADC%u",i);
 t.add("\tCylinderValidMask\tCylinderTrimsEnabled\tCylinderCapacityMask\tCylinderSparkClampMask\tCylinderRetardFloorMask");
 for(unsigned i=1;i<=4;++i)t.add("\tC%uPW\tC%uAdvance\tC%uFuelTrim\tC%uDuty",i,i,i,i);
 t.add("\ns\tcount\tcount\tms\tms\tcode\tcount\tcount\tcount\tbitfield\tbitfield\tcode\tcode\tcode\tcount\tcount\tdeg\tcount\tms\tcount\tcount\tcount\tcode\tcode\tbitfield\tbitfield\tbitfield");
 t.add("\tbitfield");for(auto unit:engine::input_units)t.add("\t%s",unit);
 for(auto unit:engine::proposal_units)t.add("\t%s",unit);
 for(unsigned i=0;i<8;++i)t.add("\tcount");
 t.add("\tbitfield\tbool\tbitfield\tbitfield\tbitfield");
 for(unsigned i=0;i<4;++i)t.add("\tms\tdeg\t%%\t%%");
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
 t.add("\n");return t.ok();
}
}
