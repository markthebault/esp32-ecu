#define main json_probe_unused_main
#include "kernel-json-003.cpp"
#undef main
int main(){auto e=evaluation();const auto s=e.sample;flex::Config off;auto raw=flex::assess(off,s,s.observation.sample_us+1,true,s.tune_revision);auto value=flex::assess(off,flex::synthetic_value(50,true,1000000,off.capture,1),1000000,true,1);
 for(unsigned n=0;n<4;++n){auto x=n==3?value:n==2?e:raw;auto*j=flex::evaluation_json(flex::expand(flex::record(x)));const char*name="";
  switch(n){case 0:name="source2_value_qualified_without_raw";cJSON_ReplaceItemInObject(j,"raw_capture_qualified",cJSON_CreateFalse());break;
   case 1:name="target_qualified_unconfirmed";cJSON_ReplaceItemInObject(j,"source",cJSON_CreateString("target_capture"));number(j,"source_code",1);break;
   case 2:name="enabled_but_not_required";cJSON_ReplaceItemInObject(j,"required",cJSON_CreateFalse());break;
   case 3:name="value_only_tagged_ready";cJSON_ReplaceItemInObject(j,"reason",cJSON_CreateString("ready"));number(j,"reason_code",2);break;}
  flex::Record parsed;const bool accepted=flex::parse_record(j,parsed,true);std::cout<<name<<" accepted="<<accepted<<'\n';cJSON_Delete(j);if(accepted){return 2;}
 }
}
