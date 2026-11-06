#pragma once
#include "ecu/boost_control.hpp"
#include "ecu/json.hpp"
namespace ecu::boost {
struct Scalar {const char*name;float Config::*member;};
inline constexpr Scalar scalars[]={
 {"maximum_map_kpa",&Config::maximum_map_kpa},{"cut_kpa",&Config::cut_kpa},{"cut_hysteresis_kpa",&Config::cut_hysteresis_kpa},{"recovery_ms",&Config::recovery_ms},
 {"frequency_hz",&Config::frequency_hz},{"control_period_ms",&Config::control_period_ms},{"min_pct",&Config::min_pct},{"max_pct",&Config::max_pct},
 {"minimum_rpm",&Config::minimum_rpm},{"minimum_tps_pct",&Config::minimum_tps_pct},{"activation_kpa",&Config::activation_kpa},{"activation_hysteresis_kpa",&Config::activation_hysteresis_kpa},{"inactive_pct",&Config::inactive_pct},
 {"kp",&Config::kp},{"ki",&Config::ki},{"kd",&Config::kd},{"integral_limit_pct",&Config::integral_limit_pct},{"derivative_filter_s",&Config::derivative_filter_s},{"slew_pct_s",&Config::slew_pct_s}};
struct Grid {const char*name;Table Config::*member;};
inline constexpr Grid grids[]={{"open_duty",&Config::open_duty},{"target",&Config::target},{"feedforward",&Config::feedforward}};
inline const char* activation_name(Activation a){return a==Activation::Barometric?"barometric":a==Activation::Fixed?"fixed":"unknown";}
template<std::size_t N>inline bool array(const cJSON*j,std::array<float,N>&a){
 if(!cJSON_IsArray(j)||cJSON_GetArraySize(j)!=int(N))return false;
 for(unsigned n=0;n<N;++n){const auto*v=cJSON_GetArrayItem(j,n);if(!cJSON_IsNumber(v)||!std::isfinite(v->valuedouble)||std::abs(v->valuedouble)>1e6)return false;a[n]=static_cast<float>(v->valuedouble);}return true;
}
inline bool parse_config(const cJSON*j,Config&c){
 if(!web::keys(j,"|pressure_enabled||mode||activation||maximum_map_kpa||cut_kpa||cut_hysteresis_kpa||recovery_ms||frequency_hz||control_period_ms||min_pct||max_pct||minimum_rpm||minimum_tps_pct||activation_kpa||activation_hysteresis_kpa||inactive_pct||kp||ki||kd||integral_limit_pct||derivative_filter_s||slew_pct_s||open_duty||target||feedforward|"))return false;
 char mode[24]{},activation[24]{};
 if(!web::boolean(j,"pressure_enabled",c.pressure_enabled)||!web::string(j,"mode",mode)||!web::string(j,"activation",activation))return false;
 if(!std::strcmp(mode,"off"))c.mode=Mode::Off;else if(!std::strcmp(mode,"open_loop"))c.mode=Mode::OpenLoop;else if(!std::strcmp(mode,"closed_loop"))c.mode=Mode::ClosedLoop;else return false;
 if(!std::strcmp(activation,"barometric"))c.activation=Activation::Barometric;else if(!std::strcmp(activation,"fixed"))c.activation=Activation::Fixed;else return false;
 for(auto f:scalars){double value;if(!web::number(j,f.name,value)||std::abs(value)>1e6)return false;c.*f.member=static_cast<float>(value);}
 for(auto f:grids){auto*g=cJSON_GetObjectItemCaseSensitive(j,f.name);auto&t=c.*f.member;
  if(!web::keys(g,"|rpm||axis||cells|")||!array(cJSON_GetObjectItemCaseSensitive(g,"rpm"),t.rpm)||!array(cJSON_GetObjectItemCaseSensitive(g,"axis"),t.axis)||!array(cJSON_GetObjectItemCaseSensitive(g,"cells"),t.cells))return false;
 }return valid(c);
}
inline cJSON* config_document(const Config&c){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 bool ok=cJSON_AddBoolToObject(j,"pressure_enabled",c.pressure_enabled)&&cJSON_AddStringToObject(j,"mode",mode_name(c.mode))&&cJSON_AddStringToObject(j,"activation",activation_name(c.activation));
 for(auto f:scalars)ok=ok&&cJSON_AddNumberToObject(j,f.name,c.*f.member);
 for(auto f:grids){auto*g=ok?cJSON_AddObjectToObject(j,f.name):nullptr;if(!g){ok=false;break;}const auto&t=c.*f.member;
  auto add=[&](const char*name,const auto&values){auto*a=cJSON_CreateFloatArray(values.data(),values.size());if(!a||!cJSON_AddItemToObject(g,name,a)){cJSON_Delete(a);return false;}return true;};
  ok=add("rpm",t.rpm)&&add("axis",t.axis)&&add("cells",t.cells);
 }if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* observation_json(const Output&o){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 bool ok=cJSON_AddStringToObject(j,"reason",reason_name(o.reason))&&cJSON_AddNumberToObject(j,"reason_code",unsigned(o.reason))&&cJSON_AddNumberToObject(j,"flags",o.flags)&&cJSON_AddBoolToObject(j,"inhibit_engine",o.inhibit_engine);
 const char*names[]={"duty_pct","demand_pct","target_kpa","feedforward_pct","error_kpa","p_term","i_term","d_term"};
 const double values[]={o.duty_pct,o.demand_pct,o.target_kpa,o.feedforward_pct,o.error_kpa,o.p_term,o.i_term,o.d_term};
 for(unsigned n=0;ok&&n<8;++n)ok=std::isfinite(values[n])?cJSON_AddNumberToObject(j,names[n],values[n])!=nullptr:cJSON_AddNullToObject(j,names[n])!=nullptr;
 auto count=[&](const char*name,std::uint64_t value){char text[24];std::snprintf(text,sizeof(text),"%llu",static_cast<unsigned long long>(value));return cJSON_AddStringToObject(j,name,text)!=nullptr;};
 ok=ok&&count("pid_updates",o.pid_updates)&&count("overboost_events",o.overboost_events);
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
}
