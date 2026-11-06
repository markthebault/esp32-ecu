// Compiles the actual target service against deterministic SDK fixtures.
#include "ecu/switch_service.hpp"
#include "ecu/engine_target.hpp"
#include "ecu/engine_binding.hpp"
#include "driver/i2c_master.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace si=ecu::switch_input;
unsigned checks=0;
void check(bool ok,const char*why){++checks;if(!ok){std::fprintf(stderr,"Check%u failed: %s\n",checks,why);std::abort();}}
namespace fake {
 std::uint64_t now=100000;
 fake_i2c_bus bus;fake_i2c_device device;
 bool bus_owned=false,device_owned=false,underfill=false,reset_guard=false;
 esp_err_t create_error=ESP_OK,add_error=ESP_OK,next_error=ESP_OK,remove_error=ESP_OK,delete_error=ESP_OK;
 unsigned creates=0,adds=0,removes=0,deletes=0,reads=0,writes=0;
 std::uint64_t first_read_us=1200,guard_us=400;
 std::array<std::uint8_t,11> reg{0xff,0,0,0,0,0,0,0,0,0,0};
 std::uint8_t contacts=0,marker=0x28;
 std::vector<int> timeouts;
 void reset_device(){reg.fill(0);reg[0]=0xff;}
 std::uint8_t gpio(){unsigned pins=marker|contacts;if(!(reg[0]&0x80)&&(reg[10]&0x80))pins|=0xc0;return static_cast<std::uint8_t>(pins^reg[1]);}
 esp_err_t transfer_error(){const auto err=next_error;next_error=ESP_OK;return err;}
}
namespace ecu::engine_target {std::uint64_t clock_us(){return fake::now;}}
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t*c,i2c_master_bus_handle_t*out){
 ++fake::creates;check(c->i2c_port==-1&&c->sda_io_num==41&&c->scl_io_num==42,"Actual adapter owns only J4 SDA/SCL");
 check(!c->flags.enable_internal_pullup&&!c->flags.allow_pd&&!c->trans_queue_depth,"External pullups, synchronous bus, no powerdown mode");
 check(c->glitch_ignore_cnt==7,"Glitch filter configured");
 if(fake::create_error)return fake::create_error;
 check(!fake::bus_owned,"No duplicate bus allocation");fake::bus_owned=true;*out=&fake::bus;return ESP_OK;
}
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t bus,const i2c_device_config_t*c,i2c_master_dev_handle_t*out){
 ++fake::adds;check(bus==&fake::bus&&fake::bus_owned,"Device belongs to owned bus");
 check(c->dev_addr_length==I2C_ADDR_BIT_LEN_7&&c->device_address==0x20&&c->scl_speed_hz==100000&&c->scl_wait_us==500&&!c->flags.disable_ack_check,"Fixed address, 100kHz, stretch limit and ACK checking");
 if(fake::add_error)return fake::add_error;
 check(!fake::device_owned,"No duplicate device allocation");fake::device_owned=true;*out=&fake::device;return ESP_OK;
}
esp_err_t i2c_master_bus_rm_device(i2c_master_dev_handle_t dev){++fake::removes;check(dev==&fake::device&&fake::device_owned,"Remove owned device");if(fake::remove_error)return fake::remove_error;fake::device_owned=false;return ESP_OK;}
esp_err_t i2c_del_master_bus(i2c_master_bus_handle_t bus){++fake::deletes;check(bus==&fake::bus&&fake::bus_owned&&!fake::device_owned,"Delete after device removal");if(fake::delete_error)return fake::delete_error;fake::bus_owned=false;return ESP_OK;}
esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t dev,const std::uint8_t*tx,std::size_t tx_n,std::uint8_t*rx,std::size_t n,int timeout){
 check(dev==&fake::device&&fake::device_owned&&tx_n==1,"Actual driver uses register-address read");
 check(timeout>=1&&timeout<=3,"Actual SDK timeout finite, floored and positive");fake::timeouts.push_back(timeout);++fake::reads;
 fake::now+=n==11?fake::first_read_us:fake::guard_us;
 const auto err=fake::transfer_error();if(err)return err;
 if(fake::underfill)return ESP_OK;
 if(n==1&&*tx==0&&fake::reset_guard){fake::reset_device();fake::reset_guard=false;}
 for(std::size_t i=0;i<n;++i){const auto reg=(*tx+(fake::reg[5]&0x20?0:i))%11;rx[i]=reg==9?fake::gpio():fake::reg[reg];}
 return ESP_OK;
}
esp_err_t i2c_master_transmit(i2c_master_dev_handle_t dev,const std::uint8_t*bytes,std::size_t n,int timeout){
 check(dev==&fake::device&&fake::device_owned&&n>=2&&n<=8,"Bounded register write");check(timeout>=1&&timeout<=3,"Write timeout finite and positive");
 ++fake::writes;fake::now+=200;const auto err=fake::transfer_error();if(err)return err;
 const auto start=bytes[0];for(std::size_t i=1;i<n;++i){const auto reg=(start+(fake::reg[5]&0x20?0:i-1))%11;fake::reg[reg]=bytes[i];}
 return ESP_OK;
}
si::Snapshot tick(std::uint8_t mask=3){const auto begin=fake::now;const auto s=ecu::switch_service::tick(mask);fake::now=std::max(fake::now,begin+5000);return s;}
si::Snapshot ready(std::uint8_t mask=3){si::Snapshot s;for(unsigned i=0;i<80;++i){s=tick(mask);if(s.fault_pending)ecu::switch_service::control_observed(s,true);if(s.ready)return s;}check(false,"Actual service reaches readiness");return s;}
bool bool_field(const cJSON*j,const char*key){auto*v=cJSON_GetObjectItemCaseSensitive(j,key);check(v&&cJSON_IsBool(v),"Typed status boolean");return cJSON_IsTrue(v);}
std::size_t allocations=0,fail_after=SIZE_MAX;
void*alloc(std::size_t n){if(allocations++==fail_after)return nullptr;return std::malloc(n);}
int main(){
 using namespace ecu;
 switch_service::init();for(unsigned i=0;i<4;++i)tick(0);
 check(!fake::creates&&!fake::adds&&!fake::reads&&!fake::writes,"Defaults do not touch I2C");
 fake::create_error=ESP_ERR_NO_MEM;auto failed=tick();check(failed.fault==si::Fault::Unavailable&&failed.fault_pending&&!fake::bus_owned,"Optional bus allocation failure is invalid, not process abort");
 switch_service::control_observed(failed,true);fake::create_error=ESP_OK;
 fake::add_error=ESP_ERR_NO_MEM;for(unsigned i=0;i<22;++i)failed=tick();
 check(fake::bus_owned&&!fake::device_owned&&fake::creates==2,"Partial allocation retains one owned bus");
 fake::add_error=ESP_OK;auto s=ready();check(s.samples[0].source==secondary::InputSource::TargetProtected&&s.samples[0].valid,"Actual adapter fixes target provenance");
 check(fake::creates==2&&fake::adds>=2,"Retry reuses partial bus instead of leaking it");
 const auto stamp=s.observed_us;s=tick();check(s.observed_us==stamp,"Challenge write never refreshes read timestamp");
 fake::contacts=3;const auto contact_reads=s.reads;do{s=tick();}while(s.reads==contact_reads);
 check(s.samples[0].level&&s.samples[1].level,"Closed contact maps to raw high on both channels");
 web::Sample live;live.table_switches=s.samples;config::Config config;const auto bound=engine::bind_inputs(live,config,fake::now);
 check(bound.input.table_switches[0].observed_us==s.observed_us&&bound.input.table_switches[1].source==secondary::InputSource::TargetProtected,"Production binding copies acquisition provenance/time without synthesis");
 fake::next_error=ESP_ERR_TIMEOUT;failed=tick();check(failed.fault_pending&&!failed.samples[0].valid,"SDK timeout immediately invalidates both inputs");
 switch_service::control_observed(failed,false);
 const auto previous_reads=failed.reads;for(unsigned i=0;i<40;++i)s=tick();
 check(s.reads>previous_reads&&s.fault_pending&&!s.ready,"Recovery cannot hide fault after skipped engine lock");
 auto wrong=failed;++wrong.fault_id;switch_service::control_observed(wrong,true);check(tick().fault_pending,"Mismatched completed snapshot cannot clear current latch");
 switch_service::control_observed(failed,true);s=ready();check(s.ready&&!s.fault_pending,"Exact completed observation permits fresh-read recovery");
 fake::underfill=true;failed=tick();if(!failed.fault_pending)failed=tick();check(failed.fault_pending&&!failed.ready,"SDK success with missing bytes cannot reuse prior valid frame");fake::underfill=false;switch_service::control_observed(failed,true);s=ready();
 // Reach low challenge to reproduce the reset that defeats an initial-only guard.
 if(!s.challenge_high){const auto old_reads=s.reads;do{s=tick();}while(s.reads==old_reads);}
 s=tick();check(!s.challenge_high,"Low loopback challenge selected");fake::reset_guard=true;failed=tick();
 check(failed.fault==si::Fault::Configuration&&!failed.ready,"Actual two-transaction path catches reset before trailing IODIR");switch_service::control_observed(failed,true);s=ready();
 s=tick(1);check(!s.samples[1].valid&&s.samples[1].source==secondary::InputSource::Unavailable,"Unrequested input is unknown");
 fake::first_read_us=2001;for(unsigned i=0;i<3&&!s.fault_pending;++i)s=tick(1);check(s.fault==si::Fault::Budget&&!s.ready,"Insufficient remaining guard budget rejects without rounded timeout");fake::first_read_us=1200;
 fake::remove_error=ESP_FAIL;auto count=fake::removes;tick(0);check(fake::removes==count+1&&fake::device_owned,"Failed cleanup preserves ownership handles");
 for(unsigned i=0;i<10;++i)tick(0);
 check(fake::removes==count+1,"Cleanup errors use bounded retry cadence");
 fake::remove_error=ESP_OK;fake::delete_error=ESP_FAIL;for(unsigned i=0;i<12;++i)tick(0);check(!fake::device_owned&&fake::bus_owned,"Partial cleanup retains bus for later deletion");
 fake::delete_error=ESP_OK;for(unsigned i=0;i<22;++i)tick(0);check(!fake::bus_owned&&!fake::device_owned,"Off eventually releases all owned handles");
 const auto traffic=fake::reads+fake::writes;for(unsigned i=0;i<10;++i)tick(0);check(traffic==fake::reads+fake::writes,"No register traffic while disabled");
 auto*j=switch_service::snapshot();check(j&&cJSON_IsString(cJSON_GetObjectItemCaseSensitive(j,"fault_id"))&&!bool_field(j,"fresh")&&!bool_field(j,"bus_allocated"),"Target status preserves U64 counters and explicit unknown/disabled status");cJSON_Delete(j);
 // Every cJSON allocation failure must return a complete object or nullptr.
 cJSON_Hooks hooks{alloc,std::free};cJSON_InitHooks(&hooks);allocations=0;j=switch_service::snapshot();check(j!=nullptr,"Status baseline allocation");const auto total=allocations;cJSON_Delete(j);
 for(std::size_t n=0;n<total;++n){allocations=0;fail_after=n;j=switch_service::snapshot();check(!j,"Status allocation failure rejects partial object");}cJSON_InitHooks(nullptr);
 std::printf("{\"passed\":true,\"actual_service_checks\":%u,\"status_allocation_cuts\":%zu,\"physical_i2c_test\":false}\n",checks,total);
}
