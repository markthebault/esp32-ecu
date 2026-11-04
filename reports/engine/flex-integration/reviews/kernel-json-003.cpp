#include "ecu/engine_json.hpp"
#include "ecu/flex_runtime_json.hpp"
#include <fstream>
#include <sstream>
#include <iostream>
#include <stdexcept>
using namespace ecu;
static unsigned checks=0;
static void ck(bool b,const char*m){++checks;if(!b)throw std::runtime_error(m);}
static cJSON* load_fixture(const std::string&p){std::ifstream f(p);std::stringstream s;s<<f.rdbuf();return cJSON_Parse(s.str().c_str());}
static cJSON* clone(const cJSON*j){return cJSON_Duplicate(j,true);}
static void number(cJSON*j,const char*k,double v){auto*x=cJSON_GetObjectItemCaseSensitive(j,k);ck(x!=nullptr,"mutation key exists");cJSON_SetNumberValue(x,v);}
static flex::Evaluation evaluation(){flex::Config c;c.correction.enabled=c.correction.temperature_enabled=true;const auto end=UINT64_MAX-100000;flex::Capture capture(c.capture);capture.edge(end-80000,true);for(unsigned n=1;n<=8;++n){capture.edge(end-80000+n*10000-3000,false);capture.edge(end-80000+n*10000,true);}flex::Sample s{capture.observe(end),c.capture,UINT32_MAX};s.observation.edges=UINT64_MAX;s.observation.fault_generation=s.observation.acknowledged_generation=UINT64_MAX-1;s.observation.config_epoch=UINT64_MAX;auto e=flex::assess(c,s,end+1,false,UINT32_MAX);ck(e.control_ok&&e.raw_qualified,"wide valid evaluation");return e;}
int main(int argc,char**argv){try{ck(argc==2,"fixtures argument");const std::string dir=argv[1];
 for(unsigned n=1;n<=8;++n){auto*j=load_fixture(dir+"/v"+std::to_string(n)+".json");ck(j!=nullptr,"load legacy");engine::Tune t;t.flex_fuel.correction.enabled=t.flex_fuel.correction.temperature_enabled=t.flex_fuel.input_confirmed=true;t.flex_fuel.correction.fuel_pct.fill(200);t.flex_fuel.capture.cycles=2;
  ck(engine::parse_tune(j,t),"legacy parse");const flex::Config neutral;ck(!t.flex_fuel.correction.enabled&&!t.flex_fuel.correction.temperature_enabled&&!t.flex_fuel.input_confirmed&&flex::same(t.flex_fuel.capture,neutral.capture)&&t.flex_fuel.correction.fuel_pct==neutral.correction.fuel_pct&&t.flex_fuel.correction.spark_deg==neutral.correction.spark_deg,"reused Tune neutral migration");
  auto*before=n==8?clone(cJSON_GetObjectItemCaseSensitive(j,"secondary_tables")):nullptr;ck(engine::upgrade_tune_document(j),"upgrade legacy");ck(cJSON_GetObjectItemCaseSensitive(j,"schema_version")->valuedouble==9,"schema9 canonical");engine::Tune canonical;ck(engine::parse_tune(j,canonical),"reparse canonical");ck(!canonical.flex_fuel.correction.enabled,"canonical disabled");
  if(n==8){ck(cJSON_Compare(before,cJSON_GetObjectItemCaseSensitive(j,"secondary_tables"),true),"schema8 secondary preserved");ck(canonical.secondary_tables.fuel.mode==secondary::Mode::Multiply&&canonical.secondary_ve.cells[0]==109,"secondary values retained");cJSON_Delete(before);}
  ck(engine::upgrade_tune_document(j),"upgrade idempotent");cJSON_Delete(j);
 }
 auto*j=load_fixture(dir+"/v8.json");number(j,"schema_version",9);engine::Tune t;ck(!engine::parse_tune(j,t),"schema9 missing flex rejects");auto*cfg=flex::config_document(flex::Config{});ck(cfg&&cJSON_AddItemToObject(j,"flex_fuel",cfg),"add full config");ck(engine::parse_tune(j,t),"schema9 full flex accepts");
 for(unsigned mutation=0;mutation<5;++mutation){auto*x=clone(j);auto*f=cJSON_GetObjectItemCaseSensitive(x,"flex_fuel");auto*c=cJSON_GetObjectItemCaseSensitive(f,"capture");auto*r=cJSON_GetObjectItemCaseSensitive(f,"correction");switch(mutation){case 0:cJSON_AddBoolToObject(f,"unknown",true);break;case 1:number(c,"cycles",2.5);break;case 2:cJSON_ReplaceItemInObject(r,"enabled",cJSON_CreateNumber(1));break;case 3:cJSON_ReplaceItemInArray(cJSON_GetObjectItemCaseSensitive(r,"fuel_pct"),0,cJSON_CreateNumber(NAN));break;case 4:cJSON_DeleteItemFromObject(f,"input_confirmed");break;}engine::Tune bad;ck(!engine::parse_tune(x,bad),"malformed config rejects");cJSON_Delete(x);}cJSON_Delete(j);
 const auto e=evaluation();const auto rec=flex::record(e);const auto ex=flex::expand(rec);ck(rec.times==std::array<std::uint64_t,7>{e.sample.observation.sample_us,e.sample.observation.window_start_us,e.sample.observation.last_edge_us,UINT64_MAX,UINT64_MAX-1,UINT64_MAX-1,UINT64_MAX},"record U64 preserves all counters");j=flex::evaluation_json(ex);ck(j!=nullptr,"record JSON builds");flex::Record parsed;ck(flex::parse_record(j,parsed,true),"valid record parser accepts");ck(parsed.times==rec.times&&parsed.flags==rec.flags&&parsed.revision==rec.revision,"JSON roundtrip preserves U64 flags revision");
 for(unsigned mutation=0;mutation<7;++mutation){auto*x=clone(j);switch(mutation){case 0:cJSON_ReplaceItemInObject(x,"sample_us",cJSON_CreateNumber(9007199254740992.));break;case 1:cJSON_ReplaceItemInObject(x,"sample_us",cJSON_CreateString("18446744073709551616"));break;case 2:cJSON_ReplaceItemInObject(x,"raw_edges",cJSON_CreateString("00"));break;case 3:number(x,"source_code",99);break;case 4:cJSON_ReplaceItemInObject(x,"pending_fault",cJSON_CreateTrue());break;case 5:number(x,"configuration_revision",0);break;case 6:cJSON_ReplaceItemInObject(x,"raw_capture_qualified",cJSON_CreateFalse());break;}
  flex::Record bad;const bool accepted=flex::parse_record(x,bad,true);if(mutation==6)std::cout<<"source2_value_qualified_without_raw_qualified_accepted "<<accepted<<'\n';else ck(!accepted,"malformed runtime record rejects");cJSON_Delete(x);
 }
 cJSON_Delete(j);flex::Record empty;j=flex::evaluation_json(flex::expand(empty));ck(j&&flex::parse_record(j,parsed,false),"empty record roundtrip");cJSON_Delete(j);
 flex::Config off;const auto value=flex::synthetic_value(50,true,1000000,off.capture,7);const auto ve=flex::assess(off,value,1000000,true,7);ck(ve.control_ok&&ve.value_qualified&&!ve.raw_qualified,"synthetic value semantics");j=flex::evaluation_json(flex::expand(flex::record(ve)));ck(j&&flex::parse_record(j,parsed,true),"value-only record roundtrip");cJSON_Delete(j);
 std::cout<<"kernel_json_checks "<<checks<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"failure after "<<checks<<": "<<e.what()<<'\n';return 1;}}
