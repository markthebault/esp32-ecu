#pragma once
// Deterministic native API model. This neither executes ESP-IDF nor models
// interrupt latency, cache stalls, electrical edges, silicon latches or RTOS WCET.
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <vector>
using esp_err_t=int;using gpio_num_t=int;
constexpr esp_err_t ESP_OK=0,ESP_FAIL=-1,ESP_ERR_NO_MEM=0x101,ESP_ERR_INVALID_STATE=0x103;
inline const char*esp_err_to_name(esp_err_t e){return e==ESP_OK?"ESP_OK":e==ESP_ERR_NO_MEM?"ESP_ERR_NO_MEM":"ESP_ERR_INVALID_STATE";}
#define ESP_ERROR_CHECK(v) assert((v)==ESP_OK)
#define IRAM_ATTR
#define DRAM_ATTR
template<class...T>void fake_log(T...){ }
#define ESP_LOGI(...) fake_log(__VA_ARGS__)
#define ESP_LOGW(...) fake_log(__VA_ARGS__)
#define ESP_LOGE(...) fake_log(__VA_ARGS__)
using portMUX_TYPE=std::mutex;
#define portMUX_INITIALIZER_UNLOCKED {}
#define portENTER_CRITICAL(p) (p)->lock()
#define portEXIT_CRITICAL(p) (p)->unlock()
#define portENTER_CRITICAL_ISR(p) (p)->lock()
#define portEXIT_CRITICAL_ISR(p) (p)->unlock()
using BaseType_t=int;using TaskHandle_t=void*;
constexpr unsigned portMAX_DELAY=UINT32_MAX;
constexpr int pdTRUE=1,pdFALSE=0,pdPASS=1;
#define configASSERT(v) assert(v)
#define pdMS_TO_TICKS(v) (v)
struct FakeSemaphore {std::mutex mutex;bool binary=false;unsigned count=0;};
using SemaphoreHandle_t=FakeSemaphore*;
inline std::vector<std::unique_ptr<FakeSemaphore>> fake_semaphores;
inline SemaphoreHandle_t xSemaphoreCreateMutex(){fake_semaphores.push_back(std::make_unique<FakeSemaphore>());return fake_semaphores.back().get();}
inline SemaphoreHandle_t xSemaphoreCreateBinary(){auto*s=xSemaphoreCreateMutex();s->binary=true;return s;}
inline int xSemaphoreTake(SemaphoreHandle_t s,unsigned wait){if(s->binary){if(!s->count)return pdFALSE;--s->count;return pdTRUE;}if(!wait)return s->mutex.try_lock()?pdTRUE:pdFALSE;s->mutex.lock();return pdTRUE;}
inline void xSemaphoreGive(SemaphoreHandle_t s){if(s->binary)++s->count;else s->mutex.unlock();}
inline void vSemaphoreDelete(SemaphoreHandle_t){ }
inline int xTaskCreatePinnedToCore(void(*)(void*),const char*,unsigned,void*,unsigned,TaskHandle_t*,unsigned){return pdPASS;}
struct FakeQueue {unsigned capacity,size;std::deque<std::vector<unsigned char>> rows;};
using QueueHandle_t=FakeQueue*;
inline std::vector<std::unique_ptr<FakeQueue>> fake_queues;
inline std::function<void()> fake_tick;
inline QueueHandle_t xQueueCreate(unsigned capacity,unsigned size){fake_queues.push_back(std::make_unique<FakeQueue>(FakeQueue{capacity,size,{}}));return fake_queues.back().get();}
inline int xQueueReceive(QueueHandle_t q,void*out,unsigned wait){if(q->rows.empty()&&wait&&fake_tick)fake_tick();if(q->rows.empty())return pdFALSE;std::memcpy(out,q->rows.front().data(),q->size);q->rows.pop_front();return pdTRUE;}
inline int xQueueOverwrite(QueueHandle_t q,const void*in){q->rows.clear();q->rows.emplace_back(static_cast<const unsigned char*>(in),static_cast<const unsigned char*>(in)+q->size);return pdTRUE;}
inline int xQueueSendFromISR(QueueHandle_t q,const void*in,BaseType_t*){if(q->rows.size()==q->capacity)return pdFALSE;q->rows.emplace_back(static_cast<const unsigned char*>(in),static_cast<const unsigned char*>(in)+q->size);return pdTRUE;}
inline std::uint64_t fake_now=1000;
struct FakeTimer{};inline FakeTimer fake_timer;
using gptimer_handle_t=FakeTimer*;
struct gptimer_alarm_event_data_t{};
struct gptimer_event_callbacks_t {bool(*on_alarm)(gptimer_handle_t,const gptimer_alarm_event_data_t*,void*)=nullptr;};
struct gptimer_config_t {int clk_src,direction;unsigned resolution_hz,intr_priority;};
struct gptimer_alarm_config_t {std::uint64_t alarm_count;};
inline gptimer_event_callbacks_t fake_gpt_callbacks;inline std::uint64_t fake_alarm=UINT64_MAX;
constexpr int GPTIMER_CLK_SRC_APB=1,GPTIMER_COUNT_UP=1;
inline int gptimer_new_timer(const gptimer_config_t*,gptimer_handle_t*h){*h=&fake_timer;return ESP_OK;}
inline int gptimer_register_event_callbacks(gptimer_handle_t,const gptimer_event_callbacks_t*c,void*){fake_gpt_callbacks=*c;return ESP_OK;}
inline int gptimer_enable(gptimer_handle_t){return ESP_OK;}
inline int gptimer_start(gptimer_handle_t){return ESP_OK;}
inline int gptimer_get_raw_count(gptimer_handle_t,std::uint64_t*t){*t=fake_now;return ESP_OK;}
inline int gptimer_set_alarm_action(gptimer_handle_t,const gptimer_alarm_config_t*c){fake_alarm=c?c->alarm_count:UINT64_MAX;return ESP_OK;}
struct FakeMcpwm {std::uint32_t enable=0,status=0;};inline std::array<FakeMcpwm,2> fake_mcpwm{};
#define MCPWM_LL_GET_HW(group) (&fake_mcpwm[group])
#define MCPWM_LL_EVENT_CAPTURE(channel) (1U<<((channel)+27))
#define SOC_MCPWM_CAPTURE_CHANNELS_PER_TIMER 3
inline std::vector<std::array<std::uint32_t,3>> fake_masks,fake_clears;
inline void mcpwm_ll_intr_enable(FakeMcpwm*d,std::uint32_t mask,bool enabled){fake_masks.push_back({static_cast<unsigned>(d-fake_mcpwm.data()),mask,enabled});if(enabled)d->enable|=mask;else d->enable&=~mask;}
inline void mcpwm_ll_intr_clear_capture_status(FakeMcpwm*d,std::uint32_t mask){fake_clears.push_back({static_cast<unsigned>(d-fake_mcpwm.data()),mask,0});d->status&=~((mask&7)<<27);}
inline void mcpwm_ll_intr_clear_status(FakeMcpwm*d,std::uint32_t mask){d->status&=~mask;}
struct FakeCapTimer {unsigned group,count=0;std::uint64_t epoch=0;};
using mcpwm_cap_timer_handle_t=FakeCapTimer*;
struct FakeSync {FakeCapTimer*timer=nullptr;};using mcpwm_sync_handle_t=FakeSync*;
inline std::vector<std::unique_ptr<FakeSync>> fake_syncs;
inline std::array<FakeCapTimer,2> fake_cap_timers{{{0,0,0},{1,0,0}}};
enum {MCPWM_CAP_EDGE_POS=1,MCPWM_CAP_EDGE_NEG=2,MCPWM_CAPTURE_CLK_SRC_APB=1,MCPWM_TIMER_DIRECTION_UP=1};
struct mcpwm_capture_event_data_t {std::uint32_t cap_value;int cap_edge;};
struct FakeCapChannel;using mcpwm_cap_channel_handle_t=FakeCapChannel*;
struct mcpwm_capture_event_callbacks_t {bool(*on_cap)(mcpwm_cap_channel_handle_t,const mcpwm_capture_event_data_t*,void*)=nullptr;};
struct FakeCapChannel {FakeCapTimer*timer;unsigned id;int gpio;bool enabled=false;mcpwm_capture_event_callbacks_t callbacks{};void*context=nullptr;};
inline std::vector<std::unique_ptr<FakeCapChannel>> fake_channels;
inline unsigned fake_capture_starts=0,fake_capture_stops=0,fake_capture_syncs=0,fake_gpio_output_writes=0;
inline int fake_flex_error_stage=0;
struct mcpwm_capture_timer_config_t {unsigned group_id;int clk_src;};
struct mcpwm_capture_channel_config_t {int gpio_num;unsigned intr_priority,prescale;struct{bool pos_edge,neg_edge;}flags;};
struct mcpwm_soft_sync_config_t{};
struct mcpwm_capture_timer_sync_phase_config_t {mcpwm_sync_handle_t sync_src;int direction;};
inline int mcpwm_new_capture_timer(const mcpwm_capture_timer_config_t*c,mcpwm_cap_timer_handle_t*h){*h=&fake_cap_timers[c->group_id];return ESP_OK;}
inline int mcpwm_capture_timer_get_resolution(mcpwm_cap_timer_handle_t,std::uint32_t*h){*h=80000000;return ESP_OK;}
inline int mcpwm_capture_timer_enable(mcpwm_cap_timer_handle_t){return ESP_OK;}
inline int mcpwm_capture_timer_start(mcpwm_cap_timer_handle_t){++fake_capture_starts;return ESP_OK;}
inline int mcpwm_capture_timer_stop(mcpwm_cap_timer_handle_t){++fake_capture_stops;return ESP_OK;}
inline int mcpwm_capture_timer_disable(mcpwm_cap_timer_handle_t){return ESP_OK;}
inline int mcpwm_del_capture_timer(mcpwm_cap_timer_handle_t){return ESP_OK;}
inline int mcpwm_new_soft_sync_src(const mcpwm_soft_sync_config_t*,mcpwm_sync_handle_t*h){fake_syncs.push_back(std::make_unique<FakeSync>());*h=fake_syncs.back().get();return ESP_OK;}
inline int mcpwm_capture_timer_set_phase_on_sync(mcpwm_cap_timer_handle_t t,const mcpwm_capture_timer_sync_phase_config_t*c){c->sync_src->timer=t;return ESP_OK;}
inline int mcpwm_soft_sync_activate(mcpwm_sync_handle_t h){h->timer->epoch=fake_now;++fake_capture_syncs;return ESP_OK;}
inline int mcpwm_del_sync_src(mcpwm_sync_handle_t){return ESP_OK;}
inline int mcpwm_new_capture_channel(mcpwm_cap_timer_handle_t t,const mcpwm_capture_channel_config_t*c,mcpwm_cap_channel_handle_t*h){if(t->group==0&&t->count==2&&fake_flex_error_stage==1)return ESP_ERR_NO_MEM;fake_channels.push_back(std::make_unique<FakeCapChannel>(FakeCapChannel{t,t->count++,c->gpio_num,false,{},nullptr}));*h=fake_channels.back().get();return ESP_OK;}
inline int mcpwm_capture_channel_register_event_callbacks(mcpwm_cap_channel_handle_t h,const mcpwm_capture_event_callbacks_t*c,void*x){if(h->gpio==38&&fake_flex_error_stage==2)return ESP_ERR_INVALID_STATE;h->callbacks=*c;h->context=x;return ESP_OK;}
inline int mcpwm_capture_channel_enable(mcpwm_cap_channel_handle_t h){if(h->gpio==38&&fake_flex_error_stage==3)return ESP_ERR_INVALID_STATE;h->enabled=true;fake_mcpwm[h->timer->group].enable|=MCPWM_LL_EVENT_CAPTURE(h->id);return ESP_OK;}
inline int mcpwm_capture_channel_disable(mcpwm_cap_channel_handle_t h){h->enabled=false;fake_mcpwm[h->timer->group].enable&=~MCPWM_LL_EVENT_CAPTURE(h->id);return ESP_OK;}
inline int mcpwm_del_capture_channel(mcpwm_cap_channel_handle_t h){h->enabled=false;return ESP_OK;}
struct FakeGpio{};inline FakeGpio GPIO;
constexpr int GPIO_MODE_INPUT=1,GPIO_PULLUP_DISABLE=0,GPIO_PULLDOWN_DISABLE=0,GPIO_INTR_DISABLE=0,GPIO_MODE_OUTPUT=2;
struct gpio_config_t {std::uint64_t pin_bit_mask;int mode,pull_up_en,pull_down_en,intr_type;};
inline gpio_config_t fake_gpio_config{};
inline int gpio_config(const gpio_config_t*c){fake_gpio_config=*c;return ESP_OK;}
inline int gpio_set_level(gpio_num_t,int){++fake_gpio_output_writes;return ESP_OK;}
inline int gpio_set_direction(gpio_num_t,int){return ESP_OK;}
inline int gpio_ll_get_level(FakeGpio*,unsigned){return 1;}
inline void gpio_ll_set_level(FakeGpio*,unsigned,int){++fake_gpio_output_writes;}
