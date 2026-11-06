#include "ecu/engine_log_service.hpp"
#include "ecu/engine_target.hpp"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <atomic>
#include <cstdio>
#include <cstring>

namespace ecu::engine_log_service {
namespace {
SemaphoreHandle_t mutex;
engine_log::Recorder recorder;
std::atomic<std::uint32_t> contention{0};
char boot[33]{};
bool export_active=false;
void expire(){recorder.expire(engine_target::clock_us());}
}
void init(){
 mutex=xSemaphoreCreateMutex();configASSERT(mutex);
 for(unsigned i=0;i<4;++i)std::snprintf(boot+i*8,9,"%08lx",static_cast<unsigned long>(esp_random()));
}
void observe(const engine::RuntimeSample&sample){
 if(xSemaphoreTake(mutex,0)!=pdTRUE){
  auto old=contention.load(std::memory_order_relaxed);
  while(old!=UINT32_MAX&&!contention.compare_exchange_weak(old,old+1,std::memory_order_relaxed)){}
  return;
 }
 recorder.append(sample,engine_target::clock_us());xSemaphoreGive(mutex);
}
const char* boot_id(){return boot;}
bool same_boot(const char*value){return value&&std::strlen(value)==32&&!std::strcmp(value,boot);}
engine_log::Header header(){
 xSemaphoreTake(mutex,portMAX_DELAY);expire();const auto h=recorder.header();xSemaphoreGive(mutex);return h;
}
std::uint32_t contention_attempts(){return contention.load(std::memory_order_relaxed);}
bool exporting(){xSemaphoreTake(mutex,portMAX_DELAY);const bool busy=export_active;xSemaphoreGive(mutex);return busy;}
bool start(unsigned period,unsigned duration){
 xSemaphoreTake(mutex,portMAX_DELAY);
 const bool ok=!export_active&&recorder.start(period,duration,engine::DataSource::Target,engine_target::clock_us());
 xSemaphoreGive(mutex);return ok;
}
bool stop(std::uint32_t id){
 xSemaphoreTake(mutex,portMAX_DELAY);const bool ok=recorder.stop(id,engine_target::clock_us());xSemaphoreGive(mutex);return ok;
}
void page(std::uint32_t id,std::uint32_t after,engine_log::Page&out){
 xSemaphoreTake(mutex,portMAX_DELAY);expire();recorder.page(id,after,out);xSemaphoreGive(mutex);
}
bool begin_export(std::uint32_t id,engine_log::Header&out){
 xSemaphoreTake(mutex,portMAX_DELAY);expire();const auto h=recorder.header();
 const bool ok=!export_active&&recorder.current(id)&&h.state!=engine_log::State::Recording&&h.retained;
 if(ok){export_active=true;out=h;}xSemaphoreGive(mutex);return ok;
}
bool export_row(std::uint32_t id,std::uint32_t sequence,engine_log::Row&out){
 xSemaphoreTake(mutex,portMAX_DELAY);const bool ok=export_active&&recorder.read(id,sequence,out);xSemaphoreGive(mutex);return ok;
}
void end_export(){xSemaphoreTake(mutex,portMAX_DELAY);export_active=false;xSemaphoreGive(mutex);}
}
