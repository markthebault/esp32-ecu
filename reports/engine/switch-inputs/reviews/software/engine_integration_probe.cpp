#include "ecu/switch_service.hpp"
#include "ecu/engine_target.hpp"
#include "driver/i2c_master.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace ecu;
namespace si=ecu::switch_input;
namespace fixture {
 std::uint64_t time=100000;fake_i2c_bus bus;fake_i2c_device dev;
 std::array<std::uint8_t,11> regs{0xff,0,0,0,0,0,0,0,0,0,0};
 int omit=-1;esp_err_t next_error=ESP_OK;
 unsigned reads=0,writes=0,created=0,deleted=0;
 std::uint8_t pins(){return static_cast<std::uint8_t>(0x2b|((!(regs[0]&0x80)&&(regs[10]&0x80))?0xc0:0));}
}
unsigned checks=0;
void need(bool b,const char*s){++checks;if(!b){std::fprintf(stderr,"FAIL%u %s\n",checks,s);std::abort();}}
namespace ecu::engine_target {std::uint64_t clock_us(){return fixture::time;}}
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t*,i2c_master_bus_handle_t*out){++fixture::created;*out=&fixture::bus;return ESP_OK;}
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t,const i2c_device_config_t*,i2c_master_dev_handle_t*out){*out=&fixture::dev;return ESP_OK;}
esp_err_t i2c_master_bus_rm_device(i2c_master_dev_handle_t){return ESP_OK;}
esp_err_t i2c_del_master_bus(i2c_master_bus_handle_t){++fixture::deleted;return ESP_OK;}
esp_err_t i2c_master_transmit(i2c_master_dev_handle_t,const std::uint8_t*p,std::size_t n,int timeout){
 need(timeout>0&&timeout<=3,"write has finite timeout");++fixture::writes;fixture::time+=100;
 if(fixture::next_error){auto e=fixture::next_error;fixture::next_error=ESP_OK;return e;}
 for(std::size_t i=1;i<n;++i)fixture::regs[p[0]+i-1]=p[i];
 return ESP_OK;
}
esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t,const std::uint8_t*p,std::size_t tx,std::uint8_t*out,std::size_t n,int timeout){
 need(tx==1&&timeout>0&&timeout<=3,"read has finite timeout");++fixture::reads;fixture::time+=n==11?1200:400;
 if(fixture::next_error){auto e=fixture::next_error;fixture::next_error=ESP_OK;return e;}
 for(std::size_t i=0;i<n;++i){
  const unsigned slot=n==11?i:p[0]==0?11:100;
  if(static_cast<int>(slot)==fixture::omit)continue;
  const auto index=p[0]+i;out[i]=index==9?fixture::pins():fixture::regs[index];
 }
 return ESP_OK;
}
si::Snapshot tick(unsigned mask=3){const auto t=fixture::time;auto s=switch_service::tick(mask);fixture::time=std::max(t+5000,fixture::time);return s;}
si::Snapshot initial_ready(){for(unsigned i=0;i<20;++i){auto s=tick();if(s.ready)return s;}need(false,"initial readiness");return {};}
#include "ecu/engine_service.hpp"
#include "ecu/engine_data.hpp"
#include "freertos/semphr.h"
#include "esp_partition.h"
#include "nvs_flash.h"
#include <string>
namespace persistence {std::string saved;}
esp_err_t nvs_flash_init_partition(const char*){return ESP_OK;}
esp_err_t nvs_open(const char*,nvs_open_mode_t,nvs_handle_t*){return ESP_ERR_NVS_NOT_FOUND;}
esp_err_t nvs_open_from_partition(const char*,const char*,nvs_open_mode_t,nvs_handle_t*h){*h=1;return ESP_OK;}
esp_err_t nvs_get_str(nvs_handle_t,const char*,char*,std::size_t*){return ESP_ERR_NVS_NOT_FOUND;}
esp_err_t nvs_get_blob(nvs_handle_t,const char*,void*,std::size_t*){return ESP_ERR_NVS_NOT_FOUND;}
esp_err_t nvs_set_blob(nvs_handle_t,const char*,const void*p,std::size_t n){persistence::saved.assign(static_cast<const char*>(p),n);return ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t){return ESP_OK;}
void nvs_close(nvs_handle_t){}
const esp_partition_t*esp_partition_find_first(unsigned,unsigned,const char*){static const esp_partition_t p{0x210000,0x20000};return &p;}
namespace ecu::engine_target {
 timing::Command last;
 bool submit(const timing::Command&c){last=c;return true;}
 void begin_configuration(){}
 void finish_configuration(std::uint32_t,std::uint32_t){}
 cJSON*snapshot(){return cJSON_CreateObject();}
 Measurement measurement(){return {};}
}
int main(){
 engine_service::init();switch_service::init();std::uint8_t mask=77;
 need(engine_service::switch_requirements(mask)&&mask==0,"default active engine tune owns no switch inputs");
 engine::Tune tune;need(engine_service::tuning_load(tune)==tuning::Result::Ok,"actual typed engine tune load");
 tune.secondary_tables.fuel.mode=secondary::Mode::Input;tune.secondary_tables.spark.mode=secondary::Mode::Input;
 tune.secondary_tables.fuel.debounce_ms=20;tune.secondary_tables.spark.debounce_ms=20;
 std::uint32_t revision=0;need(engine_service::tuning_commit(tune,revision)==tuning::Result::Ok,"actual tune commit enables requested accessory contract");
 need(engine_service::switch_requirements(mask)&&mask==3,"actual getter unions both enabled input channels");
 reviewer_force_busy=true;mask=1;need(!engine_service::switch_requirements(mask)&&mask==1,"skipped actual getter preserves caller's previous ownership mask");reviewer_force_busy=false;
 engine_service::switch_requirements(mask);
 config::Config profile;const char*units[]={"kPa","%","C","C","lambda","kPa"};const double values[]={45,10,85,25,1,101};
 for(unsigned i=0;i<6;++i){auto&sensor=profile.sensors[i];sensor.confirmed=true;sensor.mode=config::Mode::Linear;std::strcpy(sensor.unit,units[i]);sensor.y0=sensor.y1=values[i];}
 web::Sample live;live.adc_ok=true;live.synced=true;live.rpm=1200;live.raw.fill(2048);live.raw[6]=1318;live.raw[7]=3723;
 engine::RuntimeSample data;
 auto observe=[&](const si::Snapshot&s){live.table_switches=s.samples;const auto stamp=fixture::time;const bool completed=engine_service::observe(live,profile,stamp,stamp,data);switch_service::control_observed(s,completed);return completed;};
 si::Snapshot s;for(unsigned i=0;i<15;++i){s=tick(mask);need(observe(s),"uncontended actual observation completes");}
 need(data.secondary_fuel.input_qualified&&data.secondary_spark.input_qualified&&!(data.controller_faults&engine::BadSensor),"production acquire/bind/engine filtering qualifies both physical-source input shapes");
 need(data.secondary_fuel.input_source==secondary::InputSource::TargetProtected&&data.secondary_fuel.input_observed_us==s.observed_us,"target provenance and raw observation timestamp survive actual runtime encoding");
 reviewer_force_busy=true;fixture::next_error=ESP_ERR_TIMEOUT;do{s=tick(mask);}while(!s.fault_pending);const auto failure=s;const auto last_sequence=data.sequence;
 need(!observe(s)&&data.sequence==last_sequence,"actual engine mutex skip preserves previous runtime observation");
 for(unsigned i=0;i<40;++i){s=tick(mask);need(!observe(s),"actual engine remains busy while bus recovery proceeds");}
 need(s.reads>failure.reads&&s.fault_pending&&!s.ready,"actual controller skip cannot hide recovered bus fault");
 reviewer_force_busy=false;need(observe(s),"actual invalid snapshot is finally consumed");
 need(data.controller_faults&engine::BadSensor,"invalid switch reaches production BadSensor control fault");
 need(data.has(engine::FuelCut)&&data.has(engine::SparkCut)&&!data.secondary_fuel.input_qualified&&!data.secondary_spark.input_qualified,"invalid source cuts proposals and discards both filter qualifications");
 auto*j=switch_service::snapshot();need(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(j,"fault_pending")),"completed actual engine observation acknowledges matching source fault");cJSON_Delete(j);
 bool recovered=false;for(unsigned i=0;i<15;++i){s=tick(mask);observe(s);if(data.secondary_fuel.input_qualified&&data.secondary_spark.input_qualified)recovered=true;}
 need(recovered&&!(data.controller_faults&engine::BadSensor),"fresh source samples and debounce requalify actual control after consumption");
 std::printf("{\"passed\":true,\"assertions\":%u,\"actual_engine_and_switch_services\":true,\"physical_qualification\":false}\n",checks);
}
