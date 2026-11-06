#pragma once
#include "ecu/transient_json.hpp"
#include "ecu/load_json.hpp"
#include "ecu/secondary_json.hpp"
#include "ecu/flex_json.hpp"
#include "ecu/boost_runtime_json.hpp"
#include "ecu/engine_data.hpp"
#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include "ecu/json.hpp"
#include <cstdio>

namespace ecu::engine {
inline constexpr const char* input_names[]={"rpm","map_kpa","tps_pct","clt_c","iat_c","lambda","battery_v","sensor_v"};
inline constexpr const char* proposal_names[]={"rpm","ve_pct","target_lambda","advance_deg","pulse_ms","dwell_ms","deadtime_ms","air_mg","warmup","afterstart","accel","ego","duty_pct","idle_pct"};
inline constexpr const char* idle_names[]={"target_rpm","duty_pct","feedforward_pct","p_term","i_term","d_term"};
inline constexpr const char* input_units[]={"RPM","kPa","%","C","C","lambda","V","V"};
inline constexpr const char* proposal_units[]={"RPM","%","lambda","deg","ms","ms","ms","mg","ratio","ratio","ratio","ratio","%","%"};
inline const char* source_name(DataSource source){return source==DataSource::Target?"target_control_observation":source==DataSource::Synthetic?"synthetic_control_observation":"no_observation";}
inline bool json_u64(cJSON*j,const char*key,std::uint64_t value){char text[24];std::snprintf(text,sizeof(text),"%llu",static_cast<unsigned long long>(value));return cJSON_AddStringToObject(j,key,text)!=nullptr;}
inline bool json_value(cJSON*j,const char*key,double value){return finite(value)?cJSON_AddNumberToObject(j,key,value)!=nullptr:cJSON_AddNullToObject(j,key)!=nullptr;}
inline bool json_age(cJSON*j,const char*key,std::uint64_t age){return age==UINT64_MAX?cJSON_AddNullToObject(j,key)!=nullptr:cJSON_AddNumberToObject(j,key,data_age_ms(age))!=nullptr;}
inline cJSON* data_json(const RuntimeSample&r,std::uint64_t observed_us){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 const bool present=r.has(Present)&&r.sequence;
 const auto sample_age=data_age_us(r,r.sampled_us,observed_us),control_age=data_age_us(r,r.control_us,observed_us);
 const auto worker_age=(r.worker_sequence||r.worker_observed_us)&&observed_us>=r.worker_observed_us?observed_us-r.worker_observed_us:UINT64_MAX;
 bool ok=cJSON_AddNumberToObject(j,"schema_version",3)&&cJSON_AddBoolToObject(j,"available",present)&&
  cJSON_AddStringToObject(j,"data_source",source_name(r.source))&&cJSON_AddNumberToObject(j,"source_code",static_cast<unsigned>(r.source))&&
  json_u64(j,"sequence",r.sequence)&&json_u64(j,"control_us",r.control_us)&&json_u64(j,"sampled_us",r.sampled_us)&&
  json_age(j,"sample_age_ms",sample_age)&&json_age(j,"control_age_ms",control_age)&&
  cJSON_AddBoolToObject(j,"display_fresh",present&&sample_age<=1000000&&control_age<=1000000)&&
  cJSON_AddNumberToObject(j,"tune_revision",r.tune_revision)&&cJSON_AddNumberToObject(j,"sensor_revision",r.sensor_revision)&&
  cJSON_AddNumberToObject(j,"phase_epoch",r.phase_epoch)&&cJSON_AddNumberToObject(j,"flags",r.flags)&&
  cJSON_AddStringToObject(j,"phase_epoch_domain","external_configuration_context")&&
  cJSON_AddNumberToObject(j,"input_valid_mask",r.input_valid)&&cJSON_AddNumberToObject(j,"board_flags",r.board_flags)&&
  cJSON_AddNumberToObject(j,"controller_faults",r.controller_faults)&&cJSON_AddStringToObject(j,"state",state_name(static_cast<State>(r.state)))&&
  cJSON_AddNumberToObject(j,"state_code",r.state)&&cJSON_AddStringToObject(j,"strategy",strategy_name(static_cast<Strategy>(r.strategy)))&&
  cJSON_AddNumberToObject(j,"strategy_code",r.strategy)&&cJSON_AddNumberToObject(j,"phase_reason_code",r.phase_reason)&&
  cJSON_AddStringToObject(j,"phase_reason",PhaseDecoder::reason_name(static_cast<PhaseDecoder::Reason>(r.phase_reason)))&&
  cJSON_AddNumberToObject(j,"phase_losses",r.phase_losses)&&cJSON_AddNumberToObject(j,"cam_rejected",r.cam_rejected)&&json_value(j,"cam_error_deg",r.cam_error_deg);
 auto*inputs=ok?cJSON_AddObjectToObject(j,"inputs"):nullptr;
 if(!inputs)ok=false;
 for(unsigned i=0;ok&&i<input_count;++i)ok=json_value(inputs,input_names[i],present&&(r.input_valid&(1U<<i))?r.inputs[i]:NAN);
 auto*proposals=ok?cJSON_AddObjectToObject(j,"proposals"):nullptr;if(!proposals)ok=false;
 for(unsigned i=0;ok&&i<proposal_count;++i)ok=json_value(proposals,proposal_names[i],present?r.proposals[i]:NAN);
 if(ok)ok=cJSON_AddStringToObject(j,"scalar_proposal_basis","untrimmed_base_demand");
 auto*cyl=ok?cJSON_AddObjectToObject(j,"cylinders"):nullptr;if(!cyl)ok=false;
 if(ok)ok=cJSON_AddNumberToObject(cyl,"count",r.cylinder_count)&&cJSON_AddNumberToObject(cyl,"valid_mask",r.cylinder_valid)&&cJSON_AddBoolToObject(cyl,"enabled",r.cylinder_enabled)&&
  cJSON_AddNumberToObject(cyl,"capacity_mask",r.cylinder_capacity_mask)&&cJSON_AddNumberToObject(cyl,"spark_clamp_mask",r.cylinder_spark_clamp_mask)&&cJSON_AddNumberToObject(cyl,"retard_floor_mask",r.cylinder_retard_floor_mask);
 auto*rows=ok?cJSON_AddArrayToObject(cyl,"proposals"):nullptr;if(!rows)ok=false;
 for(unsigned i=0;ok&&i<8;++i){
  auto*row=cJSON_CreateObject();if(!row){ok=false;break;}
  const bool known=present&&(r.cylinder_valid&(1U<<i));
  ok=cJSON_AddNumberToObject(row,"cylinder",i+1)&&cJSON_AddBoolToObject(row,"active",i<r.cylinder_count)&&cJSON_AddNumberToObject(row,"injector_logical_channel",channels::injector(i))&&cJSON_AddNumberToObject(row,"coil_logical_channel",channels::coil(i))&&json_value(row,"pulse_ms",known?r.cylinder_pulse_ms[i]:NAN)&&json_value(row,"advance_deg",known?r.cylinder_advance_deg[i]:NAN)&&json_value(row,"fuel_pct",known?r.cylinder_fuel_pct[i]:NAN)&&json_value(row,"duty_pct",known?r.cylinder_duty_pct[i]:NAN)&&cJSON_AddItemToArray(rows,row);
  if(!ok)cJSON_Delete(row);
 }
 auto*idle=ok?cJSON_AddObjectToObject(j,"idle"):nullptr;if(!idle)ok=false;
 if(ok)ok=cJSON_AddBoolToObject(idle,"available",present&&r.idle_available)&&cJSON_AddStringToObject(idle,"state",idle::state_name(static_cast<idle::State>(r.idle_state)))&&cJSON_AddStringToObject(idle,"reason",idle::reason_name(static_cast<idle::Reason>(r.idle_reason)))&&cJSON_AddStringToObject(idle,"algorithm",idle::algorithm_name(static_cast<idle::Algorithm>(r.idle_algorithm)))&&cJSON_AddNumberToObject(idle,"state_code",r.idle_state)&&cJSON_AddNumberToObject(idle,"reason_code",r.idle_reason)&&cJSON_AddNumberToObject(idle,"algorithm_code",r.idle_algorithm)&&cJSON_AddNumberToObject(idle,"flags",r.idle_flags)&&json_u64(idle,"pid_updates",r.idle_pid_updates);
 for(unsigned i=0;ok&&i<6;++i)ok=json_value(idle,idle_names[i],present&&r.idle_available?r.idle_proposals[i]:NAN);
 auto*raw=ok?cJSON_AddArrayToObject(j,"raw_adc"):nullptr;if(!raw)ok=false;
 if(ok){auto*ae=transient::observation_json(r.transient_enrichment,present);if(!ae||!cJSON_AddItemToObject(j,"transient_enrichment",ae)){cJSON_Delete(ae);ok=false;}}
 if(ok){auto*model=load::observation_json(r.load_model,present);if(!model||!cJSON_AddItemToObject(j,"load_model",model)){cJSON_Delete(model);ok=false;}}
 if(ok){auto*second=secondary::observations_json(r.secondary_fuel,r.secondary_spark,present);if(!second||!cJSON_AddItemToObject(j,"secondary_tables",second)){cJSON_Delete(second);ok=false;}}
 if(ok){auto*flex=flex::evaluation_json(flex::expand(r.flex_fuel));if(!flex||!cJSON_AddItemToObject(j,"flex_fuel",flex)){cJSON_Delete(flex);ok=false;}else ok=json_age(flex,"read_age_ms",present&&flex::sample_timestamp_known(r.flex_fuel)&&observed_us>=r.flex_fuel.times[0]?observed_us-r.flex_fuel.times[0]:UINT64_MAX);}
 if(ok){auto*boost=boost::record_json(r.boost_control,present);if(!boost||!cJSON_AddItemToObject(j,"boost_control",boost)){cJSON_Delete(boost);ok=false;}}
 for(unsigned i=0;ok&&i<8;++i){auto*value=present&&(r.board_flags&1)?cJSON_CreateNumber(r.raw_adc[i]):cJSON_CreateNull();if(!value||!cJSON_AddItemToArray(raw,value)){cJSON_Delete(value);ok=false;}}
 auto*worker=ok?cJSON_AddObjectToObject(j,"worker_observation"):nullptr;if(!worker)ok=false;
 if(ok)ok=json_u64(worker,"command_sequence",r.worker_sequence)&&json_u64(worker,"observed_us",r.worker_observed_us)&&json_age(worker,"age_ms",worker_age)&&
  cJSON_AddNumberToObject(worker,"epoch",r.worker_epoch)&&cJSON_AddNumberToObject(worker,"tune_revision",r.worker_tune_revision)&&cJSON_AddNumberToObject(worker,"sensor_revision",r.worker_sensor_revision)&&
  cJSON_AddStringToObject(worker,"epoch_domain","executor_generation")&&
  cJSON_AddNumberToObject(worker,"timing_fault_code",r.timing_fault)&&cJSON_AddStringToObject(worker,"timing_fault",timing::cause_name(static_cast<timing::Cause>(r.timing_fault)))&&
  cJSON_AddNumberToObject(worker,"last_timing_fault_code",r.last_timing_fault)&&cJSON_AddNumberToObject(worker,"cylinder_count",r.worker_cylinder_count)&&cJSON_AddNumberToObject(worker,"virtual_high_mask",r.virtual_high_mask)&&cJSON_AddNumberToObject(worker,"physical_command_mask",r.physical_command_mask)&&
  cJSON_AddStringToObject(worker,"meaning","Earlier worker-current command and software command masks; not proof this proposal executed or an electrical measurement");
 auto*board=ok?cJSON_AddObjectToObject(j,"board_capacity"):nullptr;if(!board)ok=false;
 if(ok)ok=cJSON_AddNumberToObject(board,"injector_commands",channels::board_injector_commands)&&cJSON_AddNumberToObject(board,"coil_commands",channels::board_coil_commands)&&cJSON_AddBoolToObject(board,"additional_outputs_allocated",false);
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
