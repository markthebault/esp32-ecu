#include "ecu/engine.hpp"
#include "ecu/engine_json.hpp"
#include "ecu/tuning_layout.hpp"
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
namespace sec=ecu::secondary;
namespace eng=ecu::engine;
static unsigned checks=0,failures=0;
static void check(bool okay,const char* name){++checks;if(!okay){++failures;std::cout<<"FAIL,"<<name<<'\n';}}
static bool close(double a,double b){return std::isfinite(a)&&std::abs(a-b)<1e-9;}
static sec::Input sample(){sec::Input i;i.rpm=2000;i.map_kpa=60;i.map_qualified=true;i.tps_pct=50;i.emap_kpa=125;i.emap_qualified=true;i.ethanol_pct=50;i.ethanol_qualified=true;return i;}
static sec::Rule rule(sec::Mode mode=sec::Mode::Input){sec::Rule r;r.mode=mode;r.cells=sec::expected_cells(mode);return r;}
static sec::SwitchSample sw(std::uint64_t time,bool level=true,sec::InputSource source=sec::InputSource::Synthetic){sec::SwitchSample s;s.valid=true;s.level=level;s.observed_us=time;s.source=source;return s;}
static eng::Inputs inputs(){eng::Inputs i;i.rpm=2000;i.map_kpa=60;i.tps_pct=50;i.clt_c=85;i.iat_c=25;i.lambda=1;i.battery_v=14;i.sensor_v=5;i.synced=i.sensors_valid=i.lambda_ready=i.phase_synced=true;i.aux_pressure_kpa=125;i.aux_pressure_qualified=true;i.ethanol_pct=50;i.ethanol_qualified=true;return i;}
static void source(eng::Map&m,sec::Rule&r,unsigned n){r.source=ecu::load::Source(n);r.axis=ecu::load::Axis(n);for(unsigned j=0;j<16;++j)m.load[j]=n==0?10+j*6.f:n==1?j*100.f/15:10+j*30.f;}
static eng::Tune tune(){eng::Tune t;t.afterstart_pct=0;t.ego_enabled=t.dfco_enabled=false;t.transient_enrichment.mode=ecu::transient::Mode::Off;t.injector_cc_min=1500;t.displacement_cc=500;t.ve.cells.fill(40);t.spark.cells.fill(20);return t;}
static double bounded(double v){return std::clamp(v,-5.,40.);}

static void switch_probe(){
 for(bool level:{false,true})for(bool polarity:{false,true}){
  auto r=rule();r.active_high=polarity;auto i=sample();sec::Controller c;
  for(unsigned n=0;n<5;++n){i.switches[0]=sw(n*5000,level);auto a=c.select(sec::Kind::Fuel,r,i,n*5000,false);check(a.ok==(n==4),"initial debounce boundary");if(n==4)check(a.observation.active==(level==polarity),"polarity");}
 }
 auto r=rule();sec::SwitchFilter f;auto a=f.step(sw(0),r,0);check(!a.valid,"initial not qualified");
 a=f.step(sw(0),r,20000);check(!a.valid,"held timestamp not qualification");
 a=f.step(sw(20000),r,20000);check(a.valid&&a.level,"20ms observed qualifies");
 a=f.step(sw(25000,false),r,25000);check(a.valid&&a.level&&a.pending&&!a.pending_level,"transition holds old state");
 a=f.step(sw(44000,false),r,44000);check(a.valid&&a.level&&a.pending,"19ms transition pending");
 a=f.step(sw(45000,false),r,45000);check(a.valid&&!a.level&&!a.pending,"20ms transition takes effect");
 a=f.step(sw(45000,false),r,65000);check(a.valid&&!a.level,"max20ms read age valid");
 a=f.step(sw(45000,false),r,65001);check(!a.valid&&a.reason==sec::Reason::InputStale,"over20ms stale invalidates");
 a=f.step(sw(65002,false),r,65002);check(!a.valid,"fresh read must requalify");
 a=f.step(sw(85002,false),r,85002);check(a.valid&&!a.level,"requalified");
 a=f.step(sw(106003,false),r,106003);check(!a.valid,"unobserved21ms gap invalidates");
 a=f.step(sw(126003,false),r,126003);check(a.valid,"gap reacquired");
 a=f.step(sw(126002,false),r,126004);check(!a.valid&&a.reason==sec::Reason::InputTimeReversed,"reversed sample invalidates");
 f.reset();a=f.step(sw(100000),r,99999);check(!a.valid&&a.reason==sec::Reason::InputTimeReversed,"future invalidates");
 a=f.step(sw(100000),r,100000);a=f.step(sw(120000),r,120000);check(a.valid,"recover future");
 a=f.step(sw(120000,false),r,120001);check(!a.valid&&a.reason==sec::Reason::InputTimeReversed,"contradictory same timestamp");
 f.reset();a=f.step(sw(100000),r,100000);a=f.step(sw(120000),r,120000);a=f.step(sw(115000),r,115000);check(!a.valid,"reversed control clock invalidates");
 f.reset();a=f.step(sw(100000),r,100000);a=f.step(sw(120000),r,120000);r.input_channel=1;a=f.step(sw(125000),r,125000);check(!a.valid,"channel change requalifies");
 r.input_channel=0;f.reset();a=f.step(sw(100000),r,100000);a=f.step(sw(120000),r,120000);r.debounce_ms=25;a=f.step(sw(125000),r,125000);check(!a.valid,"debounce change requalifies");
 r=rule();f.reset();a=f.step(sw(100000),r,100000);a=f.step(sw(120000),r,120000);a=f.step(sw(125000,true,sec::InputSource::TargetProtected),r,125000);check(!a.valid,"source domain change requalifies");
 r.debounce_ms=0;f.reset();a=f.step(sw(0),r,0);check(a.valid&&a.level,"zero debounce observed immediately");
 for(unsigned mode=0;mode<5;++mode){auto q=rule(sec::Mode(mode));auto i=sample();sec::Controller c;i.switches[0]=sw(0);auto b=c.select(sec::Kind::Spark,q,i,0,true);check(b.ok&&!b.observation.active,"cranking all spark modes bypass");}
 // UINT64 boundary calculations must use subtraction and remain defined.
 r=rule();f.reset();constexpr auto top=std::numeric_limits<std::uint64_t>::max();
 a=f.step(sw(top-20000),r,top-20000);a=f.step(sw(top),r,top);check(a.valid,"clock maximum qualification");
 a=f.step(sw(0),r,0);check(!a.valid&&a.reason==sec::Reason::InputTimeReversed,"clock wrap invalidates");
}

