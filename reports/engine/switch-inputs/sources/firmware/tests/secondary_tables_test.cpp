#include "ecu/secondary_tables.hpp"
#include <cassert>
#include <iostream>
#include <limits>
using namespace ecu::secondary;
static unsigned checks=0;
static void check(bool value){++checks;assert(value);}
static Input inputs(){Input i;i.rpm=2000;i.map_kpa=50;i.tps_pct=25;i.emap_kpa=125;i.ethanol_pct=50;i.map_qualified=i.emap_qualified=i.ethanol_qualified=true;return i;}
static Rule rule(Mode mode){Rule r;r.mode=mode;r.cells=expected_cells(mode);return r;}
static void configuration(){
 Config c;ecu::load::Config primary;check(valid(c,primary));
 for(unsigned mode=0;mode<5;++mode)for(unsigned source=0;source<3;++source)for(unsigned cells=0;cells<3;++cells){
  auto r=rule(Mode(mode));r.source=ecu::load::Source(source);r.axis=ecu::load::Axis(source);r.cells=Cells(cells);
  check(valid(r)==(mode==0||r.cells==expected_cells(r.mode)));
  r.axis=ecu::load::Axis((source+1)%3);check(!valid(r));
 }
 for(unsigned condition=0;condition<4;++condition){
  auto r=rule(Mode::Conditional);r.condition=Condition(condition);r.threshold=threshold_max(r.condition);check(valid(r));
  r.threshold=std::nextafter(r.threshold,std::numeric_limits<float>::infinity());check(!valid(r));
 }
 for(float bad:{-1.f,501.f,INFINITY,NAN}){auto r=rule(Mode::Input);r.debounce_ms=bad;check(!valid(r));}
 auto r=rule(Mode::Multiply);r.source=ecu::load::Source::FollowFuel;check(!valid(r));
 c.fuel=rule(Mode::Conditional);c.fuel.condition=Condition::Map;c.fuel.threshold=50;c.fuel.source=ecu::load::Source::Tps;c.fuel.axis=ecu::load::Axis::TpsPercent;
 check(requirements(c).map&&!requirements(c).emap);
 c.fuel.source=ecu::load::Source::PressureRatio;c.fuel.axis=ecu::load::Axis::PressureRatioPercent;
 check(requirements(c).emap&&!valid(c,primary));primary.aux_role=ecu::load::AuxRole::Emap;check(valid(c,primary));
 c.fuel=rule(Mode::Off);c.spark=rule(Mode::Input);c.spark.input_channel=1;check(requirements(c).switch_mask==2);
 c.fuel=rule(Mode::Input);check(requirements(c).switch_mask==3);
}
static void conditional_and_coordinates(){
 const auto base=inputs();
 for(auto kind:{Kind::Fuel,Kind::Spark})for(unsigned condition=0;condition<4;++condition){
  auto r=rule(Mode::Conditional);r.condition=Condition(condition);
  const double center=condition==0?2000:condition==2?25:50;r.threshold=float(center);
  for(double delta:{-0.01,0.,.01}){
   auto i=base;if(condition==0)i.rpm+=delta;else if(condition==1)i.map_kpa+=delta;else if(condition==2)i.tps_pct+=delta;else i.ethanol_pct+=delta;
   Controller c;const auto s=c.select(kind,r,i,1000000,false);check(s.ok&&s.observation.active==(delta>0));
   check(s.observation.reason==(delta>0?Reason::ConditionSecondary:Reason::ConditionPrimary));
  }
 }
 for(unsigned source=0;source<3;++source){
  auto r=rule(Mode::Multiply);r.source=ecu::load::Source(source);r.axis=ecu::load::Axis(source);Controller c;
  auto s=c.select(Kind::Fuel,r,base,1000000,false);check(s.ok&&s.coordinate==(source==0?50:source==1?25:40));
 }
 auto r=rule(Mode::Conditional);r.condition=Condition::Map;r.threshold=100;r.source=ecu::load::Source::Tps;r.axis=ecu::load::Axis::TpsPercent;
 Controller c;auto i=base;i.map_qualified=false;check(c.select(Kind::Fuel,r,i,1,false).observation.reason==Reason::RequiredMap);
 r.condition=Condition::Ethanol;r.threshold=50;i=base;i.ethanol_qualified=false;
 check(c.select(Kind::Fuel,r,i,1,false).observation.reason==Reason::RequiredEthanol);
 i=base;i.ethanol_pct=NAN;check(!c.select(Kind::Fuel,r,i,1,false).ok);
 r=rule(Mode::Multiply);r.source=ecu::load::Source::PressureRatio;r.axis=ecu::load::Axis::PressureRatioPercent;
 for(double bad:std::array<double,4>{19.,501.,INFINITY,NAN}){i=base;i.emap_kpa=bad;auto s=c.select(Kind::Fuel,r,i,1,false);check(!s.ok&&s.observation.reason==Reason::RequiredEmap);}
 // Cranking bypasses all secondary spark modes, including missing switches.
 for(unsigned mode=1;mode<5;++mode){r=rule(Mode(mode));i={};auto s=c.select(Kind::Spark,r,i,1,true);check(s.ok&&!s.observation.active&&s.observation.reason==Reason::CrankingBypass);}
}
static Selection active(Mode mode){Selection s;s.ok=true;s.observation.available=true;s.observation.mode=mode;s.observation.active=mode!=Mode::Off;return s;}
static void arithmetic(){
 for(unsigned mode=0;mode<5;++mode)for(double primary:{0.,1.,80.,200.,255.})for(double secondary:{0.,25.,100.,150.,255.}){
  auto s=active(Mode(mode));const double raw=mode==0?primary:mode==1?primary*secondary/100:mode==2?primary+secondary:secondary;
  const double expected=std::clamp(raw,0.,255.);check(fuel(s,primary,secondary)==expected);check(s.ok&&s.observation.evaluated&&s.observation.clamped==(raw!=expected));
 }
 for(unsigned mode=0;mode<5;++mode)for(double primary:{-5.,0.,20.,40.})for(double secondary:{-40.,0.,20.,70.,100.,150.,255.}){
  auto s=active(Mode(mode));const double corrected=std::max(-5.,primary-10);
  const double raw=mode==0?corrected:mode==1?corrected*secondary/100:mode==2?corrected+secondary:secondary-10;
  const double expected=mode==0?raw:std::clamp(raw,-5.,40.);
  check(spark(s,primary,corrected,secondary,10)==expected);check(s.ok&&s.observation.clamped==(raw!=expected));
 }
 auto s=active(Mode::Multiply);check(spark(s,20,10,150,10)==15);
 s=active(Mode::Add);check(spark(s,20,10,20,10)==30);
 s=active(Mode::Conditional);check(spark(s,20,10,20,10)==10);
 s=active(Mode::Multiply);check(std::isnan(fuel(s,80,NAN))&&!s.ok&&s.observation.reason==Reason::Arithmetic);
 s=active(Mode::Off);const double precise=85.00000000000003;check(fuel(s,precise,NAN)==precise);
 s=active(Mode::Off);check(spark(s,20,10,NAN,10)==10);
}
static SwitchSample sample(std::uint64_t time,bool level,InputSource source=InputSource::Synthetic){return {time,source,level,true};}
static void switches(){
 auto r=rule(Mode::Input);r.debounce_ms=20;auto i=inputs();Controller c;
 i.switches[0]=sample(1000000,true);auto s=c.select(Kind::Fuel,r,i,1000000,false);check(!s.ok&&s.observation.reason==Reason::Debouncing);
 // Repeated held samples cannot finish the20ms qualification period.
 s=c.select(Kind::Fuel,r,i,1020000,false);check(!s.ok&&s.observation.reason==Reason::Debouncing);
 i.switches[0]=sample(1010000,true);s=c.select(Kind::Fuel,r,i,1020000,false);check(!s.ok);
 i.switches[0]=sample(1020000,true);s=c.select(Kind::Fuel,r,i,1020000,false);check(s.ok&&s.observation.active&&!s.observation.pending);
 i.switches[0]=sample(1025000,false);s=c.select(Kind::Fuel,r,i,1025000,false);check(s.ok&&s.observation.active&&s.observation.pending&&!s.observation.pending_level);
 i.switches[0]=sample(1030000,true);s=c.select(Kind::Fuel,r,i,1030000,false);check(s.ok&&s.observation.active&&!s.observation.pending);
 i.switches[0]=sample(1035000,false);s=c.select(Kind::Fuel,r,i,1035000,false);check(s.ok&&s.observation.active&&s.observation.pending);
 i.switches[0]=sample(1045000,false);s=c.select(Kind::Fuel,r,i,1045000,false);check(s.ok&&s.observation.active);
 i.switches[0]=sample(1055000,false);s=c.select(Kind::Fuel,r,i,1055000,false);check(s.ok&&!s.observation.active&&!s.observation.pending);
 s=c.select(Kind::Fuel,r,i,1075000,false);check(s.ok&&s.observation.input_age_ms==20);
 s=c.select(Kind::Fuel,r,i,1075001,false);check(!s.ok&&s.observation.reason==Reason::InputStale);
 i.switches[0]=sample(1080000,false);s=c.select(Kind::Fuel,r,i,1080000,false);check(!s.ok);
 i.switches[0]=sample(1100000,false);s=c.select(Kind::Fuel,r,i,1100000,false);check(s.ok);
 // A missing poll interval loses qualification even when the new sample is fresh.
 i.switches[0]=sample(1120001,false);s=c.select(Kind::Fuel,r,i,1120001,false);check(!s.ok&&s.observation.reason==Reason::Debouncing);
 i.switches[0]=sample(1140001,false);s=c.select(Kind::Fuel,r,i,1140001,false);check(s.ok);
 i.switches[0]=sample(1140001,true);s=c.select(Kind::Fuel,r,i,1140001,false);check(!s.ok&&s.observation.reason==Reason::InputTimeReversed);
 i.switches[0]=sample(1140002,true);s=c.select(Kind::Fuel,r,i,1140001,false);check(!s.ok&&s.observation.reason==Reason::InputTimeReversed);
 r.debounce_ms=0;i.switches[0]=sample(1200000,true);s=c.select(Kind::Fuel,r,i,1200000,false);check(s.ok&&s.observation.active);
 i.switches[0]=sample(1199999,true);s=c.select(Kind::Fuel,r,i,1200001,false);check(!s.ok&&s.observation.reason==Reason::InputTimeReversed);
 i.switches[0]=sample(1200002,true);s=c.select(Kind::Fuel,r,i,1200002,false);check(s.ok);
 s=c.select(Kind::Fuel,r,i,1200001,false);check(!s.ok&&s.observation.reason==Reason::InputTimeReversed);
 // Source/channel/debounce changes require a new stable interval.
 r.debounce_ms=20;i.switches[0]=sample(1300000,true,InputSource::TargetProtected);s=c.select(Kind::Fuel,r,i,1300000,false);check(!s.ok);
 i.switches[0]=sample(1320000,true,InputSource::TargetProtected);s=c.select(Kind::Fuel,r,i,1320000,false);check(s.ok);
 i.switches[0]=sample(1330000,true,InputSource::Synthetic);s=c.select(Kind::Fuel,r,i,1330000,false);check(!s.ok);
 r.input_channel=1;i.switches[1]=sample(1330000,false);s=c.select(Kind::Fuel,r,i,1330000,false);check(!s.ok);
 i.switches[1]=sample(1350000,false);s=c.select(Kind::Fuel,r,i,1350000,false);check(s.ok&&!s.observation.active);
 r.active_high=false;s=c.select(Kind::Fuel,r,i,1350000,false);check(!s.ok&&s.observation.reason==Reason::Debouncing);
 i.switches[1]=sample(1370000,false);s=c.select(Kind::Fuel,r,i,1370000,false);check(s.ok&&s.observation.active);
 i.switches[1].valid=false;s=c.select(Kind::Fuel,r,i,1370000,false);check(!s.ok&&s.observation.reason==Reason::InputUnavailable);
 // Fuel and spark each retain independent qualification/polarity.
 Controller pair;auto fuel_rule=rule(Mode::Input),spark_rule=rule(Mode::Input);fuel_rule.debounce_ms=spark_rule.debounce_ms=0;spark_rule.input_channel=1;
 i=inputs();i.switches[0]=sample(1,true);i.switches[1]=sample(1,false);
 check(pair.select(Kind::Fuel,fuel_rule,i,1,false).observation.active);
 check(!pair.select(Kind::Spark,spark_rule,i,1,false).observation.active);
}
int main(){configuration();conditional_and_coordinates();arithmetic();switches();std::cout<<"{\"passed\":true,\"secondary_checks\":"<<checks<<"}\n";}
