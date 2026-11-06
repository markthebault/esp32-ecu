// Synthetic-device harness for the actual portable acquisition state machine.
// No GPIO/I2C SDK, target provenance or protection qualification is supplied.
#include "ecu/switch_acquisition.hpp"
#include <sstream>
#include <string>
#include <new>
namespace {
namespace si=ecu::switch_input;
struct Model {si::Acquisition acquisition;std::string encoded;};
const char* boolean(bool v){return v?"true":"false";}
}
extern "C" void* switch_model_create(){return new(std::nothrow)Model;}
extern "C" void switch_model_destroy(void*p){delete static_cast<Model*>(p);}
extern "C" const char* switch_model_next(void*p,unsigned mask,std::uint64_t now){
 auto&m=*static_cast<Model*>(p);
 try{
  if(mask>3)return "{\"error\":\"invalid mask\"}";
  const auto op=m.acquisition.next(static_cast<std::uint8_t>(mask),now);std::ostringstream s;
  s<<"{\"kind\":"<<unsigned(op.kind)<<",\"token\":\""<<op.token<<"\",\"issued_us\":\""<<op.issued_us<<"\",\"reg\":"<<unsigned(op.reg)<<",\"write_size\":"<<unsigned(op.write_size)<<",\"read_size\":"<<unsigned(op.read_size)<<",\"data\":[";
  for(unsigned i=0;i<op.write_size;++i){if(i)s<<',';s<<unsigned(op.data[i]);}s<<"]}";m.encoded=s.str();return m.encoded.c_str();
 }catch(...){return "{\"error\":\"native fixture encoding failed\"}";}
}
extern "C" int switch_model_complete(void*p,std::uint64_t token,unsigned result,const std::uint8_t*data,unsigned size,std::uint64_t started,std::uint64_t ended){
 if(result>5||size>12||(!data&&size))return -1;
 si::Reply reply;reply.result=static_cast<si::Result>(result);reply.size=static_cast<std::uint8_t>(size);
 for(unsigned i=0;i<size;++i)reply.data[i]=data[i];
 return static_cast<Model*>(p)->acquisition.complete(token,reply,started,ended)?1:0;
}
extern "C" int switch_model_ack(void*p,std::uint64_t id,int control_completed){
 return control_completed==1&&static_cast<Model*>(p)->acquisition.invalid_sample_consumed(id)?1:0;
}
extern "C" const char* switch_model_snapshot(void*p){
 auto&m=*static_cast<Model*>(p);
 try{
  const auto v=m.acquisition.snapshot();std::ostringstream s;
  s<<"{\"phase\":\""<<si::phase_name(v.phase)<<"\",\"fault\":\""<<si::fault_name(v.fault)<<"\",\"last_fault\":\""<<si::fault_name(v.last_fault)<<"\",\"requested_mask\":"<<unsigned(v.requested_mask)<<",\"gpio\":"<<unsigned(v.gpio)
   <<",\"raw_known\":"<<boolean(v.raw_known)<<",\"ready\":"<<boolean(v.ready)<<",\"fault_pending\":"<<boolean(v.fault_pending)<<",\"challenge_high\":"<<boolean(v.challenge_high);
  const std::pair<const char*,std::uint64_t> counters[]={
   {"fault_id",v.fault_id},{"attempts",v.attempts},{"reads",v.reads},{"failures",v.failures},{"consumed_faults",v.consumed_faults},{"configurations",v.configurations},
   {"observed_us",v.observed_us},{"read_completed_us",v.read_completed_us},{"last_duration_us",v.last_duration_us},{"max_duration_us",v.max_duration_us},{"last_fault_us",v.last_fault_us}};
  for(const auto&e:counters)s<<",\""<<e.first<<"\":\""<<e.second<<'"';
  s<<",\"samples\":[";
  for(unsigned i=0;i<2;++i){if(i)s<<',';const auto&x=v.samples[i];s<<"{\"valid\":"<<boolean(x.valid)<<",\"level\":"<<boolean(x.level)<<",\"observed_us\":\""<<x.observed_us<<"\",\"source_code\":"<<unsigned(x.source)<<'}';}
  s<<"]}";m.encoded=s.str();return m.encoded.c_str();
 }catch(...){return "{\"error\":\"native fixture encoding failed\"}";}
}
