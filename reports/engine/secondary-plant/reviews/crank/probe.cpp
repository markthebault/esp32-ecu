#include "ecu/secondary_json.hpp"
#include <iostream>
#include <string>
#include <vector>
#include <limits>
namespace s=ecu::secondary;
namespace e=ecu::engine;
static cJSON* checks=cJSON_CreateArray();
static cJSON* observations=cJSON_CreateArray();
static unsigned count=0,failures=0,roundtrips=0;
static std::string case_name;
static void check(bool ok,const std::string& name){
 ++count;failures+=!ok;
 auto*j=cJSON_CreateObject();cJSON_AddStringToObject(j,"case",case_name.c_str());cJSON_AddStringToObject(j,"check",name.c_str());cJSON_AddBoolToObject(j,"passed",ok);cJSON_AddItemToArray(checks,j);
}
static void observe(const s::Observation&o,s::Kind kind,std::uint64_t now,bool cranking){
 auto*j=s::observation_json(o,kind);s::Observation parsed;
 ++roundtrips;const bool parsed_ok=j&&s::parse_observation(j,parsed,kind,true);check(case_name=="invalid_rule_not_bypassed"?!parsed_ok:parsed_ok,case_name=="invalid_rule_not_bypassed"?"native_json_rejects_invalid_rule_metadata":"native_json_roundtrip");
 auto*row=cJSON_CreateObject();cJSON_AddStringToObject(row,"case",case_name.c_str());cJSON_AddNumberToObject(row,"now_us",double(now));cJSON_AddStringToObject(row,"kind",kind==s::Kind::Spark?"spark":"fuel");cJSON_AddBoolToObject(row,"cranking",cranking);cJSON_AddItemToObject(row,"observation",j);cJSON_AddItemToArray(observations,row);
}
static s::Rule rule(){s::Rule r;r.mode=s::Mode::Input;r.cells=s::Cells::Absolute;r.debounce_ms=20;return r;}
static s::Input input(){s::Input i;i.rpm=220;i.map_kpa=40;i.tps_pct=25;i.emap_kpa=125;i.ethanol_pct=50;i.map_qualified=i.emap_qualified=i.ethanol_qualified=true;return i;}
static s::SwitchSample sample(std::uint64_t time,bool level=true,s::InputSource src=s::InputSource::Synthetic){return {time,src,level,true};}
static s::Selection select(s::Controller&c,s::Rule&r,s::Input&i,std::uint64_t now,bool crank,s::Kind k=s::Kind::Spark){
 auto q=c.select(k,r,i,now,crank);observe(q.observation,k,now,crank);return q;
}
static void bypass(const s::Selection&q){check(q.ok&&q.observation.valid&&!q.observation.active&&q.observation.reason==s::Reason::CrankingBypass,"cranking_valid_inactive_bypass");}
static void prime(s::Controller&c,s::Rule&r,s::Input&i,bool crank=true,std::uint64_t first=1000000,bool level=true,s::InputSource src=s::InputSource::Synthetic){
 for(unsigned n=0;n<3;++n){auto t=first+n*10000;i.switches[r.input_channel]=sample(t,level,src);auto q=select(c,r,i,t,crank);if(crank)bypass(q);}
}
static void configured_modes(){
 for(unsigned n=0;n<5;++n){case_name="bypass_mode_"+std::to_string(n);s::Controller c;auto r=rule();r.mode=s::Mode(n);r.cells=s::expected_cells(r.mode);auto i=input();i.map_qualified=false;i.map_kpa=NAN;i.tps_pct=NAN;
 auto q=select(c,r,i,1000000,true);if(n)bypass(q);else check(q.ok&&!q.observation.active&&q.observation.reason==s::Reason::Disabled,"off_unchanged");}
 case_name="invalid_rule_not_bypassed";s::Controller c;auto r=rule();r.debounce_ms=501;auto i=input();auto q=select(c,r,i,1000000,true);check(!q.ok&&q.observation.reason==s::Reason::InvalidConfig,"bad_rule_rejected");
}
static void stable_prequalification(){
 for(auto src:{s::InputSource::Synthetic,s::InputSource::TargetProtected})for(bool high:{false,true})for(bool level:{false,true})for(float debounce:{0.f,.001f,20.f,500.f}){
  case_name="stable_"+std::to_string(unsigned(src))+"_"+std::to_string(high)+"_"+std::to_string(level)+"_"+std::to_string(debounce);
  auto r=rule();r.active_high=high;r.debounce_ms=debounce;auto i=input();s::Controller c;const std::uint64_t first=1000000,period=std::uint64_t(std::llround(double(debounce)*1000));
  std::uint64_t elapsed=0;
  while(true){const auto t=first+elapsed;i.switches[0]=sample(t,level,src);const auto q=select(c,r,i,t,true);bypass(q);check(q.observation.input_source==src&&q.observation.input_raw==level&&q.observation.input_valid&&q.observation.input_observed_us==t&&q.observation.input_age_ms==0,"cranking_actual_input_diagnostics");check(q.observation.input_qualified==(elapsed>=period),"qualification_exact_observed_interval");if(elapsed==period)break;elapsed=std::min(period,elapsed+10000);}
  const auto q=select(c,r,i,first+period,false);check(q.ok&&q.observation.active==(level==high)&&q.observation.input_qualified&&!q.observation.pending,"run_no_new_qualification_delay");
 }
}
static void held_and_age(){
 case_name="held_sample_cannot_qualify";s::Controller c;auto r=rule();auto i=input();i.switches[0]=sample(1000000);bypass(select(c,r,i,1000000,true));bypass(select(c,r,i,1020000,true));auto q=select(c,r,i,1020000,false);check(!q.ok&&q.observation.reason==s::Reason::Debouncing,"held20ms_still_unqualified");
 case_name="freshness_inclusive20ms";c.reset();prime(c,r,i);q=select(c,r,i,1040000,true);bypass(q);check(q.observation.input_qualified&&q.observation.input_age_ms==20,"exact20ms_qualified");q=select(c,r,i,1040000,false);check(q.ok&&q.observation.active,"exact20ms_run_qualified");
 case_name="stale20ms_plus1";q=select(c,r,i,1040001,true);bypass(q);check(!q.observation.input_qualified&&q.observation.input_age_ms>20,"stale_bypass_resets_qualifier");q=select(c,r,i,1040001,false);check(!q.ok&&q.observation.reason==s::Reason::InputStale,"stale_run_inhibits");
 case_name="gap20ms_plus1_fresh";c.reset();prime(c,r,i);i.switches[0]=sample(1040001);q=select(c,r,i,1040001,true);bypass(q);check(!q.observation.input_qualified,"observation_gap_resets");q=select(c,r,i,1040001,false);check(!q.ok,"gap_run_inhibits");i.switches[0]=sample(1060001);q=select(c,r,i,1060001,false);check(q.ok,"gap_requalifies_after20ms");
}
static void invalid_prequalification(){
 for(unsigned fault=0;fault<7;++fault){
  case_name="crank_fault_"+std::to_string(fault);s::Controller c;auto r=rule();auto i=input();prime(c,r,i);std::uint64_t t=1025000;i.switches[0]=sample(t,false);
  if(fault==0)i.switches[0].valid=false;
  if(fault==1)i.switches[0].source=s::InputSource::Unavailable;
  if(fault==2)i.switches[0].observed_us=t+1;
  if(fault==3)i.switches[0].observed_us=t-20001;
  if(fault==4)i.switches[0].observed_us=1019999;
  if(fault==5)i.switches[0].observed_us=1020000;
  if(fault==6){t=1019999;i.switches[0].observed_us=t;}
  auto q=select(c,r,i,t,true);bypass(q);check(!q.observation.input_qualified,"invalid_during_crank_resets");check(q.observation.input_raw==i.switches[0].level&&q.observation.input_observed_us==i.switches[0].observed_us&&q.observation.input_valid==i.switches[0].valid&&q.observation.input_source==i.switches[0].source,"invalid_raw_diagnostics_retained");
  i.switches[0]=sample(1030000);q=select(c,r,i,1030000,false);check(!q.ok&&q.observation.reason==s::Reason::Debouncing,"fresh_run_requires_new_qualification");i.switches[0]=sample(1040000);q=select(c,r,i,1040000,false);check(!q.ok,"new10ms_insufficient");i.switches[0]=sample(1050000);q=select(c,r,i,1050000,false);check(q.ok&&q.observation.active,"new20ms_recovers");
 }
}
static void source_rule_transitions(){
 for(unsigned edit=0;edit<5;++edit){case_name="crank_rule_or_source_change_"+std::to_string(edit);s::Controller c;auto r=rule();auto i=input();prime(c,r,i);
  if(edit==0)i.switches[0]=sample(1025000,true,s::InputSource::TargetProtected);
  if(edit==1){r.input_channel=1;i.switches[1]=sample(1025000);}
  if(edit==2){r.active_high=false;i.switches[0]=sample(1025000);}
  if(edit==3){r.debounce_ms=10;i.switches[0]=sample(1025000);}
  if(edit==4){r.threshold=3001;i.switches[0]=sample(1025000);}
  auto q=select(c,r,i,1025000,true);bypass(q);check(!q.observation.input_qualified,"source_or_rule_change_resets");q=select(c,r,i,1025000,false);check(!q.ok,"changed_run_no_leaked_qualification");
  i.switches[r.input_channel].observed_us=1025000+std::uint64_t(std::llround(r.debounce_ms*1000));q=select(c,r,i,i.switches[r.input_channel].observed_us,false);check(q.ok&&q.observation.active==r.active_high,"changed_run_own_interval");
 }
}
static void bounce_reentry(){
 case_name="qualified_pending_across_crank_run";s::Controller c;auto r=rule();auto i=input();prime(c,r,i,false);i.switches[0]=sample(1025000,false);auto q=select(c,r,i,1025000,true);bypass(q);check(q.observation.input_qualified&&q.observation.input_level&&q.observation.pending&&!q.observation.pending_level,"crank_pending_holds_qualified_level");i.switches[0]=sample(1030000,false);q=select(c,r,i,1030000,false);check(q.ok&&q.observation.active&&q.observation.pending,"run_pending_preserves_existing_debounce");i.switches[0]=sample(1045000,false);q=select(c,r,i,1045000,false);check(q.ok&&!q.observation.active&&!q.observation.pending,"pending_switch_after20ms");
 case_name="initial_bounce_across_crank_run";c.reset();i.switches[0]=sample(1000000);bypass(select(c,r,i,1000000,true));i.switches[0]=sample(1010000,false);bypass(select(c,r,i,1010000,true));i.switches[0]=sample(1020000);q=select(c,r,i,1020000,true);bypass(q);check(!q.observation.input_qualified,"initial_bounce_unqualified");i.switches[0]=sample(1030000);q=select(c,r,i,1030000,false);check(!q.ok,"initial_bounce_run_inhibits");i.switches[0]=sample(1040000);q=select(c,r,i,1040000,false);check(q.ok&&q.observation.active,"initial_bounce_final20ms_qualifies");
 case_name="off_transition_discards_qualification";auto off=r;off.mode=s::Mode::Off;q=select(c,off,i,1040000,true);check(q.ok&&q.observation.reason==s::Reason::Disabled&&!q.observation.input_qualified&&q.observation.input_source==s::InputSource::Unavailable,"off_canonical_diagnostics");i.switches[0]=sample(1045000);q=select(c,r,i,1045000,false);check(!q.ok,"off_to_input_fresh_interval");
}
static void independent_channels(){
 for(bool shared:{false,true}){case_name=shared?"shared_channel_independent_rules":"different_channel_independent_rules";s::Controller c;auto fuel=rule(),spark=rule();spark.input_channel=shared?0:1;fuel.debounce_ms=10;spark.active_high=false;auto i=input();
 for(unsigned n=0;n<3;++n){auto t=1000000+n*10000;i.switches[0]=sample(t);i.switches[1]=sample(t,false);const auto f=select(c,fuel,i,t,true,s::Kind::Fuel),p=select(c,spark,i,t,true);bypass(p);check(f.ok==(n>=1),"fuel_independent_interval");check(p.observation.input_qualified==(n>=2),"spark_qualifies_independently_during_crank");}
 const auto f=select(c,fuel,i,1020000,false,s::Kind::Fuel),p=select(c,spark,i,1020000,false);check(f.ok&&f.observation.active&&p.ok&&p.observation.active==!shared,"independent_run_polarity");
 }
}
static e::Tune tune(){e::Tune t;t.ve.cells.fill(80);t.spark.cells.fill(20);t.secondary_spark.cells.fill(14);t.injector_cc_min=600;t.afterstart_pct=0;t.ego_enabled=t.dfco_enabled=false;t.transient_enrichment.mode=ecu::transient::Mode::Off;t.secondary_tables.spark=rule();return t;}
static e::Inputs engine_input(std::uint64_t now,double rpm=220){e::Inputs i;i.rpm=rpm;i.map_kpa=40;i.tps_pct=25;i.clt_c=85;i.iat_c=25;i.lambda=1;i.battery_v=14;i.sensor_v=5;i.synced=i.phase_synced=i.sensors_valid=i.lambda_ready=true;i.sampled_us=now;i.table_switches[0]=sample(now);return i;}
static e::Output engine_step(e::Controller&c,const e::Tune&t,e::Inputs&i){auto o=c.step(t,i,i.sampled_us);observe(o.secondary_spark,s::Kind::Spark,i.sampled_us,o.secondary_spark.reason==s::Reason::CrankingBypass);return o;}
static void engine_transition(){
 case_name="actual_engine_hysteresis_reentry";auto t=tune();check(!e::validate(t),"tune_valid");e::Controller c;
 for(unsigned n=0;n<6;++n){auto i=engine_input(1000000+n*5000);const auto o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Cranking&&o.advance_deg==t.crank_advance_deg&&!o.secondary_spark.active,"cranking_primary_angle_no_new_dependency");}
 auto i=engine_input(1030000,550);auto o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Running&&o.advance_deg==14&&o.secondary_spark.active,"crank_to_run_no_whole_controller_cut");i=engine_input(1035000,449);o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Cranking&&o.advance_deg==t.crank_advance_deg,"running_to_cranking_primary_angle");i=engine_input(1040000,500);o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Cranking,"crank_hysteresis_stays_cranking");i=engine_input(1045000,550);o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Running&&o.advance_deg==14,"qualified_reentry_no_cut");
 case_name="actual_engine_missing_input_during_crank";c.reset();for(unsigned n=0;n<6;++n){i=engine_input(1000000+n*5000);i.table_switches={};o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Cranking&&o.advance_deg==t.crank_advance_deg,"missing_switch_cranking_bypass");}i=engine_input(1030000,550);i.table_switches={};o=engine_step(c,t,i);check(bool(o.faults&e::BadSensor)&&o.fuel_cut&&o.spark_cut&&o.secondary_spark.reason==s::Reason::InputUnavailable,"missing_switch_run_full_cut");
 case_name="actual_engine_static_sensor_dependency";c.reset();i=engine_input(1000000);i.map_qualified=false;i.map_kpa=NAN;o=engine_step(c,t,i);check(bool(o.faults&e::BadSensor)&&o.fuel_cut&&o.spark_cut,"static_map_requirement_remains");
 case_name="actual_engine_invalid_resets_before_reentry";c.reset();for(unsigned n=0;n<6;++n){i=engine_input(1000000+n*5000);o=engine_step(c,t,i);}i=engine_input(1030000);i.table_switches[0].valid=false;o=engine_step(c,t,i);check(!o.faults&&o.state==e::State::Cranking&&!o.secondary_spark.input_qualified,"invalid_cranking_still_bypass");i=engine_input(1035000,550);o=engine_step(c,t,i);check(bool(o.faults&e::BadSensor)&&o.fuel_cut&&o.spark_cut,"invalid_reentry_no_cached_qualification");
}

