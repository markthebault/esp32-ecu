// Actual sender/handlers/health/JSON execute against a deterministic native
// API model. The infinite RTOS task, SDK, RF and physical LED do NOT execute.
#include "../main/espnow.cpp"
#include <fstream>
#include <iostream>
namespace ecu::engine_target {std::uint64_t clock_us(){return fake_now;}}
inline ecu::status_led::Pattern requested_pattern=ecu::status_led::Pattern::Problem;
namespace ecu::board_status {
void request(status_led::Pattern p){requested_pattern=p;}
cJSON*snapshot(){auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"available",false);cJSON_AddStringToObject(j,"source","native_api_model_no_i2c");return j;}
}
namespace r=ecu::radio;namespace w=ecu::radio::wire;
static unsigned checks=0;static std::string output_directory;
static void verify(bool v,const char*expression,unsigned line){++checks;if(!v)std::cerr<<line<<": "<<expression<<'\n';assert(v);}
#define check(v) verify((v),#v,__LINE__)
static void at(std::int64_t t){fake_radio_now=t;fake_now=21000+t-5000000;}
static void finish(){r::sent(nullptr,ESP_NOW_SEND_SUCCESS);}
static void binary(const char*name,const std::vector<std::uint8_t>&bytes){if(!output_directory.empty()){std::ofstream f(output_directory+"/"+name,std::ios::binary);check(f.good());f.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());}}
static void fixture(const char*name){r::update_view(r::radio_fault(5000000));auto*j=r::status();check(j);char*text=cJSON_Print(j);check(text);cJSON_Delete(j);if(!output_directory.empty()){std::ofstream f(output_directory+"/"+name+".json");check(f.good());f<<text<<'\n';}cJSON_free(text);}
static ecu::engine::RuntimeSample captured(){
 using namespace ecu;engine::Tune t;t.flex_fuel.input_confirmed=true;t.flex_fuel.correction.enabled=true;t.flex_fuel.capture.cycles=2;
 flex::Capture c(t.flex_fuel.capture);c.edge(1000,true,flex::Source::TargetCapture);
 for(unsigned n=1;n<=2;++n){c.edge(1000+n*10000-3000,false,flex::Source::TargetCapture);c.edge(1000+n*10000,true,flex::Source::TargetCapture);}
 engine::Inputs in;in.rpm=0;in.map_kpa=50;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sensors_valid=in.lambda_ready=true;in.sampled_us=21000;in.flex_sample={c.observe(21000),t.flex_fuel.capture,t.revision};
 engine::Controller controller;auto output=controller.step(t,in,21000);auto data=engine::synthetic_data(t,in,output,1,21000);data.source=engine::DataSource::Target;return data;
}
static void publish(ecu::engine::RuntimeSample data){
 ecu::web::Sample s;s.engine=data;s.adc_ok=true;s.raw.fill(2000);s.raw[7]=3723;ecu::config::Config c;std::array<double,6> filtered{};filtered.fill(2.7);
 r::publish(s,c,filtered);check(xQueueReceive(r::samples,&r::live,0)==pdTRUE);
}
static std::vector<std::uint8_t> capability(unsigned counter,unsigned schema,unsigned nonce){
 std::vector<std::uint8_t> p(76);w::header(p.data(),w::Capabilities,76);w::u32(p.data()+8,counter?r::session_id.load():0);w::u32(p.data()+12,counter);std::memset(p.data()+16,nonce,16);w::u32(p.data()+32,counter?1:0);w::u32(p.data()+36,schema);check(r::hmac(r::saved.peers[0].key,p.data(),44,p.data()+44));return p;
}
static void input(const std::vector<std::uint8_t>&p){r::Rx packet;packet.size=p.size();std::memcpy(packet.mac,r::saved.peers[0].mac,6);std::memcpy(packet.data,p.data(),p.size());r::handle(packet);}
static std::vector<std::uint8_t> acknowledgement(std::uint64_t seq){std::vector<std::uint8_t> p(56);w::header(p.data(),w::EngineAck,56);w::u32(p.data()+8,r::session_id);w::u64(p.data()+12,seq);check(r::hmac_key(r::streams[0].key.data(),32,p.data(),24,p.data()+24));input(p);return p;}
static void sensor_acknowledgement(std::uint32_t seq){std::vector<std::uint8_t> p(52);w::header(p.data(),w::Ack,52);w::u32(p.data()+8,r::session_id);w::u32(p.data()+12,seq);check(r::hmac(r::saved.peers[0].key,p.data(),20,p.data()+20));input(p);}
static void slot(unsigned round,std::int64_t sampled_time=-1){const auto n=fake_datagrams.size();r::service_peer(0,round,sampled_time<0?r::now():sampled_time);check(fake_datagrams.size()<=n+1);}
int main(int argc,char**argv){
 if(argc>1)output_directory=argv[1];
 r::start();at(5000000);r::radio_ok=r::storage_ok=true;r::saved=r::Store{};
 auto&peer=r::saved.peers[0];const std::uint8_t screen[]={2,170,187,204,221,238};std::memcpy(peer.mac,screen,6);std::strcpy(peer.name,"Native screen fixture");for(unsigned n=0;n<16;++n)peer.key[n]=n;
 r::session_id=0x12345678;esp_fill_random(r::engine_nonce,16);esp_wifi_get_mac(0,r::own);r::engine_sequence=(UINT64_C(1)<<53)+91;check(r::prepare_stream(0));auto good=captured();publish(good);
 check(!r::live.fault&&!r::radio_fault(5000000));r::led(false,false);check(requested_pattern==ecu::status_led::Pattern::Normal);
 auto query=capability(0,0,1);binary("query-request.bin",query);input(query);slot(2);check(fake_datagrams.back().bytes[5]==8);binary("query-reply.bin",fake_datagrams.back().bytes);finish();
 at(5010000);auto update=capability(1,5,2);binary("update-request.bin",update);input(update);
 // First reply is rate limited until250ms after the previous reply. Set its
 // previous stamp to0 in this fixture so the timed Python query can complete.
 r::streams[0].last_reply=0;slot(2);check(fake_datagrams.back().bytes[5]==8);binary("update-reply.bin",fake_datagrams.back().bytes);finish();r::maintain_streams(r::now());
 at(5020000);slot(1);check(fake_datagrams.back().bytes[5]==4);sensor_acknowledgement(w::read32(fake_datagrams.back().bytes.data()+12));check(r::ack_seen[0]&&!r::streams[0].engine_ack_seen);finish();
 at(5030000);slot(2);check(fake_datagrams.back().bytes[5]==9&&r::streams[0].pair.pending()&&r::streams[0].pair.base_submitted());auto base=fake_datagrams.back().bytes;binary("base.bin",base);const auto seq=r::streams[0].pair.sequence();finish();
 acknowledgement(seq);check(!r::streams[0].engine_ack_seen);fixture("partial");
 at(5040000);auto newer=good;newer.sequence=2;newer.control_us=newer.sampled_us=fake_now;newer.flex_fuel.values[6]=40;publish(newer);
 at(5080000);slot(3);check(fake_datagrams.back().bytes[5]==11&&!r::streams[0].pair.pending());auto extension=fake_datagrams.back().bytes;binary("flex.bin",extension);check(w::same(extension.data()+24,base.data()+218,32)&&w::read32(extension.data()+136)==0);check(r::engine_packets==1&&r::engine_datagrams==2&&r::flex_datagrams==1);finish();
 auto ack=acknowledgement(seq);binary("engine-ack.bin",ack);check(r::streams[0].engine_ack_seen&&r::ack_seen[0]);fixture("complete");
 const auto expected=r::streams[0].engine_expected_since;r::streams[0].engine_ack_seen=false;r::streams[0].engine_expected_since=2000000;
 check(r::radio_fault(5000000));fixture("engine-ack-missing");r::streams[0].engine_ack_seen=true;r::streams[0].engine_expected_since=expected;
 at(5250001);check(!r::live.fault&&r::radio_fault(5000000));r::led(r::radio_fault(5000000),false);check(requested_pattern==ecu::status_led::Pattern::Problem);fixture("held-expired");
 // Failed base and extension submissions cannot enter the ACK window.
 at(6000000);fake_send_error=ESP_FAIL;slot(4);check(r::streams[0].pair.pending()&&!r::streams[0].pair.base_submitted());const auto failed=fake_datagrams.back().bytes;const auto failed_seq=r::streams[0].pair.sequence();
 fake_send_error=ESP_OK;at(6050000);slot(5);check(fake_datagrams.back().bytes==failed);finish();fake_send_error=ESP_FAIL;at(6100000);slot(6);check(r::streams[0].pair.pending()&&r::streams[0].pair.base_submitted());check(!r::streams[0].engine_sent.acknowledge(failed_seq,r::now()));fake_send_error=ESP_OK;
 at(6150000);slot(7);check(!r::streams[0].pair.pending());finish();check(r::streams[0].engine_sent.acknowledge(failed_seq,r::now()));check(!r::streams[0].engine_sent.acknowledge(failed_seq,7000001));
 // The loop's old time must not permit an expired extension or a HMAC stall.
 at(7000000);slot(8);finish();const auto timeouts=r::pair_timeouts;at(7250001);auto attempts=fake_datagrams.size();slot(9,7050000);check(fake_datagrams.size()==attempts&&!r::streams[0].pair.pending()&&r::pair_timeouts==timeouts+1);
 at(8000000);fake_mac_delay_us=300000;attempts=fake_datagrams.size();slot(2);check(fake_datagrams.size()==attempts&&!r::streams[0].pair.pending());fake_mac_delay_us=0;
 at(9000000);slot(4);finish();check(r::streams[0].pair.pending());input(capability(0,0,3));check(!r::streams[0].pair.pending());slot(5);check(fake_datagrams.back().bytes[5]==8);finish();
 // A pair prepared while a query reply is throttled is cancelled at reply.
 at(9050000);slot(6);finish();check(r::streams[0].pair.pending());input(capability(0,0,4));at(9100000);slot(7);finish();check(r::streams[0].pair.pending());at(9260000);slot(8);check(fake_datagrams.back().bytes[5]==8&&!r::streams[0].pair.pending());finish();
 // Unpair resets pending bytes, stream keys and ACK history, then stops slots.
 at(9300000);slot(9);finish();check(r::streams[0].pair.pending());r::Command command{};std::strcpy(command.action,"unpair");std::strcpy(command.mac,"02:AA:BB:CC:DD:EE");r::command_run(command);check(!r::occupied(r::saved.peers[0])&&!r::streams[0].pair.pending()&&!r::streams[0].key_ready&&fake_deleted_peers==1);attempts=fake_datagrams.size();slot(2);check(fake_datagrams.size()==attempts&&fake_peer_blob.size()==204);
 cJSON_Delete(r::view);r::view=nullptr;std::cout<<"radio_service_checks "<<checks<<"\n";
}
