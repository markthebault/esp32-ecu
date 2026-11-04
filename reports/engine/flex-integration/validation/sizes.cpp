#include "ecu/engine_log.hpp"
#include "ecu/timing_executor.hpp"
#include <cstdio>
int main(){printf("{\"RuntimeSample\":%zu,\"FlexRecord\":%zu,\"Row\":%zu,\"Page\":%zu,\"Recorder\":%zu,\"Tune\":%zu,\"Output\":%zu,\"Command\":%zu,\"Executor\":%zu}\n",sizeof(ecu::engine::RuntimeSample),sizeof(ecu::flex::Record),sizeof(ecu::engine_log::Row),sizeof(ecu::engine_log::Page),sizeof(ecu::engine_log::Recorder),sizeof(ecu::engine::Tune),sizeof(ecu::engine::Output),sizeof(ecu::timing::Command),sizeof(ecu::timing::Executor));}
