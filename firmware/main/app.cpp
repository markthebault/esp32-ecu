#include "ecu/control.hpp"
#include "ecu/pins.hpp"
#include "ecu/web_config.hpp"
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "driver/mcpwm_cap.h"
#include "driver/spi_master.h"
#include "driver/twai.h"
#include "esp_log.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include <array>
#include <cstdint>

#ifndef ECU_BENCH_PULSES
#define ECU_BENCH_PULSES 0
#endif

namespace {
constexpr const char* tag = "ecu_a0";
// ISR lookup data must remain readable while the flash cache is disabled.
DRAM_ATTR std::array<int,8> outputs{ecu::pins::inj1_cmd,ecu::pins::inj2_cmd,
    ecu::pins::inj3_cmd,ecu::pins::inj4_cmd,ecu::pins::ign1_cmd,ecu::pins::ign2_cmd,
    ecu::pins::ign3_cmd,ecu::pins::ign4_cmd};
struct Capture { std::uint32_t ticks; std::int64_t arrived_us; bool cam; };
QueueHandle_t captures;
volatile bool capture_overflow = false;
spi_device_handle_t adc;
mcpwm_cap_timer_handle_t capture_timer;
std::uint32_t capture_hz = 0;
gptimer_handle_t pulse_timer;
volatile int bench_channel = -1;
portMUX_TYPE pulse_lock = portMUX_INITIALIZER_UNLOCKED;
DRAM_ATTR bool cam_context = true;

void all_off() {
    // Inhibit first. Clearing dwell can create a spark on an actual coil;
    // this firmware is a dummy-load bench monitor, not an engine controller.
    gpio_set_level(static_cast<gpio_num_t>(ecu::pins::arm),0);
    for (int pin : outputs) gpio_set_level(static_cast<gpio_num_t>(pin),0);
    gpio_set_level(static_cast<gpio_num_t>(ecu::pins::pump_cmd),0);
    gpio_set_level(static_cast<gpio_num_t>(ecu::pins::fan_cmd),0);
}

bool IRAM_ATTR capture_cb(mcpwm_cap_channel_handle_t,
                         const mcpwm_capture_event_data_t* event, void* context) {
    Capture item{event->cap_value,esp_timer_get_time(),context != nullptr};
    BaseType_t wake = pdFALSE;
    if (xQueueSendFromISR(captures,&item,&wake) != pdTRUE) capture_overflow = true;
    return wake == pdTRUE;
}

bool IRAM_ATTR pulse_done(gptimer_handle_t, const gptimer_alarm_event_data_t*, void*) {
    portENTER_CRITICAL_ISR(&pulse_lock);
    // One-shot compare ends a dummy-load pulse without depending on task timing.
    gpio_set_level(static_cast<gpio_num_t>(ecu::pins::arm),0);
    const int channel = bench_channel;
    if (channel >= 0 && channel < static_cast<int>(outputs.size()))
        gpio_set_level(static_cast<gpio_num_t>(outputs[static_cast<std::size_t>(channel)]),0);
    bench_channel = -1;
    portEXIT_CRITICAL_ISR(&pulse_lock);
    return false;
}

void init_gpio() {
    gpio_config_t config{};
    config.mode = GPIO_MODE_OUTPUT;
    for (int pin : outputs) config.pin_bit_mask |= 1ULL << pin;
    config.pin_bit_mask |= (1ULL << ecu::pins::arm)|(1ULL << ecu::pins::wdi)|
                           (1ULL << ecu::pins::pump_cmd)|(1ULL << ecu::pins::fan_cmd);
    ESP_ERROR_CHECK(gpio_config(&config));
    all_off();
    gpio_set_level(static_cast<gpio_num_t>(ecu::pins::wdi),0);
    config = {};
    config.mode = GPIO_MODE_INPUT;
    config.pin_bit_mask = (1ULL << ecu::pins::interlock)|(1ULL << ecu::pins::safe_n_mon);
    // Both inputs already have board-level bias. Do not load open-drain SAFE_N
    // with an internal pulldown and reduce its high-level margin.
    config.pull_down_en = GPIO_PULLDOWN_DISABLE;
    ESP_ERROR_CHECK(gpio_config(&config));
}

void init_adc() {
    spi_bus_config_t bus{};
    bus.mosi_io_num = ecu::pins::spi_mosi;
    bus.miso_io_num = ecu::pins::spi_miso;
    bus.sclk_io_num = ecu::pins::spi_clk;
    bus.quadwp_io_num = -1;
    bus.quadhd_io_num = -1;
    bus.max_transfer_sz = 3;
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_DISABLED));
    spi_device_interface_config_t device{};
    // MCP3208 at 3.3V: conservative 500 kHz, 3 bytes/sample, SPI mode 0.
    device.clock_speed_hz = 500000;
    device.mode = 0;
    device.spics_io_num = ecu::pins::adc_cs;
    device.queue_size = 1;
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST,&device,&adc));
}

