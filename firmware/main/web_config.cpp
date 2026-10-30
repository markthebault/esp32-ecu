#include "ecu/web_config.hpp"
#include "ecu/espnow.hpp"
#include "ecu/pins.hpp"
#include "config_json.hpp"
#include "web_assets.hpp"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#ifndef ECU_CONFIG_WEB
#define ECU_CONFIG_WEB 0
#endif
#if ECU_CONFIG_WEB && ECU_BENCH_PULSES
#error Configuration service must never be combined with bench output pulses
#endif
#if ECU_CONFIG_WEB
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "esp_random.h"
#endif
namespace ecu::web {
namespace {
constexpr const char* tag="ecu_config";
SemaphoreHandle_t mutex;
config::Config active;
Sample latest;
std::array<double,6> filtered{};
std::int64_t last_sample{};
std::uint32_t filtered_revision{};
std::string document;
bool storage_ok=false;
const char* storage_message="not initialized";
#if ECU_CONFIG_WEB
char token[33]{};
std::int64_t started{};
#endif
bool parse_text(const char* text,config::Config& out){
 if(!safe_json(text,std::strlen(text)))return false;
 const char* end=nullptr;auto*j=cJSON_ParseWithOpts(text,&end,true);
 const bool ok=j&&parse(j,out);cJSON_Delete(j);return ok;
}
#if ECU_CONFIG_WEB
void numeric(cJSON*j,const char*k,double v){if(std::isfinite(v))cJSON_AddNumberToObject(j,k,v);else cJSON_AddNullToObject(j,k);}
esp_err_t send_json(httpd_req_t*r,cJSON*j,const char*status="200 OK"){
 char*s=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!s)return httpd_resp_send_err(r,HTTPD_500_INTERNAL_SERVER_ERROR,"allocation failed");
 httpd_resp_set_status(r,status);httpd_resp_set_type(r,"application/json");httpd_resp_set_hdr(r,"Cache-Control","no-store");httpd_resp_set_hdr(r,"X-Content-Type-Options","nosniff");
 auto err=httpd_resp_send(r,s,HTTPD_RESP_USE_STRLEN);cJSON_free(s);return err;
}
esp_err_t message(httpd_req_t*r,const char*s,const char*status){auto*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"error",s);return send_json(r,j,status);}
bool authorized(httpd_req_t*r){
 char supplied[48]{};if(httpd_req_get_hdr_value_str(r,"X-ECU-Token",supplied,sizeof(supplied))!=ESP_OK||std::strcmp(supplied,token))return false;
 // Same-origin browser requests only. Non-browser tools can omit Origin but need the boot token.
 if(httpd_req_get_hdr_value_len(r,"Origin")){
  char origin[160]{},host[128]{},expected[160]{};
  if(httpd_req_get_hdr_value_str(r,"Origin",origin,sizeof(origin))!=ESP_OK||httpd_req_get_hdr_value_str(r,"Host",host,sizeof(host))!=ESP_OK)return false;
  std::snprintf(expected,sizeof(expected),"http://%s",host);if(std::strcmp(origin,expected))return false;
 }
 return true;
}
esp_err_t index_get(httpd_req_t*r){
 httpd_resp_set_type(r,"text/html");httpd_resp_set_hdr(r,"Cache-Control","no-store");
 httpd_resp_set_hdr(r,"Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");
 return httpd_resp_send(r,assets::index,HTTPD_RESP_USE_STRLEN);
}
esp_err_t manual_get(httpd_req_t*r){httpd_resp_set_type(r,"application/json");return httpd_resp_send(r,assets::manual,HTTPD_RESP_USE_STRLEN);}
esp_err_t guide_get(httpd_req_t*r){httpd_resp_set_type(r,"application/json");return httpd_resp_send(r,assets::guide,HTTPD_RESP_USE_STRLEN);}
esp_err_t defaults_get(httpd_req_t*r){httpd_resp_set_type(r,"application/json");return httpd_resp_send(r,assets::defaults,HTTPD_RESP_USE_STRLEN);}
esp_err_t session_get(httpd_req_t*r){auto*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"token",token);cJSON_AddBoolToObject(j,"simulator",false);return send_json(r,j);}
esp_err_t config_get(httpd_req_t*r){
 xSemaphoreTake(mutex,portMAX_DELAY);std::string copy=document;xSemaphoreGive(mutex);
 httpd_resp_set_type(r,"application/json");httpd_resp_set_hdr(r,"Cache-Control","no-store");return httpd_resp_send(r,copy.c_str(),copy.size());
}
esp_err_t config_put(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected. Reload this page.","403 Forbidden");
 if(!storage_ok)return message(r,"NVS storage unavailable. Inspect the UART log; no profile was saved.","503 Service Unavailable");
 if(r->content_len<=0||r->content_len>16384)return message(r,"Profile body must be 1-16384 bytes.","413 Content Too Large");
 char type[80]{};httpd_req_get_hdr_value_str(r,"Content-Type",type,sizeof(type));
 if(std::strncmp(type,"application/json",16))return message(r,"Use application/json.","415 Unsupported Media Type");
 std::string body(static_cast<std::size_t>(r->content_len),'\0');int received=0;
 while(received<r->content_len){int n=httpd_req_recv(r,body.data()+received,r->content_len-received);if(n<=0)return ESP_FAIL;received+=n;}
 if(!safe_json(body.c_str(),body.size()))return message(r,"Invalid profile envelope or excessive JSON nesting.","400 Bad Request");
 config::Config candidate;const char*end=nullptr;auto*j=cJSON_ParseWithOpts(body.c_str(),&end,true);
 if(!j||!parse(j,candidate)){cJSON_Delete(j);return message(r,"Profile violates schema or calibration limits. Check every field.","422 Unprocessable Entity");}
 xSemaphoreTake(mutex,portMAX_DELAY);const auto revision=active.revision;xSemaphoreGive(mutex);
 if(candidate.revision!=revision||revision==UINT32_MAX){cJSON_Delete(j);return message(r,"Profile revision changed. Export edits, reload, then reapply them.","409 Conflict");}
 candidate.revision++;cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"revision"),candidate.revision);
 char*encoded=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!encoded)return message(r,"Allocation failed.","500 Internal Server Error");
 nvs_handle_t store{};auto err=nvs_open("ecu_config",NVS_READWRITE,&store);
 if(err==ESP_OK){err=nvs_set_str(store,"profile",encoded);if(err==ESP_OK)err=nvs_commit(store);nvs_close(store);}
 if(err!=ESP_OK){cJSON_free(encoded);ESP_LOGE(tag,"Profile commit failed: %s",esp_err_to_name(err));return message(r,"Flash commit failed. Previous runtime profile remains active.","507 Insufficient Storage");}
 xSemaphoreTake(mutex,portMAX_DELAY);active=candidate;document=encoded;storage_message="saved";xSemaphoreGive(mutex);cJSON_free(encoded);
 return config_get(r);
}
esp_err_t status_get(httpd_req_t*r){
 config::Config c;Sample s;std::array<double,6> f;std::int64_t stamp;const char*storage;
 xSemaphoreTake(mutex,portMAX_DELAY);c=active;s=latest;f=filtered;stamp=last_sample;storage=storage_message;xSemaphoreGive(mutex);
 const auto now=esp_timer_get_time();const bool fresh=stamp&&now-stamp<1000000;
 auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"simulator",false);cJSON_AddStringToObject(j,"firmware","A3 configuration monitor");
 numeric(j,"uptime_s",(now-started)/1e6);numeric(j,"sample_age_ms",stamp?(now-stamp)/1000.0:-1);cJSON_AddBoolToObject(j,"fresh",fresh);numeric(j,"revision",c.revision);
 cJSON_AddBoolToObject(j,"storage_ok",storage_ok);cJSON_AddStringToObject(j,"storage",storage);cJSON_AddBoolToObject(j,"adc_ok",s.adc_ok);cJSON_AddBoolToObject(j,"safe",s.safe);cJSON_AddBoolToObject(j,"interlock",s.interlock);
 cJSON_AddBoolToObject(j,"overflow",s.overflow);cJSON_AddBoolToObject(j,"synced",s.synced);numeric(j,"rpm",s.rpm);numeric(j,"can_frames",s.can_frames);numeric(j,"cam_edges",s.cam_edges);numeric(j,"crank_edges",s.crank_edges);numeric(j,"crank_level",s.crank_level);numeric(j,"cam_level",s.cam_level);
 cJSON_AddBoolToObject(j,"arm",false);cJSON_AddStringToObject(j,"output_state","All outputs OFF");
 const double supply=s.raw[7]*c.adc_reference_v/4095.0/.6;
 numeric(j,"sensor_5v",supply);numeric(j,"battery_v",s.raw[6]*c.adc_reference_v/4095.0*13);
 auto*a=cJSON_AddArrayToObject(j,"raw_adc");for(auto n:s.raw)cJSON_AddItemToArray(a,cJSON_CreateNumber(n));
 a=cJSON_AddArrayToObject(j,"sensors");for(unsigned i=0;i<6;++i){const auto&sc=c.sensors[i];const double av=s.raw[i]*c.adc_reference_v/4095.0,sv=av/.6;
  auto reading=config::convert(sc,sv,av,supply);auto smooth=config::convert(sc,f[i],f[i]*.6,supply);auto*o=cJSON_CreateObject();cJSON_AddStringToObject(o,"id",sc.id);numeric(o,"raw",s.raw[i]);numeric(o,"adc_v",av);numeric(o,"sensor_v",sv);
  const bool good=fresh&&s.adc_ok&&reading.valid&&smooth.valid;numeric(o,"value",good?smooth.value:NAN);cJSON_AddBoolToObject(o,"valid",good);cJSON_AddBoolToObject(o,"confirmed",sc.confirmed);
  cJSON_AddStringToObject(o,"fault",!fresh?"stale sample":!s.adc_ok?"ADC transfer failed":!reading.valid?reading.fault:!smooth.valid?smooth.fault:"ok");cJSON_AddItemToArray(a,o);
 }
 return send_json(r,j);
}
esp_err_t radio_get(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 return send_json(r,radio::status());
}
esp_err_t radio_post(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 if(r->content_len<=0||r->content_len>256)return message(r,"Radio command must be 1-256 bytes.","413 Content Too Large");
 char type[80]{};httpd_req_get_hdr_value_str(r,"Content-Type",type,sizeof(type));
 if(std::strncmp(type,"application/json",16))return message(r,"Use application/json.","415 Unsupported Media Type");
 char body[257]{};int n=0;while(n<r->content_len){int got=httpd_req_recv(r,body+n,r->content_len-n);if(got<=0)return ESP_FAIL;n+=got;}
 if(!safe_json(body,n))return message(r,"Invalid command.","400 Bad Request");
 auto*j=cJSON_Parse(body);if(!j||!cJSON_IsObject(j)){cJSON_Delete(j);return message(r,"Invalid command.","422 Unprocessable Entity");}
 auto*a=cJSON_GetObjectItemCaseSensitive(j,"action");auto*m=cJSON_GetObjectItemCaseSensitive(j,"mac");auto*w=cJSON_GetObjectItemCaseSensitive(j,"window");
 const bool ok=cJSON_IsString(a)&&(!m||cJSON_IsString(m))&&(!w||cJSON_IsString(w))&&radio::command(a->valuestring,m?m->valuestring:"",w?w->valuestring:"");
 cJSON_Delete(j);if(!ok)return message(r,"Invalid radio command or queue busy.","422 Unprocessable Entity");
 auto*out=cJSON_CreateObject();cJSON_AddBoolToObject(out,"queued",true);return send_json(r,out,"202 Accepted");
}
void service_task(){
 if(gpio_get_level(static_cast<gpio_num_t>(pins::interlock))){ESP_LOGE(tag,"Service AP refused: open J3, then reboot.");return;}
 ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());esp_netif_create_default_wifi_ap();esp_netif_create_default_wifi_sta();
 wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();ESP_ERROR_CHECK(esp_wifi_init(&init));ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
 std::uint8_t mac[6];ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_AP,mac));wifi_config_t wifi{};
 std::snprintf(reinterpret_cast<char*>(wifi.ap.ssid),sizeof(wifi.ap.ssid),"ECU-Service-%02X%02X",mac[4],mac[5]);
 const auto random=esp_random();std::snprintf(reinterpret_cast<char*>(wifi.ap.password),sizeof(wifi.ap.password),"ECU%08lX%04lX",static_cast<unsigned long>(random),static_cast<unsigned long>(esp_random()&0xffff));
 wifi.ap.ssid_len=std::strlen(reinterpret_cast<char*>(wifi.ap.ssid));wifi.ap.channel=6;wifi.ap.authmode=WIFI_AUTH_WPA2_PSK;wifi.ap.max_connection=2;wifi.ap.pmf_cfg.required=true;
 ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP,&wifi));ESP_ERROR_CHECK(esp_wifi_start());
 for(unsigned i=0;i<4;++i)std::snprintf(token+i*8,9,"%08lX",static_cast<unsigned long>(esp_random()));
 httpd_config_t http=HTTPD_DEFAULT_CONFIG();http.stack_size=12288;http.max_uri_handlers=10;http.lru_purge_enable=true;http.recv_wait_timeout=5;http.send_wait_timeout=5;
 httpd_handle_t server{};ESP_ERROR_CHECK(httpd_start(&server,&http));
 const httpd_uri_t routes[]={
  {"/api/radio",HTTP_GET,radio_get,nullptr},{"/api/radio",HTTP_POST,radio_post,nullptr},
  {"/",HTTP_GET,index_get,nullptr},{"/api/session",HTTP_GET,session_get,nullptr},{"/api/guide",HTTP_GET,guide_get,nullptr},{"/api/manual",HTTP_GET,manual_get,nullptr},
  {"/api/defaults",HTTP_GET,defaults_get,nullptr},{"/api/config",HTTP_GET,config_get,nullptr},{"/api/config",HTTP_PUT,config_put,nullptr},{"/api/status",HTTP_GET,status_get,nullptr}};
 for(const auto&route:routes)ESP_ERROR_CHECK(httpd_register_uri_handler(server,&route));
 ESP_LOGW(tag,"BENCH ONLY. J3 open. No actuators. SSID=%s password=%s URL=http://192.168.4.1",wifi.ap.ssid,wifi.ap.password);
}
#endif
}
void init(){
 mutex=xSemaphoreCreateMutex();configASSERT(mutex);
 configASSERT(parse_text(assets::defaults,active));document=assets::defaults;
 const auto err=nvs_flash_init();storage_ok=err==ESP_OK;storage_message=storage_ok?"defaults; no saved profile":"NVS init failed; inspect UART";
 if(!storage_ok){ESP_LOGE(tag,"NVS init failed: %s. Partition NOT erased.",esp_err_to_name(err));return;}
 nvs_handle_t store{};auto opened=nvs_open("ecu_config",NVS_READONLY,&store);
 if(opened==ESP_ERR_NVS_NOT_FOUND)return;
 if(opened!=ESP_OK){storage_ok=false;storage_message="NVS namespace read failed";return;}
 std::size_t size=0;auto result=nvs_get_str(store,"profile",nullptr,&size);
 if(result==ESP_OK&&size>0&&size<=16385){std::string saved(size,'\0');result=nvs_get_str(store,"profile",saved.data(),&size);config::Config c;
  if(result==ESP_OK&&parse_text(saved.c_str(),c)){active=c;document=saved.c_str();storage_message="loaded from NVS";}
  else{storage_ok=false;storage_message="saved profile invalid; defaults active; inspect UART";}
 }else if(result!=ESP_ERR_NVS_NOT_FOUND){storage_ok=false;storage_message="profile read failed or too large";}
 nvs_close(store);
}
void start_service(){
#if ECU_CONFIG_WEB
 started=esp_timer_get_time();service_task();
#endif
}
bool try_config(config::Config&out){if(xSemaphoreTake(mutex,0)!=pdTRUE)return false;out=active;xSemaphoreGive(mutex);return true;}
void publish(const Sample&s){
 if(xSemaphoreTake(mutex,0)!=pdTRUE)return;
 const auto now=esp_timer_get_time();
 const double dt=last_sample?std::max(0.0,(now-last_sample)/1000.0):0;
 for(unsigned i=0;i<6;++i){const double v=s.raw[i]*active.adc_reference_v/4095.0/.6;
  if(!last_sample||filtered_revision!=active.revision||active.sensors[i].filter_ms<=0)filtered[i]=v;
  else filtered[i]+=dt/(active.sensors[i].filter_ms+dt)*(v-filtered[i]);
 }
 filtered_revision=active.revision;latest=s;last_sample=now;radio::publish(s,active,filtered);xSemaphoreGive(mutex);
}
}
