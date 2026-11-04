#include "ecu/engine.hpp"
#include "ecu/tuning_layout.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::engine;
namespace sec=ecu::secondary;
static unsigned checks=0;
static void check(bool value){++checks;assert(value);}
static bool near(double a,double b){return std::abs(a-b)<1e-9;}
static Tune tune(){Tune t;t.ve.cells.fill(80);t.spark.cells.fill(20);t.injector_cc_min=600;t.afterstart_pct=0;t.ego_enabled=t.dfco_enabled=false;t.transient_enrichment.mode=ecu::transient::Mode::Off;return t;}
static Inputs input(std::uint64_t now=1000000){Inputs s;s.rpm=2000;s.map_kpa=40;s.tps_pct=25;s.clt_c=85;s.iat_c=25;s.lambda=1;s.battery_v=14;s.sensor_v=5;s.synced=s.phase_synced=s.sensors_valid=s.lambda_ready=true;s.sampled_us=now;return s;}
static void configure(sec::Rule&r,sec::Mode mode){r.mode=mode;r.cells=sec::expected_cells(mode);r.debounce_ms=0;r.threshold=1000;}
static Output step(Tune&t,Inputs s){check(!validate(t));s.flex_sample=ecu::flex::synthetic_value(s.ethanol_pct,s.ethanol_qualified,s.sampled_us,t.flex_fuel.capture,t.revision);Controller c;return c.step(t,s,s.sampled_us);}
static void fuel_and_capacity(){
 for(unsigned m=0;m<5;++m){
  auto t=tune();auto s=input();configure(t.secondary_tables.fuel,sec::Mode(m));t.secondary_ve.cells.fill(m==1?150:20);
  s.table_switches[0]={s.sampled_us,sec::InputSource::Synthetic,true,true};auto o=step(t,s);
  const double expected=m==0?80:m==1?120:m==2?100:20;
  check(!o.faults&&near(o.ve_pct,expected));check(o.secondary_fuel.evaluated&&o.secondary_fuel.active==(m!=0));
  const double effective=o.pulse_ms-o.deadtime_ms;
  auto neutral=tune();auto base=step(neutral,s);check(near(effective/(base.pulse_ms-base.deadtime_ms),expected/80));
 }
 auto t=tune();configure(t.secondary_tables.fuel,sec::Mode::Multiply);t.secondary_ve.cells.fill(0);
 auto o=step(t,input());check(!o.faults&&o.ve_pct==0&&o.fuel_cut&&!o.spark_cut&&o.pulse_ms==0);
 t=tune();t.ve.cells.fill(200);configure(t.secondary_tables.fuel,sec::Mode::Add);t.secondary_ve.cells.fill(200);
 o=step(t,input());check(!o.faults&&o.ve_pct==255&&o.secondary_fuel.clamped);
 t.injector_cc_min=100;t.max_injection_ms=1;o=step(t,input());check(o.faults&Capacity);check(o.fuel_cut&&o.spark_cut&&o.cylinder_capacity_mask==15);
}
static void spark_order_and_cylinders(){
 for(unsigned m=1;m<5;++m){
  auto t=tune();auto s=input();t.rpm_limit=6700;t.soft_limit_band=500;s.rpm=6450;
  configure(t.secondary_tables.spark,sec::Mode(m));t.secondary_spark.cells.fill(m==1?150:m==2?10:25);
  s.table_switches[1]={s.sampled_us,sec::InputSource::Synthetic,true,true};auto o=step(t,s);
  const double expected=m==1?22.5:m==2?25:20;
  check(!o.faults&&near(o.advance_deg,expected));check(o.secondary_spark.primary==20&&o.secondary_spark.primary_corrected==15);
  for(auto advance:o.cylinder_advance_deg)check(near(advance,expected));
  t.strategy=Strategy::Sequential;t.cylinder_trims_enabled=true;t.cylinder_spark_deg={-10,-5,5,10};o=step(t,s);check(!o.faults);
  const double mul[]={7.5,15,30,37.5},add[]={15,20,30,35},switched[]={10,15,25,30};
  for(unsigned c=0;c<4;++c)check(near(o.cylinder_advance_deg[c],m==1?mul[c]:m==2?add[c]:switched[c]));
  // Cranking keeps the existing cranking angle for every secondary mode.
  s.rpm=220;s.table_switches={};o=step(t,s);check(!o.faults&&o.state==State::Cranking&&o.advance_deg==t.crank_advance_deg);
  check(!o.secondary_spark.active&&o.secondary_spark.reason==sec::Reason::CrankingBypass);
 }
 auto t=tune();configure(t.secondary_tables.spark,sec::Mode::Multiply);t.secondary_spark.cells.fill(255);t.spark.cells.fill(40);
 auto o=step(t,input());check(!o.faults&&o.advance_deg==40&&o.secondary_spark.clamped&&o.cylinder_spark_clamp_mask==15);
 t=tune();configure(t.secondary_tables.spark,sec::Mode::Add);t.secondary_spark.cells.fill(-40);o=step(t,input());
 check(!o.faults&&o.advance_deg==-5&&o.secondary_spark.clamped&&o.cylinder_spark_clamp_mask==15);
}
static void alpha(Tune&t){
 auto&l=t.load_model;l.fuel_source=l.spark_source=ecu::load::Source::Tps;l.pressure=ecu::load::Pressure::None;
 l.ve_axis=l.spark_axis=l.lambda_axis=l.trim_axis=ecu::load::Axis::TpsPercent;
 for(auto*m:{&t.ve,&t.spark,&t.lambda})for(unsigned n=0;n<16;++n)m->load[n]=n*100.f/15;
 for(auto&m:t.cylinder_fuel)for(unsigned n=0;n<6;++n)m.load[n]=n*20.f;
}
static void dependencies_and_units(){
 auto t=tune();alpha(t);auto s=input();s.map_qualified=false;s.map_kpa=NAN;
 auto o=step(t,s);check(!o.faults&&!input_requirements(t).map);
 auto&r=t.secondary_tables.fuel;configure(r,sec::Mode::Conditional);r.source=ecu::load::Source::Tps;r.axis=ecu::load::Axis::TpsPercent;r.condition=sec::Condition::Map;r.threshold=50;
 for(unsigned n=0;n<16;++n)t.secondary_ve.load[n]=n*100.f/15;
 check(input_requirements(t).map);o=step(t,s);check(o.faults&BadSensor);check(o.load_model.reason==ecu::load::Reason::RequiredMap&&o.secondary_fuel.reason==sec::Reason::RequiredMap);
 r.condition=sec::Condition::Tps;r.threshold=25;o=step(t,s);check(!o.faults&&!o.secondary_fuel.active);
 s.tps_pct=25.01;o=step(t,s);check(!o.faults&&o.secondary_fuel.active);
 r.source=ecu::load::Source::PressureRatio;r.axis=ecu::load::Axis::PressureRatioPercent;
 for(unsigned n=0;n<16;++n)t.secondary_ve.load[n]=n*40.f;
 check(validate(t)!=nullptr);t.load_model.aux_role=ecu::load::AuxRole::Emap;check(!validate(t));
 o=step(t,s);check(o.faults&BadSensor);s.map_kpa=50;s.map_qualified=true;o=step(t,s);check(o.load_model.reason==ecu::load::Reason::RequiredEmap);
 s.aux_pressure_kpa=125;s.aux_pressure_qualified=true;o=step(t,s);check(!o.faults&&o.secondary_fuel.coordinate==40);
 t.load_model.pressure=ecu::load::Pressure::MapBaro;t.load_model.baro_source=ecu::load::BaroSource::Aux;check(validate(t)!=nullptr);
 t=tune();configure(t.secondary_tables.fuel,sec::Mode::Conditional);t.secondary_tables.fuel.condition=sec::Condition::Ethanol;t.secondary_tables.fuel.threshold=50;
 o=step(t,input());check(o.faults&BadSensor);check(o.secondary_fuel.reason==sec::Reason::RequiredEthanol);
 s=input();s.ethanol_pct=50;s.ethanol_qualified=true;o=step(t,s);check(!o.faults&&!o.secondary_fuel.active);
 s.ethanol_pct=50.01;o=step(t,s);check(!o.faults&&o.secondary_fuel.active);
 // Switching modes or coordinates cannot reinterpret stored cells/axes.
 t=tune();t.secondary_tables.spark.mode=sec::Mode::Multiply;check(validate(t)!=nullptr);
 t.secondary_tables.spark.cells=sec::Cells::Multiplier;check(!validate(t));
 t.secondary_tables.spark.source=ecu::load::Source::Tps;check(validate(t)!=nullptr);
 t.secondary_tables.spark.axis=ecu::load::Axis::TpsPercent;check(validate(t)!=nullptr);
 for(unsigned n=0;n<16;++n)t.secondary_spark.load[n]=n*100.f/15;
 check(!validate(t));
}
static void input_faults(){
 auto t=tune();configure(t.secondary_tables.fuel,sec::Mode::Input);configure(t.secondary_tables.spark,sec::Mode::Input);
 t.secondary_tables.fuel.debounce_ms=t.secondary_tables.spark.debounce_ms=20;
 t.secondary_ve.cells.fill(40);t.secondary_spark.cells.fill(10);Controller c;
 for(unsigned n=0;n<3;++n){auto s=input(1000000+n*10000);s.table_switches[0]={s.sampled_us,sec::InputSource::Synthetic,true,true};s.table_switches[1]={s.sampled_us,sec::InputSource::Synthetic,false,true};auto o=c.step(t,s,s.sampled_us);
  check(n<2?bool(o.faults&BadSensor):o.faults==0);check(n<2?o.fuel_cut:o.ve_pct==40&&o.advance_deg==20);
 }
 auto s=input(1025000);s.table_switches[0]={1020000,sec::InputSource::Synthetic,true,true};s.table_switches[1]={1020000,sec::InputSource::Synthetic,false,true};
 auto o=c.step(t,s,s.sampled_us);check(!o.faults);
 s.sampled_us=1040001;o=c.step(t,s,s.sampled_us);check(o.faults&BadSensor);check(o.fuel_cut&&o.spark_cut&&o.secondary_fuel.reason==sec::Reason::InputStale);
 s=input(1045000);s.table_switches[0]={s.sampled_us,sec::InputSource::Synthetic,true,true};s.table_switches[1]={s.sampled_us,sec::InputSource::Synthetic,false,true};o=c.step(t,s,s.sampled_us);check(o.faults&BadSensor);
 s.sampled_us=1065000;for(auto&sw:s.table_switches)sw.observed_us=s.sampled_us;o=c.step(t,s,s.sampled_us);check(!o.faults);
 // Even an input fault during normal operation cannot alter the global gate.
 s.sampled_us=1070000;for(auto&sw:s.table_switches)sw.observed_us=s.sampled_us;s.table_switches[1].valid=false;o=c.step(t,s,s.sampled_us);check(o.faults&BadSensor);check(o.pulse_ms==0&&o.dwell_ms==0&&!o.proposed_enabled());
}
static void crank_input_handoff(){
 auto t=tune();configure(t.secondary_tables.spark,sec::Mode::Input);t.secondary_tables.spark.debounce_ms=20;
 t.secondary_spark.cells.fill(12);Controller c;
 auto observe=[&](std::uint64_t now,double rpm,bool level,bool valid=true){
  auto s=input(now);s.rpm=rpm;s.table_switches[1]={now,sec::InputSource::Synthetic,level,valid};return c.step(t,s,now);
 };
 for(unsigned n=0;n<=4;++n){const auto o=observe(1000000+n*5000,220,true);
  check(!o.faults&&o.state==State::Cranking&&o.advance_deg==t.crank_advance_deg);
  check(!o.secondary_spark.active&&o.secondary_spark.reason==sec::Reason::CrankingBypass);
  check(o.secondary_spark.input_qualified==(n==4));
 }
 auto o=observe(1025000,500,true);check(!o.faults&&o.state==State::Cranking);
 o=observe(1030000,550,true);check(!o.faults&&o.state==State::Running&&o.advance_deg==12&&o.secondary_spark.active);
 // A qualified bouncing contact retains its previous running selection.
 o=observe(1035000,2000,false);check(!o.faults&&o.advance_deg==12&&o.secondary_spark.pending);
 o=observe(1040000,220,false);check(!o.faults&&o.state==State::Cranking&&o.advance_deg==t.crank_advance_deg);
 o=observe(1045000,550,false);check(!o.faults&&o.advance_deg==12&&o.secondary_spark.pending);
 o=observe(1055000,2000,false);check(!o.faults&&o.advance_deg==20&&!o.secondary_spark.active);
 // Bypassed bad inputs are visible, but do not interrupt the cranking angle.
 o=observe(1060000,220,true,false);check(!o.faults&&o.advance_deg==t.crank_advance_deg&&!o.secondary_spark.input_qualified);
 o=observe(1065000,550,true);check(o.faults==BadSensor&&o.fuel_cut&&o.spark_cut&&!o.proposed_enabled());
 o=observe(1085000,550,true);check(!o.faults&&o.advance_deg==12&&o.secondary_spark.input_qualified);
}
static void secondary_transport(){
 auto t=tune();configure(t.secondary_tables.fuel,sec::Mode::Multiply);t.secondary_ve.cells.fill(150);
 ecu::tuning::Page p;ecu::tuning::encode_page(t,9,p);auto enabled=tune();
 check(ecu::tuning::decode_page(p,9,enabled));check(enabled.secondary_tables.fuel.mode==sec::Mode::Multiply&&enabled.secondary_ve.cells[0]==150);
 check(enabled.secondary_tables.spark.mode==sec::Mode::Off&&enabled.secondary_spark.cells[0]==15);
 ecu::tuning::Page roundtrip;ecu::tuning::encode_page(enabled,9,roundtrip);check(p==roundtrip);
}
int main(){fuel_and_capacity();spark_order_and_cylinders();dependencies_and_units();input_faults();crank_input_handoff();secondary_transport();std::cout<<"{\"passed\":true,\"engine_secondary_checks\":"<<checks<<"}\n";}
