#include "ecu/web_config.hpp"
#include "ecu/espnow.hpp"
#include "ecu/pins.hpp"
#include "ecu/engine_service.hpp"
#include "ecu/engine_target.hpp"
#include "ecu/engine_tuning.hpp"
#include "ecu/engine_log_service.hpp"
#include "ecu/engine_log_json.hpp"
#include "ecu/engine_log_msl.hpp"
#include "ecu/heap_object.hpp"
#include "ecu/trigger_log_json.hpp"
#include "config_json.hpp"
#include "ecu/config_storage.hpp"
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
#include <memory>
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
bool parse_text(const char* text,config::Config& out,std::string*canonical=nullptr){
 if(!safe_json(text,std::strlen(text)))return false;
 const char* end=nullptr;auto*j=cJSON_ParseWithOpts(text,&end,true);
 bool ok=j&&parse(j,out);
 if(ok&&canonical){
  ok=upgrade_profile_document(j);char*encoded=ok?cJSON_PrintUnformatted(j):nullptr;
  ok=encoded&&std::strlen(encoded)<=16384;if(ok)*canonical=encoded;cJSON_free(encoded);
 }
 cJSON_Delete(j);return ok;
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
esp_err_t trigger_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");httpd_resp_set_hdr(r,"Cache-Control","no-store");return httpd_resp_send(r,assets::trigger_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t tuning_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::tuning_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t boost_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::boost_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t flex_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::flex_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t secondary_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::secondary_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t load_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::load_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t transient_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::transient_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t idle_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::idle_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t profile_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::profile_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t cylinder_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");return httpd_resp_send(r,assets::cylinder_js,HTTPD_RESP_USE_STRLEN);}
esp_err_t engine_log_script_get(httpd_req_t*r){httpd_resp_set_type(r,"application/javascript");httpd_resp_set_hdr(r,"Cache-Control","no-store");return httpd_resp_send(r,assets::engine_log_js,HTTPD_RESP_USE_STRLEN);}
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
 if(!upgrade_profile_document(j)){cJSON_Delete(j);return message(r,"Profile migration allocation failed.","500 Internal Server Error");}
 xSemaphoreTake(mutex,portMAX_DELAY);const auto revision=active.revision;xSemaphoreGive(mutex);
 if(candidate.revision!=revision||revision==UINT32_MAX){cJSON_Delete(j);return message(r,"Profile revision changed. Export edits, reload, then reapply them.","409 Conflict");}
 candidate.revision++;cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"revision"),candidate.revision);
 char*encoded=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!encoded)return message(r,"Allocation failed.","500 Internal Server Error");
 if(std::strlen(encoded)>16384){cJSON_free(encoded);return message(r,"Migrated profile exceeds 16 KiB.","413 Content Too Large");}
 engine_target::begin_configuration();
 const auto err=config_storage::save(encoded,std::strlen(encoded));
 if(err!=ESP_OK){
  cJSON_free(encoded);engine_target::finish_configuration(0,revision);
  storage_ok=false;storage_message="profile commit failed; writes blocked until restart/inspection";
  ESP_LOGE(tag,"Profile commit failed: %s",esp_err_to_name(err));
  return message(r,"Flash commit failed. Previous runtime profile remains active; further saves are blocked until restart/inspection.","507 Insufficient Storage");
 }
 xSemaphoreTake(mutex,portMAX_DELAY);active=candidate;document=encoded;storage_message="saved";xSemaphoreGive(mutex);cJSON_free(encoded);
 engine_target::finish_configuration(0,candidate.revision);
 return config_get(r);
}
esp_err_t status_get(httpd_req_t*r){
 config::Config c;Sample s;std::array<double,6> f;std::int64_t stamp;const char*storage;
 xSemaphoreTake(mutex,portMAX_DELAY);c=active;s=latest;f=filtered;stamp=last_sample;storage=storage_message;xSemaphoreGive(mutex);
 const auto now=esp_timer_get_time();const bool fresh=stamp&&now-stamp<1000000;
 auto*j=cJSON_CreateObject();cJSON_AddBoolToObject(j,"simulator",false);cJSON_AddStringToObject(j,"firmware","A3 configuration monitor");
 numeric(j,"uptime_s",(now-started)/1e6);numeric(j,"sample_age_ms",stamp?(now-stamp)/1000.0:-1);cJSON_AddBoolToObject(j,"fresh",fresh);numeric(j,"revision",c.revision);
 cJSON_AddBoolToObject(j,"storage_ok",storage_ok);cJSON_AddStringToObject(j,"storage",storage);cJSON_AddBoolToObject(j,"adc_ok",s.adc_ok);cJSON_AddBoolToObject(j,"safe",s.safe);cJSON_AddBoolToObject(j,"interlock",s.interlock);
 cJSON_AddBoolToObject(j,"overflow",s.overflow);cJSON_AddBoolToObject(j,"timing_fault",s.timing_fault);cJSON_AddBoolToObject(j,"synced",s.synced);numeric(j,"rpm",s.rpm);numeric(j,"can_frames",s.can_frames);numeric(j,"cam_edges",s.cam_edges);numeric(j,"crank_edges",s.crank_edges);numeric(j,"crank_level",s.crank_level);numeric(j,"cam_level",s.cam_level);
 cJSON_AddBoolToObject(j,"arm",false);cJSON_AddStringToObject(j,"output_state","All outputs OFF");
 const double supply=s.raw[7]*c.adc_reference_v/4095.0/.6;
 numeric(j,"sensor_5v",supply);numeric(j,"battery_v",s.raw[6]*c.adc_reference_v/4095.0*13);
 auto*a=cJSON_AddArrayToObject(j,"raw_adc");for(auto n:s.raw)cJSON_AddItemToArray(a,cJSON_CreateNumber(n));
 a=cJSON_AddArrayToObject(j,"sensors");for(unsigned i=0;i<6;++i){const auto&sc=c.sensors[i];const double av=s.raw[i]*c.adc_reference_v/4095.0,sv=av/.6;
  auto reading=config::convert(sc,sv,av,supply);auto smooth=sc.ratiometric?config::convert(sc,sv,av,supply,&f[i]):config::convert(sc,f[i],f[i]*.6,supply);auto*o=cJSON_CreateObject();cJSON_AddStringToObject(o,"id",sc.id);numeric(o,"raw",s.raw[i]);numeric(o,"adc_v",av);numeric(o,"sensor_v",sv);
  cJSON_AddBoolToObject(o,"ratiometric",sc.ratiometric);numeric(o,"transfer_voltage_v",reading.transfer_v);numeric(o,"display_transfer_voltage_v",smooth.transfer_v);
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
esp_err_t engine_defaults_get(httpd_req_t*r){httpd_resp_set_type(r,"application/json");return httpd_resp_send(r,assets::engine_defaults,HTTPD_RESP_USE_STRLEN);}
esp_err_t engine_config_get(httpd_req_t*r){auto s=engine_service::tune_json();httpd_resp_set_type(r,"application/json");return httpd_resp_send(r,s.c_str(),s.size());}
esp_err_t engine_status_get(httpd_req_t*r){return send_json(r,engine_service::snapshot());}
esp_err_t engine_sample_get(httpd_req_t*r){return send_json(r,engine_service::sample());}
esp_err_t engine_tuning_get(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 return send_json(r,engine_tuning::snapshot());
}
bool log_boot(httpd_req_t*r){
 char value[33]{};return httpd_req_get_hdr_value_str(r,"X-ECU-Log-Boot",value,sizeof(value))==ESP_OK&&engine_log_service::same_boot(value);
}
bool log_query(httpd_req_t*r,std::uint32_t&id,std::uint32_t&after){
 char query[64]{};return httpd_req_get_url_query_len(r)<sizeof(query)&&
  httpd_req_get_url_query_str(r,query,sizeof(query))==ESP_OK&&engine_log::parse_query(query,id,after);
}
bool log_fields(cJSON*j){
 return j&&cJSON_AddStringToObject(j,"boot_id",engine_log_service::boot_id())&&
  cJSON_AddNumberToObject(j,"producer_lock_contention_attempts",engine_log_service::contention_attempts())&&
  cJSON_AddBoolToObject(j,"export_busy",engine_log_service::exporting())&&
  cJSON_AddStringToObject(j,"scope","Bounded RAM observations; proposals and earlier worker command masks are not electrical execution measurements");
}
esp_err_t engine_data_log_get(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 if(!httpd_req_get_url_query_len(r)){
  auto*j=engine_log::header_json(engine_log_service::header());
  if(!log_fields(j)){cJSON_Delete(j);return message(r,"Allocation failed.","500 Internal Server Error");}
  return send_json(r,j);
 }
 std::uint32_t id=0,after=0;
 if(!log_query(r,id,after))return message(r,"Use log_id and after for a bounded row page.","422 Unprocessable Entity");
 if(!log_boot(r))return message(r,"Device boot changed; reload log metadata.","409 Conflict");
 auto page=heap_object<engine_log::Page>();
 if(!page)return message(r,"Log page allocation failed.","500 Internal Server Error");
 engine_log_service::page(id,after,*page);
 if(page->superseded||page->future_cursor||page->invalid_row)return message(r,"Log changed or row cursor is invalid; retain collected rows and reload metadata.","409 Conflict");
 auto*j=engine_log::header_json(page->header);
 const bool ok=log_fields(j)&&cJSON_AddBoolToObject(j,"snapshot_superseded",false)&&cJSON_AddBoolToObject(j,"future_cursor",false)&&
  cJSON_AddBoolToObject(j,"invalid_row",false)&&cJSON_AddBoolToObject(j,"copied_page",true)&&
  cJSON_AddNumberToObject(j,"next_after",page->next_after)&&cJSON_AddNumberToObject(j,"gap_first",page->gap_first)&&cJSON_AddNumberToObject(j,"gap_last",page->gap_last);
 char*text=ok?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);
 if(!text)return message(r,"Allocation failed.","500 Internal Server Error");
 const auto length=std::strlen(text);text[length-1]=0;
 httpd_resp_set_type(r,"application/json");httpd_resp_set_hdr(r,"Cache-Control","no-store");httpd_resp_set_hdr(r,"X-Content-Type-Options","nosniff");
 auto result=httpd_resp_send_chunk(r,text,length-1);cJSON_free(text);
 if(result!=ESP_OK||httpd_resp_send_chunk(r,",\"records\":[",HTTPD_RESP_USE_STRLEN)!=ESP_OK)return ESP_FAIL;
 for(unsigned i=0;i<page->count;++i){
  auto*row=engine_log::row_json(page->rows[i]);text=row?cJSON_PrintUnformatted(row):nullptr;cJSON_Delete(row);
  // A truncated response is rejected as a whole by the collector. No partial
  // cursor advance or synthetic replacement row is sent on allocation failure.
  if(!text)return ESP_FAIL;
  result=i?httpd_resp_send_chunk(r,",",1):ESP_OK;
  if(result==ESP_OK)result=httpd_resp_send_chunk(r,text,HTTPD_RESP_USE_STRLEN);
  cJSON_free(text);if(result!=ESP_OK)return result;
  // HTTPD runs above the ADC/control task. Yield a tick after each bounded row,
  // even when the network is writable, so serialization cannot monopolize it.
  vTaskDelay(1);
 }
 if(httpd_resp_send_chunk(r,"]}",2)!=ESP_OK)return ESP_FAIL;
 return httpd_resp_send_chunk(r,nullptr,0);
}
esp_err_t engine_data_log_post(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 if(httpd_req_get_url_query_len(r))return message(r,"Log commands do not accept a query string.","422 Unprocessable Entity");
 if(!log_boot(r))return message(r,"Device boot changed; reload log metadata.","409 Conflict");
 if(r->content_len<=0||r->content_len>256)return message(r,"Log command must be 1-256 bytes.","413 Content Too Large");
 char type[80]{};httpd_req_get_hdr_value_str(r,"Content-Type",type,sizeof(type));
 if(std::strcmp(type,"application/json"))return message(r,"Use application/json.","415 Unsupported Media Type");
 char body[257]{};int received=0;
 while(received<r->content_len){const int n=httpd_req_recv(r,body+received,r->content_len-received);if(n<=0)return ESP_FAIL;received+=n;}
 engine_log::Request request;
 if(!engine_log::parse_request(body,received,request))return message(r,"Invalid log command.","422 Unprocessable Entity");
 const bool ok=request.start?engine_log_service::start(request.period_ms,request.duration_s):engine_log_service::stop(request.log_id);
 if(!ok)return message(r,"Log is recording, exporting, or its identity changed; reload before retrying.","409 Conflict");
 return engine_data_log_get(r);
}
esp_err_t engine_data_log_msl_get(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 if(!log_boot(r))return message(r,"Device boot changed; reload log metadata.","409 Conflict");
 std::uint32_t id=0,after=0;
 if(!log_query(r,id,after)||after)return message(r,"Use log_id and after=0 for a retained-window export.","422 Unprocessable Entity");
 engine_log::Header h;
 if(!engine_log_service::begin_export(id,h))return message(r,"Stop recording and select a nonempty current log before exporting.","409 Conflict");
 struct Lease {~Lease(){engine_log_service::end_export();}}lease;
 char buffer[engine_log::text_capacity];
 if(!engine_log::msl_header(h,buffer,sizeof(buffer),engine_log_service::boot_id()))return message(r,"Log formatter limit exceeded.","500 Internal Server Error");
 httpd_resp_set_type(r,"text/plain; charset=utf-8");httpd_resp_set_hdr(r,"Cache-Control","no-store");
 httpd_resp_set_hdr(r,"Content-Disposition","attachment; filename=ecu-retained-engine.msl");
 if(httpd_resp_send_chunk(r,buffer,HTTPD_RESP_USE_STRLEN)!=ESP_OK)return ESP_FAIL;
 engine_log::Row row;
 for(std::uint64_t sequence=h.first_sequence();sequence<=h.total;++sequence){
  if(!engine_log_service::export_row(id,static_cast<std::uint32_t>(sequence),row)||!engine_log::msl_row(h,row,buffer,sizeof(buffer))||httpd_resp_send_chunk(r,buffer,HTTPD_RESP_USE_STRLEN)!=ESP_OK)return ESP_FAIL;
  vTaskDelay(1);
 }
 return httpd_resp_send_chunk(r,nullptr,0);
}
esp_err_t engine_timing_get(httpd_req_t*r){return send_json(r,engine_target::trace_json());}
esp_err_t engine_trigger_get(httpd_req_t*r){
 std::uint32_t id=0;unsigned offset=0;const auto query_length=httpd_req_get_url_query_len(r);
 if(query_length){
  char query[64]{};
  if(query_length>=sizeof(query)||httpd_req_get_url_query_str(r,query,sizeof(query))!=ESP_OK||!trigger_log::parse_query(query,id,offset))
   return message(r,"Use frame_id and offset for a bounded record page.","422 Unprocessable Entity");
 }
 auto* j=engine_target::trigger_json(id,offset,query_length!=0);
 const bool superseded=j&&cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"snapshot_superseded"));
 return send_json(r,j,superseded?"409 Conflict":"200 OK");
}
esp_err_t engine_trigger_post(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 if(r->content_len<=0||r->content_len>256)return message(r,"Trigger command must be 1-256 bytes.","413 Content Too Large");
 char type[80]{};httpd_req_get_hdr_value_str(r,"Content-Type",type,sizeof(type));
 if(std::strcmp(type,"application/json"))return message(r,"Use application/json.","415 Unsupported Media Type");
 std::string body(static_cast<std::size_t>(r->content_len),'\0');int received=0;
 while(received<r->content_len){const int n=httpd_req_recv(r,body.data()+received,r->content_len-received);if(n<=0)return ESP_FAIL;received+=n;}
 trigger_log::Request request;if(!trigger_log::parse_request(body.c_str(),body.size(),request))return message(r,"Invalid trigger command.","422 Unprocessable Entity");
 const bool ok=request.start?engine_target::trigger_start(request.samples,request.timeout_ms):engine_target::trigger_stop(request.frame_id);
 if(!ok)return message(r,"Capture is active or frame changed; reload before retrying.","409 Conflict");
 return engine_trigger_get(r);
}
esp_err_t engine_config_put(httpd_req_t*r){
 if(!authorized(r))return message(r,"Session token or origin rejected.","403 Forbidden");
 if(r->content_len<=0||r->content_len>engine::tune_maximum)return message(r,"Engine tune must be 1-49152 bytes.","413 Content Too Large");
 char type[80]{};httpd_req_get_hdr_value_str(r,"Content-Type",type,sizeof(type));if(std::strncmp(type,"application/json",16))return message(r,"Use application/json.","415 Unsupported Media Type");
 struct EngineBody{std::array<char,engine::tune_maximum+1> bytes{};};auto body=heap_object<EngineBody>();
 if(!body)return message(r,"Engine request buffer unavailable; previous tune retained.","503 Service Unavailable");
 int n=0;while(n<r->content_len){int got=httpd_req_recv(r,body->bytes.data()+n,r->content_len-n);if(got<=0)return ESP_FAIL;n+=got;}
 if(!safe_json(body->bytes.data(),static_cast<std::size_t>(n),engine::tune_maximum))return message(r,"Invalid engine JSON envelope.","400 Bad Request");
 std::string reason;const int code=engine_service::save(body->bytes.data(),reason);if(code==200)return engine_config_get(r);
 const char*status=code==409?"409 Conflict":code==413?"413 Content Too Large":code==503?"503 Service Unavailable":code==507?"507 Insufficient Storage":code==500?"500 Internal Server Error":"422 Unprocessable Entity";
 return message(r,reason.c_str(),status);
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
 constexpr unsigned uri_capacity=42;httpd_config_t http=HTTPD_DEFAULT_CONFIG();http.stack_size=16384;http.max_uri_handlers=uri_capacity;http.lru_purge_enable=true;http.recv_wait_timeout=5;http.send_wait_timeout=5;
 httpd_handle_t server{};ESP_ERROR_CHECK(httpd_start(&server,&http));
 const httpd_uri_t routes[]={
  {"/api/engine/defaults",HTTP_GET,engine_defaults_get,nullptr},{"/api/engine/config",HTTP_GET,engine_config_get,nullptr},{"/api/engine/config",HTTP_PUT,engine_config_put,nullptr},{"/api/engine/status",HTTP_GET,engine_status_get,nullptr},
  {"/api/engine/timing",HTTP_GET,engine_timing_get,nullptr},
  {"/api/engine/sample",HTTP_GET,engine_sample_get,nullptr},
  {"/api/engine/tuning",HTTP_GET,engine_tuning_get,nullptr},{"/tuning_diagnostics.js",HTTP_GET,tuning_script_get,nullptr},{"/idle_control.js",HTTP_GET,idle_script_get,nullptr},{"/transient_enrichment.js",HTTP_GET,transient_script_get,nullptr},{"/load_model.js",HTTP_GET,load_script_get,nullptr},{"/secondary_tables.js",HTTP_GET,secondary_script_get,nullptr},{"/flex_fuel.js",HTTP_GET,flex_script_get,nullptr},{"/boost_control.js",HTTP_GET,boost_script_get,nullptr},
  {"/api/engine/data-log",HTTP_GET,engine_data_log_get,nullptr},{"/api/engine/data-log",HTTP_POST,engine_data_log_post,nullptr},
  {"/api/engine/data-log.msl",HTTP_GET,engine_data_log_msl_get,nullptr},{"/profile_metadata.js",HTTP_GET,profile_script_get,nullptr},{"/cylinder_tuning.js",HTTP_GET,cylinder_script_get,nullptr},{"/engine_logger.js",HTTP_GET,engine_log_script_get,nullptr},
  {"/api/engine/trigger-log",HTTP_GET,engine_trigger_get,nullptr},{"/api/engine/trigger-log",HTTP_POST,engine_trigger_post,nullptr},
  {"/api/radio",HTTP_GET,radio_get,nullptr},{"/api/radio",HTTP_POST,radio_post,nullptr},
  {"/",HTTP_GET,index_get,nullptr},{"/trigger_logger.js",HTTP_GET,trigger_script_get,nullptr},{"/api/session",HTTP_GET,session_get,nullptr},{"/api/guide",HTTP_GET,guide_get,nullptr},{"/api/manual",HTTP_GET,manual_get,nullptr},
  {"/api/defaults",HTTP_GET,defaults_get,nullptr},{"/api/config",HTTP_GET,config_get,nullptr},{"/api/config",HTTP_PUT,config_put,nullptr},{"/api/status",HTTP_GET,status_get,nullptr}};
 static_assert(sizeof(routes)/sizeof(routes[0])<=uri_capacity,"HTTP route budget exceeded");
 for(const auto&route:routes)ESP_ERROR_CHECK(httpd_register_uri_handler(server,&route));
 ESP_LOGW(tag,"BENCH ONLY. J3 open. No actuators. SSID=%s password=%s URL=http://192.168.4.1",wifi.ap.ssid,wifi.ap.password);
}
#endif
}
void init(){
 mutex=xSemaphoreCreateMutex();configASSERT(mutex);
 configASSERT(parse_text(assets::defaults,active,&document));
 const auto err=nvs_flash_init();storage_ok=err==ESP_OK;storage_message=storage_ok?"defaults; no saved profile":"NVS init failed; inspect UART";
 if(!storage_ok){ESP_LOGE(tag,"NVS init failed: %s. Partition NOT erased.",esp_err_to_name(err));return;}
 config::Config candidate;std::string saved,prepared;esp_err_t read_error=ESP_OK;
 const auto loaded=config_storage::load(saved,[&](const std::string&text){return parse_text(text.c_str(),candidate,&prepared);},read_error);
 if(loaded==config_storage::Load::Blob||loaded==config_storage::Load::Legacy){
  active=candidate;document.swap(prepared);
  storage_message=loaded==config_storage::Load::Blob?"loaded profile blob":"legacy profile loaded; normalized in RAM, old NVS string retained";
 }else if(loaded==config_storage::Load::Error){
  storage_ok=false;storage_message="profile read/validation failed; defaults active; saving blocked";
  ESP_LOGE(tag,"Profile read failed: %s. Stored records NOT erased.",esp_err_to_name(read_error));
 }
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
 const double supply=s.raw[7]*active.adc_reference_v/4095.0/.6;
 for(unsigned i=0;i<6;++i){const double raw=s.raw[i]*active.adc_reference_v/4095.0/.6;
  filtered[i]=config::readout_filter(active.sensors[i],raw,supply,filtered[i],dt,
                                    !last_sample||filtered_revision!=active.revision,s.adc_ok);
 }
 filtered_revision=active.revision;latest=s;last_sample=now;radio::publish(s,active,filtered);xSemaphoreGive(mutex);
}
}
