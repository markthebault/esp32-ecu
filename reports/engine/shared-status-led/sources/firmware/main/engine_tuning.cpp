#include "ecu/engine_tuning.hpp"
#include "ecu/engine_service.hpp"
#include "ecu/engine_target.hpp"
#include "ecu/tuning_stream.hpp"
#include "ecu/tuning_live.hpp"
#include "ecu/engine_data_json.hpp"
#include "ecu/heap_object.hpp"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "sdkconfig.h"
#ifndef ECU_TUNING_USB
#define ECU_TUNING_USB 0
#endif
#ifndef ECU_ENGINE_DUMMY_LOADS
#define ECU_ENGINE_DUMMY_LOADS 0
#endif
#ifndef ECU_BENCH_PULSES
#define ECU_BENCH_PULSES 0
#endif
#if ECU_TUNING_USB
#if ECU_ENGINE_DUMMY_LOADS || ECU_BENCH_PULSES
#error USB tuning is restricted to builds with physical engine outputs inhibited
#endif
#if !defined(CONFIG_ESP_CONSOLE_UART_DEFAULT) || defined(CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG) || defined(CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG) || defined(CONFIG_ESP_CONSOLE_USB_CDC)
#error USB binary tuning requires exclusive USB ownership and UART0-only diagnostics
#endif
#include "driver/usb_serial_jtag.h"
#endif
namespace ecu::engine_tuning {
namespace {
portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
struct Observation {
 tuning::Stats session;tuning::StreamStats wire;
 std::uint64_t observed_us=0,driver_tx_accepted=0,short_writes=0,max_slice_us=0;
 unsigned buffered=0;bool boot_allowed=false,started=false,host_present=false,tx_fault=false;
 const char*reason="USB tuning is not enabled in this build";
};
Observation latest;
#if ECU_TUNING_USB
class Store final:public tuning::Backend {
public:
 tuning::Result load(engine::Tune&t)override{return engine_service::tuning_load(t);}
 tuning::Result current(std::uint32_t&r)override{return engine_service::tuning_current(r);}
 tuning::Result commit(const engine::Tune&t,std::uint32_t&r)override{return engine_service::tuning_commit(t,r);}
 void sample(std::array<std::uint8_t,tuning::live_bytes>&b)override{
  engine::RuntimeSample s;if(engine_service::tuning_sample(s))tuning::live_block(s,engine_target::clock_us(),b);
  else{b.fill(0);tuning::put_u32(b.data()+52,1);tuning::put_u32(b.data()+64,UINT32_MAX);}
 }
};
struct State {Store store;tuning::Session session;tuning::Stream stream;State():session(store),stream(session){}};
TaskHandle_t task_handle=nullptr;
void publish(const Observation&o){portENTER_CRITICAL(&lock);latest=o;portEXIT_CRITICAL(&lock);}
void run(void*){
 Observation seen;seen.boot_allowed=true;seen.reason="starting";
 auto state=heap_object<State>();if(!state){seen.reason="USB tuning session allocation failed";publish(seen);vTaskDelete(nullptr);return;}
 // Installation, normal use and failure cleanup all run on the pinned CPU0.
 usb_serial_jtag_driver_config_t cfg{};cfg.rx_buffer_size=1024;cfg.tx_buffer_size=1024;
 const auto installed=usb_serial_jtag_driver_install(&cfg);
 if(installed!=ESP_OK){seen.reason=esp_err_to_name(installed);publish(seen);state.reset();vTaskDelete(nullptr);return;}
 (void)state->session.open();seen.started=true;seen.reason="ready";bool previous_host=false;
 while(true){
  const auto begin=esp_timer_get_time();const bool host=usb_serial_jtag_is_connected();
  if(!host&&previous_host){state->stream.disconnect();}previous_host=host;
  auto send=[&](const std::uint8_t*p,std::size_t n){
   std::size_t offset=0;const auto until=esp_timer_get_time()+2000;
   while(offset<n){
    const int wrote=usb_serial_jtag_write_bytes(p+offset,n-offset,0);
    if(wrote>0){offset+=unsigned(wrote);seen.driver_tx_accepted+=unsigned(wrote);}
    if(offset==n)return true;
    if(esp_timer_get_time()>=until){++seen.short_writes;return false;}
    vTaskDelay(1);
   }
   return true;
  };
  // Bounded reads and a mandatory yield prevent a continuous host stream from
  // monopolizing the ADC/control task's CPU. Parser/CRC/JSON stay task-side.
  std::array<std::uint8_t,64> bytes{};const int count=usb_serial_jtag_read_bytes(bytes.data(),bytes.size(),0);
  if(count>0)state->stream.feed(bytes.data(),count,std::uint64_t(esp_timer_get_time()),send);
  else state->stream.expire(std::uint64_t(esp_timer_get_time()),send);
  seen.session=state->session.stats();seen.wire=state->stream.stats();seen.host_present=host;
  seen.tx_fault=state->stream.transmit_fault();seen.buffered=state->stream.buffered();seen.observed_us=esp_timer_get_time();
  seen.max_slice_us=std::max(seen.max_slice_us,std::uint64_t(esp_timer_get_time()-begin));publish(seen);vTaskDelay(1);
 }
}
#endif
}
void start(bool interlock_at_boot){
#if ECU_TUNING_USB
 if(task_handle)return;
 portENTER_CRITICAL(&lock);latest.boot_allowed=!interlock_at_boot;latest.reason=interlock_at_boot?"J3 was closed at startup":"starting";portEXIT_CRITICAL(&lock);
 if(interlock_at_boot)return;
 if(xTaskCreatePinnedToCore(run,"ecu_tuning",12288,nullptr,1,&task_handle,0)!=pdPASS){
  portENTER_CRITICAL(&lock);latest.reason="USB tuning task allocation failed";portEXIT_CRITICAL(&lock);task_handle=nullptr;
 }
#else
 (void)interlock_at_boot;
#endif
}
cJSON* snapshot(){
 Observation o;portENTER_CRITICAL(&lock);o=latest;portEXIT_CRITICAL(&lock);
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 bool ok=cJSON_AddNumberToObject(j,"schema_version",1)&&cJSON_AddStringToObject(j,"transport","native_usb_serial_jtag")&&
  cJSON_AddStringToObject(j,"identity",tuning::signature)&&cJSON_AddStringToObject(j,"serial_protocol","002")&&cJSON_AddBoolToObject(j,"enabled",ECU_TUNING_USB)&&
  cJSON_AddBoolToObject(j,"boot_allowed",o.boot_allowed)&&cJSON_AddBoolToObject(j,"available",o.started)&&cJSON_AddBoolToObject(j,"host_present",o.host_present)&&
  cJSON_AddStringToObject(j,"reason",o.reason)&&cJSON_AddBoolToObject(j,"physical_outputs_inhibited",!ECU_ENGINE_DUMMY_LOADS)&&
  cJSON_AddStringToObject(j,"observed_clock_domain","esp_timer")&&
  cJSON_AddStringToObject(j,"application_support","Tested TunerStudio 3.3.01 rejects our own controller identity; offline files supported, vendor integration unresolved")&&
  cJSON_AddStringToObject(j,"commit_behavior","Any successful burn validates, persists and activates the whole tune, resets control and reacquires phase")&&
  cJSON_AddStringToObject(j,"host_presence_meaning","USB bus SOF observed, including an unopened serial port; not an application connection")&&
  cJSON_AddStringToObject(j,"qualification","Native/source tests only; USB enumeration, boot/panic traffic, sustained load, driver drops and physical timing unmeasured")&&
  cJSON_AddNullToObject(j,"driver_rx_drop_count")&&cJSON_AddStringToObject(j,"driver_rx_drop_count_meaning","Pinned SDK exposes no RX-overflow counter")&&
  engine::json_u64(j,"observed_us",o.observed_us)&&engine::json_u64(j,"driver_tx_accepted_bytes",o.driver_tx_accepted)&&
  engine::json_u64(j,"short_writes",o.short_writes)&&engine::json_u64(j,"max_slice_us",o.max_slice_us)&&
  cJSON_AddBoolToObject(j,"tx_fault",o.tx_fault)&&cJSON_AddNumberToObject(j,"buffered_bytes",o.buffered);
 auto*s=ok?cJSON_AddObjectToObject(j,"session"):nullptr;if(!s)ok=false;
 if(ok)ok=cJSON_AddBoolToObject(s,"initialized",o.session.initialized)&&cJSON_AddBoolToObject(s,"dirty",o.session.dirty)&&
  cJSON_AddStringToObject(s,"state",tuning::state_name(o.session.state))&&cJSON_AddNumberToObject(s,"origin_revision",o.session.origin_revision)&&
  cJSON_AddNumberToObject(s,"base_revision",o.session.base_revision)&&cJSON_AddNumberToObject(s,"observed_active_revision",o.session.active_revision)&&cJSON_AddNumberToObject(s,"last_code",o.session.last_code);
#define COUNT(name) ok=ok&&engine::json_u64(s,#name,o.session.name)
 COUNT(commands);COUNT(reads);COUNT(writes);COUNT(burns);COUNT(rejected);COUNT(resets);
#undef COUNT
 auto*w=ok?cJSON_AddObjectToObject(j,"wire"):nullptr;if(!w)ok=false;
#define COUNT(name) ok=ok&&engine::json_u64(w,#name,o.wire.name)
 COUNT(received);COUNT(transmitted);COUNT(frames);COUNT(crc_errors);COUNT(timeouts);COUNT(framing_errors);COUNT(tx_errors);
#undef COUNT
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
