#pragma once
#include "ecu/engine.hpp"
#include "ecu/load_json.hpp"
#include "ecu/json.hpp"
#include <cstdio>
#include <type_traits>
namespace ecu::secondary {
inline bool parse_rule(const cJSON*j,Rule&r,engine::Map&m,double maximum_map_kpa=110){
 if(!web::keys(j,"|mode||source||axis||cells||condition||threshold||debounce_ms||input_channel||active_high||map|"))return false;
 if(!load::parse_enum(j,"mode",r.mode,{{"off",Mode::Off},{"multiply",Mode::Multiply},{"add",Mode::Add},{"conditional",Mode::Conditional},{"input",Mode::Input}})||
    !load::parse_enum(j,"source",r.source,{{"map",load::Source::Map},{"tps",load::Source::Tps},{"imap_emap",load::Source::PressureRatio}})||
    !load::parse_enum(j,"axis",r.axis,{{"map_kpa",load::Axis::MapKpa},{"tps_pct",load::Axis::TpsPercent},{"imap_emap_pct",load::Axis::PressureRatioPercent}})||
    !load::parse_enum(j,"cells",r.cells,{{"absolute",Cells::Absolute},{"multiplier",Cells::Multiplier},{"adder",Cells::Adder}})||
    !load::parse_enum(j,"condition",r.condition,{{"rpm",Condition::Rpm},{"map_kpa",Condition::Map},{"tps_pct",Condition::Tps},{"ethanol_pct",Condition::Ethanol}}))return false;
 double threshold,debounce;unsigned channel;
 if(!web::number(j,"threshold",threshold)||!range(threshold,0,threshold_max(r.condition,maximum_map_kpa))||!web::number(j,"debounce_ms",debounce)||!range(debounce,0,500)||
    !web::integer(j,"input_channel",channel)||channel>1||!web::boolean(j,"active_high",r.active_high))return false;
 r.threshold=static_cast<float>(threshold);r.debounce_ms=static_cast<float>(debounce);r.input_channel=static_cast<std::uint8_t>(channel);
 auto*map=cJSON_GetObjectItemCaseSensitive(j,"map");if(!web::keys(map,"|rpm||load||cells|"))return false;
 auto array=[](const cJSON*a,auto&out){if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)!=int(out.size()))return false;for(unsigned n=0;n<out.size();++n){auto*v=cJSON_GetArrayItem(a,n);if(!cJSON_IsNumber(v)||!range(v->valuedouble,-1e6,1e6))return false;out[n]=static_cast<float>(v->valuedouble);}return true;};
 return array(cJSON_GetObjectItemCaseSensitive(map,"rpm"),m.rpm)&&array(cJSON_GetObjectItemCaseSensitive(map,"load"),m.load)&&array(cJSON_GetObjectItemCaseSensitive(map,"cells"),m.cells)&&valid(r,maximum_map_kpa);
}
inline bool parse_config(const cJSON*j,Config&c,engine::Map&fuel_map,engine::Map&spark_map,double maximum_map_kpa=110){
 return web::keys(j,"|fuel||spark|")&&parse_rule(cJSON_GetObjectItemCaseSensitive(j,"fuel"),c.fuel,fuel_map,maximum_map_kpa)&&parse_rule(cJSON_GetObjectItemCaseSensitive(j,"spark"),c.spark,spark_map,maximum_map_kpa);
}
inline cJSON* rule_document(const Rule&r,const engine::Map&m,float constant=NAN){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 bool ok=cJSON_AddStringToObject(j,"mode",mode_name(r.mode))&&cJSON_AddStringToObject(j,"source",load::source_name(r.source))&&cJSON_AddStringToObject(j,"axis",load::axis_name(r.axis))&&
  cJSON_AddStringToObject(j,"cells",cells_name(r.cells))&&cJSON_AddStringToObject(j,"condition",condition_name(r.condition))&&cJSON_AddNumberToObject(j,"threshold",r.threshold)&&
  cJSON_AddNumberToObject(j,"debounce_ms",r.debounce_ms)&&cJSON_AddNumberToObject(j,"input_channel",r.input_channel)&&cJSON_AddBoolToObject(j,"active_high",r.active_high);
 auto*map=ok?cJSON_AddObjectToObject(j,"map"):nullptr;if(!map)ok=false;
 auto add=[&](const char*name,const auto&values,bool replace=false){auto*a=cJSON_AddArrayToObject(map,name);if(!a)return false;for(auto v:values){auto*n=cJSON_CreateNumber(replace?constant:v);if(!n||!cJSON_AddItemToArray(a,n)){cJSON_Delete(n);return false;}}return true;};
 ok=ok&&add("rpm",m.rpm)&&add("load",m.load)&&add("cells",m.cells,std::isfinite(constant));
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* config_document(const Config&c,const engine::Map&fuel,const engine::Map&spark){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 auto add=[&](const char*key,const Rule&r,const engine::Map&m){auto*child=rule_document(r,m);if(!child||!cJSON_AddItemToObject(j,key,child)){cJSON_Delete(child);return false;}return true;};
 if(!add("fuel",c.fuel,fuel)||!add("spark",c.spark,spark)){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* default_document(){
 const Config c;static constexpr engine::Map axes{};auto*j=cJSON_CreateObject();if(!j)return nullptr;
 auto add=[&](const char*key,const Rule&r,float cell){auto*child=rule_document(r,axes,cell);if(!child||!cJSON_AddItemToObject(j,key,child)){cJSON_Delete(child);return false;}return true;};
 if(!add("fuel",c.fuel,85)||!add("spark",c.spark,15)){cJSON_Delete(j);return nullptr;}return j;
}
inline const char*cell_unit(Kind k,Cells c){return k==Kind::Spark&&c!=Cells::Multiplier?"deg":c==Cells::Adder?"percentage_points":"%";}
inline bool u64_text(const cJSON*j,const char*key,std::uint64_t&value){
 char text[24]{};if(!web::string(j,key,text)||!text[0]||(text[0]=='0'&&text[1]))return false;
 value=0;for(const char*p=text;*p;++p){if(*p<'0'||*p>'9'||value>(UINT64_MAX-unsigned(*p-'0'))/10)return false;value=value*10+unsigned(*p-'0');}return true;
}
inline cJSON* observation_json(const Observation&raw,Kind kind,bool present=true){
 const Observation empty;const auto&o=present&&raw.available?raw:empty;auto*j=cJSON_CreateObject();if(!j)return nullptr;bool ok=true;
 for(unsigned n=0;ok&&n<12;++n)ok=cJSON_AddBoolToObject(j,boolean_names[n],o.*boolean_members[n])!=nullptr;
 auto code=[&](const char*name,const char*label,unsigned value){char field[40];std::snprintf(field,sizeof(field),"%s_code",name);return cJSON_AddStringToObject(j,name,label)&&cJSON_AddNumberToObject(j,field,value);};
 ok=ok&&code("mode",mode_name(o.mode),static_cast<unsigned>(o.mode))&&code("source",load::source_name(o.source),static_cast<unsigned>(o.source))&&code("axis",load::axis_name(o.axis),static_cast<unsigned>(o.axis))&&
  code("cells",cells_name(o.cells),static_cast<unsigned>(o.cells))&&code("condition",condition_name(o.condition),static_cast<unsigned>(o.condition))&&
  code("reason",reason_name(o.reason),static_cast<unsigned>(o.reason))&&code("input_source",input_source_name(o.input_source),static_cast<unsigned>(o.input_source))&&
  cJSON_AddNumberToObject(j,"input_channel",o.input_channel)&&cJSON_AddNumberToObject(j,"flags",flags(o))&&cJSON_AddStringToObject(j,"cell_unit",cell_unit(kind,o.cells))&&cJSON_AddStringToObject(j,"coordinate_unit",load::axis_unit(o.axis));
 char time[24];std::snprintf(time,sizeof(time),"%llu",static_cast<unsigned long long>(o.input_observed_us));
 ok=ok&&(o.mode==Mode::Input&&o.input_source!=InputSource::Unavailable?cJSON_AddStringToObject(j,"input_observed_us",time)!=nullptr:cJSON_AddNullToObject(j,"input_observed_us")!=nullptr);
 for(unsigned n=0;ok&&n<9;++n){const float v=o.*value_members[n];ok=o.available&&std::isfinite(v)?cJSON_AddNumberToObject(j,value_names[n],v)!=nullptr:cJSON_AddNullToObject(j,value_names[n])!=nullptr;}
 if(!ok){cJSON_Delete(j);return nullptr;}return j;
}
inline cJSON* observations_json(const Observation&fuel,const Observation&spark,bool present=true){
 auto*j=cJSON_CreateObject();if(!j)return nullptr;
 auto add=[&](const char*key,const Observation&o,Kind k){auto*child=observation_json(o,k,present);if(!child||!cJSON_AddItemToObject(j,key,child)){cJSON_Delete(child);return false;}return true;};
 if(!add("fuel",fuel,Kind::Fuel)||!add("spark",spark,Kind::Spark)){cJSON_Delete(j);return nullptr;}return j;
}
inline bool parse_observation(const cJSON*j,Observation&result,Kind kind,bool present){
 if(!web::keys(j,"|available||evaluated||active||clamped||pending||input_qualified||input_level||pending_level||input_valid||input_raw||active_high||valid||mode||mode_code||source||source_code||axis||axis_code||cells||cells_code||condition||condition_code||reason||reason_code||input_source||input_source_code||input_channel||flags||cell_unit||coordinate_unit||input_observed_us||primary||primary_corrected||secondary||combined||coordinate||condition_value||input_age_ms||threshold||debounce_ms|"))return false;
 Observation o;
 for(unsigned n=0;n<12;++n)if(!web::boolean(j,boolean_names[n],o.*boolean_members[n]))return false;
 if(o.available&&!present)return false;
 auto code=[&](const char*name,unsigned maximum,auto&field,auto label){unsigned value;char key[40],text[48];std::snprintf(key,sizeof(key),"%s_code",name);
  if(!web::integer(j,key,value)||value>maximum||!web::string(j,name,text))return false;
  field=static_cast<std::decay_t<decltype(field)>>(value);return !std::strcmp(text,label(field));};
 if(!code("mode",4,o.mode,mode_name)||!code("source",2,o.source,load::source_name)||!code("axis",2,o.axis,load::axis_name)||!code("cells",2,o.cells,cells_name)||
    !code("condition",3,o.condition,condition_name)||!code("reason",17,o.reason,reason_name)||!code("input_source",2,o.input_source,input_source_name))return false;
 unsigned channel,word;char unit[32];
 if(!web::integer(j,"input_channel",channel)||channel>1||!web::integer(j,"flags",word))return false;
 o.input_channel=static_cast<std::uint8_t>(channel);if(word!=flags(o)||!web::string(j,"cell_unit",unit)||std::strcmp(unit,cell_unit(kind,o.cells))||!web::string(j,"coordinate_unit",unit)||std::strcmp(unit,load::axis_unit(o.axis)))return false;
 for(unsigned n=0;n<9;++n){const auto*v=cJSON_GetObjectItemCaseSensitive(j,value_names[n]);
  if(cJSON_IsNull(v))o.*value_members[n]=NAN;
  else if(o.available&&cJSON_IsNumber(v)&&std::isfinite(v->valuedouble)&&std::abs(v->valuedouble)<=std::numeric_limits<float>::max())o.*value_members[n]=static_cast<float>(v->valuedouble);
  else return false;
 }
 const bool input_time=o.mode==Mode::Input&&o.input_source!=InputSource::Unavailable;
 if(input_time){if(!u64_text(j,"input_observed_us",o.input_observed_us))return false;}
 else if(!cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(j,"input_observed_us")))return false;
 if(!o.available){const Observation empty;
  for(unsigned n=0;n<12;++n)if(o.*boolean_members[n]!=empty.*boolean_members[n])return false;
  if(o.mode!=empty.mode||o.cells!=empty.cells||o.source!=empty.source||o.axis!=empty.axis||o.condition!=empty.condition||o.reason!=empty.reason||o.input_source!=empty.input_source||o.input_channel)return false;
 }
 if(o.available&&(!range(o.threshold,0,threshold_max(o.condition,400))||!range(o.debounce_ms,0,500)))return false;
 if(o.evaluated&&(!o.valid||!std::isfinite(o.primary)||!std::isfinite(o.primary_corrected)||!std::isfinite(o.combined)||(o.active&&!std::isfinite(o.secondary))))return false;
 if(o.valid&&o.axis!=static_cast<load::Axis>(o.source))return false;
 if(o.input_qualified&&(!input_time||!o.input_valid||!range(o.input_age_ms,0,20)))return false;
 result=o;return true;
}
inline bool parse_observations(const cJSON*j,Observation&fuel,Observation&spark,bool present){
 return web::keys(j,"|fuel||spark|")&&parse_observation(cJSON_GetObjectItemCaseSensitive(j,"fuel"),fuel,Kind::Fuel,present)&&parse_observation(cJSON_GetObjectItemCaseSensitive(j,"spark"),spark,Kind::Spark,present);
}
// Synthetic host test/plant intake. Target provenance cannot be supplied here.
inline bool parse_synthetic_inputs(const cJSON*j,engine::Inputs&in){
 if(cJSON_GetObjectItemCaseSensitive(j,"ethanol_qualified")&&!web::boolean(j,"ethanol_qualified",in.ethanol_qualified))return false;
 if(const auto*v=cJSON_GetObjectItemCaseSensitive(j,"ethanol_pct")){if(!cJSON_IsNull(v)&&!web::number(j,"ethanol_pct",in.ethanol_pct))return false;}
 const auto*a=cJSON_GetObjectItemCaseSensitive(j,"table_switches");if(!a)return true;
 if(!cJSON_IsArray(a)||cJSON_GetArraySize(a)!=2)return false;
 for(unsigned n=0;n<2;++n){const auto*v=cJSON_GetArrayItem(a,n);auto&s=in.table_switches[n];
  if(!web::keys(v,"|valid||level||observed_us|")||!web::boolean(v,"valid",s.valid)||!web::boolean(v,"level",s.level)||!u64_text(v,"observed_us",s.observed_us))return false;
  s.source=InputSource::Synthetic;
 }
 return true;
}
} // namespace ecu::secondary
