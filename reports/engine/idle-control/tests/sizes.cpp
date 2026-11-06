#include "ecu/tuning_session.hpp"
#include "ecu/engine_log.hpp"
#include "ecu/idle_pwm.hpp"
#include <iostream>
int main(){std::cout<<"{\"runtime_sample\":"<<sizeof(ecu::engine::RuntimeSample)<<",\"recorder\":"<<sizeof(ecu::engine_log::Recorder)<<",\"page\":"<<sizeof(ecu::engine_log::Page)<<",\"tune\":"<<sizeof(ecu::engine::Tune)<<",\"session\":"<<sizeof(ecu::tuning::Session)<<",\"idle_executor\":"<<sizeof(ecu::idle::PwmExecutor)<<"}\n";}
