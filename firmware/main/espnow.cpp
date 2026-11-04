#include "ecu/espnow.hpp"
#include "ecu/engine_radio.hpp"
#include "ecu/engine_target.hpp"
#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "esp_now.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/md.h"
#include <atomic>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#if defined(ECU_SELECTED_N16R8) && ECU_BENCH_PULSES
#error Selected supplier module must never use bench output pulses
#endif
#if !defined(ECU_COMPACT_A3) || (defined(ECU_ENGINE_DUMMY_LOADS) && ECU_ENGINE_DUMMY_LOADS)
namespace ecu::radio {
void start(){}
void publish(const web::Sample&,const config::Config&,const std::array<double,6>&){}
cJSON* status(){auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"available",false);return j;}
bool command(const char*,const char*,const char*){return false;}
}
#else
namespace ecu::radio {
namespace {
using namespace wire;
constexpr const char* tag="ecu_now";
constexpr std::uint8_t broadcast[6]={255,255,255,255,255,255};
struct Peer {std::uint8_t mac[6]{},key[16]{};char name[24]{};};
struct Store {std::uint32_t version=1;std::uint8_t pmk[16]{};Peer peers[max_peers]{};};
struct Live {std::uint8_t data[88]{},meta[6][98]{};engine::RuntimeSample engine;std::uint64_t engine_sample_age=UINT64_MAX,engine_control_age=UINT64_MAX,worker_age=UINT64_MAX;bool fault=true;std::int64_t stamp=0;};
struct StreamPeer {PeerCapabilities capabilities;std::array<std::uint8_t,32> key{};SentWindow<std::uint32_t> sensor_sent;SentWindow<std::uint64_t> engine_sent;bool key_ready=false;std::int64_t last_reply=0;};
static_assert(sizeof(Store)==204,"Existing peer Storev1 layout must remain unchanged");
struct Rx {std::uint8_t mac[6]{},data[max_packet]{};int size=0;};
struct Command {char action[12]{},mac[18]{},window[33]{};};
QueueHandle_t samples,received,commands;SemaphoreHandle_t view_mutex;
Store saved;Live live;std::uint8_t own[6]{},secret[16]{},window[16]{},candidate_nonce[16]{};Peer candidate;
std::uint64_t acks[max_peers]{};bool ack_seen[max_peers]{};StreamPeer streams[max_peers];std::uint8_t engine_nonce[16]{};std::uint64_t engine_sequence=0;
std::int64_t deadline=0,last_beacon=0,candidate_started=0;bool waiting=false,approved=false,storage_ok=false,radio_ok=false;
std::int64_t fault_until=0;
std::atomic<std::uint32_t> session_id{0};std::uint32_t sequence=0;std::atomic<bool> sending{false};std::atomic<bool> rx_overflow{false};std::atomic<std::uint32_t> mac_failures{0};std::uint32_t mac_failure_count=0;std::uint64_t engine_packets=0,sensor_packets=0,capability_replies=0;
cJSON* view=nullptr;const char* last_error="initializing";
rmt_channel_handle_t led_channel{};rmt_encoder_handle_t led_encoder{};
std::int64_t now(){return esp_timer_get_time();}
void hex(const std::uint8_t*p,unsigned n,char*out){for(unsigned i=0;i<n;++i)std::sprintf(out+2*i,"%02X",p[i]);}
void mac_text(const std::uint8_t*p,char*out){std::sprintf(out,"%02X:%02X:%02X:%02X:%02X:%02X",p[0],p[1],p[2],p[3],p[4],p[5]);}
bool occupied(const Peer&p){return unicast(p.mac);}
int index_of(const std::uint8_t*mac){for(unsigned i=0;i<max_peers;++i)if(occupied(saved.peers[i])&&same(saved.peers[i].mac,mac,6))return i;return -1;}
bool commit(const Store&s){
 nvs_handle_t h{};auto err=nvs_open("ecu_now",NVS_READWRITE,&h);
 if(err==ESP_OK){err=nvs_set_blob(h,"peers",&s,sizeof(s));if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);}
 if(err!=ESP_OK){fault_until=now()+3000000;last_error="Peer storage commit failed";ESP_LOGE(tag,"%s: %s",last_error,esp_err_to_name(err));return false;}return true;
}
bool restore(){
 nvs_handle_t h{};auto err=nvs_open("ecu_now",NVS_READWRITE,&h);if(err!=ESP_OK)return false;
 std::size_t size=sizeof(saved);err=nvs_get_blob(h,"peers",&saved,&size);nvs_close(h);
 if(err==ESP_ERR_NVS_NOT_FOUND){saved=Store{};esp_fill_random(saved.pmk,16);return commit(saved);}
 if(err!=ESP_OK||size!=sizeof(saved)||saved.version!=1)return false;
 for(unsigned i=0;i<max_peers;++i){const auto&p=saved.peers[i];if(!occupied(p)){std::uint8_t empty[6]{};if(!same(p.mac,empty,6))return false;continue;}
  if(!std::memchr(p.name,0,sizeof(p.name)))return false;
  for(unsigned j=0;j<i;++j)if(same(p.mac,saved.peers[j].mac,6))return false;
 }return true;
}
esp_err_t add(const Peer&p,bool encrypt){
 esp_now_peer_info_t info{};std::memcpy(info.peer_addr,p.mac,6);info.channel=channel;info.ifidx=WIFI_IF_STA;info.encrypt=encrypt;std::memcpy(info.lmk,p.key,16);
 return esp_now_is_peer_exist(p.mac)?esp_now_mod_peer(&info):esp_now_add_peer(&info);
}
bool send(const std::uint8_t*mac,const std::uint8_t*data,unsigned size){
 if(sending.exchange(true))return false;
 auto err=esp_now_send(mac,data,size);if(err!=ESP_OK){sending=false;fault_until=now()+3000000;last_error="ESP-NOW send failed";return false;}return true;
}
void sent(const wifi_tx_info_t*,esp_now_send_status_t status){if(status!=ESP_NOW_SEND_SUCCESS)++mac_failures;sending=false;}
void receive(const esp_now_recv_info_t*info,const std::uint8_t*data,int len){
 if(!info||!info->src_addr||len<8||len>int(max_packet))return;
 Rx r;std::memcpy(r.mac,info->src_addr,6);r.size=len;std::memcpy(r.data,data,len);
 if(xQueueSend(received,&r,0)!=pdTRUE)rx_overflow=true;
}
bool hmac_key(const std::uint8_t*key,unsigned key_size,const std::uint8_t*data,unsigned size,std::uint8_t*out){
 const bool ok=mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),key,key_size,data,size,out)==0;
 if(!ok){fault_until=now()+3000000;last_error="Telemetry authentication operation failed";}return ok;
}
bool hmac(const std::uint8_t*key,const std::uint8_t*data,unsigned size,std::uint8_t*out){return hmac_key(key,16,data,size,out);}
bool prepare_stream(unsigned i){
 streams[i]=StreamPeer{};auto transcript=engine_key_transcript(engine_nonce,session_id);
 streams[i].key_ready=hmac(saved.peers[i].key,transcript.data(),transcript.size(),streams[i].key.data());return streams[i].key_ready;
}
void close_pairing(){
 if(waiting&&index_of(candidate.mac)<0)esp_now_del_peer(candidate.mac);
 deadline=0;waiting=false;approved=false;candidate=Peer{};
 std::memset(secret,0,sizeof(secret));std::memset(window,0,sizeof(window));std::memset(candidate_nonce,0,sizeof(candidate_nonce));
}
void open_pairing(){
 if(!storage_ok||!radio_ok)return;
 unsigned count=0;for(const auto&p:saved.peers)count+=occupied(p);
 if(count>=max_peers){last_error="Screen limit reached; unpair a screen first";return;}
 close_pairing();esp_fill_random(secret,16);esp_fill_random(window,16);deadline=now()+30000000;last_error="";
 char key[33]{},id[33]{};hex(secret,16,key);hex(window,16,id);
 ESP_LOGW(tag,"Pairing 30s. Enter setup key %s on screen. Window %s. Approve candidate with short PAIR press or service UI.",key,id);
}
void accept(){
 if(!waiting||approved||now()>=deadline)return;
 if(add(candidate,true)!=ESP_OK){fault_until=now()+3000000;last_error="Unable to install candidate key";close_pairing();return;}
 approved=true;candidate_started=0;
}
void handle(const Rx&r){
 const auto*p=r.data;
 if(valid(p,r.size,Ack,52)){
  const int i=index_of(r.mac);std::uint8_t proof[32]{};
  if(i>=0&&read32(p+16)==0&&read32(p+8)==session_id&&hmac(saved.peers[i].key,p,20,proof)&&same(proof,p+20,32)&&streams[i].sensor_sent.acknowledge(read32(p+12),now())){ack_seen[i]=true;acks[i]=now();}return;
 }
 if(valid(p,r.size,Capabilities,capability_size)){
  const int i=index_of(r.mac);std::uint8_t proof[32]{};
  if(i>=0&&streams[i].key_ready&&hmac(saved.peers[i].key,p,44,proof)&&same(proof,p+44,32))streams[i].capabilities.request(p,r.size,session_id);
  return;
 }
 if(valid(p,r.size,EngineAck,engine_ack_size)){
  const int i=index_of(r.mac);std::uint8_t proof[32]{};
  if(i>=0&&streams[i].key_ready&&streams[i].capabilities.engine()&&read32(p+8)==session_id&&read32(p+20)==0&&
     hmac_key(streams[i].key.data(),32,p,24,proof)&&same(proof,p+24,32)&&streams[i].engine_sent.acknowledge(read64(p+12),now())){ack_seen[i]=true;acks[i]=now();}
  return;
 }
 // READY uses the encrypted per-peer key and repeats the full pairing window.
 std::uint8_t ready_proof[32]{};
 if(valid(p,r.size,Accepted,56)&&waiting&&approved&&same(r.mac,candidate.mac,6)&&same(p+8,window,16)&&hmac(candidate.key,p,24,ready_proof)&&same(ready_proof,p+24,32)){
  Store next=saved;unsigned slot=0;while(slot<max_peers&&occupied(next.peers[slot]))++slot;
  if(slot==max_peers){last_error="Screen limit reached";close_pairing();return;}
  next.peers[slot]=candidate;
  if(!commit(next)){close_pairing();return;}
  saved=next;if(!prepare_stream(slot)){fault_until=now()+3000000;last_error="Engine telemetry key unavailable";}acks[slot]=now();ack_seen[slot]=false;waiting=false;close_pairing();if(streams[slot].key_ready)last_error="";return;
 }
 if(!valid(p,r.size,Request,96)||!deadline||now()>=deadline||!same(p+8,window,16)||!unicast(r.mac)||index_of(r.mac)>=0)return;
 if(waiting)return;
 // Name is fixed 24-byte NUL-padded printable ASCII, never HTML or a radio command.
 bool ended=false;for(unsigned i=0;i<24;++i){if(!p[40+i])ended=true;else if(ended||p[40+i]<32||p[40+i]>126)return;}if(!ended||!p[40])return;
 auto t=transcript(window,own,r.mac,p+24,p+40);std::uint8_t proof[32]{};
 if(!hmac(secret,t.data(),t.size(),proof)||!same(proof,p+64,32))return;
 auto key_data=t;key_data[0]='K';if(!hmac(secret,key_data.data(),key_data.size(),proof))return;
 candidate=Peer{};std::memcpy(candidate.mac,r.mac,6);std::memcpy(candidate.key,proof,16);std::memcpy(candidate.name,p+40,24);std::memcpy(candidate_nonce,p+24,16);
 waiting=true;approved=false;
 char mac[18]{};mac_text(candidate.mac,mac);ESP_LOGI(tag,"Candidate %s (%s). Confirm with PAIR or UI.",candidate.name,mac);
}
void command_run(const Command&c){
 if(!std::strcmp(c.action,"open")){open_pairing();return;}
 char id[33]{};hex(window,16,id);
 if(!std::strcmp(c.action,"cancel")){if(!std::strcmp(c.window,id))close_pairing();return;}
 if(!std::strcmp(c.action,"confirm")){char mac[18]{};mac_text(candidate.mac,mac);if(!std::strcmp(c.window,id)&&!std::strcmp(c.mac,mac))accept();return;}
 if(!std::strcmp(c.action,"unpair"))for(unsigned i=0;i<max_peers;++i){char mac[18]{};mac_text(saved.peers[i].mac,mac);if(occupied(saved.peers[i])&&!std::strcmp(mac,c.mac)){
  Store next=saved;next.peers[i]=Peer{};if(!commit(next))return;
  esp_now_del_peer(saved.peers[i].mac);saved=next;streams[i]=StreamPeer{};acks[i]=0;ack_seen[i]=false;last_error="";return;
 }}
}
void led_init(){
 rmt_tx_channel_config_t c{};c.gpio_num=GPIO_NUM_38;c.clk_src=RMT_CLK_SRC_DEFAULT;c.resolution_hz=10000000;c.mem_block_symbols=64;c.trans_queue_depth=1;
 ESP_ERROR_CHECK(rmt_new_tx_channel(&c,&led_channel));rmt_copy_encoder_config_t e{};ESP_ERROR_CHECK(rmt_new_copy_encoder(&e,&led_encoder));ESP_ERROR_CHECK(rmt_enable(led_channel));
}
void led(bool fault,bool pairing){
 // WS2812 GRB, low brightness. Fault takes precedence over pairing.
 const bool on=(now()/250000)%2==0;std::uint8_t rgb[3]={std::uint8_t(!fault&&!pairing?12:0),std::uint8_t(fault&&on?12:0),std::uint8_t(!fault&&pairing&&on?12:0)};
 rmt_symbol_word_t symbols[25]{};unsigned n=0;
 for(auto byte:rgb)for(int bit=7;bit>=0;--bit){bool one=byte&(1<<bit);auto&s=symbols[n++];s.level0=1;s.duration0=one?9:3;s.level1=0;s.duration1=one?3:9;}
 symbols[24].duration0=800;symbols[24].duration1=1;
 rmt_transmit_config_t tx{};ESP_ERROR_CHECK(rmt_transmit(led_channel,led_encoder,symbols,sizeof(symbols),&tx));ESP_ERROR_CHECK(rmt_tx_wait_all_done(led_channel,20));
}
void update_view(bool fault){
 auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"available",radio_ok);cJSON_AddBoolToObject(j,"storage_ok",storage_ok);cJSON_AddBoolToObject(j,"simulator",false);
 cJSON_AddBoolToObject(j,"pairing",deadline>now());cJSON_AddNumberToObject(j,"remaining_s",deadline>now()?(deadline-now()+999999)/1000000:0);cJSON_AddStringToObject(j,"error",last_error);
 cJSON_AddStringToObject(j,"led",fault?"red_blink":deadline?"blue_blink":"green");cJSON_AddNumberToObject(j,"channel",channel);cJSON_AddNumberToObject(j,"max_peers",max_peers);
 cJSON_AddNumberToObject(j,"engine_schema",engine_schema);cJSON_AddNumberToObject(j,"engine_packet_bytes",engine_size);cJSON_AddNumberToObject(j,"engine_packets_submitted",engine_packets);cJSON_AddNumberToObject(j,"sensor_packets_submitted",sensor_packets);cJSON_AddNumberToObject(j,"capability_replies_submitted",capability_replies);cJSON_AddNumberToObject(j,"mac_send_failures",mac_failure_count);
 const auto age=transmitted_age(live.engine_sample_age,live.stamp,now());if(age==UINT32_MAX)cJSON_AddNullToObject(j,"engine_sample_age_ms");else cJSON_AddNumberToObject(j,"engine_sample_age_ms",age);
 cJSON_AddStringToObject(j,"engine_data_source",live.engine.source==engine::DataSource::Target?"target_control_observation":"no_observation");
 char mac[18]{};mac_text(own,mac);cJSON_AddStringToObject(j,"mac",mac);
 char id[33]{},key[33]{};if(deadline){hex(window,16,id);hex(secret,16,key);}cJSON_AddStringToObject(j,"window",id);cJSON_AddStringToObject(j,"setup_key",key);
 if(waiting){auto*c=cJSON_AddObjectToObject(j,"candidate");mac_text(candidate.mac,mac);cJSON_AddStringToObject(c,"mac",mac);cJSON_AddStringToObject(c,"name",candidate.name);cJSON_AddBoolToObject(c,"approved",approved);}
 auto*a=cJSON_AddArrayToObject(j,"peers");for(unsigned i=0;i<max_peers;++i)if(occupied(saved.peers[i])){
  auto*p=cJSON_CreateObject();mac_text(saved.peers[i].mac,mac);cJSON_AddStringToObject(p,"mac",mac);cJSON_AddStringToObject(p,"name",saved.peers[i].name);
  const auto&cap=streams[i].capabilities;const bool connected=ack_seen[i]&&now()-acks[i]<3000000;
  const bool blocked=cap.engine()&&live.engine.has(engine::Present)&&!engine_schema_supports(cap.schema(),live.engine);
  cJSON_AddBoolToObject(p,"connected",connected);cJSON_AddBoolToObject(p,"engine_telemetry",cap.engine());cJSON_AddNumberToObject(p,"engine_schema",cap.schema());
  cJSON_AddBoolToObject(p,"engine_telemetry_blocked",blocked);cJSON_AddBoolToObject(p,"engine_upgrade_needed",blocked&&cap.schema()<engine_schema);
  cJSON_AddStringToObject(p,"engine_block_reason",blocked?"Current strategy or fault requires a newer engine schema":"");
  cJSON_AddNumberToObject(p,"capability_counter",cap.counter());cJSON_AddNumberToObject(p,"last_ack_ms",acks[i]?(now()-acks[i])/1000:-1);cJSON_AddItemToArray(a,p);
 }
 xSemaphoreTake(view_mutex,portMAX_DELAY);cJSON_Delete(view);view=j;xSemaphoreGive(view_mutex);
}
bool init_wifi(){
 wifi_mode_t mode{};
 if(esp_wifi_get_mode(&mode)==ESP_ERR_WIFI_NOT_INIT){
  if(esp_netif_init()!=ESP_OK||esp_event_loop_create_default()!=ESP_OK)return false;
  esp_netif_create_default_wifi_sta();wifi_init_config_t c=WIFI_INIT_CONFIG_DEFAULT();
  if(esp_wifi_init(&c)!=ESP_OK||esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK||esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK||esp_wifi_start()!=ESP_OK)return false;
 }
 return esp_wifi_set_channel(channel,WIFI_SECOND_CHAN_NONE)==ESP_OK&&esp_wifi_set_ps(WIFI_PS_NONE)==ESP_OK;
}
void task(void*){
 led_init();gpio_config_t button{};button.pin_bit_mask=1ULL<<0;button.mode=GPIO_MODE_INPUT;button.pull_up_en=GPIO_PULLUP_ENABLE;ESP_ERROR_CHECK(gpio_config(&button));
 storage_ok=restore();if(!storage_ok){saved=Store{};esp_fill_random(saved.pmk,16);last_error="Peer storage unavailable or invalid; existing data not erased";}
 radio_ok=init_wifi()&&esp_wifi_get_mac(WIFI_IF_STA,own)==ESP_OK&&esp_now_init()==ESP_OK;
 if(radio_ok){radio_ok=esp_now_set_pmk(saved.pmk)==ESP_OK&&esp_now_register_send_cb(sent)==ESP_OK&&esp_now_register_recv_cb(receive)==ESP_OK;}
 if(radio_ok){Peer b;std::memcpy(b.mac,broadcast,6);radio_ok=add(b,false)==ESP_OK;}
 if(radio_ok&&storage_ok)for(const auto&p:saved.peers)if(occupied(p)&&add(p,true)!=ESP_OK)radio_ok=false;
 if(!radio_ok)last_error="ESP-NOW initialization failed";else if(storage_ok)last_error="";
 session_id=esp_random();if(!session_id)session_id=1;esp_fill_random(engine_nonce,sizeof(engine_nonce));
 for(unsigned i=0;i<max_peers;++i)if(occupied(saved.peers[i])&&!prepare_stream(i))radio_ok=false;
 Button key;std::int64_t next_send=0,last_view=0,last_led=0;unsigned peer_cursor=0,round=0;std::int64_t first_live=0;
 while(true){
  const auto stamp=now();if(xQueueReceive(samples,&live,0)==pdTRUE&&!first_live)first_live=stamp;
  if(deadline&&stamp>=deadline)close_pairing();
  Command c;for(unsigned i=0;i<4&&xQueueReceive(commands,&c,0)==pdTRUE;++i)command_run(c);
  if(radio_ok){Rx r;for(unsigned i=0;i<4&&xQueueReceive(received,&r,0)==pdTRUE;++i)handle(r);}
  const auto action=key.poll(gpio_get_level(GPIO_NUM_0)==0,stamp/1000);if(action==Button::Open)open_pairing();if(action==Button::Confirm)accept();
  if(radio_ok&&!sending){
   if(approved&&stamp-candidate_started>=250000){std::uint8_t a[56]{};header(a,Accepted,sizeof(a));std::memcpy(a+8,window,16);hmac(candidate.key,a,24,a+24);send(candidate.mac,a,sizeof(a));candidate_started=stamp;}
   else if(deadline&&!waiting&&stamp-last_beacon>=500000){std::uint8_t b[24]{};header(b,Beacon,sizeof(b));std::memcpy(b+8,window,16);send(broadcast,b,sizeof(b));last_beacon=stamp;}
   else if(stamp>=next_send){
    // One transmission at a time, no accumulated backlog. Four slots per 50 ms.
    const unsigned i=peer_cursor;peer_cursor=(peer_cursor+1)%max_peers;next_send+=12500;if(stamp-next_send>12500)next_send=stamp+12500;if(!peer_cursor)++round;
    if(occupied(saved.peers[i])){
     auto& stream=streams[i];const auto tx_now=now();
     if(stream.capabilities.pending()&&stamp-stream.last_reply>=250000){
      std::uint8_t packet[capability_reply_size];stream.capabilities.reply(packet,session_id,engine_nonce,engine_sequence,tx_now);
      if(hmac(saved.peers[i].key,packet,76,packet+76)&&send(saved.peers[i].mac,packet,sizeof(packet))){stream.capabilities.sent();stream.last_reply=tx_now;++capability_replies;}
     }else if(!live.stamp||tx_now<live.stamp){
      // Negotiation remains available before the first sensor observation.
     }else if(round%10==0&&tx_now-live.stamp<1000000){
      const unsigned sensor=(round/10)%6;std::uint8_t packet[98];std::memcpy(packet,live.meta[sensor],98);u32(packet+94,session_id);send(saved.peers[i].mac,packet,sizeof(packet));
     }else if(stream.capabilities.engine()&&round%10!=1&&live.engine.has(engine::Present)&&engine_schema_supports(stream.capabilities.schema(),live.engine)){
      if(engine_sequence==UINT64_MAX){last_error="Engine telemetry sequence exhausted; restart required";fault_until=stamp+3000000;}
      else{
       std::uint8_t packet[engine_size];const auto sequence=++engine_sequence;
       if(engine_body(packet,live.engine,session_id,sequence,transmitted_age(live.engine_sample_age,live.stamp,tx_now),transmitted_age(live.engine_control_age,live.stamp,tx_now),transmitted_age(live.worker_age,live.stamp,tx_now),tx_now,stream.capabilities.schema())&&
          hmac_key(stream.key.data(),32,packet,engine_body_size,packet+engine_body_size)&&send(saved.peers[i].mac,packet,sizeof(packet))){stream.engine_sent.submitted(sequence,tx_now);++engine_packets;}
      }
     }else if(tx_now-live.stamp<1000000){
      std::uint8_t packet[88];std::memcpy(packet,live.data,sizeof(packet));u32(packet+8,session_id);u32(packet+12,++sequence);u32(packet+16,std::uint32_t(live.stamp/1000));u32(packet+84,std::uint32_t((tx_now-live.stamp)/1000));
      if(send(saved.peers[i].mac,packet,sizeof(packet))){stream.sensor_sent.submitted(sequence,tx_now);++sensor_packets;}
     }
    }
   }
  }
  if(rx_overflow.exchange(false))fault_until=stamp+3000000;
  const auto failed=mac_failures.exchange(0);if(failed){mac_failure_count+=failed;fault_until=stamp+3000000;last_error="ESP-NOW MAC send failure";}
  bool fault=!radio_ok||!storage_ok||live.fault||!live.stamp||stamp-live.stamp>1000000||stamp<fault_until;
  for(unsigned i=0;i<max_peers;++i)if(occupied(saved.peers[i])&&first_live&&stamp-(acks[i]?acks[i]:first_live)>3000000)fault=true;
  if(stamp-last_led>=100000){led(fault,deadline!=0);last_led=stamp;}
  if(stamp-last_view>=100000){update_view(fault);last_view=stamp;}
  vTaskDelay(pdMS_TO_TICKS(5));
 }
}
}
void start(){
 samples=xQueueCreate(1,sizeof(Live));received=xQueueCreate(12,sizeof(Rx));commands=xQueueCreate(8,sizeof(Command));view_mutex=xSemaphoreCreateMutex();configASSERT(samples&&received&&commands&&view_mutex);
 configASSERT(xTaskCreate(task,"ecu_now",6144,nullptr,2,nullptr)==pdPASS);
}
void publish(const web::Sample&s,const config::Config&c,const std::array<double,6>&filtered){
 if(!samples)return;
 Live l;l.stamp=now();const auto gp_now=engine_target::clock_us();l.engine=s.engine;
 l.engine_sample_age=engine::data_age_us(s.engine,s.engine.sampled_us,gp_now);l.engine_control_age=engine::data_age_us(s.engine,s.engine.control_us,gp_now);
 if(s.engine.worker_sequence||s.engine.worker_observed_us)l.worker_age=engine::data_age_us(s.engine,s.engine.worker_observed_us,gp_now);
 l.fault=!s.adc_ok||s.overflow||s.timing_fault;
 if(s.engine.idle_available&&(s.engine.idle_flags&idle::Enabled)&&s.engine.idle_state==static_cast<unsigned>(idle::State::Fault))l.fault=true;
 header(l.data,Telemetry,88);u32(l.data+20,c.revision);
 // Always bit 4: outputs inhibited. No received packet can change it.
 u16(l.data+24,(s.adc_ok?1:0)|(s.safe?2:0)|(s.interlock?4:0)|(s.synced?8:0)|16|(s.overflow?32:0));
 const double rail=s.raw[7]*c.adc_reference_v/4095/.6;
 for(unsigned i=0;i<8;++i)u16(l.data+28+2*i,s.raw[i]);
 f32(l.data+44,s.rpm);f32(l.data+48,s.raw[6]*c.adc_reference_v/4095*13);f32(l.data+52,rail);
 u32(l.data+80,std::uint32_t(s.can_frames));
 for(unsigned i=0;i<6;++i){auto instant=config::convert(c.sensors[i],s.raw[i]*c.adc_reference_v/4095/.6,s.raw[i]*c.adc_reference_v/4095,rail);auto r=config::convert(c.sensors[i],filtered[i],filtered[i]*.6,rail);
  const bool valid=s.adc_ok&&instant.valid&&r.valid;if(c.sensors[i].confirmed&&!valid)l.fault=true;if(valid)l.data[26]|=1<<i;if(c.sensors[i].confirmed)l.data[27]|=1<<i;f32(l.data+56+4*i,valid?r.value:NAN);
  auto*m=l.meta[i];header(m,Metadata,98);u32(m+8,c.revision);m[12]=i;m[13]=std::uint8_t(c.sensors[i].mode);std::memcpy(m+14,c.sensors[i].unit,16);std::memcpy(m+30,c.sensors[i].label,64);u32(m+94,session_id);
 }
 if(s.adc_ok&&(rail<4||rail>5.3))l.fault=true;
 if(s.engine.has(engine::Present)&&(!s.engine.has(engine::StorageOk)||(s.rpm>0&&(s.engine.controller_faults||l.engine_control_age>1000000))))l.fault=true;
 if(l.fault)l.data[24]|=64;
 xQueueOverwrite(samples,&l);
}
cJSON* status(){
 if(!view_mutex){auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"available",false);return j;}
 xSemaphoreTake(view_mutex,portMAX_DELAY);auto*j=view?cJSON_Duplicate(view,true):cJSON_CreateObject();xSemaphoreGive(view_mutex);return j;
}
bool command(const char*action,const char*mac,const char*window_id){
 if(!commands||std::strlen(action)>=12||std::strlen(mac)>=18||std::strlen(window_id)>=33)return false;
 if(std::strcmp(action,"open")&&std::strcmp(action,"cancel")&&std::strcmp(action,"confirm")&&std::strcmp(action,"unpair"))return false;
 Command c;std::strcpy(c.action,action);std::strcpy(c.mac,mac);std::strcpy(c.window,window_id);return xQueueSend(commands,&c,0)==pdTRUE;
}
}
#endif