static void source_condition_probe(){
 for(unsigned kind=0;kind<2;++kind)for(unsigned s=0;s<3;++s)for(unsigned cond=0;cond<4;++cond){
  auto r=rule(sec::Mode::Conditional);r.source=ecu::load::Source(s);r.axis=ecu::load::Axis(s);r.condition=sec::Condition(cond);
  const double threshold=cond==0?2000:cond==1?60:50;r.threshold=threshold;
  for(int sign=-1;sign<=1;++sign){auto i=sample();if(cond==0)i.rpm=threshold+sign*.5;else if(cond==1)i.map_kpa=threshold+sign*.5;else if(cond==2)i.tps_pct=threshold+sign*.5;else i.ethanol_pct=threshold+sign*.5;
   sec::Controller c;auto a=c.select(sec::Kind(kind),r,i,0,false);check(a.ok&&a.observation.active==(sign>0),"strict physical conditional threshold");
   const double expected=s==0?i.map_kpa:s==1?i.tps_pct:100*i.map_kpa/i.emap_kpa;check(close(a.coordinate,expected),"independent secondary coordinate");
  }
 }
 for(unsigned mode=1;mode<5;++mode){
  auto r=rule(sec::Mode(mode));auto i=sample();sec::Controller c;
  i.map_qualified=false;auto a=c.select(sec::Kind::Fuel,r,i,0,false);check(!a.ok&&a.observation.reason==sec::Reason::RequiredMap,"configured map missing fails closed");
  r.source=ecu::load::Source::Tps;r.axis=ecu::load::Axis::TpsPercent;i.map_qualified=true;i.tps_pct=NAN;a=c.select(sec::Kind::Fuel,r,i,0,false);check(!a.ok,"configured tps nan fails closed");
  r.source=ecu::load::Source::PressureRatio;r.axis=ecu::load::Axis::PressureRatioPercent;i.tps_pct=50;i.emap_qualified=false;a=c.select(sec::Kind::Fuel,r,i,0,false);check(!a.ok&&a.observation.reason==sec::Reason::RequiredEmap,"ratio requires emap");
 }
 for(unsigned cond=0;cond<4;++cond){auto r=rule(sec::Mode::Conditional);r.condition=sec::Condition(cond);r.threshold=cond==0?2000:50;r.source=ecu::load::Source::Tps;r.axis=ecu::load::Axis::TpsPercent;auto i=sample();sec::Controller c;
  if(cond==0)i.rpm=NAN;else if(cond==1)i.map_qualified=false;else if(cond==2)i.tps_pct=NAN;else i.ethanol_qualified=false;
  const auto a=c.select(sec::Kind::Fuel,r,i,0,false);check(!a.ok&&!a.observation.active,"unavailable condition never false fallback");
 }
 for(unsigned mode=0;mode<5;++mode)for(unsigned s=0;s<3;++s)for(unsigned cond=0;cond<4;++cond){
  sec::Config c;c.fuel=rule(sec::Mode(mode));c.fuel.source=ecu::load::Source(s);c.fuel.axis=ecu::load::Axis(s);c.fuel.condition=sec::Condition(cond);c.fuel.threshold=50;
  const auto r=sec::requirements(c);const bool on=mode!=0;
  check(r.map==(on&&(s!=1||(mode==3&&cond==1))),"static map union");
  check(r.emap==(on&&s==2),"static emap union");check(r.ethanol==(mode==3&&cond==3),"static ethanol union");
 }
}

