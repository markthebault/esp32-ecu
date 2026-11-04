#pragma once
#include "ecu/trigger_log.hpp"
#include "ecu/json.hpp"
#include <algorithm>

namespace ecu::trigger_log {
struct Request {bool start=false;unsigned samples=0,timeout_ms=0,frame_id=0;};
inline bool parse_request(const char* text,std::size_t length,Request& request){
 if(length>256||!web::safe_json(text,length))return false;
 auto* j=cJSON_ParseWithOpts(text,nullptr,true);char action[16]{};
 bool valid=web::string(j,"action",action);
 if(valid&&!std::strcmp(action,"start")){
  request.start=true;valid=web::keys(j,"|action||samples||timeout_ms|")&&web::integer(j,"samples",request.samples)&&
   request.samples>=16&&request.samples<=Capture::capacity&&web::integer(j,"timeout_ms",request.timeout_ms)&&request.timeout_ms>=50&&request.timeout_ms<=5000;
 }else if(valid&&!std::strcmp(action,"stop")){
  request.start=false;valid=web::keys(j,"|action||frame_id|")&&web::integer(j,"frame_id",request.frame_id)&&request.frame_id>0;
 }else valid=false;
 cJSON_Delete(j);return valid;
}
inline bool parse_query(const char* text,std::uint32_t& frame_id,unsigned& offset){
 if(!text||std::strncmp(text,"frame_id=",9))return false;
 const char* cursor=text+9;
 auto integer=[&](unsigned digits,std::uint64_t maximum,std::uint64_t& value){
  value=0;unsigned count=0;
  while(*cursor>='0'&&*cursor<='9'){
   if(++count>digits)return false;
   value=value*10+static_cast<unsigned>(*cursor++-'0');if(value>maximum)return false;
  }
  return count>0;
 };
 std::uint64_t id=0,index=0;
 if(!integer(10,UINT32_MAX,id)||!id||std::strncmp(cursor,"&offset=",8))return false;
 cursor+=8;
 if(!integer(3,Capture::capacity,index)||*cursor)return false;
 frame_id=static_cast<std::uint32_t>(id);offset=static_cast<unsigned>(index);return true;
}
// read() takes only a short per-record lock. The final identity check closes
// a rearm race after the last copied row. Record pages bound JSON memory.
constexpr unsigned page_capacity=64;
template<class Reader,class Current> cJSON* frame_json(const Header& header,Reader read,Current current,unsigned offset=0,unsigned limit=0){
 auto* j=cJSON_CreateObject();if(!j)return nullptr;bool ok=true;
 auto number=[&](cJSON* o,const char* key,double value){if(ok)ok=cJSON_AddNumberToObject(o,key,value)!=nullptr;};
 auto text=[&](cJSON* o,const char* key,const char* value){if(ok)ok=cJSON_AddStringToObject(o,key,value)!=nullptr;};
 auto boolean=[&](cJSON* o,const char* key,bool value){if(ok)ok=cJSON_AddBoolToObject(o,key,value)!=nullptr;};
 number(j,"schema_version",1);text(j,"state",name(header.state));number(j,"frame_id",header.frame_id);
 number(j,"capacity",Capture::capacity);number(j,"requested",header.requested);number(j,"count",header.count);
 number(j,"started_us",header.started_us);number(j,"deadline_us",header.deadline_us);number(j,"ended_us",header.ended_us);
 number(j,"prearm_ignored",header.prearm_ignored);number(j,"invalid_timebase_ignored",header.invalid_timebase_ignored);
 number(j,"offset",offset);number(j,"page_capacity",page_capacity);
 auto* rows=ok?cJSON_AddArrayToObject(j,"records"):nullptr;if(!rows)ok=false;
 const auto count=offset<header.count?std::min(std::min(limit,page_capacity),header.count-offset):0;
 bool superseded=false;
 for(unsigned n=0;ok&&n<count;++n){
  Record record;if(!read(header.frame_id,offset+n,record)){superseded=true;break;}
  auto* row=cJSON_CreateObject();if(!row){ok=false;break;}
  number(row,"sequence",offset+n+1);text(row,"channel",record.cam?"cam":"crank");boolean(row,"high",record.high);
  boolean(row,"timebase_valid",record.timebase_valid);number(row,"captured_us",record.captured_us);
  number(row,"callback_us",record.callback_us);number(row,"raw_counter",record.raw_counter);
  number(row,"configuration_epoch",record.configuration_epoch);
  if(!ok||!cJSON_AddItemToArray(rows,row)){cJSON_Delete(row);ok=false;break;}
 }
 if(!current(header.frame_id))superseded=true;
 if(superseded&&ok){cJSON_DeleteItemFromObjectCaseSensitive(j,"records");rows=cJSON_AddArrayToObject(j,"records");if(!rows)ok=false;}
 boolean(j,"snapshot_superseded",superseded);number(j,"returned",superseded?0:count);
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
