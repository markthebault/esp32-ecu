#include "ecu/engine_target.hpp"
#include "ecu/capture_clock.hpp"
#include "ecu/trigger_log_json.hpp"
#include "ecu/engine_phase.hpp"
#include "ecu/pins.hpp"
#include "ecu/idle_command.hpp"
#include "ecu/boost_command.hpp"
#include "ecu/boost_pwm_json.hpp"
#include "ecu/idle_pwm_json.hpp"
#include "ecu/idle_hardware.hpp"
#include "ecu/flex_hardware.hpp"
#include "ecu/flex_capture_json.hpp"
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "driver/mcpwm_cap.h"
#include "driver/mcpwm_sync.h"
#include "hal/gpio_ll.h"
#include "hal/mcpwm_ll.h"
#include "soc/gpio_struct.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_attr.h"
#include "esp_log.h"
#include <cmath>

#ifndef ECU_ENGINE_DUMMY_LOADS
#define ECU_ENGINE_DUMMY_LOADS 0
#endif
#if ECU_ENGINE_DUMMY_LOADS && defined(ECU_BENCH_PULSES) && ECU_BENCH_PULSES
#error Engine timing and legacy single-pulse bench cannot own outputs together
#endif
namespace ecu::engine_target {
namespace {
DRAM_ATTR timing::Executor executor{ECU_ENGINE_DUMMY_LOADS?4U:8U};
DRAM_ATTR idle::PwmExecutor idle_executor;
DRAM_ATTR boost::PwmExecutor boost_executor;
// Virtual execution only. The unrouted GPIO45 driver candidate is not allocated.
struct BoostIO {ECU_ISR_CODE void all_low(){} ECU_ISR_CODE bool write(bool){return true;}};
DRAM_ATTR BoostIO boost_output;
ECU_ISR_CODE void idle_engine_stop();
ECU_ISR_CODE void boost_engine_stop();
struct IdleIO {bool physical_high=false;ECU_ISR_CODE void all_low();ECU_ISR_CODE bool write(bool high);};
DRAM_ATTR IdleIO idle_output;
DRAM_ATTR timing::CaptureClock capture_clock;
#if ECU_FLEX_G38_DRAFT
DRAM_ATTR flex::CapturePort flex_port;
DRAM_ATTR flex::CaptureTicket flex_command_ticket;
DRAM_ATTR bool flex_command_live=false,flex_channel_owned=false;
mcpwm_cap_channel_handle_t flex_channel=nullptr;
bool flex_available=false;
esp_err_t flex_error=ESP_OK;
#endif
DRAM_ATTR trigger_log::Capture trigger_capture;
DRAM_ATTR timing::CaptureClock trigger_clock;
DRAM_ATTR portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
#if ECU_ENGINE_DUMMY_LOADS
DRAM_ATTR const unsigned output_pins[8]={pins::inj1_cmd,pins::inj2_cmd,pins::inj3_cmd,pins::inj4_cmd,
 pins::ign1_cmd,pins::ign2_cmd,pins::ign3_cmd,pins::ign4_cmd};
#endif
struct OutputIO {
 bool boot_allowed=false,armed=false,failed=false;
 std::uint32_t physical_mask=0;
 ECU_ISR_CODE void all_low(){
#if ECU_ENGINE_DUMMY_LOADS
  gpio_ll_set_level(&GPIO,pins::arm,0);
  for(auto pin:output_pins)gpio_ll_set_level(&GPIO,pin,0);
  gpio_ll_set_level(&GPIO,pins::pump_cmd,0);gpio_ll_set_level(&GPIO,pins::fan_cmd,0);
#endif
  physical_mask=0;
  idle_engine_stop();
  boost_engine_stop();
 }
 ECU_ISR_CODE bool write(unsigned ch,bool high){
  const auto kind=engine::channels::kind(ch);if(kind!=engine::channels::Kind::Injector&&kind!=engine::channels::Kind::Coil)return false;
#if ECU_ENGINE_DUMMY_LOADS
  if(ch>=8)return false;
  if(high&&(!armed||failed||!gpio_ll_get_level(&GPIO,pins::safe_n_mon)||!gpio_ll_get_level(&GPIO,pins::interlock)))return false;
  if(high){gpio_ll_set_level(&GPIO,pins::arm,1);gpio_ll_set_level(&GPIO,output_pins[ch],1);physical_mask|=1U<<ch;}
  else{gpio_ll_set_level(&GPIO,output_pins[ch],0);physical_mask&=~(1U<<ch);}
#else
  (void)ch;(void)high;
#endif
  return true;
 }
 void supervise(bool healthy){
#if ECU_ENGINE_DUMMY_LOADS
  const bool power= gpio_ll_get_level(&GPIO,pins::safe_n_mon)&&gpio_ll_get_level(&GPIO,pins::interlock);
  if(!boot_allowed||(armed&&(!healthy||!power))){failed=true;armed=false;all_low();}
  else if(!failed&&healthy&&power)armed=true;
#else
  (void)healthy;
#endif
 }
};
DRAM_ATTR OutputIO output;
gptimer_handle_t timer;
mcpwm_cap_timer_handle_t cap_timer;
QueueHandle_t captures,commands;
SemaphoreHandle_t started,configuration_mutex;
SemaphoreHandle_t trigger_mutex;
std::array<mcpwm_cap_channel_handle_t,2> trigger_channels{};
bool trigger_available=false;
std::array<bool,2> trigger_channel_enabled{};
esp_err_t trigger_error=ESP_OK;
TaskHandle_t timing_task;
Wheel initial_wheel;
DRAM_ATTR std::uint32_t external_epoch=1;
DRAM_ATTR std::uint64_t installed_alarm=timing::Executor::none;
DRAM_ATTR Measurement measured;
DRAM_ATTR bool cam_context=true;
bool configuration_hold=false;
std::uint32_t required_tune_revision=0,required_sensor_revision=0;
std::uint64_t superseded_captures=0,rejected_commands=0,configuration_captures=0;
struct Capture {std::uint64_t time_us;std::uint32_t epoch;bool cam;};
struct TaggedCommand {timing::Command command;std::uint32_t epoch;
#if ECU_FLEX_G38_DRAFT
 flex::CaptureTicket flex_ticket;
#endif
};

ECU_ISR_CODE std::uint64_t now_locked(){
 std::uint64_t now=0;if(timer)gptimer_get_raw_count(timer,&now);return now;
}
ECU_ISR_CODE void IdleIO::all_low(){
#if ECU_IDLE_DUMMY_LOADS
 gpio_ll_set_level(&GPIO,idle::gpio,0);
#endif
 physical_high=false;
}
ECU_ISR_CODE bool IdleIO::write(bool high){
#if ECU_IDLE_DUMMY_LOADS
 if(high&&(!output.armed||output.failed||!gpio_ll_get_level(&GPIO,pins::safe_n_mon)||!gpio_ll_get_level(&GPIO,pins::interlock)))return false;
 if(high)gpio_ll_set_level(&GPIO,pins::arm,1);
 gpio_ll_set_level(&GPIO,idle::gpio,high);physical_high=high;
#else
 (void)high;
#endif
 return true;
}
ECU_ISR_CODE void idle_engine_stop(){
 if(idle_executor.stats().active||idle_executor.stats().high)idle_executor.stop(now_locked(),idle::PwmCause::EngineFault,idle_output);
 else idle_output.all_low(); // Repeated already-low Stopped commands preserve supervised-zero continuity.
}
ECU_ISR_CODE void boost_engine_stop(){
 if(boost_executor.stats().active||boost_executor.stats().high)boost_executor.stop(now_locked(),boost::PwmCause::EngineFault,boost_output);
 else boost_output.all_low();
}
ECU_ISR_CODE void boost_fault(){
 if(boost_executor.stats().fault!=boost::PwmCause::None&&executor.stats().fault==timing::Cause::None)
  executor.trip(now_locked(),timing::Cause::BoostPwm,output);
}
ECU_ISR_CODE void idle_fault(){
 if(idle_executor.stats().fault!=idle::PwmCause::None&&executor.stats().fault==timing::Cause::None)
  executor.trip(now_locked(),timing::Cause::IdlePwm,output);
}
#if ECU_FLEX_G38_DRAFT
ECU_ISR_CODE void flex_irq_off(){
 if(flex_channel_owned){
  mcpwm_ll_intr_enable(MCPWM_LL_GET_HW(0),MCPWM_LL_EVENT_CAPTURE(2),false);
  mcpwm_ll_intr_clear_capture_status(MCPWM_LL_GET_HW(0),1U<<2);
 }
}
ECU_ISR_CODE bool flex_command_allowed(std::uint64_t now){
 const auto&c=executor.current_command();
 return flex_port.can_dispatch(flex_command_ticket,now,c.output.fuel_cut&&c.output.spark_cut);
}
ECU_ISR_CODE void flex_progress(std::uint64_t now){
 if(flex_command_live&&!flex_command_allowed(now)){
  executor.stop(now,timing::Cause::Control,output);flex_command_live=false;
 }
}
void flex_fence(std::uint64_t now){flex_irq_off();flex_port.fence(now);flex_command_live=false;}
#endif
ECU_ISR_CODE void alarm_locked(){
 auto deadline=std::min(std::min(executor.next_alarm(),idle_executor.next_alarm()),boost_executor.next_alarm());
#if ECU_FLEX_G38_DRAFT
 if(flex_command_live)deadline=std::min(deadline,flex_command_ticket.valid_until_us+1);
#endif
 if(deadline==timing::Executor::none){
  if(installed_alarm!=deadline)gptimer_set_alarm_action(timer,nullptr);
  installed_alarm=deadline;return;
 }
 if(deadline==installed_alarm)return;
 const auto now=now_locked();if(deadline<now+5)deadline=now+5;
 gptimer_alarm_config_t alarm{};alarm.alarm_count=deadline;
 if(gptimer_set_alarm_action(timer,&alarm)!=ESP_OK){
  executor.trip(now,timing::Cause::Timebase,output);gptimer_set_alarm_action(timer,nullptr);
  installed_alarm=timing::Executor::none;return;
 }
 installed_alarm=deadline;
}
bool IRAM_ATTR on_alarm(gptimer_handle_t,const gptimer_alarm_event_data_t*,void*){
 portENTER_CRITICAL_ISR(&lock);
 installed_alarm=timing::Executor::none;
#if ECU_ENGINE_DUMMY_LOADS
 if(output.armed&&(!gpio_ll_get_level(&GPIO,pins::safe_n_mon)||!gpio_ll_get_level(&GPIO,pins::interlock))){
  output.failed=true;output.armed=false;executor.trip(now_locked(),timing::Cause::Gate,output);
 }
#endif
 const auto now=now_locked();
#if ECU_FLEX_G38_DRAFT
 flex_progress(now);
#endif
 executor.dispatch(now,output);idle_executor.dispatch(now,idle_output);boost_executor.dispatch(now,boost_output);idle_fault();boost_fault();alarm_locked();
 portEXIT_CRITICAL_ISR(&lock);return false;
}
bool IRAM_ATTR on_capture(mcpwm_cap_channel_handle_t,const mcpwm_capture_event_data_t* event,void* context){
 BaseType_t wake=pdFALSE;
 portENTER_CRITICAL_ISR(&lock);
 const auto now=now_locked();executor.raw_capture(now);const auto stamp=capture_clock.map(event->cap_value,now);
 if(stamp.error!=timing::CaptureClock::Error::None){
  executor.trip(now,timing::Cause::Timebase,output);alarm_locked();portEXIT_CRITICAL_ISR(&lock);return false;
 }
 Capture item{stamp.time_us,external_epoch,context!=nullptr};
 if(!item.cam)++measured.crank_edges;else ++measured.cam_edges;
 executor.raw_capture(item.time_us);
 if(configuration_hold){++configuration_captures;portEXIT_CRITICAL_ISR(&lock);return false;}
 if(xQueueSendFromISR(captures,&item,&wake)!=pdTRUE){
  measured.overflow=true;executor.trip(now,timing::Cause::CaptureOverflow,output);alarm_locked();
 }
 portEXIT_CRITICAL_ISR(&lock);return wake==pdTRUE;
}
bool IRAM_ATTR on_trigger_capture(mcpwm_cap_channel_handle_t,const mcpwm_capture_event_data_t* event,void* context){
 portENTER_CRITICAL_ISR(&lock);
 const auto now=now_locked();const auto stamp=trigger_clock.map(event->cap_value,now);
 trigger_capture.append({stamp.time_us,now,event->cap_value,external_epoch,context!=nullptr,
  event->cap_edge==MCPWM_CAP_EDGE_POS,stamp.error==timing::CaptureClock::Error::None});
 portEXIT_CRITICAL_ISR(&lock);return false;
}
#if ECU_FLEX_G38_DRAFT
bool IRAM_ATTR on_flex_capture(mcpwm_cap_channel_handle_t,const mcpwm_capture_event_data_t* event,void*){
 portENTER_CRITICAL_ISR(&lock);
 const auto now=now_locked();const auto stamp=capture_clock.map_interval(event->cap_value,now);
 const bool polarity=event->cap_edge==MCPWM_CAP_EDGE_POS||event->cap_edge==MCPWM_CAP_EDGE_NEG;
 const auto result=flex_port.push(stamp.time_us,now,event->cap_edge==MCPWM_CAP_EDGE_POS,
  polarity&&stamp.error==timing::CaptureClock::Error::None,event->cap_value);
 if(result==flex::Ingress::Result::Suppress){
  flex_irq_off();
  if(flex_port.required()){executor.stop(now,timing::Cause::Control,output);flex_command_live=false;alarm_locked();}
 }
 // Flex edges never refresh crank/cam producer/tooth deadlines.
 portEXIT_CRITICAL_ISR(&lock);return false;
}
void init_flex_capture(bool synced){
 // Pinned IDF allocates first-free: the two preceding group0 allocations own
 // slots0/1. This private group has exactly three channels; reserve slot2.
 static_assert(SOC_MCPWM_CAPTURE_CHANNELS_PER_TIMER==3,"Re-audit capture allocation");
 if(!synced){flex_error=ESP_ERR_INVALID_STATE;return;}
 mcpwm_capture_channel_config_t cfg{};cfg.gpio_num=flex::gpio;cfg.intr_priority=3;
 cfg.prescale=1;cfg.flags.pos_edge=cfg.flags.neg_edge=true;
 flex_error=mcpwm_new_capture_channel(cap_timer,&cfg,&flex_channel);
 if(flex_error!=ESP_OK)return;
 flex_channel_owned=true;mcpwm_capture_event_callbacks_t cb{};cb.on_cap=on_flex_capture;
 flex_error=mcpwm_capture_channel_register_event_callbacks(flex_channel,&cb,nullptr);
 if(flex_error==ESP_OK)flex_error=mcpwm_capture_channel_enable(flex_channel);
 portENTER_CRITICAL(&lock);flex_irq_off();portEXIT_CRITICAL(&lock);
 if(flex_error!=ESP_OK){
  // Never stop/resync the common timer or clear crank/cam status. A failed
  // optional allocation stays unavailable, with its SDK error observable.
  if(mcpwm_del_capture_channel(flex_channel)==ESP_OK){flex_channel=nullptr;flex_channel_owned=false;}
  return;
 }
 flex_available=true;
}
#endif
bool disable_trigger_channels(){
 bool ok=true;
 for(unsigned i=0;i<trigger_channels.size();++i)if(trigger_channel_enabled[i]){
  const auto result=mcpwm_capture_channel_disable(trigger_channels[i]);
  if(result==ESP_OK)trigger_channel_enabled[i]=false;
  else{if(trigger_error==ESP_OK)trigger_error=result;ok=false;}
 }
 return ok;
}
void service_trigger_logger(){
 if(xSemaphoreTake(trigger_mutex,0)!=pdTRUE)return;
 portENTER_CRITICAL(&lock);const auto state=trigger_capture.header().state;portEXIT_CRITICAL(&lock);
 if(state!=trigger_log::State::Armed)disable_trigger_channels();
 xSemaphoreGive(trigger_mutex);
}
void init_trigger_logger(){
#if !ECU_ENGINE_DUMMY_LOADS && !(defined(ECU_BENCH_PULSES) && ECU_BENCH_PULSES)
 // Dedicated latches: both-edge diagnostics must not replace group0 decoder
 // captures. Driver allocation/registration stays on the core1 timing task.
 mcpwm_cap_timer_handle_t diagnostic_timer=nullptr;mcpwm_sync_handle_t sync=nullptr;
 bool enabled=false,running=false;
 auto setup=[&]()->esp_err_t{
  mcpwm_capture_timer_config_t cfg{};cfg.group_id=1;cfg.clk_src=MCPWM_CAPTURE_CLK_SRC_APB;
  auto result=mcpwm_new_capture_timer(&cfg,&diagnostic_timer);if(result!=ESP_OK)return result;
  std::uint32_t hz=0;result=mcpwm_capture_timer_get_resolution(diagnostic_timer,&hz);if(result!=ESP_OK)return result;
  result=mcpwm_capture_timer_enable(diagnostic_timer);if(result!=ESP_OK)return result;enabled=true;
  result=mcpwm_capture_timer_start(diagnostic_timer);if(result!=ESP_OK)return result;running=true;
  mcpwm_soft_sync_config_t software{};
  result=mcpwm_new_soft_sync_src(&software,&sync);if(result!=ESP_OK)return result;
  mcpwm_capture_timer_sync_phase_config_t phase{};phase.sync_src=sync;phase.direction=MCPWM_TIMER_DIRECTION_UP;
  result=mcpwm_capture_timer_set_phase_on_sync(diagnostic_timer,&phase);if(result!=ESP_OK)return result;
  std::uint64_t before=0,after=0;
  portENTER_CRITICAL(&lock);gptimer_get_raw_count(timer,&before);result=mcpwm_soft_sync_activate(sync);gptimer_get_raw_count(timer,&after);
  const bool synced=result==ESP_OK&&trigger_clock.sync(hz,before,after);portEXIT_CRITICAL(&lock);
  if(!synced)return result==ESP_OK?ESP_ERR_INVALID_STATE:result;
  for(unsigned i=0;i<2;++i){
   mcpwm_capture_channel_config_t channel{};channel.gpio_num=i?pins::cam:pins::crank;channel.intr_priority=1;
   channel.prescale=1;channel.flags.pos_edge=true;channel.flags.neg_edge=true;
   result=mcpwm_new_capture_channel(diagnostic_timer,&channel,&trigger_channels[i]);if(result!=ESP_OK)return result;
   mcpwm_capture_event_callbacks_t cb{};cb.on_cap=on_trigger_capture;
   result=mcpwm_capture_channel_register_event_callbacks(trigger_channels[i],&cb,i?&cam_context:nullptr);if(result!=ESP_OK)return result;
  }
  return ESP_OK;
 };
 trigger_error=setup();trigger_available=trigger_error==ESP_OK;
 if(!trigger_available){
  for(auto& channel:trigger_channels)if(channel){mcpwm_del_capture_channel(channel);channel=nullptr;}
  if(diagnostic_timer){
   if(running)mcpwm_capture_timer_stop(diagnostic_timer);
   if(enabled)mcpwm_capture_timer_disable(diagnostic_timer);
   mcpwm_del_capture_timer(diagnostic_timer);
  }
  if(sync)mcpwm_del_sync_src(sync);
  ESP_LOGW("ecu_timing","Trigger diagnostics unavailable: %s; decoder channels retained",esp_err_to_name(trigger_error));
 }
#endif
}
void init_peripherals(){
#if ECU_FLEX_G38_DRAFT
 // Explicitly remove former output ownership. Capture setup only enables an
 // input route; it must never leave an earlier GPIO/RMT output driver active.
 gpio_config_t flex_pin{};flex_pin.pin_bit_mask=1ULL<<flex::gpio;
 flex_pin.mode=GPIO_MODE_INPUT;flex_pin.pull_up_en=GPIO_PULLUP_DISABLE;flex_pin.pull_down_en=GPIO_PULLDOWN_DISABLE;
 flex_pin.intr_type=GPIO_INTR_DISABLE;ESP_ERROR_CHECK(gpio_config(&flex_pin));
#endif
#if ECU_IDLE_DUMMY_LOADS
 ESP_ERROR_CHECK(gpio_set_level(static_cast<gpio_num_t>(idle::gpio),0));
 ESP_ERROR_CHECK(gpio_set_direction(static_cast<gpio_num_t>(idle::gpio),GPIO_MODE_OUTPUT));
#endif
 gptimer_config_t cfg{};cfg.clk_src=GPTIMER_CLK_SRC_APB;cfg.direction=GPTIMER_COUNT_UP;
 cfg.resolution_hz=1000000;cfg.intr_priority=3;
 ESP_ERROR_CHECK(gptimer_new_timer(&cfg,&timer));
 gptimer_event_callbacks_t callbacks{};callbacks.on_alarm=on_alarm;
 ESP_ERROR_CHECK(gptimer_register_event_callbacks(timer,&callbacks,nullptr));
 ESP_ERROR_CHECK(gptimer_enable(timer));ESP_ERROR_CHECK(gptimer_start(timer));
 mcpwm_capture_timer_config_t capture{};capture.group_id=0;capture.clk_src=MCPWM_CAPTURE_CLK_SRC_APB;
 ESP_ERROR_CHECK(mcpwm_new_capture_timer(&capture,&cap_timer));
 std::uint32_t hz=0;ESP_ERROR_CHECK(mcpwm_capture_timer_get_resolution(cap_timer,&hz));
 ESP_ERROR_CHECK(mcpwm_capture_timer_enable(cap_timer));ESP_ERROR_CHECK(mcpwm_capture_timer_start(cap_timer));
 mcpwm_soft_sync_config_t software{};mcpwm_sync_handle_t sync;
 ESP_ERROR_CHECK(mcpwm_new_soft_sync_src(&software,&sync));
 mcpwm_capture_timer_sync_phase_config_t phase{};phase.sync_src=sync;phase.direction=MCPWM_TIMER_DIRECTION_UP;
 ESP_ERROR_CHECK(mcpwm_capture_timer_set_phase_on_sync(cap_timer,&phase));
 std::uint64_t before=0,after=0;esp_err_t sync_result;
 // Boot only: MCPWM control need not run while cache is disabled.
 portENTER_CRITICAL(&lock);gptimer_get_raw_count(timer,&before);
 sync_result=mcpwm_soft_sync_activate(sync);gptimer_get_raw_count(timer,&after);
 const bool synced=sync_result==ESP_OK&&capture_clock.sync(hz,before,after);
 if(!synced)executor.trip(after,timing::Cause::Timebase,output);
 portEXIT_CRITICAL(&lock);
 for(unsigned i=0;i<2;++i){
  mcpwm_capture_channel_config_t channel{};channel.gpio_num=i?pins::cam:pins::crank;
  channel.intr_priority=3;channel.prescale=1;channel.flags.pos_edge=true;
  mcpwm_cap_channel_handle_t handle;ESP_ERROR_CHECK(mcpwm_new_capture_channel(cap_timer,&channel,&handle));
  mcpwm_capture_event_callbacks_t cb{};cb.on_cap=on_capture;
  ESP_ERROR_CHECK(mcpwm_capture_channel_register_event_callbacks(handle,&cb,i?&cam_context:nullptr));
  ESP_ERROR_CHECK(mcpwm_capture_channel_enable(handle));
 }
#if ECU_FLEX_G38_DRAFT
 init_flex_capture(synced);
#endif
 init_trigger_logger();
 portENTER_CRITICAL(&lock);measured.ready=synced;portEXIT_CRITICAL(&lock);
 ESP_LOGI("ecu_timing","APB capture=%luHz; epoch bracket=%llu..%llu us; physical policy=%s",
  static_cast<unsigned long>(hz),static_cast<unsigned long long>(before),static_cast<unsigned long long>(after),
  ECU_ENGINE_DUMMY_LOADS?"DUMMY LOADS ONLY":"COMPILE-TIME INHIBITED");
}
void run(void*){
 init_peripherals();engine::PhaseDecoder decoder({initial_wheel.slots,initial_wheel.missing,initial_wheel.max_rpm});
 xSemaphoreGive(started);
 timing::Command latest;std::uint32_t accepted_epoch=0,observed_epoch=0;bool have_command=false;
 auto refresh_epoch=[&](){
  portENTER_CRITICAL(&lock);const auto epoch=external_epoch;
  const bool changed=epoch!=observed_epoch;
  if(changed){observed_epoch=epoch;have_command=false;measured.rpm=0;measured.synced=false;measured.phase_synced=false;}
  portEXIT_CRITICAL(&lock);if(changed)decoder.reset();
 };
 auto service_command=[&](){
  TaggedCommand tagged;
  if(xQueueReceive(commands,&tagged,0)!=pdTRUE)return;
  portENTER_CRITICAL(&lock);
  if(configuration_hold||tagged.epoch!=external_epoch||tagged.command.tune_revision<required_tune_revision||
     tagged.command.sensor_revision<required_sensor_revision){++rejected_commands;portEXIT_CRITICAL(&lock);return;}
#if ECU_FLEX_G38_DRAFT
  const bool both_cut=tagged.command.output.fuel_cut&&tagged.command.output.spark_cut;
  if(!flex_port.can_dispatch(tagged.flex_ticket,now_locked(),both_cut)){
   ++rejected_commands;executor.stop(now_locked(),timing::Cause::Control,output);flex_command_live=false;alarm_locked();portEXIT_CRITICAL(&lock);return;
  }
#endif
  const auto now=now_locked();
#if ECU_FLEX_G38_DRAFT
  flex_progress(now);
#endif
  executor.progress(now,output);
  const auto& c=tagged.command;
  if(!have_command||accepted_epoch!=tagged.epoch||c.slots!=latest.slots||c.missing!=latest.missing||c.max_rpm!=latest.max_rpm||c.tune_revision!=latest.tune_revision)
   decoder=engine::PhaseDecoder({c.slots,c.missing,c.max_rpm},c.angle);
  latest=c;have_command=true;accepted_epoch=tagged.epoch;observed_epoch=tagged.epoch;
#if ECU_FLEX_G38_DRAFT
  flex_command_ticket=tagged.flex_ticket;flex_command_live=tagged.flex_ticket.required&&!both_cut;
#endif
  executor.command(latest,now,output);
  const bool healthy=decoder.synced()&&now>=latest.sampled_us&&now-latest.sampled_us<20000&&
   !(latest.output.faults&~std::uint32_t(engine::OverRev))&&executor.stats().fault==timing::Cause::None;
  output.supervise(healthy);
  idle_executor.submit(idle::pwm_command(latest,executor.current_command(),now,executor.stats(),configuration_hold),now,idle_output);
  boost_executor.submit(boost::pwm_command(latest,executor.current_command(),now,executor.stats(),configuration_hold,decoder.synced()),now,boost_output);idle_fault();boost_fault();
  alarm_locked();portEXIT_CRITICAL(&lock);
 };
 for(;;){
  refresh_epoch();service_command();Capture edge{};bool received=xQueueReceive(captures,&edge,pdMS_TO_TICKS(1))==pdTRUE;
  if(received){
   for(unsigned drained=0;received&&drained<64;++drained){
    refresh_epoch();service_command();
    portENTER_CRITICAL(&lock);const bool current_capture=edge.epoch==external_epoch&&!configuration_hold;
    if(!current_capture)++configuration_captures;
    portEXIT_CRITICAL(&lock);
    if(current_capture&&(!edge.cam||decoder.required())){
     const auto now=clock_us();
     if(now<edge.time_us||now-edge.time_us>1000){
      if(edge.cam&&decoder.phase_synced())decoder.invalidate(engine::PhaseDecoder::Reason::Unmapped);
      portENTER_CRITICAL(&lock);
      if(edge.epoch==external_epoch&&!configuration_hold)executor.trip(now_locked(),timing::Cause::CaptureAge,output);
      alarm_locked();portEXIT_CRITICAL(&lock);
     }else{
      const bool was_synced=decoder.synced();
      if(edge.cam)decoder.cam(edge.time_us,now);else decoder.edge(edge.time_us,now);
      if(decoder.required()){
       portENTER_CRITICAL(&lock);
       if(have_command&&accepted_epoch==external_epoch&&edge.epoch==external_epoch&&!configuration_hold)
        executor.phase(decoder.phase_synced(),decoder.deadline(),now_locked(),output);
       const bool phase_fault=executor.stats().fault==timing::Cause::CamPhase;alarm_locked();portEXIT_CRITICAL(&lock);
       if(phase_fault&&!decoder.faulted())decoder.invalidate(engine::PhaseDecoder::Reason::Timeout);
      }
      if(was_synced&&!decoder.synced()){
       portENTER_CRITICAL(&lock);
       if(edge.epoch==external_epoch&&!configuration_hold)executor.stop(now_locked(),timing::Cause::Control,output);
       alarm_locked();portEXIT_CRITICAL(&lock);
      }
      if(!edge.cam&&decoder.synced()&&have_command&&(edge.time_us<latest.command_us||edge.time_us<latest.sampled_us)){
       portENTER_CRITICAL(&lock);++superseded_captures;portEXIT_CRITICAL(&lock);
      }
      else if(!edge.cam&&decoder.synced()&&have_command){
       bool committed=false,cancelled=false;
       const auto stall_timeout=decoder.stall_timeout();
       for(unsigned attempt=0;attempt<4;++attempt){
        timing::Executor::Candidate candidate;
        portENTER_CRITICAL(&lock);
#if ECU_FLEX_G38_DRAFT
        flex_progress(now_locked());
#endif
        executor.progress(now_locked(),output);
        const bool valid_epoch=accepted_epoch==external_epoch
#if ECU_FLEX_G38_DRAFT
         &&flex_command_allowed(now_locked())
#endif
         ;
        executor.prepare(candidate,edge.time_us,stall_timeout);portEXIT_CRITICAL(&lock);
        if(!valid_epoch){cancelled=true;break;}
        candidate.calculate(decoder.required()?decoder.phase_tooth():decoder.tooth(),decoder.rpm());
        portENTER_CRITICAL(&lock);
#if ECU_FLEX_G38_DRAFT
        flex_progress(now_locked());
#endif
        const auto result=executor.commit(candidate,now_locked(),output);alarm_locked();portEXIT_CRITICAL(&lock);
        if(result!=timing::Executor::Commit::Retry){committed=true;break;}
       }
       if(!committed&&!cancelled){portENTER_CRITICAL(&lock);executor.trip(now_locked(),timing::Cause::Contention,output);alarm_locked();portEXIT_CRITICAL(&lock);}
      }
     }
    }
    received=drained+1<64&&xQueueReceive(captures,&edge,0)==pdTRUE;
   }
  }
  const auto now=clock_us();decoder.tick(now);
  const auto rpm=decoder.rpm();const bool synced=decoder.synced();
  portENTER_CRITICAL(&lock);const auto checked_now=now_locked();
#if ECU_FLEX_G38_DRAFT
  flex_progress(checked_now);
#endif
  executor.progress(checked_now,output);idle_executor.dispatch(checked_now,idle_output);boost_executor.dispatch(checked_now,boost_output);idle_fault();boost_fault();trigger_capture.expire(checked_now);
  measured.rpm=accepted_epoch==external_epoch&&!configuration_hold?rpm:0;
  measured.synced=accepted_epoch==external_epoch&&!configuration_hold&&decoder.crank_synced();
  measured.phase_synced=accepted_epoch==external_epoch&&!configuration_hold&&decoder.phase_synced();
  measured.tune_revision=have_command?latest.tune_revision:0;measured.sensor_revision=have_command?latest.sensor_revision:0;
  measured.phase_epoch=accepted_epoch==external_epoch&&!configuration_hold?external_epoch:0;
  measured.phase_required=decoder.required();measured.phase_losses=decoder.losses();measured.cam_rejected=decoder.rejected();
  measured.cam_error_deg=decoder.cam_error_deg();measured.phase_reason=decoder.reason();
  if(decoder.required()&&have_command&&accepted_epoch==external_epoch&&!configuration_hold)
   executor.phase(decoder.phase_synced(),decoder.deadline(),checked_now,output);
  const bool healthy=have_command&&accepted_epoch==external_epoch&&synced&&checked_now>=latest.sampled_us&&
   checked_now-latest.sampled_us<20000&&!(latest.output.faults&~std::uint32_t(engine::OverRev))&&executor.stats().fault==timing::Cause::None;
  output.supervise(healthy);
  if(output.failed&&ECU_ENGINE_DUMMY_LOADS)executor.trip(checked_now,timing::Cause::Gate,output);
  const bool recovered=executor.recover(checked_now,capture_clock.ready()&&!output.failed&&!configuration_hold&&
   accepted_epoch==external_epoch&&have_command&&!synced&&latest.output.state==engine::State::Stopped&&!latest.output.faults);
  alarm_locked();portEXIT_CRITICAL(&lock);if(recovered)decoder.reset();service_trigger_logger();
 }
}
}
void init(Wheel wheel,bool interlock_at_boot){
 initial_wheel=wheel;output.boot_allowed=interlock_at_boot;
 captures=xQueueCreate(64,sizeof(Capture));commands=xQueueCreate(1,sizeof(TaggedCommand));started=xSemaphoreCreateBinary();configuration_mutex=xSemaphoreCreateMutex();trigger_mutex=xSemaphoreCreateMutex();
 configASSERT(captures&&commands&&started&&configuration_mutex&&trigger_mutex);
 configASSERT(xTaskCreatePinnedToCore(run,"ecu_timing",16384,nullptr,20,&timing_task,1)==pdPASS);
 xSemaphoreTake(started,portMAX_DELAY);vSemaphoreDelete(started);started=nullptr;
}
std::uint64_t clock_us(){return now_locked();}
Measurement measurement(){
 portENTER_CRITICAL(&lock);auto copy=measured;const auto&stats=executor.stats();const auto&cmd=executor.current_command();
 copy.timing_fault=stats.fault!=timing::Cause::None;copy.timing_cause=static_cast<std::uint8_t>(stats.fault);copy.last_timing_cause=static_cast<std::uint8_t>(stats.last_fault);
 copy.worker_cylinder_count=cmd.sequence?cmd.angle.cylinders:0;copy.worker_sequence=cmd.sequence;copy.worker_tune_revision=cmd.tune_revision;copy.worker_sensor_revision=cmd.sensor_revision;copy.worker_epoch=stats.epoch;
 copy.worker_observed_us=now_locked();copy.virtual_high_mask=stats.high_mask;copy.physical_command_mask=output.physical_mask;
 portEXIT_CRITICAL(&lock);return copy;
}
bool submit(const timing::Command& command){
 return submit_capture(command,{});
}
bool submit_capture(const timing::Command& command,const flex::CaptureTicket& ticket){
 if(!commands)return false;
 TaggedCommand tagged;tagged.command=command;
 portENTER_CRITICAL(&lock);
 if(configuration_hold||command.tune_revision<required_tune_revision||command.sensor_revision<required_sensor_revision){++rejected_commands;portEXIT_CRITICAL(&lock);return false;}
#if ECU_FLEX_G38_DRAFT
 if(!flex_port.can_issue(ticket,now_locked(),command.output.fuel_cut&&command.output.spark_cut)){
  ++rejected_commands;portEXIT_CRITICAL(&lock);return false;
 }
 tagged.flex_ticket=ticket;
#else
 (void)ticket;
#endif
 tagged.epoch=external_epoch;tagged.command.configuration_epoch=external_epoch;portEXIT_CRITICAL(&lock);
 return xQueueOverwrite(commands,&tagged)==pdTRUE;
}
void inhibit(timing::Cause cause){
 if(!timer)return;
 portENTER_CRITICAL(&lock);++external_epoch;
#if ECU_FLEX_G38_DRAFT
 flex_fence(now_locked());
#endif
 executor.stop(now_locked(),cause,output);alarm_locked();portEXIT_CRITICAL(&lock);
}
void begin_configuration(){
 configASSERT(configuration_mutex);xSemaphoreTake(configuration_mutex,portMAX_DELAY);
 portENTER_CRITICAL(&lock);configuration_hold=true;++external_epoch;
#if ECU_FLEX_G38_DRAFT
 flex_fence(now_locked());
#endif
 executor.stop(now_locked(),timing::Cause::Configuration,output);idle_executor.configuration(now_locked(),idle_output);boost_executor.configuration(now_locked(),boost_output);alarm_locked();portEXIT_CRITICAL(&lock);
}
void finish_configuration(std::uint32_t tune_revision,std::uint32_t sensor_revision){
 portENTER_CRITICAL(&lock);
 if(tune_revision>required_tune_revision)required_tune_revision=tune_revision;
 if(sensor_revision>required_sensor_revision)required_sensor_revision=sensor_revision;
 ++external_epoch;configuration_hold=false;
#if ECU_FLEX_G38_DRAFT
 flex_fence(now_locked());
#endif
 executor.stop(now_locked(),timing::Cause::Configuration,output);idle_executor.configuration(now_locked(),idle_output);boost_executor.configuration(now_locked(),boost_output);alarm_locked();portEXIT_CRITICAL(&lock);
 xSemaphoreGive(configuration_mutex);
}
flex::CaptureWork flex_configure(const flex::CaptureRequest&r,bool valid,std::uint64_t stale_us){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);
 const bool binding=!configuration_hold&&r.tune_revision&&r.sensor_revision&&
  r.tune_revision>=required_tune_revision&&r.sensor_revision>=required_sensor_revision;
 if(flex_port.changes(r,external_epoch,binding,flex_available,valid,stale_us))flex_irq_off();
 const auto now=now_locked();auto work=flex_port.configure(r,external_epoch,binding,flex_available,valid,stale_us,now);
 if(!work.active||!work.version.armed)flex_irq_off();
 flex_progress(now);alarm_locked();portEXIT_CRITICAL(&lock);return work;
#else
 (void)r;(void)valid;(void)stale_us;return {};
#endif
}
bool flex_arm(flex::CaptureVersion expected){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);const auto work=flex_port.work();bool ok=false;
 // A stale arm request must not mask a different, already live episode.
 if(flex_available&&flex_channel_owned&&work.active&&!work.version.armed&&flex::same(expected,work.version)){
  flex_irq_off();ok=flex_port.arm(expected,now_locked());
  if(ok)mcpwm_ll_intr_enable(MCPWM_LL_GET_HW(0),MCPWM_LL_EVENT_CAPTURE(2),true);
 }
 portEXIT_CRITICAL(&lock);return ok;