static void arithmetic_probe(){
 for(unsigned mode=0;mode<5;++mode)for(double p:{0.,1.,37.,85.,100.,254.,255.})for(double q:{0.,1.,37.,50.,99.,100.,150.,255.}){
  auto r=rule(sec::Mode(mode));r.debounce_ms=0;r.threshold=0;auto i=sample();i.switches[0]=sw(0);sec::Controller c;auto s=c.select(sec::Kind::Fuel,r,i,0,false);
  const double expected=mode==0?p:mode==1?std::min(255.,p*q/100):mode==2?std::min(255.,p+q):q;
  const auto value=sec::fuel(s,p,q);check(s.ok&&close(value,expected),"fuel arithmetic zero/saturation");
 }
 for(unsigned mode=0;mode<5;++mode)for(double p:{-5.,0.,1.,20.,40.})for(double retard:{0.,3.,10.}){
  for(double q:mode==1?std::initializer_list<double>{0.,50.,100.,150.,255.}:mode==2?std::initializer_list<double>{-40.,0.,10.,40.,70.}:std::initializer_list<double>{-5.,0.,10.,20.,40.}){
   auto r=rule(sec::Mode(mode));r.debounce_ms=0;r.threshold=0;auto i=sample();i.switches[0]=sw(0);sec::Controller c;auto s=c.select(sec::Kind::Spark,r,i,0,false);
   const double corrected=std::max(-5.,p-retard);double expected=corrected;
   if(mode==1)expected=bounded(corrected*q/100);else if(mode==2)expected=bounded(corrected+q);else if(mode>=3)expected=bounded(q-retard);
   const auto value=sec::spark(s,p,corrected,q,retard);check(s.ok&&close(value,expected),"spark correction order and final NA bounds");
  }
 }
 for(auto bad:{NAN,INFINITY,-INFINITY}){sec::Controller c;auto r=rule(sec::Mode::Add);auto s=c.select(sec::Kind::Fuel,r,sample(),0,false);check(std::isnan(sec::fuel(s,bad,10))&&!s.ok,"bad primary arithmetic faults");
  s=c.select(sec::Kind::Fuel,r,sample(),0,false);check(std::isnan(sec::fuel(s,85,bad))&&!s.ok,"bad secondary arithmetic faults");}
}

