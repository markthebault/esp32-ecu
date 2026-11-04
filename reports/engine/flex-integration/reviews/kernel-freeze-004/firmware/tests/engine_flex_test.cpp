#include "ecu/engine.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::engine;
static unsigned checks=0;
static void check(bool v){++checks;assert(v);}
static void near(double a,double b,double tolerance=1e-8){check(std::isfinite(a)&&std::abs(a-b)<tolerance);}
static Tune tune(Strategy strategy=Strategy::BatchWasted){Tune t;t.strategy=strategy;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);t.crank_pct.fill(100);t.spark.cells.fill(20);t.transient_enrichment.mode=ecu::transient::Mode::Off;return t;}
static Inputs input(const Tune&t,std::uint64_t now=1000000,double tps=10){
 Inputs s;s.rpm=2000;s.map_kpa=50;s.tps_pct=tps;s.clt_c=85;s.iat_c=25;s.lambda=1;s.battery_v=14;s.sensor_v=5;s.synced=s.phase_synced=s.sensors_valid=s.lambda_ready=true;s.sampled_us=now;
 ecu::flex::Capture capture(t.flex_fuel.capture);const auto start=now-t.flex_fuel.capture.cycles*10000;capture.edge(start,true);
 for(unsigned n=1;n<=t.flex_fuel.capture.cycles;++n){capture.edge(start+n*10000-3000,false);capture.edge(start+n*10000,true);}
 s.flex_sample={capture.observe(now),t.flex_fuel.capture,t.revision};return s;
}
static void quality(){
 auto t=tune();t.flex_fuel.correction.enabled=true;auto good=input(t);Controller c;auto o=c.step(t,good,1000000);check(!o.faults&&o.flex_fuel.raw_qualified);
 for(unsigned mutation=0;mutation<19;++mutation){
  auto s=good;auto&v=s.flex_sample.observation;
  switch(mutation){case 0:s.flex_sample.calibration.low_hz=49;break;case 1:s.flex_sample.tune_revision=2;break;
   case 2:v.sample_us=1000001;break;case 3:v.sample_us-=250001;v.window_start_us-=250001;break;
   case 4:v.pending_fault=true;break;case 5:v.fault_generation=1;break;case 6:v.window_cycles=7;break;
   case 7:v.frequency_hz=110;break;case 8:v.source=ecu::flex::Source::TargetCapture;break;
   case 9:v.source=static_cast<ecu::flex::Source>(99);break;case 10:v.ethanol_pct=NAN;break;
   case 11:v.frequency_hz=400;v.window_start_us=v.sample_us-20000;break;
   case 12:v.frequency_hz=10;v.window_start_us=v.sample_us-800000;break;
   case 13:v.ethanol_pct=99;break;case 14:v.fuel_temp_c=120;break;
   case 15:v.unfiltered_ethanol_pct=NAN;break;case 16:v.unfiltered_fuel_temp_c=NAN;break;
   case 17:v.frequency_clamped=true;break;case 18:v.edges=2;break;}
  Controller failed;o=failed.step(t,s,1000000);check((o.faults&BadSensor)&&o.fuel_cut&&o.spark_cut&&!o.flex_fuel.control_ok&&!o.flex_fuel.corrections.valid);
 }
 good=input(t);good.flex_sample.observation.source=ecu::flex::Source::TargetCapture;t.flex_fuel.input_confirmed=true;Controller target;o=target.step(t,good,1000000);check(!o.faults);
 // Bare legacy fields never bypass the new quality contract.
 t=tune();t.secondary_tables.fuel.mode=ecu::secondary::Mode::Conditional;t.secondary_tables.fuel.condition=ecu::secondary::Condition::Ethanol;t.secondary_tables.fuel.threshold=40;
 auto scalar=input(t);scalar.flex_sample={};scalar.ethanol_pct=99;scalar.ethanol_qualified=true;Controller bare;o=bare.step(t,scalar,1000000);check(o.faults&BadSensor);
 scalar.flex_sample=ecu::flex::synthetic_value(50,true,1000000,t.flex_fuel.capture,t.revision);Controller legacy;o=legacy.step(t,scalar,1000000);check(!o.faults&&o.secondary_fuel.active&&o.flex_fuel.value_qualified&&!o.flex_fuel.raw_qualified);
 t.flex_fuel.correction.enabled=true;Controller no_raw;o=no_raw.step(t,scalar,1000000);check(o.faults&BadSensor);check(o.flex_fuel.reason==ecu::flex::Reason::RawCaptureRequired);
 t=tune();t.flex_fuel.correction.enabled=true;t.flex_fuel.capture.low_hz=100;t.flex_fuel.capture.high_hz=200;t.flex_fuel.capture.fault_hz=220;
 auto high_gap=input(t);auto&v=high_gap.flex_sample.observation;v.frequency_hz=200;v.window_start_us=960000;v.low_pulse_us=4975;v.ethanol_pct=v.unfiltered_ethanol_pct=100;v.fuel_temp_c=v.unfiltered_fuel_temp_c=.04125*4975-81.25;
 Controller glitch;o=glitch.step(t,high_gap,1000000);check((o.faults&BadSensor)&&!o.flex_fuel.raw_qualified);
}
static void contexts(){
 ecu::flex::Capture capture;capture.edge(0,true);for(unsigned n=1;n<=8;++n){capture.edge(n*10000-3000,false);capture.edge(n*10000,true);}
 auto old=capture.observe(80000);check(old.valid);capture.context_changed();check(!capture.acknowledge(old.fault_generation+1));auto pending=capture.observe(80001);check(pending.pending_fault&&!pending.valid&&pending.config_epoch==old.config_epoch+1);
 capture.context_changed();check(!capture.acknowledge(pending.fault_generation));auto newer=capture.observe(80002);check(newer.pending_fault&&newer.fault_generation>pending.fault_generation);check(capture.acknowledge(newer.fault_generation));check(!capture.acknowledge(newer.fault_generation));
 capture.edge(90000,true);for(unsigned n=1;n<=7;++n){capture.edge(90000+n*10000-3000,false);capture.edge(90000+n*10000,true);}check(!capture.observe(160000).valid);capture.edge(167000,false);capture.edge(170000,true);check(capture.observe(170000).valid);
 ecu::flex::Config config;const auto mismatch=ecu::flex::assess(config,{old,config.capture,1},170000,true,2);check(!mismatch.control_ok&&mismatch.reason==ecu::flex::Reason::ConfigurationMismatch);
 capture.context_changed();capture.edge(100,true);auto reversed=capture.observe(170001);check(reversed.pending_fault&&reversed.last_fault==ecu::flex::Reason::TimeReversed);
}
static void fuel(){
 for(auto strategy:{Strategy::BatchWasted,Strategy::Sequential,Strategy::SemiSequential})for(float f:{0.f,50.f,100.f,150.f})for(float temperature:{0.f,80.f,120.f}){
  auto t=tune(strategy);Controller baseline;auto b=baseline.step(t,input(t),1000000);check(!b.faults);
  t.flex_fuel.correction.enabled=t.flex_fuel.correction.temperature_enabled=true;t.flex_fuel.correction.fuel_pct.fill(f);t.flex_fuel.correction.temperature_pct.fill(temperature);
  Controller changed;auto o=changed.step(t,input(t),1000000);check(!o.faults&&!o.spark_cut);
  const auto dose=(b.pulse_ms-b.deadtime_ms)*(f/100.)*(temperature/100.);
  near(o.pulse_ms,dose==0?0:dose+b.deadtime_ms);check(o.fuel_cut==(dose==0));
  auto s=input(t);s.rpm=200;Controller cranking;auto crank=cranking.step(t,s,1000000);check(!crank.faults&&crank.state==State::Cranking);near(crank.advance_deg,t.crank_advance_deg);
 }
 // Factors affect ordinary fuel BEFORE an independent reference AE adder.
 for(auto apply:{ecu::transient::Apply::Multiply,ecu::transient::Apply::AddReference}){
  auto t=tune(Strategy::Sequential);t.transient_enrichment.mode=ecu::transient::Mode::TpsRate;t.transient_enrichment.tps_min_change_pct=0;t.transient_enrichment.apply=apply;
  t.cylinder_trims_enabled=true;t.cylinder_fuel[0].cells.fill(125);t.flex_fuel.correction.enabled=t.flex_fuel.correction.temperature_enabled=true;t.flex_fuel.correction.fuel_pct.fill(150);t.flex_fuel.correction.temperature_pct.fill(80);
  Controller active;Output o;for(unsigned n=0;n<=4;++n)o=active.step(t,input(t,1000000+n*5000,10+n*.5),1000000+n*5000);
  auto off=t;off.flex_fuel.correction.enabled=off.flex_fuel.correction.temperature_enabled=false;off.transient_enrichment.mode=ecu::transient::Mode::Off;Controller base;auto b=base.step(off,input(off,1020000,12),1020000);
  check(!o.faults&&!b.faults);const auto flow=t.injector_cc_min*t.fuel_density_g_cc/60;
  const auto reference=100000*.0005/(287.05*298.15)*1e6/t.stoich_afr;
  const auto dose=(b.pulse_ms-b.deadtime_ms)*flow*1.5*.8;
  const auto expected=apply==ecu::transient::Apply::Multiply?dose*1.1:dose+reference*.1;
  near((o.pulse_ms-o.deadtime_ms)*flow,expected,1e-6);near((o.cylinder_pulse_ms[0]-o.deadtime_ms)*flow,expected*1.25,1e-6);
  t.flex_fuel.correction.fuel_pct.fill(0);Controller zero;for(unsigned n=0;n<=4;++n)o=zero.step(t,input(t,1000000+n*5000,10+n*.5),1000000+n*5000);
  check(!o.faults&&o.fuel_cut&&!o.spark_cut&&o.pulse_ms==0&&o.flex_fuel.zero_factor);for(auto pulse:o.cylinder_pulse_ms)check(pulse==0);
 }
}
static void spark(){
 for(auto mode:{ecu::secondary::Mode::Off,ecu::secondary::Mode::Multiply,ecu::secondary::Mode::Add,ecu::secondary::Mode::Conditional}){
  auto t=tune();t.rpm_limit=2200;t.soft_limit_band=400;t.rpm_hysteresis=50;t.flex_fuel.correction.enabled=true;t.flex_fuel.correction.spark_deg.fill(5);
  t.secondary_tables.spark.mode=mode;t.secondary_tables.spark.cells=ecu::secondary::expected_cells(mode);t.secondary_tables.spark.threshold=100;
  t.secondary_spark.cells.fill(mode==ecu::secondary::Mode::Multiply?150:mode==ecu::secondary::Mode::Add?10:25);
  Controller c;auto o=c.step(t,input(t),1000000);check(!o.faults);near(o.advance_deg,mode==ecu::secondary::Mode::Multiply||mode==ecu::secondary::Mode::Add?30:mode==ecu::secondary::Mode::Conditional?25:20);
  auto s=input(t);s.rpm=200;Controller crank;o=crank.step(t,s,1000000);check(!o.faults&&o.flex_fuel.spark_bypassed);near(o.advance_deg,5);
 }
 auto t=tune(Strategy::Sequential);t.cylinder_trims_enabled=true;t.spark.cells.fill(40);t.flex_fuel.correction.enabled=true;t.flex_fuel.correction.spark_deg.fill(5);t.cylinder_spark_deg.fill(-10);
 Controller trim;auto o=trim.step(t,input(t),1000000);check(!o.faults);near(o.advance_deg,40);for(auto advance:o.cylinder_advance_deg)near(advance,35);
 t.cylinder_spark_deg.fill(0);t.flex_fuel.correction.spark_deg.fill(40);Controller limit;o=limit.step(t,input(t),1000000);check(!o.faults);near(o.advance_deg,40);check(o.flex_fuel.spark_clamped);
}
int main(){quality();contexts();fuel();spark();std::cout<<"engine_flex_checks "<<checks<<"\n";}
