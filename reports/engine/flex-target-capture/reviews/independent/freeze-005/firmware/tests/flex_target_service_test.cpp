// Include the actual service translation units so deterministic API-model
// scheduling can exercise their private ISR/worker paths without test hooks
// or exporting firmware internals. ESP-IDF/hardware execution is NOT modeled.
#include "../main/engine_target.cpp"
#include "../main/engine_service.cpp"
#include <fstream>
#include <iostream>
#include <string>
namespace ecu::switch_service {cJSON*snapshot(){return cJSON_CreateObject();}}
static unsigned checks=0;
static void verify(bool ok,const char*expression,unsigned line){++checks;if(!ok)std::cerr<<line<<": "<<expression<<"\n";assert(ok);}
#define check(v) verify((v),#v,__LINE__)
namespace target=ecu::engine_target;namespace service=ecu::engine_service;
static std::string output_directory;
static void fixture(const char*name){
 auto*j=service::snapshot();check(j);char*text=cJSON_Print(j);check(text);cJSON_Delete(j);
 if(!output_directory.empty()){std::ofstream f(output_directory+"/"+name+".json");check(f.good());f<<text<<'\n';}
 cJSON_free(text);
}
static void edge(std::uint64_t time,bool high,int polarity=0){
 fake_now=time;auto*h=target::flex_channel;check(h&&h->id==2&&h->timer->group==0);
 mcpwm_capture_event_data_t event{static_cast<std::uint32_t>((time-h->timer->epoch)*80),polarity?polarity:high?MCPWM_CAP_EDGE_POS:MCPWM_CAP_EDGE_NEG};
 check(h->callbacks.on_cap);h->callbacks.on_cap(h,&event,h->context);
}
static void wave(){const auto rise=fake_now+100;edge(rise,true);for(unsigned n=1;n<=2;++n){edge(rise+n*10000-3000,false);edge(rise+n*10000,true);}}
static ecu::config::Config sensor_config;
static ecu::web::Sample sensor_sample;
static ecu::engine::RuntimeSample observed;
static void observe(){check(service::observe(sensor_sample,sensor_config,fake_now,fake_now,observed));}
static void save_tune(bool enabled,bool confirmed,bool ethanol=false){
 auto*j=cJSON_Parse(service::tune_json().c_str());check(j);auto*f=cJSON_GetObjectItemCaseSensitive(j,"flex_fuel");
 cJSON_SetBoolValue(cJSON_GetObjectItemCaseSensitive(f,"input_confirmed"),confirmed);
 cJSON_SetBoolValue(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(f,"correction"),"enabled"),enabled);
 cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(f,"capture"),"cycles"),2);
 auto*rule=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(j,"secondary_tables"),"fuel");
 cJSON_SetValuestring(cJSON_GetObjectItemCaseSensitive(rule,"mode"),ethanol?"conditional":"off");
 cJSON_SetValuestring(cJSON_GetObjectItemCaseSensitive(rule,"condition"),ethanol?"ethanol_pct":"rpm");
 cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(rule,"threshold"),ethanol?40:3000);
 char*text=cJSON_PrintUnformatted(j);check(text);cJSON_Delete(j);std::string reason;check(service::save(text,reason)==200);cJSON_free(text);
}
struct Finished{};
static int allocation_budget=-1;static unsigned live_allocations=0;
static void*allocate(std::size_t size){if(allocation_budget==0)return nullptr;if(allocation_budget>0)--allocation_budget;auto*p=std::malloc(size);if(p)++live_allocations;return p;}
static void release(void*p){if(p){check(live_allocations>0);--live_allocations;std::free(p);}}
static void allocation_checks(){
 const auto before=target::flex_port.snapshot(fake_now);cJSON_Hooks hooks{allocate,release};cJSON_InitHooks(&hooks);bool completed=false;
 for(int n=0;n<512&&!completed;++n){allocation_budget=n;auto*j=target::flex_snapshot();completed=j!=nullptr;cJSON_Delete(j);check(live_allocations==0);}
 cJSON_InitHooks(nullptr);check(completed);
 const auto after=target::flex_port.snapshot(fake_now);check(before.acks==after.acks&&before.view.ticket.publication==after.view.ticket.publication);
}
static void scenario(){
 static unsigned tick=0;static ecu::flex::CaptureTicket original;static std::uint64_t suppression=0,previous_crank=0,rejections=0;
 const auto protected_bits=MCPWM_LL_EVENT_CAPTURE(0)|MCPWM_LL_EVENT_CAPTURE(1);
 check((fake_mcpwm[0].enable&protected_bits)==protected_bits);
 check(fake_capture_starts==2&&fake_capture_stops==0&&fake_capture_syncs==2&&fake_gpio_output_writes==0);
 if(fake_flex_error_stage){
  check(!target::flex_available);save_tune(true,true);observe();check(observed.flex_fuel.flags!=0&&service::latest.fuel_cut&&service::latest.spark_cut);
  check(!target::flex_work().version.armed&&!target::flex_view().sample.observation.valid);fixture("unavailable");throw Finished{};
 }
 switch(tick++){
 case 0:{
  check(fake_gpio_config.pin_bit_mask==(1ULL<<38)&&fake_gpio_config.mode==GPIO_MODE_INPUT);
  save_tune(true,true);observe();
  // Configuration consumes one invalid notification before the50ms retry.
  check(service::latest.fuel_cut&&service::latest.spark_cut);suppression=target::flex_work().ingress.last_suppression_us;
  check(!target::flex_work().ingress.pending_fault);fixture("acquiring");break;
 }
 case 1:{
  fake_now=suppression+50000;observe();check(target::flex_work().version.armed);
  previous_crank=target::executor.stats().last_capture_us;wave();observe();
  check(service::latest.flex_fuel.raw_qualified&&service::latest.flex_fuel.control_ok&&!service::latest.fuel_cut&&!service::latest.spark_cut);
  check(target::executor.stats().last_capture_us==previous_crank&&target::measured.crank_edges==0&&target::measured.cam_edges==0);
  original=target::flex_view().ticket;check(target::flex_port.can_issue(original,fake_now,false));fixture("qualified");break;
 }
 case 2:{
  check(target::flex_command_live&&target::flex_command_ticket.valid_until_us==original.valid_until_us);
  edge(fake_now+7000,false);edge(fake_now+3000,true);observe();
  // Discard this queued command in the test scheduler. A newer producer
  // publication must not alter the command already accepted by the worker.
  target::TaggedCommand dropped;check(xQueueReceive(target::commands,&dropped,0)==pdTRUE);
  check(target::flex_command_ticket.valid_until_us==original.valid_until_us);
  check(target::flex_view().ticket.valid_until_us>original.valid_until_us);
  check(fake_alarm<=original.valid_until_us+1);break;
 }
 case 3:{
  fake_now=original.valid_until_us+1;check(target::flex_view().current);
  fake_gpt_callbacks.on_alarm(&fake_timer,nullptr,nullptr);
  check(!target::flex_command_live&&target::executor.stats().high_mask==0);
  check(!target::flex_port.can_dispatch(original,fake_now,false));
  observe();fixture("deadline");break;
 }
 case 4:{
  // Fault while controller mutex is busy. Neither the missed update nor a
  // diagnostic read may acknowledge either fault notification.
  for(unsigned n=1;n<=65;++n)edge(fake_now+2000,n%2==0);
  auto w=target::flex_work();check(!w.version.armed&&w.ingress.pending_fault&&w.ingress.counters.discarded==64);
  suppression=w.ingress.last_suppression_us;
  check(!(fake_mcpwm[0].enable&MCPWM_LL_EVENT_CAPTURE(2)));
  const auto acks=target::flex_port.snapshot(fake_now).acks;
  xSemaphoreTake(service::mutex,portMAX_DELAY);check(!service::observe(sensor_sample,sensor_config,fake_now,fake_now,observed));xSemaphoreGive(service::mutex);
  for(unsigned n=0;n<10;++n){auto*j=target::flex_snapshot();check(j);cJSON_Delete(j);}
  check(target::flex_port.snapshot(fake_now).acks==acks&&target::flex_work().ingress.pending_fault);
  observe();check(service::latest.flex_fuel.sample.observation.pending_fault&&service::latest.fuel_cut&&service::latest.spark_cut);
  check(!target::flex_work().ingress.pending_fault&&target::flex_port.snapshot(fake_now).acks==acks+1);fixture("overflow");break;
 }
 case 5:{
  fake_now=suppression+49999;observe();check(!target::flex_work().version.armed);
  ++fake_now;observe();check(target::flex_work().version.armed&&!service::latest.flex_fuel.raw_qualified);
  wave();observe();check(service::latest.flex_fuel.raw_qualified);fixture("recovered");
  const auto old=target::flex_view();target::begin_configuration();
  observe();check(!target::flex_view().current&&service::latest.fuel_cut&&service::latest.spark_cut);
  ++sensor_config.revision;target::finish_configuration(service::active.revision,sensor_config.revision);
  check(!target::flex_port.can_issue(old.ticket,fake_now,false));
  observe();check(service::latest.flex_fuel.sample.observation.pending_fault&&!target::flex_work().ingress.pending_fault);
  check(!ecu::flex::same(old.ticket.version,target::flex_view().ticket.version));fixture("reconfigured");break;
 }
 case 6:{
  save_tune(false,true);observe();check(!target::flex_work().active&&!target::flex_work().version.armed);
  check(!service::latest.flex_fuel.required&&service::latest.flex_fuel.control_ok&&target::flex_work().ingress.pending_fault);fixture("disabled");
  save_tune(true,false);observe();check(!target::flex_work().version.armed&&service::latest.fuel_cut&&service::latest.spark_cut);fixture("unconfirmed");
  auto forged=target::flex_view().sample;forged.observation.source=ecu::flex::Source::Synthetic;
  check(!target::flex_publish(target::flex_work().version,forged));
  save_tune(false,true,true);observe();check(service::latest.flex_fuel.required&&!service::latest.flex_fuel.corrections.enabled);
  suppression=target::flex_work().ingress.last_suppression_us;break;
 }
 case 7:{
  fake_now=suppression+50000;observe();check(target::flex_work().version.armed);wave();observe();
  check(service::latest.flex_fuel.raw_qualified&&!service::latest.flex_fuel.corrections.enabled&&service::latest.secondary_fuel.active);
  fixture("ethanol-only");original=target::flex_view().ticket;
  // Publish a real FPU-domain pulse fault between acquisition and control.
  // The old, still-queued command must be rejected by the actual worker.
  edge(fake_now+4000,false);edge(fake_now+6000,true);
  xSemaphoreTake(service::mutex,portMAX_DELAY);target::FlexBackend backend;
  auto invalid=service::flex_owner.tick(backend,target::flex_work().request);xSemaphoreGive(service::mutex);
  check(invalid.sample.observation.pending_fault&&invalid.sample.observation.reason==ecu::flex::Reason::PulseWidth);
  check(ecu::flex::same(original.version,invalid.ticket.version)&&!target::flex_port.can_dispatch(original,fake_now,false));
  check(!target::commands->rows.empty());rejections=target::rejected_commands;fixture("capture-fault-unconsumed");break;
 }
 case 8:{
  check(target::rejected_commands==rejections+1&&!target::flex_command_live);
  observe();check(service::latest.flex_fuel.sample.observation.pending_fault&&service::latest.fuel_cut&&service::latest.spark_cut);
  for(unsigned n=0;n<2;++n){edge(fake_now+7000,false);edge(fake_now+3000,true);}observe();
  check(service::latest.flex_fuel.raw_qualified&&target::flex_view().ticket.capture_generation>original.capture_generation);
  check(fake_now<original.valid_until_us&&!target::flex_port.can_dispatch(original,fake_now,false));fixture("capture-fault-recovered");
  for(const auto&m:fake_masks)check(m[0]==0&&m[1]==MCPWM_LL_EVENT_CAPTURE(2));
  for(const auto&c:fake_clears)check(c[0]==0&&c[1]==4);
  allocation_checks();
  throw Finished{};
 }
 default:assert(false);
 }
}
int main(int argc,char**argv){
 if(argc>1)output_directory=argv[1];
 if(argc>2)fake_flex_error_stage=std::stoi(argv[2]);
 target::captures=xQueueCreate(64,sizeof(target::Capture));target::commands=xQueueCreate(1,sizeof(target::TaggedCommand));
 target::started=xSemaphoreCreateBinary();target::configuration_mutex=xSemaphoreCreateMutex();target::trigger_mutex=xSemaphoreCreateMutex();
 service::init();check(service::storage_ok);
 const char*units[]={"kPa","%","C","C","lambda","kPa"};const double values[]={50,10,85,25,1,100};
 for(unsigned n=0;n<6;++n){auto&s=sensor_config.sensors[n];s.mode=ecu::config::Mode::Linear;s.confirmed=true;std::strcpy(s.unit,units[n]);s.y0=s.y1=values[n];sensor_sample.raw[n]=2000;}
 sensor_sample.raw[6]=1336;sensor_sample.raw[7]=3723;sensor_sample.adc_ok=sensor_sample.synced=sensor_sample.phase_synced=true;sensor_sample.rpm=2000;
 fake_tick=scenario;try{target::run(nullptr);}catch(const Finished&){}
 check(fake_gpio_output_writes==0);std::cout<<"flex_target_service_checks "<<checks<<" mode "<<fake_flex_error_stage<<"\n";
}
