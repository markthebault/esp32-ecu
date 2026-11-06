// Host ABI for the same finite recorder and strict command parser as target.
#include "ecu/trigger_log_json.hpp"
extern "C" void* trigger_create(){return new ecu::trigger_log::Capture;}
extern "C" void trigger_destroy(void* p){delete static_cast<ecu::trigger_log::Capture*>(p);}
extern "C" int trigger_validate(const char* text,unsigned length){ecu::trigger_log::Request request;return ecu::trigger_log::parse_request(text,length,request);}
extern "C" int trigger_command(void* p,const char* text,unsigned length,std::uint64_t now){
 ecu::trigger_log::Request request;if(!ecu::trigger_log::parse_request(text,length,request))return 422;
 auto& capture=*static_cast<ecu::trigger_log::Capture*>(p);
 return (request.start?capture.start(request.samples,request.timeout_ms,now):capture.stop(request.frame_id,now))?200:409;
}
extern "C" void trigger_append(void* p,std::uint64_t captured,std::uint64_t callback,unsigned counter,unsigned epoch,unsigned flags){
 static_cast<ecu::trigger_log::Capture*>(p)->append({captured,callback,counter,epoch,bool(flags&1),bool(flags&2),bool(flags&4)});
}
extern "C" void trigger_expire(void* p,std::uint64_t now){static_cast<ecu::trigger_log::Capture*>(p)->expire(now);}
extern "C" const char* trigger_frame(void* p,unsigned expected,unsigned offset,unsigned count){
 auto& capture=*static_cast<ecu::trigger_log::Capture*>(p);const auto header=capture.header();
 auto* j=ecu::trigger_log::frame_json(header,[&](unsigned id,unsigned index,ecu::trigger_log::Record& record){return capture.read(id,index,record);},
  [&](unsigned id){return capture.header().frame_id==id&&(!expected||expected==id);},offset,count);
 return encode(j);
}
