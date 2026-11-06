#pragma once
#include "ecu/engine.hpp"
#include "ecu/flex_runtime.hpp"
#include "ecu/boost_runtime.hpp"
#include <cfloat>

namespace ecu::engine {
enum class DataSource : std::uint8_t {None=0,Target=1,Synthetic=2};
enum InputIndex : unsigned {DecodedRpm,MapKpa,TpsPct,CltC,IatC,Lambda,BatteryV,SensorV,input_count};
enum ProposalIndex : unsigned {ProposalRpm,VePct,TargetLambda,AdvanceDeg,PulseMs,DwellMs,DeadtimeMs,AirMg,Warmup,Afterstart,Accel,Ego,DutyPct,IdlePct,proposal_count};
enum DataFlag : std::uint16_t {
 Present=1,InputsFresh=2,StorageOk=4,CrankSynced=8,PhaseSynced=16,PhaseRequired=32,
 Submitted=64,DummyPolicy=128,PhaseContextMatch=256,ProposedActive=512,
 FuelCut=1024,SparkCut=2048,Pump=4096,Fan=8192,InputsQualified=16384,
 DisplayFresh=32768 // Calculated at transmission/read time, never at control evaluation.
};
// Task-only immutable observation. Proposals and the worker's earlier command
// observation are deliberately separate; neither is an electrical measurement.
struct RuntimeSample {
 std::uint64_t sequence=0,control_us=0,sampled_us=0,worker_sequence=0,worker_observed_us=0;
 std::uint32_t tune_revision=0,sensor_revision=0,phase_epoch=0,worker_epoch=0,
  worker_tune_revision=0,worker_sensor_revision=0,controller_faults=0,phase_losses=0,cam_rejected=0;
 std::array<float,input_count> inputs{};
 std::array<float,proposal_count> proposals{};
 std::array<float,6> idle_proposals{};std::uint64_t idle_pid_updates=0;
 std::uint32_t idle_flags=0;std::uint8_t idle_state=0,idle_reason=0,idle_algorithm=0;bool idle_available=false;
 transient::Output transient_enrichment;
 load::Observation load_model;
 secondary::Observation secondary_fuel,secondary_spark;
 flex::Record flex_fuel;
 boost::Record boost_control;
 std::array<float,8> cylinder_pulse_ms{},cylinder_advance_deg{},cylinder_fuel_pct{},cylinder_duty_pct{};
 float cam_error_deg=0;
 std::array<std::uint16_t,8> raw_adc{};
 std::uint16_t flags=0;
 std::uint32_t virtual_high_mask=0,physical_command_mask=0;
 std::uint8_t input_valid=0,state=0,strategy=0,phase_reason=0,timing_fault=0,last_timing_fault=0,
  board_flags=0,cylinder_count=0,worker_cylinder_count=0; // ADC/SAFE/interlock/overflow, bits0..3.
 DataSource source=DataSource::None;
 std::uint8_t cylinder_valid=0,cylinder_enabled=0,cylinder_capacity_mask=0,cylinder_spark_clamp_mask=0,cylinder_retard_floor_mask=0;
 bool has(DataFlag flag)const{return (flags&flag)!=0;}
};
static_assert(sizeof(RuntimeSample)<=816,"Runtime/log sample exceeds its explicit eight-cylinder diagnostic budget");
inline float data_float(double value){return finite(value)&&std::abs(value)<=FLT_MAX?static_cast<float>(value):NAN;}
inline void data_values(RuntimeSample& r,const Inputs& in,const Output& out,const Tune&t){
 const double inputs[]={in.rpm,in.map_kpa,in.tps_pct,in.clt_c,in.iat_c,in.lambda,in.battery_v,in.sensor_v};
 const double proposals[]={out.rpm,out.ve_pct,out.target_lambda,out.advance_deg,out.pulse_ms,out.dwell_ms,out.deadtime_ms,out.air_mg,out.warmup,out.afterstart,out.accel,out.ego,out.duty_pct,out.idle_pct};
 for(unsigned i=0;i<input_count;++i)r.inputs[i]=data_float(inputs[i]);
 for(unsigned i=0;i<proposal_count;++i)r.proposals[i]=data_float(proposals[i]);
 r.cylinder_count=t.cylinders>=1&&t.cylinders<=8?t.cylinders:0;
 r.cylinder_valid=out.cylinder_data&&r.cylinder_count?static_cast<std::uint8_t>((1U<<r.cylinder_count)-1):0;r.cylinder_enabled=out.cylinder_trims_enabled;
 r.cylinder_capacity_mask=out.cylinder_capacity_mask;r.cylinder_spark_clamp_mask=out.cylinder_spark_clamp_mask;r.cylinder_retard_floor_mask=out.cylinder_retard_floor_mask;
 for(unsigned i=0;i<8;++i){r.cylinder_pulse_ms[i]=data_float(out.cylinder_pulse_ms[i]);r.cylinder_advance_deg[i]=data_float(out.cylinder_advance_deg[i]);r.cylinder_fuel_pct[i]=data_float(out.cylinder_fuel_pct[i]);r.cylinder_duty_pct[i]=data_float(out.cylinder_duty_pct[i]);}
 const double idle_values[]={out.idle.target_rpm,out.idle.duty_pct,out.idle.feedforward_pct,out.idle.p_term,out.idle.i_term,out.idle.d_term};
 for(unsigned i=0;i<6;++i){r.idle_proposals[i]=data_float(idle_values[i]);}r.idle_available=true;r.idle_pid_updates=out.idle.pid_updates;r.idle_flags=out.idle.flags;r.idle_state=static_cast<std::uint8_t>(out.idle.state);r.idle_reason=static_cast<std::uint8_t>(out.idle.reason);
 r.controller_faults=out.faults;r.state=static_cast<std::uint8_t>(out.state);
 r.transient_enrichment=out.transient_enrichment;
 r.load_model=out.load_model;
 r.secondary_fuel=out.secondary_fuel;r.secondary_spark=out.secondary_spark;
 r.flex_fuel=flex::record(out.flex_fuel);
 r.boost_control=boost::record(out.boost_control,t.boost_control,!(out.faults&BadTune));
 r.flags=Present|(out.proposed_enabled()?ProposedActive:0)|(out.fuel_cut?FuelCut:0)|(out.spark_cut?SparkCut:0)|(out.pump?Pump:0)|(out.fan?Fan:0);
}
inline std::uint8_t data_input_mask(const Inputs& in,std::uint8_t qualified,double maximum_map=110){
 std::uint8_t mask=0;
 if(range(in.rpm,0,12000))mask|=1U<<DecodedRpm;
 const double value[]={in.rpm,in.map_kpa,in.tps_pct,in.clt_c,in.iat_c,in.lambda,in.battery_v,in.sensor_v};
 const double low[]={0,10,0,-40,-40,.65,7,4.75},high[]={12000,maximum_map,100,140,110,1.5,18,5.25};
 for(unsigned i=1;i<input_count;++i)if((qualified&(1U<<i))&&(i!=MapKpa||in.map_qualified)&&range(value[i],low[i],high[i]))mask|=1U<<i;
 return mask;
}
inline RuntimeSample synthetic_data(const Tune&t,const Inputs&in,const Output&out,std::uint64_t sequence,std::uint64_t now){
 RuntimeSample r;data_values(r,in,out,t);r.source=DataSource::Synthetic;r.sequence=sequence;r.control_us=now;r.sampled_us=in.sampled_us;r.tune_revision=t.revision;
 r.idle_algorithm=static_cast<std::uint8_t>(t.idle_control.algorithm);r.strategy=static_cast<std::uint8_t>(t.strategy);auto qualified=static_cast<std::uint8_t>(in.sensors_valid?255:0);if(!in.lambda_ready)qualified&=~(1U<<Lambda);
 r.input_valid=data_input_mask(in,qualified,maximum_map_kpa(t));r.flags|=StorageOk|(in.synced?CrankSynced:0)|(in.phase_synced?PhaseSynced:0)|
  (t.strategy==Strategy::Sequential?PhaseRequired:0)|(now>=in.sampled_us&&now-in.sampled_us<=20000?InputsFresh:0)|
  (in.sensors_valid&&out.secondary_fuel.valid&&out.secondary_spark.valid&&out.flex_fuel.control_ok&&(!(out.load_model.flags&load::AuxRequired)||(out.load_model.flags&load::AuxInRange))?InputsQualified:0);
 return r;
}
inline std::uint64_t data_age_us(const RuntimeSample&r,std::uint64_t point,std::uint64_t now){return r.has(Present)&&r.sequence&&now>=point?now-point:UINT64_MAX;}
inline std::uint32_t data_age_ms(std::uint64_t age){
 if(age==UINT64_MAX)return UINT32_MAX;
 constexpr auto max=std::uint64_t(UINT32_MAX-1)*1000;
 return age>=max?UINT32_MAX-1:static_cast<std::uint32_t>(age/1000+(age%1000!=0));
}
}
