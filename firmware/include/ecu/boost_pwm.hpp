#pragma once
#include "ecu/idle_pwm.hpp"
namespace ecu::boost {
using PwmCommand=idle::PwmCommand;
using PwmStats=idle::PwmStats;
using PwmCause=idle::PwmCause;
//10..50Hz, with the same20ms freshness,25us lateness and explicit supervised
// zero-demand recovery as idle. This is a separate channel, not a pin driver.
using PwmExecutor=idle::PwmExecutorBase<20000,100000>;
}
