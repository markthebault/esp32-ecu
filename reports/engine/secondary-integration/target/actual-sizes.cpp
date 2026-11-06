#include "ecu/engine_log.hpp"
#include "ecu/tuning_stream.hpp"
#include "cJSON.h"
#include <cstdio>
using namespace ecu;
extern "C" {
char bytes_cjson[sizeof(cJSON)];
char bytes_tune[sizeof(engine::Tune)];
char bytes_observation[sizeof(secondary::Observation)];
char bytes_sample[sizeof(engine::RuntimeSample)];
char bytes_row[sizeof(engine_log::Row)];
char bytes_page[sizeof(engine_log::Page)];
char bytes_recorder[sizeof(engine_log::Recorder)];
char bytes_session[sizeof(tuning::Session)];
char bytes_reply[sizeof(tuning::Reply)];
}
#ifndef TARGET_SIZE_ONLY
int main(){std::printf("{\"cjson\":%zu,\"tune\":%zu,\"observation\":%zu,\"sample\":%zu,\"row\":%zu,\"page\":%zu,\"recorder\":%zu,\"session\":%zu,\"reply\":%zu}\n",sizeof(cJSON),sizeof(engine::Tune),sizeof(secondary::Observation),sizeof(engine::RuntimeSample),sizeof(engine_log::Row),sizeof(engine_log::Page),sizeof(engine_log::Recorder),sizeof(tuning::Session),sizeof(tuning::Reply));}
#endif
