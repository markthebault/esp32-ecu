#include "ecu/switch_service.hpp"
#include "ecu/switch_transport.hpp"
#include "ecu/engine_target.hpp"
#include "ecu/pins.hpp"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include <cstdio>

namespace ecu::switch_service {
namespace {
using switch_input::Result;
Result result(esp_err_t code){return code==ESP_OK?Result::Ok:code==ESP_ERR_TIMEOUT?Result::Timeout:
 code==ESP_ERR_NOT_FOUND||code==ESP_ERR_NO_MEM?Result::Unavailable:Result::BusError;}
class Driver {
 i2c_master_bus_handle_t bus_=nullptr;i2c_master_dev_handle_t device_=nullptr;
public:
 esp_err_t last_error=ESP_OK;
 bool allocated()const{return bus_||device_;}
 Result prepare(){
  if(!bus_){
   i2c_master_bus_config_t bus{};bus.i2c_port=-1;
   bus.sda_io_num=static_cast<gpio_num_t>(pins::i2c_sda);bus.scl_io_num=static_cast<gpio_num_t>(pins::i2c_scl);
   bus.clk_source=I2C_CLK_SRC_DEFAULT;bus.glitch_ignore_cnt=7;
   // J4 already has R16/R17 4.7k pullups. Never enable internal pullups or scan.
   last_error=i2c_new_master_bus(&bus,&bus_);if(last_error!=ESP_OK){bus_=nullptr;return result(last_error);}
  }
  if(!device_){
   i2c_device_config_t device{};device.dev_addr_length=I2C_ADDR_BIT_LEN_7;
   device.device_address=switch_input::address;device.scl_speed_hz=100000;device.scl_wait_us=500;
   last_error=i2c_master_bus_add_device(bus_,&device,&device_);
   if(last_error!=ESP_OK){device_=nullptr;return result(last_error);}
  }
  return Result::Ok;
 }
 Result read(std::uint8_t reg,std::uint8_t*bytes,std::size_t size,int timeout_ms){
  last_error=i2c_master_transmit_receive(device_,&reg,1,bytes,size,timeout_ms);return result(last_error);
 }
 Result write(std::uint8_t reg,const std::uint8_t*bytes,std::size_t size,int timeout_ms){
  std::array<std::uint8_t,8> frame{};frame[0]=reg;
  if(size>frame.size()-1){last_error=ESP_ERR_INVALID_ARG;return Result::BusError;}
  std::copy_n(bytes,size,frame.begin()+1);
  last_error=i2c_master_transmit(device_,frame.data(),size+1,timeout_ms);return result(last_error);
 }
 void release(){
  if(device_){last_error=i2c_master_bus_rm_device(device_);if(last_error!=ESP_OK)return;device_=nullptr;}
  if(bus_){last_error=i2c_del_master_bus(bus_);if(last_error==ESP_OK)bus_=nullptr;}
 }
};
Driver driver;
switch_input::Acquisition acquisition{secondary::InputSource::TargetProtected};
portMUX_TYPE publication_lock=portMUX_INITIALIZER_UNLOCKED;
switch_input::Snapshot published;
bool initialized=false,published_allocated=false;
esp_err_t published_error=ESP_OK;
std::uint64_t release_due=0;
void publish(){
 const auto copy=acquisition.snapshot();const bool allocated=driver.allocated();const auto error=driver.last_error;
 portENTER_CRITICAL(&publication_lock);published=copy;published_allocated=allocated;published_error=error;portEXIT_CRITICAL(&publication_lock);
}
bool decimal(cJSON*object,const char*key,std::uint64_t value){
 char bytes[21];std::snprintf(bytes,sizeof bytes,"%llu",static_cast<unsigned long long>(value));
 return cJSON_AddStringToObject(object,key,bytes)!=nullptr;
}
}
void init(){initialized=true;publish();}
switch_input::Snapshot tick(std::uint8_t requested_mask){
 if(!initialized)return {};
 const auto now=engine_target::clock_us();
 const auto op=acquisition.next(requested_mask,now);
 if(!requested_mask){
  // No device/register traffic while both rules are Off or use another mode.
  // SDK deletion has no timeout API. Retry failed cleanup without discarding
  // owned handles; never claim this task is a hard real-time deadline.
  if(driver.allocated()&&now>=release_due){driver.release();release_due=now>UINT64_MAX-switch_input::retry_us?UINT64_MAX:now+switch_input::retry_us;}
 }else{
  release_due=0;
  if(op){const auto done=switch_input::execute(op,driver,[]{return engine_target::clock_us();});
   acquisition.complete(op.token,done.reply,done.started_us,done.ended_us);}
 }
 publish();return acquisition.snapshot();
}
void control_observed(const switch_input::Snapshot&observed,bool completed){
 if(completed&&observed.fault_pending&&!observed.ready){
  (void)acquisition.invalid_sample_consumed(observed.fault_id);publish();
 }
}
cJSON* snapshot(){
 switch_input::Snapshot s;bool allocated;esp_err_t error;
 portENTER_CRITICAL(&publication_lock);s=published;allocated=published_allocated;error=published_error;portEXIT_CRITICAL(&publication_lock);
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 const auto now=engine_target::clock_us();
 bool ok=cJSON_AddStringToObject(j,"source","target_j4_i2c")&&
  cJSON_AddStringToObject(j,"contract","SW2-J4-DRAFT1")&&
  cJSON_AddStringToObject(j,"phase",switch_input::phase_name(s.phase))&&
  cJSON_AddStringToObject(j,"fault",switch_input::fault_name(s.fault))&&
  cJSON_AddStringToObject(j,"last_fault",switch_input::fault_name(s.last_fault))&&
  cJSON_AddNumberToObject(j,"requested_mask",s.requested_mask)&&
  cJSON_AddNumberToObject(j,"address",switch_input::address)&&
  cJSON_AddNumberToObject(j,"gpio",s.gpio)&&cJSON_AddBoolToObject(j,"raw_known",s.raw_known)&&
  cJSON_AddBoolToObject(j,"ready",s.ready)&&cJSON_AddBoolToObject(j,"fault_pending",s.fault_pending)&&
  cJSON_AddBoolToObject(j,"fresh",s.raw_known&&s.ready&&now>=s.observed_us&&now-s.observed_us<=switch_input::fresh_us)&&
  cJSON_AddBoolToObject(j,"bus_allocated",allocated)&&cJSON_AddNumberToObject(j,"sdk_error",error)&&
  cJSON_AddNumberToObject(j,"sample_age_ms",s.raw_known&&now>=s.observed_us?(now-s.observed_us)/1000.0:-1)&&
  cJSON_AddNumberToObject(j,"budget_us",switch_input::budget_us)&&
  cJSON_AddNumberToObject(j,"last_duration_us",s.last_duration_us)&&cJSON_AddNumberToObject(j,"max_duration_us",s.max_duration_us);
 for(const auto&entry:std::array<std::pair<const char*,std::uint64_t>,9>{{
  {"fault_id",s.fault_id},{"last_fault_us",s.last_fault_us},{"attempts",s.attempts},{"reads",s.reads},
  {"failures",s.failures},{"consumed_faults",s.consumed_faults},{"configurations",s.configurations},
  {"observed_us",s.observed_us},{"read_completed_us",s.read_completed_us}}})ok=decimal(j,entry.first,entry.second)&&ok;
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
} // namespace ecu::switch_service
