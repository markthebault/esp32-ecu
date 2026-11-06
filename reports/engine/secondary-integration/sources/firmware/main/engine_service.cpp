#include "ecu/engine_service.hpp"
#include "ecu/engine_json.hpp"
#include "ecu/engine_binding.hpp"
#include "ecu/engine_storage.hpp"
#include "ecu/engine_target.hpp"
#include "ecu/idle_command.hpp"
#include "ecu/engine_data_json.hpp"
#include "ecu/heap_object.hpp"
#include "ecu/tuning_document.hpp"
#include "web_assets.hpp"
#include "nvs.h"
#include "esp_partition.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <memory>
namespace ecu::engine_service {
namespace {
SemaphoreHandle_t mutex;
engine::Tune active;engine::Controller controller;engine::Output latest;
engine::RuntimeSample latest_data;
using Document=std::unique_ptr<char,decltype(&cJSON_free)>;
Document document{nullptr,&cJSON_free};
const char* document_text(){return document?document.get():web::assets::engine_defaults;}
bool storage_ok=false;std::uint64_t stamp=0;const char* binding="waiting for sensor sample";
const char*storage_reason="Engine NVS unavailable or invalid; saved tune retained, defaults shadow-only";
std::uint64_t command_sequence=0;std::uint32_t sensor_revision=0;
bool parse_text(const char*s,engine::Tune&t){if(!web::safe_json(s,std::strlen(s),engine::tune_maximum))return false;auto*j=cJSON_ParseWithOpts(s,nullptr,true);bool ok=j&&engine::parse_tune(j,t);cJSON_Delete(j);return ok;}
}
void init(){
 mutex=xSemaphoreCreateMutex();configASSERT(mutex);
 configASSERT(parse_text(document_text(),active));esp_err_t error=ESP_OK;std::string saved;
 const auto*partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"engine_nvs");
 if(!partition||partition->address!=0x210000||partition->size<0x20000){
  storage_reason="Engine NVS layout mismatch: matching partition table requires128 KiB at0x210000; saved bytes retained";
  ESP_LOGE("ecu_engine","%s",storage_reason);return;
 }
 auto candidate=heap_object<engine::Tune>();
 if(!candidate){ESP_LOGE("ecu_engine","Engine load allocation failed; saved data preserved, defaults shadow-only");return;}
 const auto result=engine_storage::load(saved,[&](const std::string&s){return parse_text(s.c_str(),*candidate);},error);
 if(result==engine_storage::Load::Missing){storage_ok=true;return;}
 if(result==engine_storage::Load::Loaded||result==engine_storage::Load::Migrated){
  auto*j=cJSON_ParseWithOpts(saved.c_str(),nullptr,true);const bool ok=j&&engine::upgrade_tune_document(j);
  Document canonical(ok?cJSON_PrintUnformatted(j):nullptr,&cJSON_free);cJSON_Delete(j);
  if(canonical&&std::strlen(canonical.get())<=engine::tune_maximum){active=*candidate;document=std::move(canonical);storage_ok=true;}else error=ESP_ERR_NO_MEM;
 }
 if(result==engine_storage::Load::Migrated)ESP_LOGI("ecu_engine","Legacy engine tune copied to dedicated blob partition; old record retained");
 if(!storage_ok)ESP_LOGE("ecu_engine","Engine storage unavailable or invalid (%s); no application erase requested, defaults shadow-only",esp_err_to_name(error));
}
bool observe(const web::Sample&s,const config::Config&c,std::uint64_t now,std::uint64_t sampled,engine::RuntimeSample& published){
 if(!mutex||xSemaphoreTake(mutex,0)!=pdTRUE)return false;
 auto bound=engine::bind_inputs(s,c,now,&active);binding=bound.reason;auto&in=bound.input;
 in.sampled_us=sampled;
 in.phase_synced=in.phase_synced&&s.phase_tune_revision==active.revision&&s.phase_sensor_revision==c.revision;
 if(sensor_revision!=c.revision){controller.reset();sensor_revision=c.revision;}
 latest=controller.step(active,in,now);stamp=now;
 if(!storage_ok){latest.faults|=engine::BadTune;latest.state=engine::State::Faulted;latest.fuel_cut=latest.spark_cut=true;}
 timing::Command command;command.angle=engine::angle_config(active);command.output=latest;
 command.sequence=++command_sequence;command.command_us=now;command.sampled_us=sampled;
 command.tune_revision=active.revision;command.sensor_revision=c.revision;
 command.phase_epoch=s.phase_epoch;
 command.max_injector_high_us=std::llround(active.max_injection_ms*1000);command.max_coil_high_us=std::llround(active.max_dwell_ms*1000);
 command.slots=c.slots;command.missing=c.missing;command.max_rpm=c.max_rpm;
 idle::prepare_pwm(command,active);
 const bool submitted=engine_target::submit(command);
 engine::RuntimeSample data;engine::data_values(data,in,latest);
 data.sequence=command.sequence;data.control_us=now;data.sampled_us=sampled;data.tune_revision=active.revision;data.sensor_revision=c.revision;
 data.idle_algorithm=static_cast<std::uint8_t>(active.idle_control.algorithm);data.source=engine::DataSource::Target;data.strategy=static_cast<std::uint8_t>(active.strategy);data.phase_epoch=s.phase_epoch;
 data.input_valid=engine::data_input_mask(in,bound.qualified);if(s.overflow)data.input_valid&=~(1U<<engine::DecodedRpm);
 data.flags|=(storage_ok?engine::StorageOk:0)|(in.synced?engine::CrankSynced:0)|(in.phase_synced?engine::PhaseSynced:0)|
  (active.strategy==engine::Strategy::Sequential?engine::PhaseRequired:0)|(submitted?engine::Submitted:0)|
  (now>=sampled&&now-sampled<=20000?engine::InputsFresh:0)|(in.sensors_valid&&latest.secondary_fuel.valid&&latest.secondary_spark.valid?engine::InputsQualified:0)|
  (s.phase_epoch&&s.phase_tune_revision==active.revision&&s.phase_sensor_revision==c.revision?engine::PhaseContextMatch:0);
#if defined(ECU_ENGINE_DUMMY_LOADS) && ECU_ENGINE_DUMMY_LOADS
 data.flags|=engine::DummyPolicy;
#endif
 data.worker_sequence=s.worker_sequence;data.worker_observed_us=s.worker_observed_us;data.worker_epoch=s.worker_epoch;
 data.worker_tune_revision=s.worker_tune_revision;data.worker_sensor_revision=s.worker_sensor_revision;
 data.phase_reason=s.phase_reason;data.phase_losses=s.phase_losses;data.cam_rejected=s.cam_rejected;data.cam_error_deg=s.cam_error_deg;
 data.timing_fault=s.timing_cause;data.last_timing_fault=s.last_timing_cause;data.virtual_high_mask=s.virtual_high_mask;data.physical_command_mask=s.physical_command_mask;
 data.board_flags=(s.adc_ok?1:0)|(s.safe?2:0)|(s.interlock?4:0)|(s.overflow?8:0);
 for(unsigned i=0;i<8;++i)data.raw_adc[i]=static_cast<std::uint16_t>(s.raw[i]);
 latest_data=data;published=data;xSemaphoreGive(mutex);return true;
}
std::string tune_json(){xSemaphoreTake(mutex,portMAX_DELAY);std::string copy=document_text();xSemaphoreGive(mutex);return copy;}
namespace {
// Owned, fully prepared text reaches the configuration fence only after all
// project-side allocation/validation succeeds. This path allocates no strings.
int persist_prepared(const engine::Tune&candidate,std::uint32_t expected,Document prepared,const char*&reason){
 if(!prepared||std::strlen(prepared.get())>engine::tune_maximum){reason="Encoded engine tune exceeds 48 KiB; previous data retained";return 413;}
 xSemaphoreTake(mutex,portMAX_DELAY);
 if(!storage_ok){reason=storage_reason;xSemaphoreGive(mutex);return 503;}
 if(expected!=active.revision||expected==UINT32_MAX){reason="Engine tune revision changed; reload before saving";xSemaphoreGive(mutex);return 409;}
 engine_target::begin_configuration();
 const auto err=engine_storage::save(prepared.get(),std::strlen(prepared.get()));
 if(err!=ESP_OK){storage_ok=false;storage_reason="Engine persistence failed; runtime retained, saves blocked until restart and inspection";reason=storage_reason;engine_target::finish_configuration(active.revision,0);xSemaphoreGive(mutex);return 507;}
 active=candidate;active.revision=expected+1;document.swap(prepared);controller.reset();stamp=0;latest=engine::Output{};latest_data=engine::RuntimeSample{};
 engine_target::finish_configuration(active.revision,0);xSemaphoreGive(mutex);return 200;
}
int prepare_and_save(const char*text,const char*&reason){
 auto candidate=heap_object<engine::Tune>();if(!candidate){reason="Engine tune allocation failed; previous data retained";return 500;}
 if(!web::safe_json(text,std::strlen(text),engine::tune_maximum)){reason="Invalid engine tune JSON";return 422;}
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);if(!j){reason="Invalid engine tune JSON";return 422;}
 if(!engine::parse_tune(j,*candidate)){cJSON_Delete(j);reason="Invalid engine tune: schema, table axes, physical units or hardware pulse limits";return 422;}
 if(!engine::upgrade_tune_document(j)){cJSON_Delete(j);reason="Allocation failed";return 500;}
 if(candidate->revision==UINT32_MAX){cJSON_Delete(j);reason="Engine tune revision exhausted";return 409;}
 cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"revision"),candidate->revision+1);
 Document prepared(cJSON_PrintUnformatted(j),&cJSON_free);cJSON_Delete(j);
 if(!prepared){reason="Allocation failed";return 500;}
 return persist_prepared(*candidate,candidate->revision,std::move(prepared),reason);
}
}
int save(const char*text,std::string&reason){const char*message="";const int code=prepare_and_save(text,message);if(code!=200)reason=message;return code;}
cJSON* sample(){
 xSemaphoreTake(mutex,portMAX_DELAY);const auto copy=latest_data;xSemaphoreGive(mutex);
 return engine::data_json(copy,engine_target::clock_us());
}
tuning::Result tuning_load(engine::Tune&out){
 if(!mutex||xSemaphoreTake(mutex,0)!=pdTRUE)return tuning::Result::Busy;
 out=active;const bool ok=storage_ok;xSemaphoreGive(mutex);return ok?tuning::Result::Ok:tuning::Result::StorageBlocked;
}
tuning::Result tuning_current(std::uint32_t&revision){
 if(!mutex||xSemaphoreTake(mutex,0)!=pdTRUE)return tuning::Result::Busy;
 revision=active.revision;const bool ok=storage_ok;xSemaphoreGive(mutex);return ok?tuning::Result::Ok:tuning::Result::StorageBlocked;
}
bool tuning_sample(engine::RuntimeSample&out){
 if(!mutex||xSemaphoreTake(mutex,0)!=pdTRUE)return false;
 out=latest_data;xSemaphoreGive(mutex);return true;
}
tuning::Result tuning_commit(const engine::Tune&candidate,std::uint32_t&saved_revision){
 if(engine::validate(candidate))return tuning::Result::Invalid;
 struct Text{std::array<char,engine::tune_maximum+1> bytes{};};
 auto copy=heap_object<Text>();if(!copy)return tuning::Result::NoMemory;
 if(!mutex||xSemaphoreTake(mutex,0)!=pdTRUE)return tuning::Result::Busy;
 if(!storage_ok){xSemaphoreGive(mutex);return tuning::Result::StorageBlocked;}
 if(candidate.revision!=active.revision||candidate.revision==UINT32_MAX){xSemaphoreGive(mutex);return tuning::Result::Conflict;}
 const auto size=std::strlen(document_text());if(size>engine::tune_maximum){xSemaphoreGive(mutex);return tuning::Result::Invalid;}
 std::memcpy(copy->bytes.data(),document_text(),size+1);xSemaphoreGive(mutex);
 auto*j=cJSON_ParseWithOpts(copy->bytes.data(),nullptr,true);copy.reset();if(!j)return tuning::Result::NoMemory;
 tuning::Document update(j);const bool ok=tuning::update_document(update,candidate);
 if(ok)cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"revision"),candidate.revision+1);
 Document encoded(ok?cJSON_PrintUnformatted(j):nullptr,&cJSON_free);cJSON_Delete(j);if(!encoded)return tuning::Result::NoMemory;
 const char*reason="";const int code=persist_prepared(candidate,candidate.revision,std::move(encoded),reason);
 if(code==200){saved_revision=candidate.revision+1;return tuning::Result::Ok;}
 if(code==409)return tuning::Result::Conflict;
 if(code==503||code==507)return tuning::Result::StorageBlocked;
 if(code==500)return tuning::Result::NoMemory;
 return tuning::Result::Invalid;
}
cJSON* snapshot(){
 xSemaphoreTake(mutex,portMAX_DELAY);const auto output=latest;const auto revision=active.revision;const auto strategy=active.strategy;const bool stored=storage_ok;const auto sample_stamp=stamp;const auto* reason=binding;const auto* storage_message=storage_reason;xSemaphoreGive(mutex);
 auto*j=engine::output_json(output);if(!j)return nullptr;if(!cJSON_AddStringToObject(j,"error",stored?"":storage_message)){cJSON_Delete(j);return nullptr;}const auto now=engine_target::clock_us();cJSON_AddNumberToObject(j,"revision",revision);cJSON_AddBoolToObject(j,"storage_ok",stored);cJSON_AddStringToObject(j,"binding",reason);cJSON_AddNumberToObject(j,"sample_age_ms",sample_stamp&&now>=sample_stamp?(now-sample_stamp)/1000.0:-1);cJSON_AddBoolToObject(j,"simulator",false);cJSON_AddBoolToObject(j,"fresh",sample_stamp&&now>=sample_stamp&&now-sample_stamp<50000);auto*timing=engine_target::snapshot();if(!timing||!cJSON_AddItemToObject(j,"timing",timing)){cJSON_Delete(timing);cJSON_Delete(j);return nullptr;}
 cJSON_AddStringToObject(j,"active_strategy",engine::strategy_name(strategy));
 const auto phase=engine_target::measurement();cJSON_AddBoolToObject(j,"crank_synced",phase.synced);cJSON_AddBoolToObject(j,"phase_synced",phase.phase_synced);cJSON_AddBoolToObject(j,"phase_required",phase.phase_required);
 cJSON_AddStringToObject(j,"phase_reason",engine::PhaseDecoder::reason_name(phase.phase_reason));cJSON_AddNumberToObject(j,"phase_losses",phase.phase_losses);cJSON_AddNumberToObject(j,"cam_rejected",phase.cam_rejected);cJSON_AddNumberToObject(j,"cam_error_deg",phase.cam_error_deg);return j;
}
}