static void simultaneous_coordinate_faults(){
 for(auto kind:{s::Kind::Fuel,s::Kind::Spark})for(unsigned source=0;source<3;++source)for(unsigned fault=0;fault<4;++fault){
  case_name="simultaneous_coordinate_fault_"+std::to_string(unsigned(kind))+"_"+std::to_string(source)+"_"+std::to_string(fault);
  s::Controller c;auto r=rule();r.source=ecu::load::Source(source);r.axis=ecu::load::Axis(source);auto i=input();
  for(unsigned n=0;n<3;++n){const auto now=1000000+n*10000;i.switches[0]=sample(now);const auto q=select(c,r,i,now,kind==s::Kind::Spark,kind);if(kind==s::Kind::Spark)bypass(q);}
  const auto expected=source==0?s::Reason::RequiredMap:source==1?s::Reason::RequiredTps:s::Reason::RequiredEmap;
  if(source==0)i.map_qualified=false;else if(source==1)i.tps_pct=NAN;else i.emap_qualified=false;
  i.switches[0]=sample(1025000);
  if(fault==0)i.switches[0].valid=false;else if(fault==1)i.switches[0].source=s::InputSource::Unavailable;else if(fault==2)i.switches[0].observed_us=1025001;else i.switches[0].observed_us=1004999;
  auto q=select(c,r,i,1025000,false,kind);check(!q.ok&&q.observation.reason==expected,"coordinate_reason_precedence");check(!q.observation.input_qualified,"simultaneous_invalid_input_resets");
  i=input();i.switches[0]=sample(1030000);q=select(c,r,i,1030000,false,kind);check(!q.ok&&q.observation.reason==s::Reason::Debouncing,"coordinate_recovery_requires_new_switch_interval");i.switches[0]=sample(1050000);q=select(c,r,i,1050000,false,kind);check(q.ok&&q.observation.active,"simultaneous_fault_recovers_after20ms");
 }
}
static void exact_u64_observation_time(){
 case_name="exact_u64_observation_time";s::Controller c;auto r=rule();auto i=input();const auto first=UINT64_MAX-30000;
 for(unsigned n=0;n<3;++n){const auto now=first+n*10000;i.switches[0]=sample(now);const auto q=select(c,r,i,now,true);bypass(q);check(q.observation.input_observed_us==now,"exact_u64_native_time");}
 const auto q=select(c,r,i,UINT64_MAX-10000,false);check(q.ok&&q.observation.active,"u64_qualified_run");
}

int main(){simultaneous_coordinate_faults();exact_u64_observation_time();configured_modes();stable_prequalification();held_and_age();invalid_prequalification();source_rule_transitions();bounce_reentry();independent_channels();engine_transition();auto*root=cJSON_CreateObject();cJSON_AddBoolToObject(root,"passed",!failures);cJSON_AddNumberToObject(root,"checks",count);cJSON_AddNumberToObject(root,"failures",failures);cJSON_AddNumberToObject(root,"native_roundtrips",roundtrips);cJSON_AddItemToObject(root,"results",checks);cJSON_AddItemToObject(root,"observations",observations);char*text=cJSON_PrintUnformatted(root);std::cout<<text<<'\n';cJSON_free(text);cJSON_Delete(root);return failures?1:0;}
