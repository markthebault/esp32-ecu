// Independent scenarios around the actual shared service, with a small owned
// MCP register/SDK model. Each invocation starts fresh service globals.
#include "ecu/switch_service.hpp"
#include "ecu/board_status.hpp"
#include "ecu/engine_target.hpp"
#include "driver/i2c_master.h"
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
namespace si=ecu::switch_input;namespace sl=ecu::status_led;
static unsigned checks=0;
static void check(bool x,const char*s){++checks;if(!x){std::fprintf(stderr,"failed[%u]: %s\n",checks,s);std::exit(1);}}
namespace model{
 std::atomic<std::uint64_t> now{100000};std::uint64_t origin=100000;
 fake_i2c_bus bus;std::array<fake_i2c_device,2> device;
 bool bus_live=false,stuck=false;std::array<bool,2> live{},underfill{},reset_trailing{};
 unsigned create_count=0,delete_count=0;std::array<unsigned,2> added{},removed{},read_count{},write_count{};
 esp_err_t create_error=0,delete_error=0;std::array<esp_err_t,2> add_error{},remove_error{},transfer_error{};
 std::array<std::array<std::uint8_t,11>,2> reg{{{{255,0,0,0,0,0,0,0,0,0,0}},{{255,0,0,0,0,0,0,0,0,0,0}}}};
 std::array<std::uint64_t,2> first_read{1200,1200},guard_read{400,400},write_time{200,200};
 std::uint64_t create_time=0,remove_time=0;bool overrun=false;
 const auto owner=std::this_thread::get_id();
 struct Event{std::uint64_t when;unsigned slot,kind,reg,n;int timeout;};std::vector<Event> events;
 static unsigned slot(i2c_master_dev_handle_t d){check(d==&device[0]||d==&device[1],"known handle");return d==&device[1];}
 static void own(){check(std::this_thread::get_id()==owner,"SDK has one owner");}
 static esp_err_t elapsed(unsigned s,std::uint64_t duration,int timeout){
  const auto start=now.load();check(start>=origin&&start-origin<3000,"no transfer begins beyond shared origin budget");
  check(timeout>0&&timeout<=int((3000-(start-origin))/1000),"one origin and floored positive timeout");
  if(stuck){now.fetch_add(static_cast<std::uint64_t>(timeout)*1000);return ESP_ERR_TIMEOUT;}
  if(overrun)now.fetch_add(duration);else now.fetch_add(std::min(duration,std::uint64_t(timeout)*1000));
  if(transfer_error[s])return transfer_error[s];
  return !overrun&&duration>std::uint64_t(timeout)*1000?ESP_ERR_TIMEOUT:ESP_OK;
 }
 static std::uint8_t at(unsigned s,unsigned r){if(r!=9)return reg[s][r];if(s)return reg[s][10]&~reg[s][0];return std::uint8_t((0x2b|((!(reg[0][0]&128)&&(reg[0][10]&128))?192:0))^reg[0][1]);}
}
namespace ecu::engine_target{std::uint64_t clock_us(){return model::now.load();}}
esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t*c,i2c_master_bus_handle_t*out){model::own();++model::create_count;check(!model::bus_live,"no duplicate bus");check(c->sda_io_num==41&&c->scl_io_num==42&&!c->flags.enable_internal_pullup,"fixed bus/external pullups");model::now.fetch_add(model::create_time);if(model::create_error)return model::create_error;model::bus_live=true;*out=&model::bus;return ESP_OK;}
esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t b,const i2c_device_config_t*c,i2c_master_dev_handle_t*out){model::own();check(b==&model::bus&&model::bus_live&&c->device_address>=32&&c->device_address<=33,"device address owner");const auto s=c->device_address-32;check(!model::live[s],"no duplicate device");++model::added[s];if(model::add_error[s])return model::add_error[s];model::live[s]=true;*out=&model::device[s];return ESP_OK;}
esp_err_t i2c_master_bus_rm_device(i2c_master_dev_handle_t d){model::own();const auto s=model::slot(d);check(model::live[s],"remove live handle");++model::removed[s];model::now.fetch_add(model::remove_time);if(model::remove_error[s])return model::remove_error[s];model::live[s]=false;return ESP_OK;}
esp_err_t i2c_del_master_bus(i2c_master_bus_handle_t b){model::own();check(b==&model::bus&&model::bus_live&&!model::live[0]&&!model::live[1],"delete after last client");++model::delete_count;if(model::delete_error)return model::delete_error;model::bus_live=false;return ESP_OK;}
esp_err_t i2c_master_transmit_receive(i2c_master_dev_handle_t d,const std::uint8_t*tx,std::size_t tn,std::uint8_t*rx,std::size_t n,int timeout){model::own();const auto s=model::slot(d);check(model::live[s]&&tn==1&&*tx+n<=11,"bounded register read");++model::read_count[s];model::events.push_back({model::now.load(),s,0,*tx,unsigned(n),timeout});const auto err=model::elapsed(s,n==11?model::first_read[s]:model::guard_read[s],timeout);if(err)return err;if(model::underfill[s])return ESP_OK;if(n==1&&*tx==0&&model::reset_trailing[s]){model::reg[s].fill(0);model::reg[s][0]=255;model::reset_trailing[s]=false;}for(unsigned i=0;i<n;++i)rx[i]=model::at(s,*tx+((model::reg[s][5]&32)?0:i));return ESP_OK;}
esp_err_t i2c_master_transmit(i2c_master_dev_handle_t d,const std::uint8_t*p,std::size_t n,int timeout){model::own();const auto s=model::slot(d);check(model::live[s]&&n>=2&&n<=8&&*p+n<=12,"bounded register write");++model::write_count[s];model::events.push_back({model::now.load(),s,1,*p,unsigned(n-1),timeout});const auto err=model::elapsed(s,model::write_time[s],timeout);if(err)return err;for(unsigned i=1;i<n;++i)model::reg[s][*p+((model::reg[s][5]&32)?0:i-1)]=p[i];return ESP_OK;}
static si::Snapshot tick(unsigned mask=3,bool ack=true){model::origin=model::now.load();auto s=ecu::switch_service::tick(static_cast<std::uint8_t>(mask));if(ack&&s.fault_pending)ecu::switch_service::control_observed(s,true);const auto end=model::now.load();model::now.store(std::max(end,model::origin+5000));return s;}
static cJSON*status(){auto*j=ecu::board_status::snapshot();check(j,"complete status JSON");return j;}
static bool flag(const cJSON*j,const char*k){const auto*v=cJSON_GetObjectItemCaseSensitive(j,k);check(cJSON_IsBool(v),"boolean status");return cJSON_IsTrue(v);}
static const char*text(const cJSON*j,const char*k){const auto*v=cJSON_GetObjectItemCaseSensitive(j,k);check(cJSON_IsString(v),"string status");return v->valuestring;}
static double number(const cJSON*j,const char*k){const auto*v=cJSON_GetObjectItemCaseSensitive(j,k);check(cJSON_IsNumber(v),"numeric status");return v->valuedouble;}
static si::Snapshot ready(unsigned mask=3){si::Snapshot s;for(unsigned i=0;i<200;++i){s=tick(mask);auto*j=status();const bool good=flag(j,"ready");cJSON_Delete(j);if(good&&(!mask||s.ready))return s;}check(false,"readiness bounded model progress");return s;}
int main(int argc,char**argv){check(argc==2,"case argument");const char*mode=argv[1];ecu::switch_service::init();ecu::board_status::request(sl::Pattern::Normal);
 if(!std::strcmp(mode,"partial")){
  model::create_error=ESP_ERR_NO_MEM;tick(0);check(!model::bus_live&&!model::live[1],"failed create has no fake handle");model::create_error=0;model::add_error[1]=ESP_ERR_NO_MEM;for(unsigned n=0;n<25;++n)tick(0);check(model::bus_live&&!model::live[1]&&model::create_count==2,"partial bus retained once");model::add_error[1]=0;ready(0);check(model::create_count==2&&model::live[1],"LED allocation recovery reuses bus");ready(3);check(model::create_count==2&&model::live[0],"switch joins same retained bus");
 }else if(!std::strcmp(mode,"priority")){
  ready();std::size_t begin=model::events.size();for(unsigned n=0;n<100;++n)tick();
  for(std::size_t n=begin;n<model::events.size();++n){const auto&e=model::events[n];check(e.when%1==0,"integer transfer time");if(e.slot==1){for(std::size_t k=n+1;k<model::events.size()&&model::events[k].when-e.when<3000;++k)check(model::events[k].slot==1,"LED never precedes switch in same tick");}}
  auto*j=status();check(std::strtoull(text(j,"budget_skips"),nullptr,10)>0,"guarded LED reads skipped rather than second deadline");cJSON_Delete(j);
  model::overrun=true;model::first_read[0]=3300;begin=model::events.size();for(unsigned n=0;n<3;++n)tick();bool saw=false;for(std::size_t n=begin;n<model::events.size();++n){if(model::events[n].slot==0&&model::events[n].n==11){saw=true;check(n+1==model::events.size()||model::events[n+1].when>=model::events[n].when+5000,"switch overrun stops same-tick LED traffic");}}check(saw,"overrun injected");
 }else if(!std::strcmp(mode,"cleanup")){
  ready();model::remove_error[0]=ESP_FAIL;const auto old=model::removed[0];tick(0);check(model::live[0]&&model::live[1]&&model::bus_live&&model::removed[0]==old+1,"partial removal preserves both clients");for(unsigned n=0;n<18;++n)tick(0);check(model::removed[0]==old+1,"cleanup retry backoff");model::remove_error[0]=0;for(unsigned n=0;n<25;++n)tick(0);check(!model::live[0]&&model::live[1]&&model::bus_live&&!model::delete_count,"last LED client retains bus");
 }else if(!std::strcmp(mode,"local_failure")){
  auto s=ready();model::transfer_error[1]=ESP_ERR_TIMEOUT;bool failed=false;for(unsigned n=0;n<80&&!failed;++n){s=tick();auto*j=status();failed=number(j,"sdk_error")==ESP_ERR_TIMEOUT;cJSON_Delete(j);}check(failed&&s.ready&&!s.fault_pending,"LED failure adds no required-switch dependency");auto*j=status();check(flag(j,"known")&&!flag(j,"fresh")&&!flag(j,"ready")&&number(j,"last_verified_latch")==2,"failed LED retains only cached verified history");cJSON_Delete(j);
 }else if(!std::strcmp(mode,"reset")){
  ready(0);model::reset_trailing[1]=true;bool bad=false;for(unsigned n=0;n<80&&!bad;++n){tick(0);auto*j=status();bad=!std::strcmp(text(j,"fault"),"configuration_mismatch");cJSON_Delete(j);}check(bad,"reset between guarded reads rejects");ready(0);model::underfill[1]=true;for(unsigned n=0;n<30;++n)tick(0);auto*j=status();check(!flag(j,"ready")&&!flag(j,"fresh"),"success with underfilled reply cannot refresh history");cJSON_Delete(j);
 }else if(!std::strcmp(mode,"stale_u64")){
  model::now.store(9007199254740993ULL);ready(0);auto*j=status();const auto stamp=std::strtoull(text(j,"observed_us"),nullptr,10);check(stamp>9007199254740992ULL,"source time crosses JS precision bound exactly");const auto verifies=std::strtoull(text(j,"verifications"),nullptr,10);cJSON_Delete(j);model::now.fetch_add(250001);j=status();check(flag(j,"known")&&!flag(j,"fresh")&&!flag(j,"ready")&&std::strtoull(text(j,"observed_us"),nullptr,10)==stamp&&std::strtoull(text(j,"verifications"),nullptr,10)==verifies,"diagnostics do not refresh stale evidence");cJSON_Delete(j);model::now.store(UINT64_MAX);tick(0);j=status();check(!std::strcmp(text(j,"phase"),"reset_required")&&!flag(j,"fresh"),"U64 exhaustion fails closed without deadline wrap");cJSON_Delete(j);
 }else if(!std::strcmp(mode,"requests")){
  ready(0);const auto traffic=model::events.size();std::thread radio([](){for(unsigned n=0;n<10000;++n)ecu::board_status::request(n%2?sl::Pattern::Pairing:sl::Pattern::Problem);ecu::board_status::request(sl::Pattern::Off);});radio.join();check(model::events.size()==traffic,"radio requests never do SDK traffic");auto*j=status();check(!flag(j,"ready")&&!std::strcmp(text(j,"requested_pattern"),"off"),"unserviced coalesced policy not ready");cJSON_Delete(j);ready(0);check(model::reg[1][10]==0,"latest policy wins");
 }else if(!std::strcmp(mode,"byte_mode")){
  ecu::board_status::request(sl::Pattern::Off);ready(0);model::reg[1][5]|=32;model::now.fetch_add(100000);tick(0);auto*j=status();check(!flag(j,"ready")&&!flag(j,"fresh")&&!std::strcmp(text(j,"fault"),"configuration_mismatch"),"zero color cannot disguise byte-mode register corruption");cJSON_Delete(j);
 }else check(false,"known case");
 std::printf("{\"passed\":true,\"case\":\"%s\",\"checks\":%u,\"source\":\"independent SDK model around actual switch_service.cpp\",\"physical_test\":false}\n",mode,checks);
}
