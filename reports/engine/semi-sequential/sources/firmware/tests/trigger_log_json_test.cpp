#include "ecu/trigger_log_json.hpp"
#include <cassert>
#include <cstdlib>
#include <iostream>
using namespace ecu::trigger_log;
namespace {
unsigned budget=UINT32_MAX,live=0;
void* allocate(std::size_t size){if(!budget)return nullptr;--budget;auto* p=std::malloc(size);if(p)++live;return p;}
void release(void* p){if(p){--live;std::free(p);}}
}
int main(){
 Capture capture;assert(capture.start(64,1000,1000));
 for(unsigned i=0;i<64;++i)capture.append({1000+i,1002+i,i,1,false,true,true});
 const auto header=capture.header();
 auto reader=[&](unsigned id,unsigned i,Record& row){return capture.read(id,i,row);};
 auto current=[&](unsigned id){return capture.header().frame_id==id;};
 auto* j=frame_json(header,reader,current,0,512);assert(j);
 assert(cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(j,"records"))==64);cJSON_Delete(j);
 // Rearm immediately after the last record read: final validation must discard
 // the old snapshot, even though every per-record read succeeded.
 j=frame_json(header,[&](unsigned id,unsigned i,Record& row){const bool ok=reader(id,i,row);if(i==63)assert(capture.start(16,1000,2000));return ok;},current,0,64);
 assert(j&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"snapshot_superseded")));
 assert(cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(j,"records"))==0);cJSON_Delete(j);
 // Fail every individual allocation position through one full page and its
 // encoded string. No partial or unmarked JSON may be returned, and all
 // successful allocations must be released on every failure path.
 Capture allocation;assert(allocation.start(64,1000,1000));
 for(unsigned i=0;i<64;++i)allocation.append({1000+i,1002+i,i,1,false,true,true});
 const auto allocation_header=allocation.header();
 cJSON_Hooks hooks{allocate,release};cJSON_InitHooks(&hooks);unsigned failures=0,successes=0;
 for(unsigned limit=0;limit<2000;++limit){
  budget=limit;auto* result=frame_json(allocation_header,[&](unsigned id,unsigned i,Record& row){return allocation.read(id,i,row);},[](unsigned){return true;},0,64);
  if(result){
   assert(cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(result,"records"))==64);
   char* encoded=cJSON_PrintUnformatted(result);if(encoded){++successes;cJSON_free(encoded);}else ++failures;cJSON_Delete(result);
  }else ++failures;
  assert(live==0);
 }
 cJSON_InitHooks(nullptr);assert(failures>100&&successes>0);
 Request request;
 for(const char* text:{"{}","{\"action\":\"start\",\"samples\":16,\"samples\":32,\"timeout_ms\":100}","{\"action\":\"start\",\"samples\":true,\"timeout_ms\":100}","{\"action\":\"stop\",\"frame_id\":0}"})assert(!parse_request(text,std::strlen(text),request));
 std::uint32_t id;unsigned offset;
 assert(parse_query("frame_id=4294967295&offset=512",id,offset)&&id==UINT32_MAX&&offset==512);
 for(const char* query:{"frame_id=0&offset=0","frame_id=4294967296&offset=0","frame_id=1&offset=513","frame_id=1&offset=0&x=1","offset=0&frame_id=1","frame_id=-1&offset=0"})assert(!parse_query(query,id,offset));
 std::cout<<"Paged trigger JSON, final-row rearm, strict command/query and 2000 allocation-failure positions passed\n";
}