bool sample(std::array<unsigned,8>& values) {
    for (unsigned ch=0; ch<8; ++ch) {
        spi_transaction_t t{};
        t.flags = SPI_TRANS_USE_TXDATA|SPI_TRANS_USE_RXDATA;
        t.length = 24;
        t.tx_data[0] = static_cast<std::uint8_t>(0x06|((ch&4)>>2));
        t.tx_data[1] = static_cast<std::uint8_t>((ch&3)<<6);
        if (spi_device_polling_transmit(adc,&t) != ESP_OK) return false;
        values[ch] = ((t.rx_data[1]&0x0fU)<<8)|t.rx_data[2];
    }
    return true;
}

void init_capture() {
    captures = xQueueCreate(128,sizeof(Capture));
    configASSERT(captures);
    mcpwm_capture_timer_config_t timer{};
    timer.group_id = 0;
    timer.clk_src = MCPWM_CAPTURE_CLK_SRC_DEFAULT;
    ESP_ERROR_CHECK(mcpwm_new_capture_timer(&timer,&capture_timer));
    ESP_ERROR_CHECK(mcpwm_capture_timer_get_resolution(capture_timer,&capture_hz));
    for (unsigned i=0; i<2; ++i) {
        mcpwm_capture_channel_config_t cfg{};
        cfg.gpio_num = i == 0 ? ecu::pins::crank : ecu::pins::cam;
        cfg.prescale = 1;
        cfg.flags.pos_edge = true;
        mcpwm_cap_channel_handle_t channel;
        ESP_ERROR_CHECK(mcpwm_new_capture_channel(capture_timer,&cfg,&channel));
        mcpwm_capture_event_callbacks_t callbacks{};
        callbacks.on_cap = capture_cb;
        ESP_ERROR_CHECK(mcpwm_capture_channel_register_event_callbacks(channel,&callbacks,
            i == 0 ? nullptr : &cam_context));
        ESP_ERROR_CHECK(mcpwm_capture_channel_enable(channel));
    }
    ESP_ERROR_CHECK(mcpwm_capture_timer_enable(capture_timer));
    ESP_ERROR_CHECK(mcpwm_capture_timer_start(capture_timer));
}

void init_bench_timer() {
    gptimer_config_t cfg{};
    cfg.clk_src = GPTIMER_CLK_SRC_DEFAULT;
    cfg.direction = GPTIMER_COUNT_UP;
    cfg.resolution_hz = 1000000;
    ESP_ERROR_CHECK(gptimer_new_timer(&cfg,&pulse_timer));
    gptimer_event_callbacks_t callbacks{};
    callbacks.on_alarm = pulse_done;
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(pulse_timer,&callbacks,nullptr));
    ESP_ERROR_CHECK(gptimer_enable(pulse_timer));
}

void init_can() {
    // This mode does not transmit frames or ACKs, even if JP1 is fitted.
    const twai_general_config_t general = TWAI_GENERAL_CONFIG_DEFAULT(static_cast<gpio_num_t>(ecu::pins::can_tx),
        static_cast<gpio_num_t>(ecu::pins::can_rx),TWAI_MODE_LISTEN_ONLY);
    const twai_timing_config_t timing = TWAI_TIMING_CONFIG_500KBITS();
    const twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    ESP_ERROR_CHECK(twai_driver_install(&general,&timing,&filter));
    ESP_ERROR_CHECK(twai_start());
}

} // namespace

