// Actual target service, deterministic two-device SDK/bus model. No physical
// wiring, optical output, target timing or analog behavior is measured here.
#include "ecu/switch_service.hpp"
#include "ecu/board_status.hpp"
#include "ecu/engine_target.hpp"
#include "ecu/engine.hpp"
#include "driver/i2c_master.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <string>
#include <thread>
#include <vector>
namespace si=ecu::switch_input;
namespace sl=ecu::status_led;
static unsigned checks=0;
static void verify(bool ok,const char*why,unsigned line){++checks;if(!ok){std::fprintf(stderr,"Check%u line%u failed: %s\n",checks,line,why);std::abort();}}
#define check(value) verify((value),#value,__LINE__)
namespace fake {
 std::uint64_t now=100000,tick_start=100000;
 fake_i2c_bus bus;std::array<fake_i2c_device,2> devices;
 bool bus_owned=false,common_stuck=false;
 std::array<bool,2> owned{},reset_guard{},underfill{};
 std::array<esp_err_t,2> transfer_error{},remove_error{};
 std::array<unsigned,2> adds{},removes{},reads{},writes{};
 unsigned creates=0,deletes=0,traffic=0;
 std::thread::id owner=std::this_thread::get_id();
 std::array<std::array<std::uint8_t,11>,2> reg{{{{0xff,0,0,0,0,0,0,0,0,0,0}},{{0xff,0,0,0,0,0,0,0,0,0,0}}}};
 std::array<std::uint64_t,2> read_us{{1200,1200}},guard_us{{400,400}},write_us{{200,200}};
 struct Write {unsigned slot,reg,value;};std::vector<Write> trace;
 unsigned slot(i2c_master_dev_handle_t dev){check(dev==&devices[0]||dev==&devices[1]);return dev==&devices[1];}
 void sdk(){check(std::this_thread::get_id()==owner);}
 void timeout(int ms){sdk();check(now>=tick_start&&now-tick_start<=3000);check(ms>=1&&ms<=int((3000-(now-tick_start))/1000));++traffic;}
 std::uint8_t gpio(unsigned slot){
  if(slot)return reg[1][10]&~reg[1][0];
  unsigned raw=0x28|3;if(!(reg[0][0]&0x80)&&(reg[0][10]&0x80))raw|=0xc0;
  return raw^reg[0][1];
 }
}
namespace ecu::engine_target {std::uint64_t clock_us(){return fake::now;}}
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t*c,i2c_master_bus_handle_t*out){
 fake::sdk();++fake::creates;check(!fake::bus_owned&&c->sda_io_num==41&&c->scl_io_num==42&&c->i2c_port==-1);
 check(!c->flags.enable_internal_pullup&&!c->flags.allow_pd&&!c->trans_queue_depth&&c->glitch_ignore_cnt==7);
 fake::bus_owned=true;*out=&fake::bus;return ESP_OK;
}
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t bus,const i2c_device_config_t*c,i2c_master_dev_handle_t*out){
 fake::sdk();check(bus==&fake::bus&&fake::bus_owned&&c->dev_addr_length==I2C_ADDR_BIT_LEN_7);
 check((c->device_address==0x20||c->device_address==0x21)&&c->scl_speed_hz==100000&&c->scl_wait_us==500&&!c->flags.disable_ack_check);
 const unsigned slot=c->device_address-0x20;check(!fake::owned[slot]);fake::owned[slot]=true;++fake::adds[slot];*out=&fake::devices[slot];return ESP_OK;
}
esp_err_t i2c_master_bus_rm_device(i2c_master_dev_handle_t dev){
 fake::sdk();const auto slot=fake::slot(dev);check(fake::owned[slot]);++fake::removes[slot];
 if(fake::remove_error[slot])return fake::remove_error[slot];
 fake::owned[slot]=false;return ESP_OK;
}
esp_err_t i2c_del_master_bus(i2c_master_bus_handle_t bus){
 fake::sdk();check(bus==&fake::bus&&fake::bus_owned&&!fake::owned[0]&&!fake::owned[1]);++fake::deletes;fake::bus_owned=false;return ESP_OK;
}
esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t dev,const std::uint8_t*tx,std::size_t tx_n,std::uint8_t*rx,std::size_t n,int timeout){
 fake::timeout(timeout);const auto slot=fake::slot(dev);check(fake::owned[slot]&&tx_n==1);++fake::reads[slot];
 fake::now+=n==11?fake::read_us[slot]:fake::guard_us[slot];
 if(fake::common_stuck)return ESP_ERR_TIMEOUT;
 if(fake::transfer_error[slot])return fake::transfer_error[slot];
 if(fake::underfill[slot])return ESP_OK;
 if(n==1&&*tx==0&&fake::reset_guard[slot]){fake::reg[slot].fill(0);fake::reg[slot][0]=0xff;fake::reset_guard[slot]=false;}
 for(unsigned i=0;i<n;++i){const auto r=(*tx+(fake::reg[slot][5]&0x20?0:i))%11;rx[i]=r==9?fake::gpio(slot):fake::reg[slot][r];}
 if(n==11&&*tx==0)fake::reg[slot][7]=0;
 return ESP_OK;
}
esp_err_t i2c_master_transmit(i2c_master_dev_handle_t dev,const std::uint8_t*bytes,std::size_t n,int timeout){
 fake::timeout(timeout);const auto slot=fake::slot(dev);check(fake::owned[slot]&&n>=2&&n<=8);++fake::writes[slot];fake::now+=fake::write_us[slot];
 if(fake::common_stuck)return ESP_ERR_TIMEOUT;
 if(fake::transfer_error[slot])return fake::transfer_error[slot];
 for(unsigned i=1;i<n;++i){const auto r=(bytes[0]+(fake::reg[slot][5]&0x20?0:i-1))%11;fake::trace.push_back({slot,r,bytes[i]});fake::reg[slot][r]=bytes[i];}
 return ESP_OK;
}
static ecu::engine::Output control(const si::Snapshot&s,bool required){
 using namespace ecu::engine;Tune t;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);
 if(required){t.secondary_tables.fuel.mode=ecu::secondary::Mode::Input;t.secondary_tables.fuel.debounce_ms=0;t.secondary_tables.spark.mode=ecu::secondary::Mode::Input;t.secondary_tables.spark.debounce_ms=0;}
 Inputs in;in.rpm=2000;in.map_kpa=50;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;
 in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;in.sampled_us=fake::now;in.table_switches=s.samples;
 Controller controller;return controller.step(t,in,fake::now);
}
static si::Snapshot tick(std::uint8_t mask=3,bool consume=true){
 fake::tick_start=fake::now;auto s=ecu::switch_service::tick(mask);
 // Deliberate SDK overrun tests can exceed this; normal arbitration cannot.
 if(fake::read_us[0]<=1200&&fake::read_us[1]<=1200)check(fake::now-fake::tick_start<=3000);
 if(s.fault_pending&&consume){auto o=control(s,mask!=0);if(mask)check((o.faults&ecu::engine::BadSensor)&&o.fuel_cut&&o.spark_cut);ecu::switch_service::control_observed(s,true);}
 fake::now=std::max(fake::now,fake::tick_start+5000);return s;
}
static bool boolean(cJSON*j,const char*key){auto*v=cJSON_GetObjectItemCaseSensitive(j,key);check(cJSON_IsBool(v));return cJSON_IsTrue(v);}
static double number(cJSON*j,const char*key){auto*v=cJSON_GetObjectItemCaseSensitive(j,key);check(cJSON_IsNumber(v));return v->valuedouble;}
static si::Snapshot ready(std::uint8_t mask=3){
 si::Snapshot s;for(unsigned n=0;n<150;++n){s=tick(mask);auto*j=ecu::board_status::snapshot();const bool led=boolean(j,"ready");cJSON_Delete(j);if(led&&(!mask||s.ready))return s;}check(false);return s;
}
static std::size_t allocations=0,fail_after=SIZE_MAX;
static void*alloc(std::size_t n){if(allocations++==fail_after)return nullptr;return std::malloc(n);}
static const char*fixture_directory=nullptr;
static void export_status(const char*name){
 if(!fixture_directory)return;
 auto*j=ecu::board_status::snapshot();check(j);char*text=cJSON_PrintUnformatted(j);cJSON_Delete(j);check(text);
 const std::string path=std::string(fixture_directory)+"/"+name+".json";
 const int file=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);check(file>=0);
 const auto n=std::strlen(text);check(write(file,text,n)==static_cast<ssize_t>(n));check(close(file)==0);cJSON_free(text);
}
int main(int argc,char**argv){
 check(argc==1||argc==2);if(argc==2)fixture_directory=argv[1];
 using namespace ecu;switch_service::init();
 const auto before=fake::traffic;board_status::request(sl::Pattern::Normal);check(fake::traffic==before);
 auto s=ready(0);check(fake::creates==1&&fake::adds[1]==1&&!fake::adds[0]&&!fake::reads[0]&&!fake::writes[0]);
 check(fake::trace.size()==10&&fake::trace[0].slot==1&&fake::trace[0].reg==10&&fake::trace[0].value==0);
 for(unsigned n=0;n<9;++n)check(fake::trace[n].value==(fake::trace[n].reg==5?4U:0U));
 check(fake::trace[9].reg==10&&fake::trace[9].value==2);
 auto*j=board_status::snapshot();check(boolean(j,"ready")&&number(j,"last_verified_latch")==2&&number(j,"shared_budget_us")==3000);cJSON_Delete(j);
 export_status("green_ready");
 s=ready();check(s.samples[0].source==secondary::InputSource::TargetProtected&&s.samples[0].valid&&s.samples[1].valid);
 check(fake::creates==1&&fake::adds[0]==1&&fake::adds[1]==1);check(!control(s,true).faults);
 // The guard read does not leave two whole ms for another guarded LED read.
 for(unsigned n=0;n<100;++n)s=tick();
 j=board_status::snapshot();
 auto*skips=cJSON_GetObjectItemCaseSensitive(j,"budget_skips");check(cJSON_IsString(skips)&&std::strtoull(skips->valuestring,nullptr,10)>0);cJSON_Delete(j);
 // Address-local LED failure is advisory. The required switch remains valid
 // and control does not acquire a new LED dependency or LED SDK error.
 fake::transfer_error[1]=ESP_ERR_TIMEOUT;
 bool failed=false;for(unsigned n=0;n<50&&!failed;++n){s=tick();j=board_status::snapshot();failed=number(j,"sdk_error")==ESP_ERR_TIMEOUT;cJSON_Delete(j);}
 check(failed&&s.ready&&!s.fault_pending&&!control(s,true).faults);
 j=board_status::snapshot();check(!boolean(j,"fresh")&&boolean(j,"known")&&number(j,"last_verified_latch")==2);cJSON_Delete(j);
 export_status("led_timeout");
 j=switch_service::snapshot();check(number(j,"sdk_error")==ESP_OK&&boolean(j,"ready"));cJSON_Delete(j);
 fake::transfer_error[1]=ESP_OK;s=ready();check(s.ready);
 // Reset exactly between the two guarded transactions cannot retain Ready.
 fake::reset_guard[1]=true;failed=false;
 for(unsigned n=0;n<50&&!failed;++n){s=tick();j=board_status::snapshot();failed=!std::strcmp(cJSON_GetObjectItemCaseSensitive(j,"fault")->valuestring,"configuration_mismatch");cJSON_Delete(j);}
 check(failed&&s.ready&&!control(s,true).faults);s=ready();
 export_status("led_recovered");
 // Cleanup retries preserve the switch handle and never delete the LED bus.
 fake::remove_error[0]=ESP_FAIL;const auto removed=fake::removes[0];tick(0);check(fake::owned[0]&&fake::removes[0]==removed+1);
 for(unsigned n=0;n<10;++n)tick(0);
 check(fake::removes[0]==removed+1);
 fake::remove_error[0]=ESP_OK;ready(0);for(unsigned n=0;n<25;++n)tick(0);
 check(!fake::owned[0]&&fake::owned[1]&&fake::bus_owned&&!fake::deletes&&fake::creates==1);
 // Requesting policy from another task never performs SDK I/O.
 const auto traffic=fake::traffic;std::thread radio([](){for(unsigned n=0;n<1000;++n)board_status::request(n%2?sl::Pattern::Pairing:sl::Pattern::Problem);board_status::request(sl::Pattern::Normal);});radio.join();
 check(fake::traffic==traffic);s=ready();
 // A stuck shared bus DOES invalidate a required switch. A skipped control
 // observation cannot ACK it, even while the LED independently retries.
 fake::common_stuck=true;s=tick(3,false);check(s.fault_pending&&!s.ready&&control(s,true).fuel_cut);
 export_status("shared_bus_fault");
 switch_service::control_observed(s,false);for(unsigned n=0;n<25;++n)s=tick(3,false);check(s.fault_pending&&!s.ready);
 fake::common_stuck=false;for(unsigned n=0;n<25;++n)s=tick(3,false);check(s.fault_pending&&!s.ready);
 switch_service::control_observed(s,true);s=ready();check(s.ready&&!control(s,true).faults);
 export_status("bus_recovered");
 // A read-only query after the monitor stops cannot refresh producer age.
 const auto stale_traffic=fake::traffic;fake::now+=sl::fresh_us+1;
 j=board_status::snapshot();check(!boolean(j,"ready")&&!boolean(j,"fresh")&&boolean(j,"known"));cJSON_Delete(j);
 check(fake::traffic==stale_traffic);export_status("stale_latch");
 // Every board-status allocation cut yields nullptr, never a partial object.
 cJSON_Hooks hooks{alloc,std::free};cJSON_InitHooks(&hooks);allocations=0;j=board_status::snapshot();check(j);const auto total=allocations;cJSON_Delete(j);
 for(std::size_t n=0;n<total;++n){allocations=0;fail_after=n;j=board_status::snapshot();check(!j);}cJSON_InitHooks(nullptr);
 std::printf("{\"passed\":true,\"shared_service_checks\":%u,\"status_allocation_cuts\":%zu,\"physical_i2c_or_LED_test\":false}\n",checks,total);
}