#else
 (void)expected;return false;
#endif
}
flex::CaptureWork flex_work(){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);auto work=flex_port.work();portEXIT_CRITICAL(&lock);return work;
#else
 return {};
#endif
}
bool flex_pop(flex::CaptureVersion version,flex::IngressEdge&edge){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);const bool ok=flex_port.pop(version,edge);portEXIT_CRITICAL(&lock);return ok;
#else
 (void)version;(void)edge;return false;
#endif
}
bool flex_publish(flex::CaptureVersion version,const flex::Sample&sample){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);const auto now=now_locked();const bool ok=flex_port.publish(version,sample,now);
 if(!flex_port.armed())flex_irq_off();
 const auto view=flex_port.view(now);
 if(flex_port.required()&&(!ok||!view.current||!view.ticket.qualified)){
  executor.stop(now,timing::Cause::Control,output);flex_command_live=false;
 }
 flex_progress(now);alarm_locked();portEXIT_CRITICAL(&lock);return ok;
#else
 (void)version;(void)sample;return false;
#endif
}
flex::CaptureView flex_view(){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);auto view=flex_port.view(now_locked());portEXIT_CRITICAL(&lock);return view;
#else
 return {};
#endif
}
bool flex_acknowledge(const flex::CaptureView&view){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);const bool ok=flex_port.acknowledge(view,now_locked());
 if(!flex_port.armed())flex_irq_off();
 portEXIT_CRITICAL(&lock);return ok;
