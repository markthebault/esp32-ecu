// Host simulator and tests use the target's actual parser and conversion code.
#include "config_json.hpp"
#include <cstring>
struct HostReading {double value,sensor_v,adc_v;int valid;char fault[64];double transfer_v,display_transfer_v;};
extern "C" int validate_profile(const char* text){
 if(!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);return ok?1:0;
}
extern "C" int normalize_profile(const char*text,char*out,unsigned capacity){
 if(!out||!capacity||!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 const bool ok=j&&ecu::web::parse(j,c)&&ecu::web::upgrade_profile_document(j);
 char*encoded=ok?cJSON_PrintUnformatted(j):nullptr;cJSON_Delete(j);
 if(!encoded)return 0;
 const auto size=std::strlen(encoded);
 const bool fits=size<capacity&&size<=16384;if(fits)std::memcpy(out,encoded,size+1);
 cJSON_free(encoded);return fits?1:0;
}
extern "C" int profile_transfer_voltage(const char*text,const unsigned*raw,double*out){
 if(!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 const bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);if(!ok)return 0;
 const double supply=raw[7]*c.adc_reference_v/4095/.6;
 for(unsigned i=0;i<6;++i)out[i]=ecu::config::transfer_voltage(c.sensors[i],raw[i]*c.adc_reference_v/4095/.6,supply);
 return 1;
}
extern "C" int filter_profile(const char*text,const unsigned*raw,const double*previous,
                              double dt_ms,int reset,int adc_ok,double*out){
 if(!ecu::config::finite(dt_ms)||dt_ms<0||!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 const bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);if(!ok)return 0;
 const double supply=raw[7]*c.adc_reference_v/4095/.6;
 for(unsigned i=0;i<6;++i)out[i]=ecu::config::readout_filter(c.sensors[i],raw[i]*c.adc_reference_v/4095/.6,supply,previous[i],dt_ms,reset,adc_ok);
 return 1;
}
extern "C" int evaluate_profile(const char*text,const unsigned*raw,const double*filtered,HostReading*out){
 if(!ecu::web::safe_json(text,std::strlen(text)))return 0;
 auto*j=cJSON_ParseWithOpts(text,nullptr,true);ecu::config::Config c;
 bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);if(!ok)return 0;
 const double supply=raw[7]*c.adc_reference_v/4095.0/.6;
 for(unsigned i=0;i<6;++i){const double av=raw[i]*c.adc_reference_v/4095.0,sv=av/.6;
  auto instant=ecu::config::convert(c.sensors[i],sv,av,supply);
  auto smooth=c.sensors[i].ratiometric?ecu::config::convert(c.sensors[i],sv,av,supply,&filtered[i]):ecu::config::convert(c.sensors[i],filtered[i],filtered[i]*.6,supply);
  out[i].value=smooth.value;out[i].sensor_v=sv;out[i].adc_v=av;out[i].valid=instant.valid&&smooth.valid;
  out[i].transfer_v=instant.transfer_v;out[i].display_transfer_v=smooth.transfer_v;
  std::snprintf(out[i].fault,sizeof(out[i].fault),"%s",!instant.valid?instant.fault:smooth.fault);
 }
 return 1;
}
