#pragma once
#include "ecu/idle_pwm.hpp"
#include "ecu/timing_executor.hpp"
#include <cmath>
namespace ecu::idle {
// Task-only conversion. Integer PWM dispatch never evaluates floating point.
inline void prepare_pwm(timing::Command& c,const engine::Tune&t){
 c.idle_period_us=static_cast<unsigned>(std::llround(1000000./t.idle_control.frequency_hz));
 c.idle_high_us=static_cast<unsigned>(std::llround(c.idle_period_us*c.output.idle_pct/100.));
}
inline PwmCommand pwm_command(const timing::Command& c,const timing::Command& effective,std::uint64_t now,const timing::TimingStats&s,bool hold=false){
 PwmCommand p;p.sequence=c.sequence;p.command_us=c.command_us;p.sampled_us=c.sampled_us;
 p.tune_revision=c.tune_revision;p.sensor_revision=c.sensor_revision;p.period_us=c.idle_period_us;
 const bool accepted=effective.sequence==c.sequence&&effective.tune_revision==c.tune_revision&&effective.sensor_revision==c.sensor_revision&&
  effective.configuration_epoch==c.configuration_epoch&&!effective.output.faults;
 p.enabled=!hold&&accepted&&s.fault==timing::Cause::None&&effective.output.proposed_enabled()&&(c.output.idle.flags&Enabled);
 p.high_us=p.enabled?c.idle_high_us:0;
 const bool quiet=now>=s.last_capture_us&&now-s.last_capture_us>150000;
 p.supervised_stop=!p.enabled&&accepted&&quiet&&c.output.state==engine::State::Stopped&&!c.output.faults&&
  now>=c.command_us&&now-c.command_us<20000&&now>=c.sampled_us&&now-c.sampled_us<20000&&!hold;
 return p;
}
} // namespace ecu::idle
