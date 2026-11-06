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
int main(int argc,char**argv){
 switch_service::init();auto s=initial_ready();need(s.samples[0].level&&s.samples[1].level,"both real register-derived contacts high");
 if(argc>2&&!std::strcmp(argv[1],"omit")){
  fixture::omit=std::atoi(argv[2]);const auto count=s.reads;do{s=tick();}while(s.reads==count&&!s.fault_pending);
  need(s.ready==(fixture::omit==8),"only ignored historical INTCAP may be omitted without semantic impact");
 }else if(argc>1&&!std::strcmp(argv[1],"race")){
  fixture::next_error=ESP_ERR_TIMEOUT;do{s=tick();}while(!s.fault_pending);const auto first=s;
  switch_service::control_observed(first,false);
  for(unsigned i=0;i<40;++i)s=tick();
  need(s.reads>first.reads&&!s.ready&&s.fault_pending,"actual SDK adapter does not hide skipped failure");
  fixture::next_error=ESP_FAIL;do{s=tick();}while(s.fault_id==first.fault_id);const auto second=s;
  switch_service::control_observed(first,true);s=tick();need(s.fault_pending&&s.fault_id==second.fault_id,"actual service rejects old acknowledged snapshot");
  switch_service::control_observed(second,true);for(unsigned i=0;i<40&&!s.ready;++i)s=tick();need(s.ready,"new source read recovers after exact ACK");
 }else if(argc>1&&!std::strcmp(argv[1],"fatal")){
  fixture::time=s.read_completed_us-1;s=tick();need(s.phase==si::Phase::Fatal,"actual adapter latches reversed producer clock");
  switch_service::control_observed(s,true);s=tick(0);need(s.phase==si::Phase::Fatal&&!s.raw_known&&fixture::deleted==1,"Off releases I2C and preserves fatal state");
  s=tick(3);need(s.phase==si::Phase::Fatal&&!s.ready&&fixture::created==1,"Input cannot recreate bus to clear fatal latch");
 }
 auto*j=switch_service::snapshot();need(j!=nullptr,"diagnostic JSON built");auto*f=cJSON_GetObjectItemCaseSensitive(j,"fault_id");need(cJSON_IsString(f),"fault ID is exact decimal string");cJSON_Delete(j);
 std::printf("{\"passed\":true,\"assertions\":%u,\"scenario\":\"%s\",\"physical_qualification\":false}\n",checks,argc>1?argv[1]:"normal");
}
