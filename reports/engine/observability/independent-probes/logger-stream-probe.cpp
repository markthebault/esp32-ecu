#include "ecu/engine_log_json.hpp"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
using namespace ecu;
static std::size_t budget=SIZE_MAX,live=0,peak=0;
void* allocate(std::size_t n){if(!budget)return nullptr;--budget;auto* p=static_cast<std::size_t*>(std::malloc(n+sizeof(std::size_t)));if(!p)return nullptr;*p=n;live+=n;peak=std::max(peak,live);return p+1;}
void release(void* p){if(!p)return;auto* raw=static_cast<std::size_t*>(p)-1;live-=*raw;std::free(raw);}
struct Response {std::string body;bool complete=false,header_failure=false;};
Response stream(const engine_log::Page&p){
 Response out;auto*j=engine_log::header_json(p.header);bool ok=j&&cJSON_AddStringToObject(j,"boot_id","0123456789abcdef0123456789abcdef")&&cJSON_AddBoolToObject(j,"copied_page",true)&&cJSON_AddNumberToObject(j,"next_after",p.next_after)&&cJSON_AddNumberToObject(j,"gap_first",p.gap_first)&&cJSON_AddNumberToObject(j,"gap_last",p.gap_last);char* text=ok?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);
 if(!text){out.header_failure=true;return out;}out.body=text;cJSON_free(text);out.body.pop_back();out.body+=",\"records\":[";
 for(unsigned n=0;n<p.count;++n){j=engine_log::row_json(p.rows[n]);text=j?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);if(!text)return out;if(n)out.body+=',';out.body+=text;cJSON_free(text);}
 out.body+="]}";out.complete=true;return out;
}
int main(){
 engine_log::Recorder log;assert(log.start(20,1,engine::DataSource::Target,0));for(unsigned n=0;n<16;++n){engine::RuntimeSample s;s.source=engine::DataSource::Target;s.flags=engine::Present;s.sequence=n+1;s.control_us=s.sampled_us=n*20000;assert(log.append(s,n*20000));}engine_log::Page page;log.page(log.header().log_id,0,page);cJSON_Hooks hooks{allocate,release};cJSON_InitHooks(&hooks);unsigned rejected=0,truncated=0,complete=0;std::size_t max_server_peak=0;
 for(unsigned n=0;n<4500;++n){budget=n;peak=0;auto response=stream(page);assert(live==0);max_server_peak=std::max(max_server_peak,peak);budget=SIZE_MAX;auto*j=cJSON_Parse(response.body.c_str());if(response.complete){assert(j&&cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(j,"records"))==16);++complete;}else{assert(!j);if(response.header_failure)++rejected;else ++truncated;}cJSON_Delete(j);assert(live==0);}
 cJSON_InitHooks(nullptr);assert(rejected&&truncated&&complete);std::cout<<"{\"allocation_positions\":4500,\"header_failures_before_response\":"<<rejected<<",\"truncated_invalid_json_responses\":"<<truncated<<",\"complete_valid_pages\":"<<complete<<",\"peak_cjson_server_bytes_native\":"<<max_server_peak<<",\"all_partial_responses_rejected_by_json_parse\":true,\"no_cjson_leaks\":true}\n";
}
