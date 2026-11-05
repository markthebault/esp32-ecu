// Actual sender/handlers/health/JSON execute against a deterministic native
// API model. The infinite RTOS task, SDK, RF and physical LED do NOT execute.
#include "../main/espnow.cpp"
#include <fstream>
#include <iostream>
#include <map>
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
static ecu::engine::RuntimeSample captured(bool boosted=false,double map=50,double rpm=0,std::uint64_t sampled=21000){
 using namespace ecu;engine::Tune t;t.flex_fuel.input_confirmed=true;t.flex_fuel.correction.enabled=true;t.flex_fuel.capture.cycles=2;
 if(boosted){t.injector_cc_min=600;t.dfco_enabled=false;t.boost_control.pressure_enabled=true;t.boost_control.mode=boost::Mode::OpenLoop;t.boost_control.open_duty.cells.fill(40);}
 flex::Capture c(t.flex_fuel.capture);const auto start=sampled-20000;c.edge(start,true,flex::Source::TargetCapture);
 for(unsigned n=1;n<=2;++n){c.edge(start+n*10000-3000,false,flex::Source::TargetCapture);c.edge(start+n*10000,true,flex::Source::TargetCapture);}
 engine::Inputs in;in.rpm=rpm;in.map_kpa=map;in.tps_pct=boosted?50:10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sensors_valid=in.lambda_ready=true;in.sampled_us=sampled;in.flex_sample={c.observe(sampled),t.flex_fuel.capture,t.revision};
 if(boosted)in.synced=in.phase_synced=true;
 engine::Controller controller;auto output=controller.step(t,in,sampled);auto data=engine::synthetic_data(t,in,output,1,sampled);data.source=engine::DataSource::Target;return data;
}
static void publish(ecu::engine::RuntimeSample data){
 ecu::web::Sample s;s.engine=data;s.adc_ok=true;s.raw.fill(2000);s.raw[7]=3723;ecu::config::Config c;std::array<double,6> filtered{};filtered.fill(2.7);
 r::publish(s,c,filtered);check(xQueueReceive(r::samples,&r::live,0)==pdTRUE);
}
static std::vector<std::uint8_t> capability(unsigned counter,unsigned schema,unsigned nonce,unsigned peer=0){
 std::vector<std::uint8_t> p(76);w::header(p.data(),w::Capabilities,76);w::u32(p.data()+8,counter?r::session_id.load():0);w::u32(p.data()+12,counter);std::memset(p.data()+16,nonce,16);w::u32(p.data()+32,counter?1:0);w::u32(p.data()+36,schema);check(r::hmac(r::saved.peers[peer].key,p.data(),44,p.data()+44));return p;
}
static void input(const std::vector<std::uint8_t>&p,unsigned peer=0){r::Rx packet;packet.size=p.size();std::memcpy(packet.mac,r::saved.peers[peer].mac,6);std::memcpy(packet.data,p.data(),p.size());r::handle(packet);}
static std::vector<std::uint8_t> acknowledgement(std::uint64_t seq){std::vector<std::uint8_t> p(56);w::header(p.data(),w::EngineAck,56);w::u32(p.data()+8,r::session_id);w::u64(p.data()+12,seq);check(r::hmac_key(r::streams[0].key.data(),32,p.data(),24,p.data()+24));input(p);return p;}
static void sensor_acknowledgement(std::uint32_t seq){std::vector<std::uint8_t> p(52);w::header(p.data(),w::Ack,52);w::u32(p.data()+8,r::session_id);w::u32(p.data()+12,seq);check(r::hmac(r::saved.peers[0].key,p.data(),20,p.data()+20));input(p);}
static void slot(unsigned round,std::int64_t sampled_time=-1,unsigned peer=0){const auto n=fake_datagrams.size();r::service_peer(peer,round,sampled_time<0?r::now():sampled_time);check(fake_datagrams.size()<=n+1);}
static void boost_service(){
 at(5000000);r::saved=r::Store{};for(unsigned i=0;i<4;++i){r::streams[i]=r::StreamPeer{};r::ack_seen[i]=false;r::acks[i]=0;}r::fault_until=0;r::last_error="";
 auto&peer=r::saved.peers[0];const std::uint8_t screen[]={2,170,187,204,221,238};std::memcpy(peer.mac,screen,6);std::strcpy(peer.name,"Schema6 native fixture");for(unsigned n=0;n<16;++n)peer.key[n]=n;
 r::engine_sequence=(UINT64_C(1)<<53)+91;check(r::prepare_stream(0));const auto good=captured(true,150,2000);publish(good);check(!r::live.fault);
 auto query=capability(0,0,1);binary("schema6-query-request.bin",query);input(query);slot(2);binary("schema6-query-reply.bin",fake_datagrams.back().bytes);finish();
 at(5010000);auto update=capability(1,6,2);binary("schema6-update-request.bin",update);input(update);r::streams[0].last_reply=0;slot(2);binary("schema6-update-reply.bin",fake_datagrams.back().bytes);finish();r::maintain_streams(r::now());
 const auto observations=r::engine_packets,datagrams=r::engine_datagrams,flexes=r::flex_datagrams,boosts=r::boost_datagrams;
 at(5030000);slot(2);auto base=fake_datagrams.back().bytes;binary("schema6-base.bin",base);const auto seq=r::streams[0].pair.sequence();check(base[5]==9&&base[20]==6&&r::streams[0].pair.part_index()==1);finish();acknowledgement(seq);check(!r::streams[0].engine_ack_seen);fixture("schema6-partial-base");
 auto*before_ack=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(r::view,"peers"),0);check(cJSON_GetObjectItemCaseSensitive(before_ack,"last_ack_ms")->valuedouble==-1&&!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(before_ack,"connected")));
 // A later pressure fault must not replace any part of the earlier snapshot.
 at(5040000);auto pressure=captured(true,230,2000);pressure.sequence=2;publish(pressure);check(r::live.fault);
 at(5080000);slot(3);auto flex=fake_datagrams.back().bytes;binary("schema6-flex.bin",flex);check(flex[5]==11&&flex[20]==6&&r::streams[0].pair.part_index()==2&&r::streams[0].pair.pending());finish();acknowledgement(seq);check(!r::streams[0].engine_ack_seen&&r::engine_packets==observations);fixture("schema6-partial-flex");
 at(5130000);slot(4);auto boost=fake_datagrams.back().bytes;binary("schema6-boost.bin",boost);check(boost[5]==12&&boost.size()==144&&!r::streams[0].pair.pending());check(w::same(boost.data()+24,base.data()+218,32)&&!(boost[110]&4)&&boost[108]==1);finish();
 check(r::engine_packets==observations+1&&r::engine_datagrams==datagrams+3&&r::flex_datagrams==flexes+1&&r::boost_datagrams==boosts+1);
 auto ack=acknowledgement(seq);binary("schema6-engine-ack.bin",ack);check(r::streams[0].engine_ack_seen&&r::ack_seen[0]);fixture("schema6-complete");publish(good);
 // Readback cannot report a future ACK as fresh after a clock discontinuity.
 at(5129999);r::update_view(false);auto*future_ack=cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(r::view,"peers"),0);check(cJSON_GetObjectItemCaseSensitive(future_ack,"last_ack_ms")->valuedouble==-1&&cJSON_GetObjectItemCaseSensitive(future_ack,"last_engine_ack_ms")->valuedouble==-1&&!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(future_ack,"engine_connected")));at(5130000);
 // Third-part SDK failure retries exact bytes, with no complete ACK entry.
 at(6000000);slot(2);finish();const auto retry_seq=r::streams[0].pair.sequence();at(6050000);slot(3);finish();fake_send_error=ESP_FAIL;at(6100000);slot(4);const auto failed=fake_datagrams.back().bytes;
 check(r::streams[0].pair.pending()&&r::streams[0].pair.part_index()==2&&!r::streams[0].engine_sent.acknowledge(retry_seq,r::now())&&r::engine_packets==observations+1);
 fake_send_error=ESP_OK;at(6150000);slot(5);check(fake_datagrams.back().bytes==failed&&!r::streams[0].pair.pending());finish();check(r::streams[0].engine_sent.acknowledge(retry_seq,r::now()));check(!r::streams[0].engine_sent.acknowledge(retry_seq,7000001));
 // Absolute deadline applies after two parts too, using current call time.
 at(7200000);slot(2);finish();const auto expired_seq=r::streams[0].pair.sequence();at(7250000);slot(3);finish();auto attempts=fake_datagrams.size();at(7450001);slot(4,7300000);check(fake_datagrams.size()==attempts&&!r::streams[0].pair.pending()&&!r::streams[0].engine_sent.acknowledge(expired_seq,r::now()));
 at(8000000);fake_mac_delay_us=100000;attempts=fake_datagrams.size();slot(2);check(fake_datagrams.size()==attempts&&!r::streams[0].pair.pending());fake_mac_delay_us=0;
 // Query, downgrade and re-enable retire incomplete observations and ACKs.
 at(9000000);slot(2);finish();at(9050000);slot(3);finish();check(r::streams[0].pair.part_index()==2);input(capability(0,0,3));check(!r::streams[0].pair.pending());slot(4);check(fake_datagrams.back().bytes[5]==8);finish();
 at(9300000);slot(2);finish();publish(good);input(capability(2,5,4));check(!r::streams[0].pair.pending()&&!r::streams[0].engine_ack_seen);r::streams[0].last_reply=0;slot(3);finish();slot(4);check(fake_datagrams.back().bytes[5]==4);finish();fixture("schema6-downgraded");
 input(capability(3,6,5));r::streams[0].last_reply=0;slot(2);finish();
 // Four peer slots use the actual sender with the task's12.5ms slot grid.
 // The native API model is not a measurement of RF or RTOS scheduling.
 for(unsigned i=1;i<4;++i){r::saved.peers[i]=peer;r::saved.peers[i].mac[5]-=i;check(r::prepare_stream(i));input(capability(1,6,5+i,i),i);slot(2,-1,i);finish();}
 at(10000000);publish(good);const auto begin=fake_datagrams.size();const auto before=r::engine_packets;
 for(unsigned n=0;n<80;++n){at(10000000+12500*n);slot(2+n/4,-1,n%4);if(r::sending){const auto size=fake_datagrams.size();slot(2+n/4,-1,(n+1)%4);check(fake_datagrams.size()==size);finish();}}
 std::array<unsigned,4> counts{};std::array<std::uint64_t,4> last{};
 for(unsigned n=begin;n<fake_datagrams.size();++n){const auto&d=fake_datagrams[n];check(d.bytes.size()<=250&&d.result==ESP_OK);if(d.bytes[5]==12){for(unsigned i=0;i<4;++i)if(w::same(d.mac.data(),r::saved.peers[i].mac,6)){++counts[i];last[i]=w::read64(d.bytes.data()+12);}}}
 for(unsigned i=0;i<4;++i){check(counts[i]==5);check(r::streams[i].engine_sent.acknowledge(last[i],r::now()));}
 check(r::engine_packets==before+20&&fake_datagrams.size()-begin==80);
 if(!output_directory.empty()){std::ofstream f(output_directory+"/schema6-four-peers.json");f<<"{\"passed\":true,\"slot_us\":12500,\"slots\":80,\"seconds\":1,\"submitted_observations\":[5,5,5,5],\"RF_or_RTOS_measured\":false}\n";}
 // Fifteen seconds covers five complete rotations of all six metadata
 // channels. Fresh actual controller/capture samples arrive in every slot.
 at(20000000);r::maintain_streams(r::now());const auto fair_begin=fake_datagrams.size();
 for(unsigned n=0;n<1200;++n){at(20000000+12500*n);auto fresh=captured(true,150,2000,fake_now);fresh.sequence=100+n;publish(fresh);slot(22+n/4,-1,n%4);check(r::sending);finish();}
 std::array<unsigned,4> metas{},sensors{},complete{},channels{};std::array<std::int64_t,4> sensor_time{},meta_time{};
 std::int64_t maximum_latency=0;std::map<std::uint64_t,FakeDatagram> bases;
 for(unsigned n=fair_begin;n<fake_datagrams.size();++n){const auto&d=fake_datagrams[n];unsigned i=0;while(i<4&&!w::same(d.mac.data(),r::saved.peers[i].mac,6))++i;check(i<4&&d.result==ESP_OK);
  if(d.bytes[5]==5){check(d.bytes[12]<6);channels[i]|=1U<<d.bytes[12];++metas[i];if(meta_time[i])check(d.stamp-meta_time[i]==500000);meta_time[i]=d.stamp;}
  else if(d.bytes[5]==4){++sensors[i];if(sensor_time[i])check(d.stamp-sensor_time[i]==500000);sensor_time[i]=d.stamp;}
  else if(d.bytes[5]==9){check(w::read64(d.bytes.data()+92)==std::uint64_t(d.stamp)&&w::read32(d.bytes.data()+24)==0);bases.emplace(w::read64(d.bytes.data()+12),d);}
  else if(d.bytes[5]==11){const auto&base=bases.at(w::read64(d.bytes.data()+12));check(w::same(d.bytes.data()+24,base.bytes.data()+218,32)&&w::read32(d.bytes.data()+192)==0);}
  else if(d.bytes[5]==12){const auto&base=bases.at(w::read64(d.bytes.data()+12));check(w::same(d.bytes.data()+24,base.bytes.data()+218,32));const auto elapsed=d.stamp-base.stamp;check(elapsed<=200000);maximum_latency=std::max(maximum_latency,elapsed);++complete[i];}
  else check(false);
 }
 for(unsigned i=0;i<4;++i)check(metas[i]==30&&sensors[i]==30&&complete[i]==80&&channels[i]==63);
 check(maximum_latency==200000&&fake_datagrams.size()-fair_begin==1200);
 if(!output_directory.empty()){std::ofstream f(output_directory+"/schema6-fairness.json");f<<"{\"passed\":true,\"seconds\":15,\"slots\":1200,\"peers\":4,\"metadata_per_peer\":30,\"sensors_per_peer\":30,\"all_six_metadata_channels\":true,\"complete_observations_per_peer\":80,\"maximum_assembly_us\":200000,\"reserved_stream_gap_us\":500000,\"RF_or_RTOS_measured\":false}\n";}
 // Unpair at each pending stage clears all bytes, keys and ACK history.
 const auto saved_peer=peer;
 for(unsigned stage=0;stage<3;++stage){
  at(40000000+stage*1000000);r::saved.peers[0]=saved_peer;check(r::prepare_stream(0));input(capability(1,6,10+stage));slot(2);finish();
  fake_send_error=stage==0?ESP_FAIL:ESP_OK;slot(2);if(r::sending)finish();fake_send_error=ESP_OK;
  if(stage==2){at(r::now()+50000);slot(3);finish();}check(r::streams[0].pair.part_index()==stage);
  r::Command command{};std::strcpy(command.action,"unpair");std::strcpy(command.mac,"02:AA:BB:CC:DD:EE");r::command_run(command);
  check(!r::occupied(r::saved.peers[0])&&!r::streams[0].pair.pending()&&!r::streams[0].key_ready&&!r::streams[0].engine_ack_seen);attempts=fake_datagrams.size();slot(2);check(fake_datagrams.size()==attempts&&fake_peer_blob.size()==204);
 }
}
int main(int argc,char**argv){
 if(argc>1)output_directory=argv[1];
 r::start();at(5000000);r::radio_ok=r::storage_ok=true;r::saved=r::Store{};
 auto&peer=r::saved.peers[0];const std::uint8_t screen[]={2,170,187,204,221,238};std::memcpy(peer.mac,screen,6);std::strcpy(peer.name,"Native screen fixture");for(unsigned n=0;n<16;++n)peer.key[n]=n;
 r::session_id=0x12345678;esp_fill_random(r::engine_nonce,16);esp_wifi_get_mac(0,r::own);r::engine_sequence=(UINT64_C(1)<<53)+91;check(r::prepare_stream(0));auto good=captured();publish(good);
 check(!r::live.fault&&!r::radio_fault(5000000));r::led(false,false);check(requested_pattern==ecu::status_led::Pattern::Normal);
 // Pressure protection is a problem even without a rotating engine. A
 // stopped monitor must not suppress the red policy for this new fault.
 auto pressure=good;pressure.controller_faults=ecu::engine::Overboost;
 pressure.boost_control.available=pressure.boost_control.pressure_enabled=pressure.boost_control.inhibit_engine=true;
 pressure.boost_control.flags=ecu::boost::Enabled|ecu::boost::PressureValid|ecu::boost::OverboostLatched;
 pressure.boost_control.reason=static_cast<unsigned>(ecu::boost::Reason::Overboost);
 check(pressure.inputs[ecu::engine::DecodedRpm]==0);publish(pressure);check(r::live.fault&&r::radio_fault(5000000));
 r::led(r::radio_fault(5000000),true);check(requested_pattern==ecu::status_led::Pattern::Problem);
 publish(good);check(!r::live.fault);r::led(false,true);check(requested_pattern==ecu::status_led::Pattern::Pairing);r::led(false,false);
 auto query=capability(0,0,1);binary("query-request.bin",query);input(query);slot(2);check(fake_datagrams.back().bytes[5]==8);binary("query-reply.bin",fake_datagrams.back().bytes);finish();
 at(5010000);auto update=capability(1,5,2);binary("update-request.bin",update);input(update);
 // First reply is rate limited until250ms after the previous reply. Set its
 // previous stamp to0 in this fixture so the timed Python query can complete.
 r::streams[0].last_reply=0;slot(2);check(fake_datagrams.back().bytes[5]==8);binary("update-reply.bin",fake_datagrams.back().bytes);finish();r::maintain_streams(r::now());
 publish(pressure);fixture("boost-profile-blocked");auto*peers=cJSON_GetObjectItemCaseSensitive(r::view,"peers");auto*screen_status=cJSON_GetArrayItem(peers,0);
 check(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(screen_status,"engine_telemetry_blocked")));
 check(std::strstr(cJSON_GetObjectItemCaseSensitive(screen_status,"engine_block_reason")->valuestring,"boost pressure profile"));publish(good);
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
 boost_service();cJSON_Delete(r::view);r::view=nullptr;std::cout<<"radio_service_checks "<<checks<<"\n";
}