extern "C" void app_main() {
    init_gpio();
    ecu::web::init();
    init_adc();
    init_capture();
    init_can();
    init_bench_timer();
    ESP_LOGW(tag,"Configuration monitor. No vehicle calibration. Engine scheduling DISABLED.");
    ecu::config::Config profile;
    (void)ecu::web::try_config(profile);
    ecu::MissingTooth decoder({profile.slots,profile.missing,profile.max_rpm});
    ecu::web::start_service();
    ESP_LOGI(tag,"Bench trigger profile: %u-%u, capture ceiling %u RPM",
             profile.slots,profile.missing,profile.max_rpm);
    bool have_capture = false, watchdog_high = false;
    std::uint32_t previous_ticks = 0;
    std::uint64_t accumulated_ticks = 0, can_frames = 0, cam_edges = 0, crank_edges = 0;
    std::int64_t last_capture_wall = 0, last_print = 0, last_heartbeat = 0, last_publish = 0;
#if ECU_BENCH_PULSES
    std::int64_t last_pulse = 0;
    unsigned next_channel = 0;
    bool pulse_latched_fault = false;
#endif
    TickType_t wake = xTaskGetTickCount();
    while (true) {
        const auto now = esp_timer_get_time();
        ecu::config::Config next;
        if (ecu::web::try_config(next) && next.revision != profile.revision) {
            const bool trigger_changed = next.slots != profile.slots || next.missing != profile.missing || next.max_rpm != profile.max_rpm;
            profile = next;
            if (trigger_changed) { decoder = ecu::MissingTooth({profile.slots,profile.missing,profile.max_rpm}); have_capture = false; }
        }
        Capture event{};
        while (xQueueReceive(captures,&event,0) == pdTRUE) {
            if (event.cam) { ++cam_edges; continue; }
            ++crank_edges;
            if (!have_capture || event.arrived_us-last_capture_wall > 150000) {
                decoder.reset();
                accumulated_ticks = 0;
                have_capture = true;
            } else {
                // Unsigned subtraction handles the hardware counter wrapping.
                accumulated_ticks += static_cast<std::uint32_t>(event.ticks-previous_ticks);
            }
            previous_ticks = event.ticks;
            last_capture_wall = event.arrived_us;
            decoder.edge(accumulated_ticks*1000000ULL/capture_hz);
        }
        if (have_capture && now-last_capture_wall > static_cast<std::int64_t>(decoder.stall_timeout())) {
            decoder.reset(); have_capture = false;
        }
        std::array<unsigned,8> raw{};
        const bool adc_ok = sample(raw);
        const bool safe = gpio_get_level(static_cast<gpio_num_t>(ecu::pins::safe_n_mon)) != 0;
        const bool interlock = gpio_get_level(static_cast<gpio_num_t>(ecu::pins::interlock)) != 0;
        twai_message_t message{};
        // Bound background work so a busy bus cannot starve supervision.
        for (unsigned i=0; i<16 && twai_receive(&message,0) == ESP_OK; ++i) ++can_frames;
        const bool healthy = decoder.valid() && adc_ok && !capture_overflow && esp_timer_get_time()-now < 10000;
        if (!healthy || !safe || !interlock) all_off();
        // The watchdog is fed by the supervised loop, not a free-running ISR.
        if (healthy && now-last_heartbeat >= 10000) {
            watchdog_high = !watchdog_high;
            gpio_set_level(static_cast<gpio_num_t>(ecu::pins::wdi),watchdog_high ? 1 : 0);
            last_heartbeat = now;
        }
#if ECU_BENCH_PULSES
        if (!healthy || !safe || !interlock) pulse_latched_fault = true;
        // A power cycle with J3 closed is needed after a bench inhibit.
        // MAIN_LS follows ARM, so NEVER connect actuator power in this mode.
        if (!pulse_latched_fault && healthy && safe && interlock && now-last_pulse >= 1000000 && bench_channel < 0) {
            all_off();
            ESP_ERROR_CHECK(gptimer_set_raw_count(pulse_timer,0));
            gptimer_alarm_config_t alarm{};
            alarm.alarm_count = 1000;
            ESP_ERROR_CHECK(gptimer_set_alarm_action(pulse_timer,&alarm));
            bench_channel = static_cast<int>(next_channel);
            // Start the cutoff clock first: an interrupted start cannot leave
            // an unbounded pulse. Actual pulse width can be less than 1 ms.
            portENTER_CRITICAL(&pulse_lock);
            ESP_ERROR_CHECK(gptimer_start(pulse_timer));
            gpio_set_level(static_cast<gpio_num_t>(ecu::pins::arm),1);
            gpio_set_level(static_cast<gpio_num_t>(outputs[next_channel]),1);
            portEXIT_CRITICAL(&pulse_lock);
            next_channel = (next_channel+1)%outputs.size();
            last_pulse = now;
        }
        // GPTimer one-shot alarms do not stop the counter themselves.
        if (bench_channel < 0) (void)gptimer_stop(pulse_timer);
#else
        all_off();
        (void)interlock;
#endif
        if (now-last_publish >= 50000) {
            ecu::web::Sample live;
            live.raw=raw; live.adc_ok=adc_ok; live.safe=safe; live.interlock=interlock;
            live.overflow=capture_overflow; live.synced=decoder.synced(); live.rpm=decoder.rpm();
            live.can_frames=can_frames; live.cam_edges=cam_edges; live.crank_edges=crank_edges;
            live.crank_level=gpio_get_level(static_cast<gpio_num_t>(ecu::pins::crank));
            live.cam_level=gpio_get_level(static_cast<gpio_num_t>(ecu::pins::cam));
            ecu::web::publish(live); last_publish=now;
        }
        if (now-last_print >= 1000000) {
            ESP_LOGI(tag,"sync=%d rpm=%.0f ADC=[%u,%u,%u,%u,%u,%u,%u,%u] safe=%d lock=%d CAN=%llu cam=%llu overflow=%d ARM=%d",
                decoder.synced(),decoder.rpm(),raw[0],raw[1],raw[2],raw[3],raw[4],raw[5],raw[6],raw[7],
                safe,interlock,static_cast<unsigned long long>(can_frames),
                static_cast<unsigned long long>(cam_edges),capture_overflow,
                gpio_get_level(static_cast<gpio_num_t>(ecu::pins::arm)));
            last_print = now;
        }
        vTaskDelayUntil(&wake,pdMS_TO_TICKS(5));
    }
}
