#include "ecu/engine_json.hpp"
#include "ecu/tuning_document.hpp"
#include "ecu/engine_log_msl.hpp"
#include <cassert>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <unordered_set>
static int budget=-1;
static std::unordered_set<void*> owned;
void* allocation(std::size_t size){if(budget==0)return nullptr;if(budget>0)--budget;auto p=std::malloc(size);if(p)owned.insert(p);return p;}
void release(void* p){if(!p)return;assert(owned.erase(p)==1);std::free(p);}
int main(int argc,char**argv){
 assert(argc==2);std::ifstream file(argv[1]);std::string original((std::istreambuf_iterator<char>(file)),{});assert(!original.empty());
 cJSON_Hooks hooks{allocation,release};cJSON_InitHooks(&hooks);unsigned failures=0,successes=0;
 for(unsigned n=0;n<4000;++n){budget=n;ecu::engine::Tune tune;std::string encoded;bool ok=ecu::engine::canonical_tune(original.c_str(),tune,encoded);budget=-1;if(ok){assert(!tune.idle_enabled);assert(encoded.find("\"schema_version\":4")!=std::string::npos);successes++;}else failures++;assert(owned.empty());}
 assert(failures&&successes);
 auto* tree=cJSON_Parse(original.c_str());assert(tree);assert(ecu::engine::upgrade_tune_document(tree));auto* idle=cJSON_GetObjectItemCaseSensitive(tree,"idle_control");assert(idle);assert(cJSON_SetValuestring(cJSON_GetObjectItemCaseSensitive(idle,"algorithm"),"on_off"));
 ecu::engine::Tune candidate;candidate.idle_control.algorithm=ecu::idle::Algorithm::ClosedLoop;ecu::tuning::Document document(tree);budget=0;assert(!ecu::tuning::update_document(document,candidate));budget=-1;cJSON_Delete(tree);assert(owned.empty());
 cJSON_InitHooks(nullptr);
 ecu::engine_log::Header header;header.source=ecu::engine::DataSource::Synthetic;header.total=header.log_id=header.overwritten=header.missed_periods=header.repeated=header.invalid=UINT32_MAX;header.period_ms=1000;header.duration_s=900;header.retained=256;
 char text[2048];assert(ecu::engine_log::msl_header(header,text,sizeof(text),"ffffffffffffffffffffffffffffffff"));auto header_size=std::strlen(text);
 ecu::engine_log::Row row;row.sample.sequence=row.sample.worker_sequence=row.sample.idle_pid_updates=UINT64_MAX;row.sample.idle_available=true;row.sample.flags=ecu::engine::Present;row.sample.idle_proposals.fill(FLT_MAX);row.sample.proposals.fill(FLT_MAX);row.sample.inputs.fill(FLT_MAX);row.sample.input_valid=255;row.sample.cylinder_valid=15;row.sample.cylinder_pulse_ms.fill(FLT_MAX);row.sample.cylinder_advance_deg.fill(FLT_MAX);row.sample.cylinder_fuel_pct.fill(FLT_MAX);row.sample.cylinder_duty_pct.fill(FLT_MAX);assert(ecu::engine_log::msl_row(header,row,text,sizeof(text)));
 std::cout<<"canonical_cjson_allocation_positions=4000 failed="<<failures<<" completed="<<successes<<" leaked=0\nalgorithm_growth_allocation_failure=retained_private_document_only\nmaximum_msl_header_bytes="<<header_size<<" maximum_msl_row_bytes="<<std::strlen(text)<<" capacity=2048\n";
}
