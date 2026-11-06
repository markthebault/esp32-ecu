#include "ecu/engine.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::engine;
namespace l=ecu::load;
template<std::size_t N>void axis(std::array<float,N>&a,float maximum){for(unsigned n=0;n<N;++n)a[n]=maximum*n/(N-1);}
Tune alpha(){
 Tune t;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);t.crank_pct.fill(100);t.transient_enrichment.mode=ecu::transient::Mode::Off;
 auto&c=t.load_model;c.fuel_source=c.spark_source=l::Source::Tps;c.ve_axis=c.spark_axis=c.lambda_axis=c.trim_axis=l::Axis::TpsPercent;c.pressure=l::Pressure::None;
 for(auto*m:{&t.ve,&t.spark,&t.lambda})axis(m->load,100);
 for(auto&m:t.cylinder_fuel)axis(m.load,100);
 t.ve.cells.fill(20);return t;
}
Inputs input(std::uint64_t now){Inputs i;i.rpm=1000;i.map_kpa=NAN;i.map_qualified=false;i.tps_pct=10;i.clt_c=85;i.iat_c=25;i.battery_v=14;i.sensor_v=5;i.lambda=1.1;i.sampled_us=now;i.synced=i.phase_synced=i.sensors_valid=i.lambda_ready=true;return i;}
void alpha_and_dependencies(){
 auto t=alpha();assert(!validate(t));Controller a,b;auto i=input(1000);auto x=a.step(t,i,1000);assert(!x.faults&&x.load_model.values[l::FuelLoad]==10&&x.load_model.values[l::PressureFactor]==1);
 i.map_qualified=true;i.map_kpa=100;auto y=b.step(t,i,1000);assert(!y.faults&&x.pulse_ms==y.pulse_ms&&x.air_mg==y.air_mg);
 i=input(2000);i.map_qualified=true;i.map_kpa=111;assert(a.step(t,i,2000).faults&BadSensor);
 i=input(3000);assert(!a.step(t,i,3000).faults);
 t.transient_enrichment.mode=ecu::transient::Mode::MapRate;assert(a.step(t,input(4000),4000).faults&BadSensor);
 t=alpha();t.load_model.pressure=l::Pressure::MapReference;assert(a.step(t,input(5000),5000).faults&BadSensor);
 t=alpha();t.load_model.spark_source=l::Source::Map;assert(validate(t));
 t=alpha();t.load_model.afr=l::Afr::Off;t.load_model.lambda_source=l::Source::Map;t.load_model.lambda_axis=l::Axis::MapKpa;t.lambda=Map{};t.lambda.cells.fill(1);
 Controller inactive;auto neutral=inactive.step(t,input(1000),1000);assert(!neutral.faults&&std::isnan(neutral.target_lambda)&&neutral.load_model.values[l::AfrFactor]==1);
 t.ego_enabled=true;Controller feedback;assert(feedback.step(t,input(1000),1000).faults&BadSensor);
}
void ratio_and_distinct_coordinates(){
 auto t=alpha();auto&c=t.load_model;c.fuel_source=l::Source::PressureRatio;c.ve_axis=c.lambda_axis=c.trim_axis=l::Axis::PressureRatioPercent;c.aux_role=l::AuxRole::Emap;
 axis(t.ve.load,600);axis(t.lambda.load,600);for(auto&m:t.cylinder_fuel)axis(m.load,600);
 for(unsigned y=0;y<16;++y)for(unsigned x=0;x<16;++x){t.ve.cells[y*16+x]=20+t.ve.load[y]/20;t.spark.cells[y*16+x]=10+t.spark.load[y]/10;}
 assert(!validate(t));Controller controller;auto i=input(1000);i.map_qualified=true;i.map_kpa=100;i.aux_pressure_qualified=true;i.aux_pressure_kpa=80;
 auto o=controller.step(t,i,1000);assert(!o.faults&&std::abs(o.ve_pct-26.25)<1e-6&&std::abs(o.advance_deg-11)<1e-6);
 assert(o.load_model.values[l::FuelLoad]==125&&o.load_model.values[l::SparkLoad]==10&&o.load_model.values[l::LambdaLoad]==125);
 i=input(2000);i.map_qualified=true;i.map_kpa=100;assert(controller.step(t,i,2000).faults&BadSensor);
 c.pressure=l::Pressure::MapBaro;c.baro_source=l::BaroSource::Aux;assert(validate(t));
}
void zero_and_additive_fuel(){
 for(auto strategy:{Strategy::BatchWasted,Strategy::SemiSequential,Strategy::Sequential}){
  auto t=alpha();t.strategy=strategy;t.ve.cells.fill(0);t.ego_enabled=true;Controller controller;auto o=controller.step(t,input(1000),1000);
  assert(!o.faults&&o.fuel_cut&&!o.spark_cut&&o.pulse_ms==0&&o.duty_pct==0&&o.ego==1&&o.load_model.flags&l::ZeroBaseFuel);
  for(auto value:o.cylinder_pulse_ms)assert(value==0);
  auto&ae=t.transient_enrichment;ae.mode=ecu::transient::Mode::TpsRate;ae.apply=ecu::transient::Apply::AddReference;ae.tps_min_change_pct=0;
  for(unsigned n=0;n<=4;++n){auto i=input(10000+n*5000);i.tps_pct=10+n;o=controller.step(t,i,i.sampled_us);}
  assert(!o.faults&&!o.fuel_cut&&o.pulse_ms>o.deadtime_ms&&std::isnan(o.accel)&&o.load_model.flags&l::AccelRatioUnavailable);
  assert(o.transient_enrichment.values[ecu::transient::AddedFuelMg]>0&&o.ego==1&&std::isnan(o.transient_enrichment.values[ecu::transient::MapDot]));
  auto bad=input(35000);bad.tps_pct=101;o=controller.step(t,bad,35000);assert(o.faults&BadSensor&&o.fuel_cut&&o.spark_cut&&o.pulse_ms==0);
 }
 auto t=alpha();t.lambda.cells.fill(1.2f);Controller boundary;auto o=boundary.step(t,input(1000),1000);assert(!o.faults&&std::isfinite(o.load_model.values[l::AfrFactor]));
 for(auto mode:{l::Afr::Off,l::Afr::Target,l::Afr::Measured}){
  Tune flat;flat.lambda.cells.fill(1.2f);flat.load_model.afr=mode;flat.load_model.afr_delay_s=0;flat.afterstart_pct=0;
  auto i=input(1000);i.map_kpa=71.355;i.map_qualified=true;i.rpm=3250.95;Controller fractional;auto f=fractional.step(flat,i,1000);
  assert(!f.faults&&f.load_model.reason==l::Reason::Ready&&std::isfinite(f.load_model.values[l::AfrFactor])&&f.pulse_ms>f.deadtime_ms);
 }
}
void afr_start_epoch(){
 auto t=alpha();t.load_model.afr=l::Afr::Measured;t.load_model.afr_delay_s=.05f;Controller controller;auto o=controller.step(t,input(1000),1000);
 assert(o.load_model.afr_state()==l::AfrState::StartDelay);
 o=controller.step(t,input(50000),50000);assert(o.load_model.afr_state()==l::AfrState::StartDelay);
 o=controller.step(t,input(51000),51000);assert(o.load_model.afr_state()==l::AfrState::Measured);
 auto i=input(52000);i.rpm=6600;assert(controller.step(t,i,52000).faults&OverRev);
 o=controller.step(t,input(53000),53000);assert(!o.faults&&o.load_model.afr_state()==l::AfrState::Measured);
 i=input(54000);i.tps_pct=101;assert(controller.step(t,i,54000).faults&BadSensor);
 o=controller.step(t,input(55000),55000);assert(o.load_model.afr_state()==l::AfrState::Measured);
 i=input(60000);i.rpm=0;controller.step(t,i,60000);o=controller.step(t,input(61000),61000);assert(o.load_model.afr_state()==l::AfrState::StartDelay);
 auto f=alpha();f.load_model.afr=l::Afr::Measured;f.load_model.afr_delay_s=.1f;Controller fraction;fraction.step(f,input(1000),1000);
 o=fraction.step(f,input(100999),100999);assert(o.load_model.afr_state()==l::AfrState::StartDelay);
 o=fraction.step(f,input(101000),101000);assert(o.load_model.afr_state()==l::AfrState::Measured);
 // Fresh decoder0 while another sensor is faulted is a possible new start;
 // this conservatively delays measured feedback without certifying shaft rest.
 Controller faulted;faulted.step(t,input(1000),1000);faulted.step(t,input(51000),51000);
 for(unsigned n=52;n<=552;++n){auto stopped=input(n*1000);stopped.rpm=0;stopped.synced=false;stopped.sensors_valid=false;faulted.step(t,stopped,n*1000);}
 o=faulted.step(t,input(553000),553000);assert(!o.faults&&o.load_model.afr_state()==l::AfrState::StartDelay);
}
int main(){alpha_and_dependencies();ratio_and_distinct_coordinates();zero_and_additive_fuel();afr_start_epoch();std::cout<<"Engine load coordinates, optional MAP/NA guard, zero/reference fuel, strategy opening counts and AFR genuine-start epoch passed\n";}
