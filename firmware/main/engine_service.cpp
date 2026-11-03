#include "ecu/engine_service.hpp"
#include "ecu/engine_json.hpp"
#include "ecu/engine_binding.hpp"
#include "ecu/engine_storage.hpp"
#include "ecu/engine_target.hpp"
#include "web_assets.hpp"
#include "nvs.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <memory>
namespace ecu::engine_service {
namespace {
SemaphoreHandle_t mutex;
engine::Tune active;engine::Controller controller;engine::Output latest;
std::string document;bool storage_ok=false;std::uint64_t stamp=0;const char* binding="waiting for sensor sample";
std::uint64_t command_sequence=0;std::uint32_t sensor_revision=0;
bool parse_text(const char*s,engine::Tune&t){if(!web::safe_json(s,std::strlen(s)))return false;auto*j=cJSON_ParseWithOpts(s,nullptr,true);bool ok=j&&engine::parse_tune(j,t);cJSON_Delete(j);return ok;}
}
void init(){
 mutex=xSemaphoreCreateMutex();configASSERT(mutex);document=web::assets::engine_defaults;
 configASSERT(parse_text(document.c_str(),active));esp_err_t error=ESP_OK;std::string saved;
 auto candidate=std::make_unique<engine::Tune>();
 const auto result=engine_storage::load(saved,[&](const std::string&s){return parse_text(s.c_str(),*candidate);},error);
 if(result==engine_storage::Load::Missing){storage_ok=true;return;}
 if(result==engine_storage::Load::Loaded||result==engine_storage::Load::Migrated){active=*candidate;document=std::move(saved);storage_ok=true;}
 if(result==engine_storage::Load::Migrated)ESP_LOGI("ecu_engine","Legacy engine tune copied to dedicated blob partition; old record retained");
 if(!storage_ok)ESP_LOGE("ecu_engine","Engine storage unavailable or invalid (%s); no application erase requested, defaults shadow-only",esp_err_to_name(error));
}
void observe(const web::Sample&s,const config::Config&c,std::uint64_t now,std::uint64_t sampled){
 if(!mutex||xSemaphoreTake(mutex,0)!=pdTRUE)return;
 auto bound=engine::bind_inputs(s,c,now);binding=bound.reason;auto&in=bound.input;
 in.sampled_us=sampled;
 if(sensor_revision!=c.revision){controller.reset();sensor_revision=c.revision;}
 latest=controller.step(active,in,now);stamp=now;
 if(!storage_ok){latest.faults|=engine::BadTune;latest.state=engine::State::Faulted;latest.fuel_cut=latest.spark_cut=true;}
 timing::Command command;command.angle={active.tooth1_btdc_deg,active.max_dwell_ms};command.output=latest;
 command.sequence=++command_sequence;command.command_us=now;command.sampled_us=sampled;
 command.tune_revision=active.revision;command.sensor_revision=c.revision;
 command.max_injector_high_us=std::llround(active.max_injection_ms*1000);command.max_coil_high_us=std::llround(active.max_dwell_ms*1000);
 command.slots=c.slots;command.missing=c.missing;command.max_rpm=c.max_rpm;
 engine_target::submit(command);xSemaphoreGive(mutex);
}
std::string tune_json(){xSemaphoreTake(mutex,portMAX_DELAY);std::string copy=document;xSemaphoreGive(mutex);return copy;}
int save(const char*text,std::string&reason){
 auto candidate=std::make_unique<engine::Tune>();if(!parse_text(text,*candidate)){reason="Invalid engine tune: schema, table axes, physical units or hardware pulse limits";return 422;}
 xSemaphoreTake(mutex,portMAX_DELAY);
 if(!storage_ok){reason="Engine NVS storage unavailable; previous data preserved";xSemaphoreGive(mutex);return 503;}
 if(candidate->revision!=active.revision||active.revision==UINT32_MAX){reason="Engine tune revision changed; reload before saving";xSemaphoreGive(mutex);return 409;}
 auto*j=cJSON_Parse(text);candidate->revision++;cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"revision"),candidate->revision);char*encoded=cJSON_PrintUnformatted(j);cJSON_Delete(j);
 if(!encoded){reason="Allocation failed";xSemaphoreGive(mutex);return 500;}
 if(std::strlen(encoded)>16384){reason="Encoded engine tune exceeds 16 KiB; previous data retained";cJSON_free(encoded);xSemaphoreGive(mutex);return 413;}
 engine_target::begin_configuration();
 const auto err=engine_storage::save(encoded);
 if(err!=ESP_OK){storage_ok=false;reason="Engine persistence failed; runtime retained, saves blocked until restart and inspection";cJSON_free(encoded);engine_target::finish_configuration(active.revision,0);xSemaphoreGive(mutex);return 507;}
 active=*candidate;document=encoded;cJSON_free(encoded);controller.reset();stamp=0;latest=engine::Output{};engine_target::finish_configuration(active.revision,0);xSemaphoreGive(mutex);return 200;
}
cJSON* snapshot(){
 xSemaphoreTake(mutex,portMAX_DELAY);auto*j=engine::output_json(latest);const auto now=engine_target::clock_us();cJSON_AddNumberToObject(j,"revision",active.revision);cJSON_AddBoolToObject(j,"storage_ok",storage_ok);cJSON_AddStringToObject(j,"binding",binding);cJSON_AddNumberToObject(j,"sample_age_ms",stamp&&now>=stamp?(now-stamp)/1000.0:-1);cJSON_AddBoolToObject(j,"simulator",false);cJSON_AddBoolToObject(j,"fresh",stamp&&now>=stamp&&now-stamp<50000);xSemaphoreGive(mutex);cJSON_AddItemToObject(j,"timing",engine_target::snapshot());return j;
}
}
