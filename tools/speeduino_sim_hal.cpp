// Deterministic replacement for upstream native SoftwareTimer.cpp only.
// No production decoder/scheduler/calculation changes. Virtual GPIO only.
#include "SoftwareTimer.h"
#include "timers.h"
#include <map>
#include <functional>
#include <stdexcept>
#include <cstdint>
extern software_timer_t idleTimer;

namespace {
using Tick = software_timer_t::counter_t;
using Callbacks = std::map<uint16_t, std::function<void(Tick)>>;
// Intentionally process-lifetime storage: timers may be destroyed after statics.
Callbacks& callbacks() { static auto* value = new Callbacks; return *value; }
uint64_t now_us = 0;
uint16_t next_id = 0;
}
extern "C" uint64_t speeduino_sim_micros() { return now_us; }
extern "C" void speeduino_sim_observe();
extern "C" void speeduino_sim_advance(uint64_t target) {
    if (target < now_us) throw std::runtime_error("virtual clock reversal");
    if (target > 60000000) throw std::runtime_error("native benchmark clock exceeds60s bound");
    while (now_us < target) {
        auto next = ((now_us / software_timer_t::TIMER_RESOLUTION)+1)*software_timer_t::TIMER_RESOLUTION;
        now_us = next > target ? target : next;
        if (now_us % software_timer_t::TIMER_RESOLUTION == 0) {
            for (const auto& item : callbacks()) item.second(static_cast<Tick>(now_us/software_timer_t::TIMER_RESOLUTION));
            speeduino_sim_observe();
        }
        if (now_us % 1000 == 0) { oneMSInterval(); speeduino_sim_observe(); }
    }
}
software_timer_t::software_timer_t() : counter(now_us/TIMER_RESOLUTION) {
    tickCallbackId = next_id++;
    callbacks()[tickCallbackId] = [this](Tick) {
        const auto resolution=this==&idleTimer?ECU_SIM_IDLE_TICK_US:TIMER_RESOLUTION;
        if(now_us%resolution==0)onNextTick(static_cast<Tick>(now_us/resolution));
    };
}
software_timer_t::~software_timer_t() { callbacks().erase(tickCallbackId); }
void software_timer_t::setCallback(const callback_t& cb) { callback = cb; }
void software_timer_t::enableTimer() { enabled = true; }
void software_timer_t::disableTimer() { enabled = false; }
void software_timer_t::onNextTick(counter_t tick) {
    counter = tick;
    #if ECU_SIM_TIMER_BITS == 16
    if(enabled.load()&&callback&&counter.load()==compare.load())callback();
#else
    if (enabled.load() && callback && counter.load() >= compare.load()) callback();
#endif
}
TickEventGuard::TickEventGuard() noexcept {}
TickEventGuard::~TickEventGuard() noexcept {}