#else
 (void)view;return false;
#endif
}
cJSON* flex_snapshot(){
#if ECU_FLEX_G38_DRAFT
 portENTER_CRITICAL(&lock);const auto now=now_locked();const auto copy=flex_port.snapshot(now);
 const auto available=flex_available;const auto error=flex_error;const auto uncertainty=capture_clock.uncertainty_us();
 portEXIT_CRITICAL(&lock);
 return flex::capture_json(copy,now,true,available,esp_err_to_name(error),uncertainty);
#else
 return flex::capture_json({},clock_us(),false,false,"profile_not_built",0);
#endif
}
cJSON* snapshot(){
 timing::TimingStats stats;timing::Command command;std::uint32_t physical;bool armed,failed,ready,held;std::uint32_t uncertainty;std::uint64_t now,sequence,superseded,rejected,configuration_skipped;
 portENTER_CRITICAL(&lock);stats=executor.stats();command=executor.current_command();physical=output.physical_mask;
 armed=output.armed;failed=output.failed;now=now_locked();sequence=executor.trace_sequence();
 ready=measured.ready;uncertainty=capture_clock.uncertainty_us();held=configuration_hold;
 superseded=superseded_captures;rejected=rejected_commands;configuration_skipped=configuration_captures;portEXIT_CRITICAL(&lock);
 auto* j=cJSON_CreateObject();cJSON_AddStringToObject(j,"mode",ECU_ENGINE_DUMMY_LOADS?"hardware_timer_dummy_loads":"hardware_timer_virtual_outputs");
 cJSON_AddBoolToObject(j,"available",ready);cJSON_AddBoolToObject(j,"physical_policy_enabled",ECU_ENGINE_DUMMY_LOADS);
 cJSON_AddBoolToObject(j,"bench_armed",armed);cJSON_AddBoolToObject(j,"bench_gate_fault",failed);
 cJSON_AddNumberToObject(j,"logical_cylinders",command.sequence?command.angle.cylinders:0);cJSON_AddNumberToObject(j,"maximum_logical_cylinders",executor.maximum_cylinders());cJSON_AddNumberToObject(j,"fitted_injector_commands",engine::channels::board_injector_commands);cJSON_AddNumberToObject(j,"fitted_coil_commands",engine::channels::board_coil_commands);
 cJSON_AddNumberToObject(j,"virtual_high_mask",stats.high_mask);cJSON_AddNumberToObject(j,"physical_high_mask",physical);
 cJSON_AddNumberToObject(j,"clock_uncertainty_us",uncertainty);
 cJSON_AddBoolToObject(j,"configuration_hold",held);cJSON_AddNumberToObject(j,"superseded_captures",superseded);cJSON_AddNumberToObject(j,"rejected_commands",rejected);
 cJSON_AddNumberToObject(j,"configuration_captures_ignored",configuration_skipped);
#define FIELD(k) cJSON_AddNumberToObject(j,#k,static_cast<double>(stats.k))
 FIELD(dispatched);FIELD(cuts);FIELD(faults);FIELD(recoveries);FIELD(retries);FIELD(max_lateness_us);FIELD(max_capture_age_us);
 FIELD(max_producer_gap_us);FIELD(max_injector_high_us);FIELD(max_coil_high_us);FIELD(last_fault_us);FIELD(generation);FIELD(epoch);
#undef FIELD
 cJSON_AddStringToObject(j,"fault",timing::cause_name(stats.fault));cJSON_AddStringToObject(j,"last_fault",timing::cause_name(stats.last_fault));
 cJSON_AddStringToObject(j,"angle_stop_reason",engine::AngleScheduler::reason_name(stats.angle_reason));
 cJSON_AddNumberToObject(j,"producer_age_us",stats.last_progress_us&&now>=stats.last_progress_us?now-stats.last_progress_us:-1.);
 cJSON_AddNumberToObject(j,"command_sequence",command.sequence);cJSON_AddNumberToObject(j,"tune_revision",command.tune_revision);
 cJSON_AddNumberToObject(j,"trace_sequence",sequence);cJSON_AddNumberToObject(j,"trace_overwritten",sequence>timing::Executor::trace_capacity?sequence-timing::Executor::trace_capacity:0);
 idle::PwmStats idle_stats;bool idle_high;portENTER_CRITICAL(&lock);idle_stats=idle_executor.stats();idle_high=idle_output.physical_high;portEXIT_CRITICAL(&lock);
 auto*idle_json=idle::pwm_json(idle_stats,ECU_IDLE_DUMMY_LOADS,idle_high);
 if(!idle_json||!cJSON_AddItemToObject(j,"idle_pwm",idle_json)){cJSON_Delete(idle_json);cJSON_Delete(j);return nullptr;}
 boost::PwmStats boost_stats;portENTER_CRITICAL(&lock);boost_stats=boost_executor.stats();portEXIT_CRITICAL(&lock);
 auto*boost_json=boost::pwm_json(boost_stats);
 if(!boost_json||!cJSON_AddItemToObject(j,"boost_pwm",boost_json)){cJSON_Delete(boost_json);cJSON_Delete(j);return nullptr;}
 cJSON_AddStringToObject(j,"qualification","Source/native tests only; actual_us is dispatcher observation time. Per-pin edges, target jitter and electrical behavior are unmeasured");return j;
}
cJSON* trace_json(){
 auto* j=cJSON_CreateObject();cJSON_AddItemToObject(j,"timing",snapshot());auto* events=cJSON_AddArrayToObject(j,"events");
 portENTER_CRITICAL(&lock);const auto end=executor.trace_sequence();portEXIT_CRITICAL(&lock);
 const auto begin=end>timing::Executor::trace_capacity?end-timing::Executor::trace_capacity+1:1;unsigned missed=0;
 for(auto seq=begin;seq<=end;++seq){
  timing::TimingEvent e;portENTER_CRITICAL(&lock);const bool found=executor.trace(seq,e);portEXIT_CRITICAL(&lock);
  if(!found){++missed;continue;}
  auto* row=cJSON_CreateObject();cJSON_AddNumberToObject(row,"sequence",e.sequence);cJSON_AddNumberToObject(row,"scheduled_us",e.scheduled_us);
  cJSON_AddNumberToObject(row,"actual_us",e.actual_us);cJSON_AddNumberToObject(row,"channel",e.channel);cJSON_AddBoolToObject(row,"high",e.high);
  cJSON_AddNumberToObject(row,"tune_revision",e.tune_revision);cJSON_AddStringToObject(row,"cause",timing::cause_name(e.cause));cJSON_AddItemToArray(events,row);
 }
 cJSON_AddNumberToObject(j,"missed_during_snapshot",missed);return j;
}
bool trigger_start(unsigned samples,unsigned timeout_ms){
 xSemaphoreTake(trigger_mutex,portMAX_DELAY);
 bool ok=false;
 if(trigger_available&&trigger_error==ESP_OK){
  portENTER_CRITICAL(&lock);trigger_capture.expire(now_locked());const bool idle=trigger_capture.header().state!=trigger_log::State::Armed;portEXIT_CRITICAL(&lock);
  if(idle&&disable_trigger_channels()){
   // This group1 capture timer is exclusively diagnostic. SDK disable leaves
   // pending status set; clear all capture bits while its channels are off.
   mcpwm_ll_intr_clear_status(MCPWM_LL_GET_HW(1),MCPWM_LL_EVENT_CAPTURE(0)|MCPWM_LL_EVENT_CAPTURE(1)|MCPWM_LL_EVENT_CAPTURE(2));
   portENTER_CRITICAL(&lock);ok=trigger_capture.start(samples,timeout_ms,now_locked());portEXIT_CRITICAL(&lock);
  }
  if(ok){
   for(unsigned i=0;i<trigger_channels.size();++i){
    const auto result=mcpwm_capture_channel_enable(trigger_channels[i]);
    if(result!=ESP_OK){trigger_error=result;ok=false;break;}trigger_channel_enabled[i]=true;
   }
   if(!ok){
    disable_trigger_channels();
    portENTER_CRITICAL(&lock);trigger_capture.stop(trigger_capture.header().frame_id,now_locked());portEXIT_CRITICAL(&lock);
   }
  }
 }
 xSemaphoreGive(trigger_mutex);return ok;
}
bool trigger_stop(std::uint32_t frame_id){
 xSemaphoreTake(trigger_mutex,portMAX_DELAY);
 portENTER_CRITICAL(&lock);const bool ok=trigger_capture.stop(frame_id,now_locked());portEXIT_CRITICAL(&lock);
 if(ok)disable_trigger_channels();
 xSemaphoreGive(trigger_mutex);return ok;
}
cJSON* trigger_json(std::uint32_t expected_frame,unsigned offset,bool records){
 xSemaphoreTake(trigger_mutex,portMAX_DELAY);const auto available=trigger_available&&trigger_error==ESP_OK;const auto error=trigger_error;
 const bool interrupts_enabled=trigger_channel_enabled[0]||trigger_channel_enabled[1];xSemaphoreGive(trigger_mutex);
 portENTER_CRITICAL(&lock);const auto header=trigger_capture.header();const auto uncertainty=trigger_clock.uncertainty_us();portEXIT_CRITICAL(&lock);
 auto* j=trigger_log::frame_json(header,[](std::uint32_t id,unsigned index,trigger_log::Record& record){
  portENTER_CRITICAL(&lock);const bool ok=trigger_capture.read(id,index,record);portEXIT_CRITICAL(&lock);return ok;
 },[&](std::uint32_t id){
  portENTER_CRITICAL(&lock);const bool current=trigger_capture.header().frame_id==id;portEXIT_CRITICAL(&lock);
  return current&&(!expected_frame||expected_frame==id);
 },offset,records?trigger_log::page_capacity:0);
 if(!j)return nullptr;
 const bool ok=cJSON_AddStringToObject(j,"data_source","mcpwm_reported_capture_edges")&&cJSON_AddBoolToObject(j,"simulator",false)&&
  cJSON_AddBoolToObject(j,"available",available)&&cJSON_AddStringToObject(j,"driver_error",esp_err_to_name(error))&&
  cJSON_AddBoolToObject(j,"diagnostic_interrupts_enabled",interrupts_enabled)&&
  cJSON_AddBoolToObject(j,"includes_falling_edges",true)&&cJSON_AddBoolToObject(j,"includes_cam",true)&&
  cJSON_AddNumberToObject(j,"clock_uncertainty_us",uncertainty)&&
  cJSON_AddStringToObject(j,"qualification","SDK-reported edge polarity and capture latch, not analog voltage or per-pin output measurements. Capture overwrite/loss and timing remain unmeasured on hardware. Cam phase is not decoded.");
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