static void integrated_probe(){
 for(unsigned strategy=0;strategy<3;++strategy)for(unsigned mode=0;mode<5;++mode)for(unsigned fs=0;fs<3;++fs)for(unsigned ss=0;ss<3;++ss){
  auto t=tune();t.strategy=eng::Strategy(strategy);t.cylinder_trims_enabled=strategy==1;
  t.cylinder_spark_deg={-10,-3,3,10};
  t.secondary_tables.fuel=rule(sec::Mode(mode));t.secondary_tables.spark=rule(sec::Mode(mode));t.secondary_tables.spark.input_channel=1;
  source(t.secondary_ve,t.secondary_tables.fuel,fs);source(t.secondary_spark,t.secondary_tables.spark,ss);
  t.secondary_tables.fuel.threshold=t.secondary_tables.spark.threshold=0;
  t.secondary_tables.fuel.debounce_ms=t.secondary_tables.spark.debounce_ms=0;
  if(fs==2||ss==2)t.load_model.aux_role=ecu::load::AuxRole::Emap;
  t.secondary_ve.cells.fill(mode==1?150:mode==2?20:60);
  t.secondary_spark.cells.fill(mode==1?150:mode==2?10:30);
  check(eng::validate(t)==nullptr,"integrated configuration valid");
  eng::Controller c;auto i=inputs();i.rpm=6400;i.sampled_us=1000000;i.table_switches[0]=sw(1000000);i.table_switches[1]=sw(1000000);
  auto o=c.step(t,i,1000000);check(o.faults==0,"integrated enabled modes run");
  const double retard=10*(6400.-6200)/300;
  const double expected_ve=mode==0?40:mode==1?60:60;
  check(close(o.ve_pct,expected_ve),"integrated VE");
  const double expected_spark=mode==0?20-retard:mode==1?(20-retard)*1.5:mode==2?30-retard:30-retard;
  check(close(o.advance_deg,expected_spark),"integrated scalar spark order");
  for(unsigned j=0;j<4;++j){const double offset=strategy==1?t.cylinder_spark_deg[j]:0;
   double expected;if(mode==0)expected=bounded(std::clamp(20+offset,-5.,40.)-retard);
   else if(mode==1)expected=bounded(bounded(std::clamp(20+offset,-5.,40.)-retard)*1.5);
   else if(mode==2)expected=bounded(bounded(std::clamp(20+offset,-5.,40.)-retard)+10);
   else expected=bounded(std::clamp(30+offset,-5.,40.)-retard);
   check(close(o.cylinder_advance_deg[j],expected),"integrated per-cylinder correction order");
  }
 }
 for(unsigned mode=1;mode<5;++mode){auto t=tune();t.secondary_tables.fuel=rule(sec::Mode(mode));t.secondary_tables.fuel.debounce_ms=0;t.secondary_tables.fuel.threshold=0;t.secondary_ve.cells.fill(0);auto i=inputs();i.sampled_us=1000000;i.table_switches[0]=sw(1000000);eng::Controller c;auto o=c.step(t,i,1000000);
  if(mode!=2)check(o.faults==0&&o.fuel_cut&&o.pulse_ms==0&&!o.spark_cut,"zero composed fuel suppresses opening");
 }
 // A potential secondary MAP source remains required even below its RPM switch.
 auto t=tune();t.load_model.fuel_source=t.load_model.spark_source=ecu::load::Source::Tps;t.load_model.ve_axis=t.load_model.spark_axis=t.load_model.lambda_axis=t.load_model.trim_axis=ecu::load::Axis::TpsPercent;t.load_model.pressure=ecu::load::Pressure::None;t.load_model.afr=ecu::load::Afr::Off;
 for(auto*m:{&t.ve,&t.spark,&t.lambda})for(unsigned n=0;n<16;++n)m->load[n]=n*100.f/15;
 for(auto&m:t.cylinder_fuel)for(unsigned n=0;n<6;++n)m.load[n]=n*20;
 t.secondary_tables.fuel=rule(sec::Mode::Conditional);auto i=inputs();i.map_qualified=false;i.map_kpa=NAN;i.sampled_us=1000000;eng::Controller c;auto o=c.step(t,i,1000000);check((o.faults&eng::BadSensor)&&o.fuel_cut&&o.spark_cut,"inactive configured secondary MAP still required");
 source(t.secondary_ve,t.secondary_tables.fuel,1);t.secondary_tables.fuel.condition=sec::Condition::Map;t.secondary_tables.fuel.threshold=60;c.reset();o=c.step(t,i,1000000);check((o.faults&eng::BadSensor)&&eng::input_requirements(t).map,"MAP switch condition adds dependency");
 t.secondary_tables.fuel.condition=sec::Condition::Ethanol;t.secondary_tables.fuel.threshold=50;i.ethanol_qualified=false;c.reset();o=c.step(t,i,1000000);check((o.faults&eng::BadSensor)&&o.secondary_fuel.reason==sec::Reason::RequiredEthanol,"ethanol not fabricated zero");
}

