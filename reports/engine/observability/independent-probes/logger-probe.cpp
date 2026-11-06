#include "ecu/engine_log_json.hpp"
#include "ecu/engine_log_msl.hpp"
#include <cassert>
#include <iostream>
#include <string>
using namespace ecu;
engine::RuntimeSample point(std::uint64_t sequence,std::uint64_t now){engine::RuntimeSample s;s.sequence=sequence;s.control_us=s.sampled_us=now;s.flags=engine::Present;s.source=engine::DataSource::Target;return s;}
int main(){
 engine_log::Recorder timeout;assert(timeout.start(100,1,engine::DataSource::Target,0));assert(timeout.append(point(1,0),0));timeout.expire(1000000);assert(timeout.header().missed_periods==9);
 engine_log::Recorder stop;assert(stop.start(100,1,engine::DataSource::Target,0));assert(stop.append(point(1,0),0));stop.stop(stop.header().log_id,500000);assert(stop.header().missed_periods==5);
 unsigned cases=0;std::uint32_t rng=0x12345678;
 for(unsigned period:{20,50,100,200,500,1000})for(unsigned duration:{1,2,900})for(unsigned variant=0;variant<20;++variant){
  engine_log::Recorder log;assert(log.start(period,duration,engine::DataSource::Target,123));std::uint64_t now=123,seq=0;const auto end=123+std::uint64_t(duration)*1000000;
  while(now<end){rng=rng*1664525+1013904223;auto sample=point(++seq,now);switch(rng%7){case 0:sample.flags=0;break;case 1:sample.control_us=now+1;break;case 2:sample.sequence=seq>3?seq-3:0;break;case 3:sample.source=engine::DataSource::Synthetic;break;default:break;}log.append(sample,now);now+=1+(rng>>8)%600000;}
  log.expire(end+1000);const auto h=log.header();assert(h.state==engine_log::State::Timeout);assert(std::uint64_t(h.total)+h.missed_periods+h.repeated+h.invalid==std::uint64_t(duration)*1000/period);assert(h.overwritten==h.total-h.retained);assert(h.retained<=256);++cases;
 }
 engine_log::Recorder ring;assert(ring.start(20,30,engine::DataSource::Target,0));for(unsigned n=0;n<600;++n)assert(ring.append(point(n+1,n*20000),n*20000));engine_log::Page page;ring.page(ring.header().log_id,0,page);assert(page.count==16&&page.gap_first==1&&page.gap_last==344&&page.rows[0].sequence==345);const auto old_id=page.header.log_id;const auto copied=page.rows[0];for(unsigned n=600;n<900;++n)ring.append(point(n+1,n*20000),n*20000);engine_log::Row row;assert(!ring.read(old_id,345,row));assert(copied.sequence==345&&copied.sample.sequence==345);assert(ring.stop(old_id,18000000));assert(ring.start(20,1,engine::DataSource::Target,18000000));assert(!ring.stop(old_id,18000001));assert(page.header.log_id==old_id&&page.rows[0].sample.sequence==345);
 auto s=point(UINT64_C(9007199254740993),1000);s.worker_sequence=UINT64_C(9007199254740995);s.worker_observed_us=800;s.input_valid=1;s.inputs[0]=1000;s.inputs[1]=45;auto*j=engine::data_json(s,1100);assert(j);auto*inputs=cJSON_GetObjectItemCaseSensitive(j,"inputs");assert(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(inputs,"map_kpa")));assert(std::string(cJSON_GetObjectItemCaseSensitive(j,"sequence")->valuestring)=="9007199254740993");cJSON_Delete(j);assert(engine::data_age_us(s,1000,999)==UINT64_MAX);
 std::cout<<"{\"recorder_bytes\":"<<sizeof(engine_log::Recorder)<<",\"runtime_sample_bytes\":"<<sizeof(engine::RuntimeSample)<<",\"row_bytes\":"<<sizeof(engine_log::Row)<<",\"page_bytes\":"<<sizeof(engine_log::Page)<<",\"timeout_terminal_misses\":"<<timeout.header().missed_periods<<",\"stop_terminal_misses\":"<<stop.header().missed_periods<<",\"schedule_accounting_cases\":"<<cases<<",\"copied_pages_survive_overwrite_and_rearm\":true,\"invalid_inputs_are_null\":true,\"u64_ids_remain_lossless\":true,\"future_age_invalid\":true}\n";
}
