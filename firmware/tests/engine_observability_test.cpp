#include "ecu/engine_radio.hpp"
#include "ecu/engine_log_json.hpp"
#include "ecu/engine_log_msl.hpp"
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <string>
#include <unordered_map>

using namespace ecu;
engine::RuntimeSample sample(std::uint64_t sequence,std::uint64_t now){
 engine::Inputs in;in.rpm=1000;in.map_kpa=45;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sampled_us=now;in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;
 engine::Tune tune;tune.strategy=engine::Strategy::Sequential;engine::Controller controller;const auto out=controller.step(tune,in,now);return engine::synthetic_data(tune,in,out,sequence,now);
}
void recorder_tests(){
 engine_log::Recorder recorder;assert(!recorder.start(21,1,engine::DataSource::Synthetic,0));assert(!recorder.start(20,901,engine::DataSource::Synthetic,0));assert(!recorder.start(20,1,engine::DataSource::None,0));
 assert(recorder.start(20,60,engine::DataSource::Synthetic,0));const auto id=recorder.header().log_id;
 for(unsigned n=0;n<600;++n)assert(recorder.append(sample(n+1,n*20000ULL),n*20000ULL));
 auto h=recorder.header();assert(h.total==600&&h.retained==256&&h.overwritten==344&&h.first_sequence()==345);
 engine_log::Page page;recorder.page(id,0,page);assert(page.gap_first==1&&page.gap_last==344&&page.count==16&&page.next_after==360);
 const auto copied=page.rows[0];engine_log::Row row;assert(!recorder.read(id,344,row));assert(recorder.read(id,345,row));
 for(unsigned n=600;n<900;++n)assert(recorder.append(sample(n+1,n*20000ULL),n*20000ULL));
 assert(!recorder.read(id,345,row));assert(copied.sequence==345&&copied.sample.sequence==345); // The copied page stays immutable.
 recorder.page(id,901,page);assert(page.future_cursor);recorder.page(id+1,0,page);assert(page.superseded);
 assert(!recorder.stop(id+1,18000000));assert(recorder.stop(id,18000000));assert(recorder.start(100,1,engine::DataSource::Synthetic,18000000));
 recorder.page(id,0,page);assert(page.superseded);assert(!recorder.stop(id,18000000));
}
void clock_and_sampling_tests(){
 engine_log::Recorder r;assert(r.start(100,2,engine::DataSource::Synthetic,0));assert(r.append(sample(1,0),0));
 assert(r.append(sample(2,375000),375000));assert(r.header().missed_periods==2&&r.header().total==2);
 assert(!r.append(sample(2,375000),400000));assert(r.header().repeated==1);
 auto future=sample(3,600000);assert(!r.append(future,500000));assert(r.header().invalid==1);
 assert(r.append(sample(4,600000),600000));r.expire(599999);assert(r.header().state==engine_log::State::Clock);
 engine_log::Recorder stalled;assert(stalled.start(100,1,engine::DataSource::Synthetic,0));assert(stalled.append(sample(1,0),0));
 stalled.expire(1000000);assert(stalled.header().state==engine_log::State::Timeout&&stalled.header().missed_periods==9);
 assert(stalled.start(100,2,engine::DataSource::Synthetic,1000000));assert(stalled.append(sample(2,1000000),1000000));
 assert(stalled.stop(stalled.header().log_id,1500000));assert(stalled.header().missed_periods==5);
 engine_log::Recorder timeout;assert(timeout.start(20,1,engine::DataSource::Synthetic,UINT64_MAX-1000000));
 assert(timeout.append(sample(1,UINT64_MAX-1),UINT64_MAX-1));timeout.expire(UINT64_MAX);assert(timeout.header().state==engine_log::State::Timeout);
 using namespace radio::wire;
 assert(transmitted_age(18000,5000000,5012500)==31);assert(transmitted_age(UINT64_MAX,5,7)==UINT32_MAX);assert(transmitted_age(0,5,4)==UINT32_MAX);
}
void capabilities_and_ack_tests(){
 using namespace radio::wire;PeerCapabilities peer;std::uint8_t request[capability_size]{};header(request,Capabilities,capability_size);
 request[16]=7;assert(peer.request(request,sizeof(request),123));assert(!peer.engine()&&peer.counter()==0&&peer.pending());
 std::uint8_t reply[capability_reply_size],nonce[16]{};nonce[0]=42;peer.reply(reply,123,nonce,UINT64_C(9007199254740993),5000000);assert(read64(reply+60)==UINT64_C(9007199254740993));assert(same(reply+16,request+16,16));peer.sent();
 u32(request+8,123);u32(request+12,1);u32(request+32,engine_feature);u32(request+36,engine_schema);assert(peer.request(request,sizeof(request),123));assert(peer.engine()&&peer.counter()==1);peer.sent();assert(peer.request(request,sizeof(request),123));
 request[16]^=1;assert(!peer.request(request,sizeof(request),123));request[16]^=1;
 u32(request+8,124);assert(!peer.request(request,sizeof(request),123));u32(request+8,123);u32(request+32,2);assert(!peer.request(request,sizeof(request),123));
 peer.reset();assert(!peer.engine()&&peer.counter()==0&&!peer.pending());
 SentWindow<std::uint32_t> window;for(auto n:{UINT32_MAX-1,UINT32_MAX,0U,1U}){window.submitted(n);assert(window.acknowledge(n));assert(!window.acknowledge(n));}assert(!window.acknowledge(2));
 for(unsigned n=2;n<12;++n)window.submitted(n);
 assert(!window.acknowledge(2));assert(window.acknowledge(11));
 SentWindow<std::uint64_t> wide;wide.submitted(UINT64_C(9007199254740993));assert(wide.acknowledge(UINT64_C(9007199254740993)));
 SentWindow<std::uint32_t> aged;aged.submitted(40,0);assert(aged.acknowledge(40,0));aged.submitted(42,1);
 assert(!aged.acknowledge(42,1000002));aged.submitted(41,1000003);assert(aged.acknowledge(41,1000003));
 aged.submitted(43,2000000);assert(!aged.acknowledge(43,1999999));assert(aged.acknowledge(43,3000000));
 wide.submitted(UINT64_C(9007199254740994),2000000);assert(!wide.acknowledge(UINT64_C(9007199254740994),3000001));
}
unsigned fields(const std::string&line){unsigned n=1;for(auto c:line)if(c=='\t')++n;return n;}
void framing_and_msl_tests(){
 auto r=sample(UINT64_C(9007199254740993),20000);r.worker_sequence=UINT64_C(9007199254740995);r.input_valid&=~(1U<<engine::Lambda);std::uint8_t bytes[radio::wire::engine_size];
 assert(radio::wire::engine_body(bytes,r,123,456,30,30,35,5000000));assert(radio::wire::valid(bytes,sizeof(bytes),radio::wire::EngineTelemetry,sizeof(bytes)));assert(radio::wire::read64(bytes+40)==r.sequence);
 assert(radio::wire::read32(bytes+112+4*engine::Lambda)==0x7fc00000);assert(radio::wire::read32(bytes+24)==30);
 assert((bytes[23]&128)!=0);assert(radio::wire::engine_body(bytes,r,123,457,1001,1001,1002,6000000));assert((bytes[23]&128)==0);
 engine_log::Header h;h.source=engine::DataSource::Synthetic;h.total=h.retained=1;engine_log::Row row{r,20000,1,1};char text[engine_log::text_capacity];assert(engine_log::msl_header(h,text,sizeof(text)));
 std::string header=text;const auto start=header.find('\n',header.find('\n')+1)+1;const auto end=header.find('\n',start);const auto count=fields(header.substr(start,end-start));assert(count==105);
 assert(engine_log::msl_row(h,row,text,sizeof(text)));assert(fields(text)==count);assert(std::string(text).find("NaN")!=std::string::npos);assert(!engine_log::msl_row(h,row,text,10));
 engine_log::Request q;assert(engine_log::parse_request("{\"action\":\"start\",\"period_ms\":20,\"duration_s\":1}",49,q)==false); // Explicit lengths must match the actual envelope.
 std::string body="{\"action\":\"start\",\"period_ms\":20,\"duration_s\":1}";assert(engine_log::parse_request(body.c_str(),body.size(),q));
 body="{\"action\":\"stop\",\"log_id\":1,\"log_id\":2}";assert(!engine_log::parse_request(body.c_str(),body.size(),q));
 std::uint32_t id=0,after=0;assert(engine_log::parse_query("log_id=1&after=0",id,after));assert(!engine_log::parse_query("log_id=1&after=4294967296",id,after));
}
static std::unordered_map<void*,std::size_t> allocations;static int budget=-1;
static std::size_t live_bytes=0,peak_bytes=0,allocation_count=0;
void* allocate(std::size_t n){if(budget==0)return nullptr;if(budget>0)--budget;auto*p=std::malloc(n);if(p){allocations[p]=n;live_bytes+=n;peak_bytes=std::max(peak_bytes,live_bytes);++allocation_count;}return p;}
void release(void*p){if(!p)return;const auto i=allocations.find(p);assert(i!=allocations.end());live_bytes-=i->second;allocations.erase(i);std::free(p);}
void allocation_tests(){
 engine_log::Recorder r;assert(r.start(20,1,engine::DataSource::Synthetic,0));for(unsigned i=0;i<16;++i)r.append(sample(i+1,i*20000),i*20000);
 engine_log::Page page;r.page(r.header().log_id,0,page);cJSON_Hooks hooks{allocate,release};cJSON_InitHooks(&hooks);
 budget=-1;auto*complete=engine_log::page_json(page);assert(complete);const auto required=allocation_count;auto*encoded=cJSON_PrintUnformatted(complete);assert(encoded);const auto output_bytes=std::strlen(encoded),full_peak=peak_bytes;cJSON_free(encoded);cJSON_Delete(complete);assert(allocations.empty()&&!live_bytes);
 unsigned failed=0,passed=0;for(std::size_t n=0;n<=required;++n){budget=static_cast<int>(n);auto*j=engine_log::page_json(page);if(j){++passed;assert(n==required&&cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(j,"records"))==16);}else ++failed;cJSON_Delete(j);assert(allocations.empty()&&!live_bytes);}
 cJSON_InitHooks(nullptr);assert(failed==required&&passed==1);std::cout<<"JSON allocation positions: "<<failed<<" rejected, "<<passed<<" complete page; native cJSON peak="<<full_peak<<" bytes, output="<<output_bytes<<" bytes (allocator overhead excluded)\n";
}
int main(){recorder_tests();clock_and_sampling_tests();capabilities_and_ack_tests();framing_and_msl_tests();allocation_tests();std::cout<<"Engine observation, bounded log, ages, negotiation, ACK rollover and formatting tests passed\n";}