static std::string read(const char*path){std::ifstream f(path);std::ostringstream s;s<<f.rdbuf();return s.str();}
static void rule_change_probe(){
 for(unsigned change=0;change<7;++change){auto r=rule();r.threshold=50;auto i=sample();sec::Controller c;
  i.switches[0]=i.switches[1]=sw(100000);auto a=c.select(sec::Kind::Fuel,r,i,100000,false);
  i.switches[0]=i.switches[1]=sw(120000);a=c.select(sec::Kind::Fuel,r,i,120000,false);check(a.ok,"prior rule qualified");
  if(change==0)r.active_high=false;else if(change==1)r.input_channel=1;else if(change==2)r.debounce_ms=25;
  else if(change==3){r.source=ecu::load::Source::Tps;r.axis=ecu::load::Axis::TpsPercent;}
  else if(change==4)r.condition=sec::Condition::Tps;else if(change==5)r.threshold=51;
  else{r.mode=sec::Mode::Off;a=c.select(sec::Kind::Fuel,r,i,120000,false);r.mode=sec::Mode::Input;}
  i.switches[0]=i.switches[1]=sw(125000);a=c.select(sec::Kind::Fuel,r,i,125000,false);check(!a.ok&&a.observation.reason==sec::Reason::Debouncing,"any rule change requalifies");
  const auto finish=125000+std::uint64_t(r.debounce_ms*1000);
  // Keep the independent observation gap under20ms while waiting25ms.
  i.switches[0]=i.switches[1]=sw(135000);a=c.select(sec::Kind::Fuel,r,i,135000,false);
  i.switches[0]=i.switches[1]=sw(finish);a=c.select(sec::Kind::Fuel,r,i,finish,false);check(a.ok,"new rule reacquires");
 }
 auto t=tune();t.secondary_tables.fuel=rule();eng::Controller c;auto i=inputs();i.sampled_us=100000;i.table_switches[0]=sw(100000);auto o=c.step(t,i,100000);
 i.sampled_us=120000;i.table_switches[0]=sw(120000);o=c.step(t,i,120000);check(o.faults==0&&o.secondary_fuel.input_qualified,"engine input initially qualified");
 t.spark.cells[0]=100;i.sampled_us=125000;i.table_switches[0]=sw(125000);o=c.step(t,i,125000);check(o.faults==eng::BadTune,"bad tune faults");
 t.spark.cells[0]=20;i.sampled_us=130000;i.table_switches[0]=sw(130000);o=c.step(t,i,130000);check((o.faults&eng::BadSensor)&&!o.secondary_fuel.input_qualified,"bad tune interval resets input qualification");
 i.sampled_us=150000;i.table_switches[0]=sw(150000);o=c.step(t,i,150000);check(o.faults==0&&o.secondary_fuel.input_qualified,"engine input requalified");
 auto r=rule();r.debounce_ms=NAN;sec::SwitchFilter f;auto a=f.step(sw(0),r,0);check(!a.valid&&a.reason==sec::Reason::InvalidConfig,"invalid debounce checked before rounding");
 r=rule(sec::Mode::Add);sec::Controller controller;auto s=controller.select(sec::Kind::Fuel,r,sample(),0,false);check(std::isnan(sec::fuel(s,1e300,1))&&!s.ok,"non-F32 primary rejected");
 s=controller.select(sec::Kind::Fuel,r,sample(),0,false);check(std::isnan(sec::fuel(s,1,1e300))&&!s.ok,"non-F32 secondary rejected");
}
static void transport_probe(int count,char**files){
 for(int n=0;n<count;++n){const auto body=read(files[n]);auto*j=cJSON_Parse(body.c_str());check(j!=nullptr,"fixture parse");if(!j)continue;
  auto t=tune();t.secondary_tables.fuel=rule(sec::Mode::Multiply);t.secondary_tables.spark=rule(sec::Mode::Add);t.secondary_ve.cells.fill(200);t.secondary_spark.cells.fill(50);
  const bool parsed=eng::parse_tune(j,t);check(parsed,"historical fixture accepted");check(t.secondary_tables.fuel.mode==sec::Mode::Off&&t.secondary_tables.spark.mode==sec::Mode::Off,"historical JSON resets modes");check(t.secondary_ve.cells[0]==85&&t.secondary_spark.cells[0]==15,"historical JSON resets unrepresented maps");cJSON_Delete(j);
 }
 auto original=tune();ecu::tuning::Page p;ecu::tuning::encode_page(original,42,p);auto t=tune();t.secondary_tables.fuel=rule(sec::Mode::Multiply);t.secondary_tables.spark=rule(sec::Mode::Add);t.secondary_ve.cells.fill(200);t.secondary_spark.cells.fill(50);
 check(ecu::tuning::decode_page(p,42,t),"own008 page accepted");check(t.secondary_tables.fuel.mode==sec::Mode::Off&&t.secondary_tables.spark.mode==sec::Mode::Off,"own008 resets modes");check(t.secondary_ve.cells[0]==85&&t.secondary_spark.cells[0]==15,"own008 resets maps");
}
int main(int argc,char**argv){switch_probe();source_condition_probe();arithmetic_probe();integrated_probe();rule_change_probe();transport_probe(argc-1,argv+1);std::cout<<"TOTAL,"<<checks<<",FAILURES,"<<failures<<'\n';return failures?1:0;}
