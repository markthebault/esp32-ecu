#pragma once
#include "ecu/engine_log.hpp"
#include "ecu/engine_data_json.hpp"

namespace ecu::engine_log {
struct Request {bool start=false;unsigned period_ms=0,duration_s=0;std::uint32_t log_id=0;};
inline bool parse_request(const char*body,unsigned length,Request& request){
 if(!body||length>256||std::strlen(body)!=length||!web::safe_json(body,length))return false;
 auto*j=cJSON_ParseWithOpts(body,nullptr,true);char action[8]{};bool ok=j&&web::string(j,"action",action);
 if(ok&&!std::strcmp(action,"start")){
  request.start=true;ok=web::keys(j,"|action||period_ms||duration_s|")&&web::integer(j,"period_ms",request.period_ms)&&web::integer(j,"duration_s",request.duration_s)&&Recorder::valid_period(request.period_ms)&&request.duration_s>=1&&request.duration_s<=900;
 }else if(ok&&!std::strcmp(action,"stop")){
  unsigned id=0;request.start=false;ok=web::keys(j,"|action||log_id|")&&web::integer(j,"log_id",id)&&id;request.log_id=id;
 }else ok=false;
 cJSON_Delete(j);return ok;
}
inline bool query_number(const char*&p,std::uint32_t&value){
 if(*p<'0'||*p>'9')return false;
 std::uint64_t n=0;unsigned digits=0;while(*p>='0'&&*p<='9'){if(++digits>10)return false;n=n*10+(*p++-'0');if(n>UINT32_MAX)return false;}
 value=static_cast<std::uint32_t>(n);return true;
}
inline bool parse_query(const char*query,std::uint32_t&id,std::uint32_t&after){
 if(!query||std::strncmp(query,"log_id=",7))return false;
 auto*p=query+7;if(!query_number(p,id)||!id||std::strncmp(p,"&after=",7))return false;p+=7;
 return query_number(p,after)&&!*p;
}
inline cJSON* header_json(const Header&h){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 const bool ok=cJSON_AddNumberToObject(j,"schema_version",1)&&cJSON_AddNumberToObject(j,"log_id",h.log_id)&&
  cJSON_AddStringToObject(j,"state",state_name(h.state))&&cJSON_AddStringToObject(j,"data_source",engine::source_name(h.source))&&
  cJSON_AddNumberToObject(j,"source_code",static_cast<unsigned>(h.source))&&cJSON_AddNumberToObject(j,"period_ms",h.period_ms)&&
  cJSON_AddNumberToObject(j,"duration_s",h.duration_s)&&cJSON_AddNumberToObject(j,"capacity",Recorder::capacity)&&
  cJSON_AddNumberToObject(j,"total",h.total)&&cJSON_AddNumberToObject(j,"retained",h.retained)&&cJSON_AddNumberToObject(j,"first_sequence",h.first_sequence())&&
  cJSON_AddNumberToObject(j,"overwritten",h.overwritten)&&cJSON_AddNumberToObject(j,"missed_periods",h.missed_periods)&&
  cJSON_AddNumberToObject(j,"repeated_skipped",h.repeated)&&cJSON_AddNumberToObject(j,"invalid_skipped",h.invalid)&&
  engine::json_u64(j,"started_us",h.started_us)&&engine::json_u64(j,"deadline_us",h.deadline_us)&&engine::json_u64(j,"ended_us",h.ended_us);
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* row_json(const Row&r){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 auto*sample=engine::data_json(r.sample,r.recorded_us);
 if(!sample||!cJSON_AddNumberToObject(j,"log_id",r.log_id)||!cJSON_AddNumberToObject(j,"row_sequence",r.sequence)||!engine::json_u64(j,"recorded_us",r.recorded_us)||!cJSON_AddItemToObject(j,"sample",sample)){
  cJSON_Delete(sample);cJSON_Delete(j);return nullptr;
 }
 return j;
}
// Native tooling can build the whole page. The MCU streams at most one row's
// JSON tree at a time to avoid retaining16 large DOM subtrees on its heap.
inline cJSON* page_json(const Page&p){
 auto*j=header_json(p.header);if(!j)return nullptr;
 bool ok=cJSON_AddBoolToObject(j,"snapshot_superseded",p.superseded)&&cJSON_AddBoolToObject(j,"future_cursor",p.future_cursor)&&
  cJSON_AddBoolToObject(j,"invalid_row",p.invalid_row)&&cJSON_AddNumberToObject(j,"next_after",p.next_after)&&
  cJSON_AddNumberToObject(j,"gap_first",p.gap_first)&&cJSON_AddNumberToObject(j,"gap_last",p.gap_last);
 auto*rows=ok?cJSON_AddArrayToObject(j,"records"):nullptr;if(!rows)ok=false;
 for(unsigned i=0;ok&&i<p.count;++i){auto*row=row_json(p.rows[i]);if(!row||!cJSON_AddItemToArray(rows,row)){cJSON_Delete(row);ok=false;}}
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
