#pragma once
#include "ecu/flex_capture_owner.hpp"
#include "ecu/flex_json.hpp"

namespace ecu::flex {
// Rendering a copied publication never observes Capture or offers/ACKs faults.
inline cJSON* capture_json(const CapturePortSnapshot&s,std::uint64_t now,bool built,bool available,
                           const char*error,unsigned uncertainty){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 auto u64=[](cJSON*object,const char*key,std::uint64_t value){
  char text[24];std::snprintf(text,sizeof(text),"%llu",static_cast<unsigned long long>(value));
  return cJSON_AddStringToObject(object,key,text)!=nullptr;
 };
 const auto&w=s.work;const auto&v=s.view;const auto&i=w.ingress;const auto&c=i.counters;
 bool ok=cJSON_AddNumberToObject(j,"schema_version",1)&&
  cJSON_AddStringToObject(j,"data_source",built?"target_mcpwm_flex":"target_capture_not_built")&&
  cJSON_AddBoolToObject(j,"built",built)&&cJSON_AddBoolToObject(j,"available",available)&&
  cJSON_AddStringToObject(j,"driver_error",error)&&cJSON_AddNumberToObject(j,"gpio",38)&&
  cJSON_AddNumberToObject(j,"capture_group",0)&&cJSON_AddNumberToObject(j,"capture_channel",2)&&
  cJSON_AddNumberToObject(j,"clock_uncertainty_us",uncertainty)&&cJSON_AddBoolToObject(j,"both_edges",true)&&
  cJSON_AddBoolToObject(j,"has_hardware_fifo",false)&&u64(j,"query_us",now)&&
  cJSON_AddBoolToObject(j,"required",w.request.required)&&cJSON_AddBoolToObject(j,"confirmed",w.request.confirmed)&&
  cJSON_AddBoolToObject(j,"binding",w.binding)&&cJSON_AddBoolToObject(j,"active",w.active)&&
  cJSON_AddBoolToObject(j,"armed",i.armed)&&cJSON_AddBoolToObject(j,"pending_fault",i.pending_fault)&&
  cJSON_AddBoolToObject(j,"terminal",i.terminal)&&cJSON_AddBoolToObject(j,"retry_holdoff",i.retry_holdoff)&&
  cJSON_AddStringToObject(j,"last_fault",ingress_fault_name(i.last_fault))&&
  cJSON_AddNumberToObject(j,"queued",i.queued)&&cJSON_AddNumberToObject(j,"queue_capacity",Ingress::capacity)&&
  cJSON_AddNumberToObject(j,"external_epoch",w.external_epoch)&&
  cJSON_AddNumberToObject(j,"requested_tune_revision",w.request.tune_revision)&&
  cJSON_AddNumberToObject(j,"requested_sensor_revision",w.request.sensor_revision)&&
  u64(j,"context",i.context)&&u64(j,"fault_generation",i.fault_generation)&&
  u64(j,"acknowledged_generation",i.acknowledged_generation)&&u64(j,"armed_after_us",i.armed_after_us)&&
  u64(j,"last_observed_us",i.last_observed_us)&&u64(j,"last_suppression_us",i.last_suppression_us)&&
  u64(j,"rejected_publications",s.rejected_publications)&&u64(j,"rejected_acks",s.rejected_acks)&&u64(j,"acks",s.acks)&&
  u64(j,"minimum_command_publication",s.minimum_command_publication);
 auto*requested=ok?cJSON_AddObjectToObject(j,"requested_calibration"):nullptr;if(!requested)ok=false;
 for(auto field:capture_fields)ok=ok&&cJSON_AddNumberToObject(requested,field.name,w.request.calibration.*field.member);
 ok=ok&&cJSON_AddNumberToObject(requested,"cycles",w.request.calibration.cycles);
 auto*counts=ok?cJSON_AddObjectToObject(j,"counters"):nullptr;if(!counts)ok=false;
#define FC(name) ok=ok&&u64(counts,#name,c.name)
 FC(callbacks);FC(accepted);FC(dequeued);FC(discarded);FC(ignored_context);FC(ignored_inactive);FC(ignored_prearm);FC(suppressions);FC(rejected_ack);
#undef FC
 auto*faults=ok?cJSON_AddObjectToObject(counts,"faults"):nullptr;if(!faults)ok=false;
 for(unsigned n=0;n<c.faults.size();++n)ok=ok&&u64(faults,ingress_fault_name(static_cast<IngressFault>(n)),c.faults[n]);
 auto*p=ok?cJSON_AddObjectToObject(j,"publication"):nullptr;if(!p)ok=false;
 ok=ok&&cJSON_AddBoolToObject(p,"present",v.present)&&cJSON_AddBoolToObject(p,"current",v.current)&&
  cJSON_AddBoolToObject(p,"qualified",v.ticket.qualified&&v.current)&&cJSON_AddBoolToObject(p,"ack_eligible",v.ack_eligible)&&
  cJSON_AddBoolToObject(p,"sample_valid",v.sample.observation.valid)&&cJSON_AddBoolToObject(p,"pending_fault",v.sample.observation.pending_fault)&&
  cJSON_AddStringToObject(p,"reason",reason_name(v.sample.observation.reason))&&
  cJSON_AddStringToObject(p,"capture_reason",reason_name(v.sample.observation.capture_reason))&&
  cJSON_AddStringToObject(p,"source",source_name(v.sample.observation.source))&&
  cJSON_AddNumberToObject(p,"producer_tune_revision",v.sample.tune_revision)&&
  u64(p,"sequence",v.ticket.publication)&&u64(p,"context",v.ticket.version.context)&&
  u64(p,"ingress_generation",v.ticket.version.generation)&&u64(p,"capture_generation",v.ticket.capture_generation)&&
  u64(p,"acknowledged_generation",v.sample.observation.acknowledged_generation)&&u64(p,"armed_after_us",v.ticket.version.armed_after_us)&&
  u64(p,"published_us",v.published_us)&&u64(p,"sample_us",v.ticket.sample_us)&&
  u64(p,"valid_until_us",v.ticket.valid_until_us);
 auto*cal=ok?cJSON_AddObjectToObject(p,"producer_calibration"):nullptr;if(!cal)ok=false;
 for(auto field:capture_fields)ok=ok&&cJSON_AddNumberToObject(cal,field.name,v.sample.calibration.*field.member);
 ok=ok&&cJSON_AddNumberToObject(cal,"cycles",v.sample.calibration.cycles)&&
  cJSON_AddStringToObject(j,"qualification","Development capture path; no protected circuit or physical timing qualification. One hardware latch per channel can overwrite edges. Engine outputs remain inhibited.");
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
} // namespace ecu::flex
