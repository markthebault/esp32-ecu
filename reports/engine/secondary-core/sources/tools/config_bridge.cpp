// Host simulator and tests use the target's actual parser and conversion code.
#include "config_json.hpp"
#include <cstring>
struct HostReading {double value,sensor_v,adc_v;int valid;char fault[64];};
extern "C" int validate_profile(const char* text){
 if(!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);return ok?1:0;
}
extern "C" int evaluate_profile(const char*text,const unsigned*raw,const double*filtered,HostReading*out){
 if(!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);if(!ok)return 0;
 const double supply=raw[7]*c.adc_reference_v/4095.0/.6;
 for(unsigned i=0;i<6;++i){const double av=raw[i]*c.adc_reference_v/4095.0,sv=av/.6;
  auto instant=ecu::config::convert(c.sensors[i],sv,av,supply);
  auto smooth=ecu::config::convert(c.sensors[i],filtered[i],filtered[i]*.6,supply);
  out[i].value=smooth.value;out[i].sensor_v=sv;out[i].adc_v=av;out[i].valid=instant.valid&&smooth.valid;
  std::snprintf(out[i].fault,sizeof(out[i].fault),"%s",!instant.valid?instant.fault:smooth.fault);
 }
 return 1;
}
