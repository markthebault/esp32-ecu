#include "ecu/engine_data_json.hpp"
#include "ecu/engine_radio.hpp"
#include <string>
namespace {std::string text;}
extern "C" const char* review_sample(unsigned strategy,unsigned fault,unsigned last){
 ecu::engine::Tune t;t.strategy=static_cast<ecu::engine::Strategy>(strategy);
 ecu::engine::Inputs in;in.rpm=1200;in.map_kpa=46;in.tps_pct=12.5;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sampled_us=10;in.synced=in.sensors_valid=in.lambda_ready=true;
 ecu::engine::Controller controller;const auto out=controller.step(t,in,10);auto r=ecu::engine::synthetic_data(t,in,out,17,10);
 r.timing_fault=fault;r.last_timing_fault=last;
 auto*j=ecu::engine::data_json(r,10);if(!j)return nullptr;char*s=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!s)return nullptr;
 text=s;cJSON_free(s);return text.c_str();
}
extern "C" int review_supports(unsigned schema,unsigned strategy,unsigned fault,unsigned last){ecu::engine::RuntimeSample r;r.strategy=strategy;r.timing_fault=fault;r.last_timing_fault=last;return ecu::radio::wire::engine_schema_supports(schema,r);}
