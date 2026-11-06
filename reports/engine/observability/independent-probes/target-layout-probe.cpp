#include "ecu/engine_log.hpp"
extern "C" {
char review_runtime_sample[sizeof(ecu::engine::RuntimeSample)];
char review_row[sizeof(ecu::engine_log::Row)];
char review_page[sizeof(ecu::engine_log::Page)];
char review_recorder[sizeof(ecu::engine_log::Recorder)];
}
