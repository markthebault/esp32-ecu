#pragma once
#include "ecu/idle_control.hpp"
#include "ecu/boost_control.hpp"
#include "ecu/transient_enrichment.hpp"
#include "ecu/load_model.hpp"
#include "ecu/secondary_tables.hpp"
#include "ecu/flex_engine.hpp"
// Engine-development core shared by the ESP32 shadow monitor and native SIL.
// Independent implementation. Physical outputs are NOT enabled by this module.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include "ecu/engine_limits.hpp"
#include "ecu/cylinder_channels.hpp"
namespace ecu::engine {
constexpr unsigned bins=16;
struct Map {
 std::array<float,bins> rpm{80,200,400,600,800,1000,1200,1600,2000,2500,3000,3500,4000,5000,6000,8000};
 std::array<float,bins> load{10,15,20,25,30,35,40,45,50,55,60,70,80,90,100,110};
 std::array<float,bins*bins> cells{}; // row=load, column=RPM; values in physical units.
};
struct TrimMap {
 std::array<float,6> rpm{80,800,1600,3000,5000,8000},load{10,30,50,70,90,110};
 std::array<float,36> cells{}; // percent of effective fuel,100 is neutral.
 TrimMap(){cells.fill(100);}
};
inline bool finite(double x){return std::isfinite(x);}
inline bool range(double x,double lo,double hi){return finite(x)&&x>=lo&&x<=hi;}
inline bool range(float x,double lo,double hi){return finite(x)&&x>=static_cast<float>(lo)&&x<=static_cast<float>(hi);}
template<std::size_t N>bool ascending(const std::array<float,N>& a){for(unsigned i=0;i<N;++i)if(!finite(a[i])||(i&&a[i]<=a[i-1]))return false;return true;}
template<std::size_t N>unsigned segment(const std::array<float,N>& a,double x){unsigned i=0;while(i<N-2&&x>a[i+1])++i;return i;}
template<std::size_t N>double interpolate(const std::array<float,N>& x,const std::array<float,N>& y,double v){
 auto i=segment(x,v);double f=std::clamp((v-x[i])/(x[i+1]-x[i]),0.0,1.0);return y[i]+(y[i+1]-y[i])*f;
}
template<class Grid>inline double lookup(const Grid&m,double rpm,double load){
 unsigned x=segment(m.rpm,rpm),y=segment(m.load,load);
 const auto width=m.rpm.size();
 const double fx=std::clamp((rpm-m.rpm[x])/(m.rpm[x+1]-m.rpm[x]),0.0,1.0),fy=std::clamp((load-m.load[y])/(m.load[y+1]-m.load[y]),0.0,1.0);
 auto a=m.cells[y*width+x]*(1-fx)+m.cells[y*width+x+1]*fx;
 auto b=m.cells[(y+1)*width+x]*(1-fx)+m.cells[(y+1)*width+x+1]*fx;return a*(1-fy)+b*fy;
}
inline double lookup(const TrimMap&m,double rpm,double load){
 const auto x=segment(m.rpm,rpm),y=segment(m.load,load);
 const double fx=std::clamp((rpm-m.rpm[x])/(m.rpm[x+1]-m.rpm[x]),0.0,1.0),fy=std::clamp((load-m.load[y])/(m.load[y+1]-m.load[y]),0.0,1.0);
 // Difference-form interpolation keeps a constant100% surface exactly neutral.
 const double a=m.cells[y*6+x]+(m.cells[y*6+x+1]-m.cells[y*6+x])*fx;
 const double b=m.cells[(y+1)*6+x]+(m.cells[(y+1)*6+x+1]-m.cells[(y+1)*6+x])*fx;
 return a+(b-a)*fy;
}
enum class Strategy : std::uint8_t {BatchWasted,Sequential,SemiSequential};
inline bool strategy_valid(Strategy s){return s==Strategy::BatchWasted||s==Strategy::Sequential||s==Strategy::SemiSequential;}
inline const char* strategy_name(Strategy s){switch(s){case Strategy::BatchWasted:return "batch_wasted";case Strategy::Sequential:return "sequential";case Strategy::SemiSequential:return "semi_sequential";default:return "unknown";}}
template<std::size_t CylinderCapacity>inline bool firing_order_valid(const std::array<unsigned,CylinderCapacity>&order,unsigned count=4){return channels::order_valid(order,count);}
template<std::size_t CylinderCapacity>struct BasicTune {
 unsigned revision=1;
 Strategy strategy=Strategy::BatchWasted;
 // Four-stroke, even-fire only. The order starts at cylinder 1 compression TDC.
 std::array<unsigned,CylinderCapacity> firing_order{1,3,4,2};
 float injection_end_deg=540,cam_sync_deg=450,cam_window_deg=20;
 unsigned cylinders=4;
 float displacement_cc=2000,injector_cc_min=300,fuel_density_g_cc=.745f,stoich_afr=14.7f;
 float cranking_rpm=450,crank_advance_deg=5,rpm_limit=6500,rpm_hysteresis=200,soft_limit_band=300;
 float max_duty=.8f,max_injection_ms=15,max_dwell_ms=3.5f,tooth1_btdc_deg=90;
 float afterstart_pct=15,afterstart_s=20,accel_threshold_pct_s=40,accel_gain=.002f,accel_decay_s=.4f;
 bool ego_enabled=false,dfco_enabled=true,idle_enabled=false;
 float ego_kp=.15f,ego_ki=.08f,ego_limit=.1f,ego_min_clt=70;
 float dfco_rpm=2000,dfco_hysteresis=300,dfco_tps=1,dfco_delay_s=.5f;
 float idle_target_rpm=900,idle_kp=.03f,idle_ki=.02f,fan_on_c=95,fan_off_c=90,pump_prime_s=2;
 std::array<float,6> coolant_c{-40,0,20,40,70,110},warmup_pct{180,150,130,115,100,100},crank_pct{250,210,180,160,140,130};
 std::array<float,5> battery_v{8,10,12,14,16},deadtime_ms{2,1.5f,1.15f,.9f,.7f},dwell_ms{3.5f,3.3f,3,2.8f,2.5f};
 Map ve{},spark{},lambda{};
 idle::Config idle_control;
 transient::Config transient_enrichment;
 load::Config load_model;
 // Historical schemas1..7 migrate these fields to Off. Schema8/own009
 // carry the full model; protected target switch acquisition is separate.
 secondary::Config secondary_tables;
 Map secondary_ve{},secondary_spark{};
 flex::Config flex_fuel;
 boost::Config boost_control;
 bool cylinder_trims_enabled=false;
 std::array<TrimMap,CylinderCapacity> cylinder_fuel{};
 std::array<float,CylinderCapacity> cylinder_spark_deg{}; // Cylinder identifiers, not order slots or pins.
 BasicTune(){ve.cells.fill(85);spark.cells.fill(15);lambda.cells.fill(1);secondary_ve.cells.fill(85);secondary_spark.cells.fill(15);}
};
// Historical types remain distinct for legacy probes. Public schema11 uses
// eight logical cylinder slots; this does not allocate extra physical drivers.
using LegacyTune=BasicTune<4>;
using ExpandedTune=BasicTune<8>;
using Tune=ExpandedTune;
template<std::size_t CylinderCapacity>inline void reset_secondary_tables(BasicTune<CylinderCapacity>&t){
 t.secondary_tables={};t.secondary_ve={};t.secondary_spark={};
 t.secondary_ve.cells.fill(85);t.secondary_spark.cells.fill(15);
}
template<std::size_t CylinderCapacity>inline double maximum_map_kpa(const BasicTune<CylinderCapacity>&t){return t.boost_control.pressure_enabled?t.boost_control.maximum_map_kpa:110;}
template<std::size_t CylinderCapacity>inline load::Requirements input_requirements(const BasicTune<CylinderCapacity>&t){
 auto r=load::requirements(t.load_model,t.cylinder_trims_enabled,t.transient_enrichment.mode==transient::Mode::MapRate,t.ego_enabled);
 const auto extra=secondary::requirements(t.secondary_tables);r.map|=extra.map||t.boost_control.pressure_enabled;r.emap|=extra.emap;
 r.baro|=t.boost_control.mode==boost::Mode::ClosedLoop&&t.load_model.baro_source==load::BaroSource::Aux;return r;
}
template<std::size_t CylinderCapacity>inline const char* validate(const BasicTune<CylinderCapacity>&t){
 if(!t.revision||!t.cylinders||t.cylinders>CylinderCapacity)return "Cylinder count exceeds the selected logical channel capacity";
 if(!strategy_valid(t.strategy)||!firing_order_valid(t.firing_order,t.cylinders)||!range(t.injection_end_deg,0,719)||!range(t.cam_sync_deg,0,719)||!range(t.cam_window_deg,5,45))return "Invalid strategy, firing order or cam/injection reference";
 if(t.cylinder_trims_enabled&&t.strategy!=Strategy::Sequential)return "Cylinder trims require the sequential strategy";
 if(!transient::valid(t.transient_enrichment))return "Invalid transient enrichment configuration";
 if(!boost::valid(t.boost_control))return "Invalid boost/pressure configuration";
 if(input_requirements(t).baro&&t.load_model.aux_role!=load::AuxRole::Baro)return "Closed-loop boost needs the selected barometric input";
 if(!flex::valid(t.flex_fuel))return "Invalid flex-fuel capture or correction configuration";
 if(!load::valid(t.load_model,t.cylinder_trims_enabled,t.ego_enabled))return "Load sources, table bases or shared pressure roles disagree";
 if(!secondary::valid(t.secondary_tables,t.load_model,maximum_map_kpa(t)))return "Secondary-table source, units, mode or shared pressure role disagree";
 const Map*secondary_maps[]={&t.secondary_ve,&t.secondary_spark};const secondary::Rule*rules[]={&t.secondary_tables.fuel,&t.secondary_tables.spark};
 for(unsigned k=0;k<2;++k){const auto&m=*secondary_maps[k];const auto&r=*rules[k];
  if(!ascending(m.rpm)||!ascending(m.load))return "Secondary-table axes must increase strictly";
  for(auto v:m.rpm)if(!range(v,50,10000))return "Secondary-table RPM axis out of range";
  for(auto v:m.load)if(!range(v,load::axis_min(r.axis),load::axis_max(r.axis,maximum_map_kpa(t))))return "Secondary-table load axis disagrees with its declared basis";
  for(auto v:m.cells)if(!range(v,secondary::cell_min(static_cast<secondary::Kind>(k),r.cells),secondary::cell_max(static_cast<secondary::Kind>(k),r.cells)))return "Secondary-table cell disagrees with its declared meaning";
 }
 for(unsigned cylinder=0;cylinder<CylinderCapacity;++cylinder){
  const auto&m=t.cylinder_fuel[cylinder];
  if(!range(t.cylinder_spark_deg[cylinder],-10,10)||!ascending(m.rpm)||!ascending(m.load))return "Invalid cylinder trim or axes";
  for(auto v:m.rpm)if(!range(v,50,10000))return "Cylinder trim RPM axis out of range";
  for(auto v:m.load)if(!range(v,load::axis_min(t.load_model.trim_axis),load::axis_max(t.load_model.trim_axis,maximum_map_kpa(t))))return "Cylinder trim load axis disagrees with its declared basis";
  for(auto v:m.cells)if(!range(v,50,150))return "Cylinder fuel trim must be50-150percent";
 }
 if(!range(t.displacement_cc,25,12000)||!range(t.injector_cc_min,25,5000)||!range(t.fuel_density_g_cc,.6,.9)||!range(t.stoich_afr,9,16))return "Invalid engine or injector specification";
 if(!range(t.cranking_rpm,100,800)||!range(t.crank_advance_deg,-5,15)||!range(t.rpm_limit,1500,8000)||!range(t.rpm_hysteresis,50,500)||!range(t.soft_limit_band,0,500)||t.cranking_rpm>=t.rpm_limit-t.rpm_hysteresis)return "Invalid starting/rev limit settings";
 if(!range(t.max_duty,.1,.85)||!range(t.max_injection_ms,1,15)||!range(t.max_dwell_ms,.5,3.5)||!range(t.tooth1_btdc_deg,0,359))return "Pulse limits exceed the current carrier contract";
 if(!range(t.afterstart_pct,0,100)||!range(t.afterstart_s,0,120)||!range(t.accel_threshold_pct_s,1,1000)||!range(t.accel_gain,0,.02)||!range(t.accel_decay_s,.05,2))return "Invalid enrichment settings";
 if(!range(t.ego_kp,0,1)||!range(t.ego_ki,0,1)||!range(t.ego_limit,0,.25)||!range(t.ego_min_clt,0,110))return "Invalid closed-loop lambda settings";
 if(!range(t.dfco_rpm,1200,5000)||!range(t.dfco_hysteresis,50,1000)||!range(t.dfco_tps,0,5)||!range(t.dfco_delay_s,.1,5)||t.dfco_rpm-t.dfco_hysteresis<=t.cranking_rpm)return "Invalid overrun settings";
 if(!idle::valid(t.idle_control,{t.idle_enabled,t.idle_target_rpm,t.idle_kp,t.idle_ki}))return "Invalid idle control configuration";
 if(!range(t.idle_target_rpm,600,1500)||!range(t.idle_kp,0,double(.2f))||!range(t.idle_ki,0,double(.2f))||!range(t.fan_on_c,70,110)||!range(t.fan_off_c,60,105)||t.fan_off_c>=t.fan_on_c||!range(t.pump_prime_s,0,5))return "Invalid auxiliary settings";
 if(!ascending(t.coolant_c)||!ascending(t.battery_v))return "Curve axes must increase strictly";
 for(unsigned i=0;i<6;++i)if(!range(t.coolant_c[i],-40,140)||!range(t.warmup_pct[i],80,300)||!range(t.crank_pct[i],100,400))return "Invalid coolant enrichment curve";
 for(unsigned i=0;i<5;++i)if(!range(t.battery_v[i],7,18)||!range(t.deadtime_ms[i],.1,3)||!range(t.dwell_ms[i],.5,t.max_dwell_ms))return "Invalid battery compensation curve";
 const Map*maps[]={&t.ve,&t.spark,&t.lambda};const load::Axis bases[]={t.load_model.ve_axis,t.load_model.spark_axis,t.load_model.lambda_axis};
 for(unsigned k=0;k<3;++k){const auto&m=*maps[k];if(!ascending(m.rpm)||!ascending(m.load))return "Map axes must increase strictly";
  for(auto v:m.rpm)if(!range(v,50,10000))return "RPM axis out of range";
  for(auto v:m.load)if(!range(v,load::axis_min(bases[k]),load::axis_max(bases[k],maximum_map_kpa(t))))return "Map load axis disagrees with its declared physical basis";
  for(auto v:m.cells)if(!range(v,k==0?0:k==1?-5:.75,k==0?255:k==1?40:1.2))return "Map cell outside supported range";
 }
 return nullptr;
}
enum Fault:std::uint32_t { BadTune=1,NoSync=2,BadSensor=4,Stale=8,OverTemp=16,OverRev=32,Capacity=64,Timing=128,CamPhase=256,Overboost=512 };
enum class State {Stopped,Cranking,Warmup,Running,Overrun,Faulted};
inline const char* state_name(State s){switch(s){case State::Stopped:return "stopped";case State::Cranking:return "cranking";case State::Warmup:return "warmup";case State::Running:return "running";case State::Overrun:return "overrun";default:return "fault";}}
struct Inputs {
 double rpm=0,map_kpa=0,tps_pct=0,clt_c=0,iat_c=0,lambda=1,battery_v=0,sensor_v=0;
 std::uint64_t sampled_us=0;bool synced=false,sensors_valid=false,lambda_ready=false,phase_synced=false;
 // Additive auxiliary input; the original input/quality field ordering stays.
 double aux_pressure_kpa=NAN;bool map_qualified=true,aux_pressure_qualified=false;
 double ethanol_pct=NAN;bool ethanol_qualified=false;
 std::array<secondary::SwitchSample,2> table_switches{};
 flex::Sample flex_sample{};
 bool flex_context_match=true;
};
template<std::size_t CylinderCapacity>struct BasicOutput {
 State state=State::Stopped;std::uint32_t faults=0;
 idle::Output idle;
 boost::Output boost_control;
 transient::Output transient_enrichment;
 load::Observation load_model;
 secondary::Observation secondary_fuel,secondary_spark;
 flex::Evaluation flex_fuel;
 double rpm=0,ve_pct=0,target_lambda=1,advance_deg=0,pulse_ms=0,dwell_ms=0,deadtime_ms=0,air_mg=0;
 double warmup=1,afterstart=1,accel=1,ego=1,duty_pct=0,idle_pct=0;
 bool fuel_cut=false,spark_cut=false,pump=false,fan=false;
 // Scalars retain the untrimmed base demand for compatible consumers. The
 // scheduler uses these physical-cylinder demands when cylinder_data is true.
 std::array<double,CylinderCapacity> cylinder_pulse_ms{},cylinder_advance_deg{},cylinder_duty_pct{};
 std::array<double,CylinderCapacity> cylinder_fuel_pct=[]{std::array<double,CylinderCapacity> values{};values.fill(100);return values;}();
 unsigned cylinder_count=4;
 bool cylinder_data=false,cylinder_trims_enabled=false;
 std::uint8_t cylinder_capacity_mask=0,cylinder_spark_clamp_mask=0,cylinder_retard_floor_mask=0;
 double pulse_for(unsigned cylinder)const{return cylinder<CylinderCapacity?(cylinder_data&&cylinder_trims_enabled?cylinder_pulse_ms[cylinder]:pulse_ms):NAN;}
 double advance_for(unsigned cylinder)const{return cylinder<CylinderCapacity?(cylinder_data&&cylinder_trims_enabled?cylinder_advance_deg[cylinder]:advance_deg):NAN;}
 // Any proposed edge belongs to the virtual/shadow executor, never GPIO.
 bool proposed_enabled()const{return faults==0&&state!=State::Stopped;}
};
using LegacyOutput=BasicOutput<4>;
using ExpandedOutput=BasicOutput<8>;
using Output=ExpandedOutput;
template<class Config,std::size_t CylinderCapacity>inline bool demand_valid(const Config&t,const BasicOutput<CylinderCapacity>&o,double rpm){
 const bool sequential=t.strategy==Strategy::Sequential;
 if(!strategy_valid(t.strategy)||!firing_order_valid(t.firing_order,t.cylinders)||o.cylinder_count!=t.cylinders||!range(t.max_injection_ms,1,15)||!range(t.max_duty,.1,double(.85f))||!range(t.max_dwell_ms,.5,3.5))return false;
 if(!o.proposed_enabled())return true;
 if(!range(rpm,50,8000)||!range(o.dwell_ms,.5,t.max_dwell_ms)||!finite(o.advance_deg)||
    (o.cylinder_trims_enabled&&(!sequential||!o.cylinder_data)))return false;
 const double interval_ms=60000/rpm*(sequential?2:1);
 for(unsigned cylinder=0;cylinder<t.cylinders;++cylinder)if((!o.fuel_cut&&(!range(o.pulse_for(cylinder),.001,t.max_injection_ms)||o.pulse_for(cylinder)/interval_ms>std::min(double(t.max_duty),.85)))||!range(o.advance_for(cylinder),-5,40))return false;
 return true;
}
class Controller {
 bool seen_=false,was_crank_=true,rev_cut_=false,dfco_=false,fan_=false,afr_running_=false;
 std::uint64_t last_=0,started_=0,dfco_since_=0,boot_=0,afr_started_=0;
 double previous_tps_=0,ae_=1,ego_i_=0;idle::Controller idle_control_;transient::Controller transient_control_;secondary::Controller secondary_control_;boost::Controller boost_control_;
public:
 void reset(){*this=Controller{};}
 template<std::size_t CylinderCapacity>BasicOutput<CylinderCapacity> step(const BasicTune<CylinderCapacity>&t,const Inputs&s,std::uint64_t now){
  BasicOutput<CylinderCapacity> o;o.rpm=s.rpm;o.cylinder_count=t.cylinders;o.cylinder_trims_enabled=t.cylinder_trims_enabled;bool transient_evaluated=false;
  auto finish=[&](){
   if(!(o.faults&BadTune)){
    boost::Input input;input.rpm=s.rpm;input.map_kpa=s.map_kpa;input.tps_pct=s.tps_pct;input.sampled_us=s.sampled_us;
    input.map_qualified=s.map_qualified;input.tps_qualified=s.sensors_valid;
    input.baro_kpa=t.load_model.baro_source==load::BaroSource::Fixed?t.load_model.fixed_baro_kpa:s.aux_pressure_kpa;
    input.baro_qualified=t.load_model.baro_source==load::BaroSource::Fixed||(s.aux_pressure_qualified&&t.load_model.aux_role==load::AuxRole::Baro);
    input.running=o.state==State::Running||o.state==State::Warmup||o.state==State::Overrun;input.cranking=o.state==State::Cranking;
    input.engine_fault=o.faults!=0;input.overrun=o.state==State::Overrun||(o.fuel_cut&&o.transient_enrichment.phase==transient::Phase::Deceleration);
    o.boost_control=boost_control_.step(t.boost_control,input,now);
    if(o.boost_control.inhibit_engine){
     o.faults|=o.boost_control.flags&boost::OverboostLatched?Overboost:o.boost_control.reason==boost::Reason::Clock?Timing:o.boost_control.reason==boost::Reason::Stale?Stale:BadSensor;
     o.state=State::Faulted;o.fuel_cut=o.spark_cut=true;o.pump=false;
     o.pulse_ms=o.dwell_ms=o.duty_pct=0;o.cylinder_pulse_ms.fill(0);o.cylinder_duty_pct.fill(0);o.cylinder_data=false;
     ego_i_=0;ae_=1;dfco_=false;dfco_since_=0;
    }
   }
   if(o.faults||o.state==State::Stopped||o.state==State::Cranking||o.state==State::Overrun){
    const auto reset=transient_control_.inhibit(t.transient_enrichment);
    if(!transient_evaluated)o.transient_enrichment=reset;
    else{o.transient_enrichment.phase=transient::Phase::Inactive;o.transient_enrichment.flags&=~transient::Active;o.transient_enrichment.reason=transient::Reason::Inhibited;o.transient_enrichment.values[transient::RemainingMs]=0;}
   }
   idle::Input input;input.rpm=s.rpm;input.tps_pct=s.tps_pct;input.clt_c=s.clt_c;input.battery_v=s.battery_v;input.sampled_us=s.sampled_us;input.valid=s.sensors_valid;
   input.running=o.state==State::Running||o.state==State::Warmup||o.state==State::Overrun;input.cranking=o.state==State::Cranking;input.overrun=o.state==State::Overrun||(o.fuel_cut&&o.transient_enrichment.phase==transient::Phase::Deceleration);input.engine_fault=o.faults!=0;
   o.idle=idle_control_.step(t.idle_control,{t.idle_enabled,t.idle_target_rpm,t.idle_kp,t.idle_ki},input,now);o.idle_pct=o.idle.duty_pct;return o;
  };
  const double dt=seen_&&now>=last_?(now-last_)/1e6:0;
  const bool timing=(!seen_||now>last_)&&dt<=.1;
  if(!seen_)boot_=now;
  const double rate=dt>0?(s.tps_pct-previous_tps_)/dt:0;
  previous_tps_=s.tps_pct;last_=now;seen_=true;
  if(validate(t)){secondary_control_.reset();o.faults=BadTune;o.state=State::Faulted;o.fuel_cut=o.spark_cut=true;return finish();}
  // A fresh possible stopped/cranking interval invalidates only the measured
  // AFR epoch, even while another input is faulted. It does not certify a
  // physical stop or change the historical ASE epoch. Stale ADC timestamps
  // cannot repeatedly move this start timer.
  if(now>=s.sampled_us&&now-s.sampled_us<=20000&&range(s.rpm,0,t.cranking_rpm))afr_running_=false;
  const auto extra=secondary::requirements(t.secondary_tables);
  o.flex_fuel=flex::assess(t.flex_fuel,s.flex_sample,now,extra.ethanol,t.revision,s.flex_context_match);
  secondary::Input selection_input;selection_input.rpm=s.rpm;selection_input.map_kpa=s.map_kpa;selection_input.tps_pct=s.tps_pct;
  selection_input.emap_kpa=s.aux_pressure_kpa;selection_input.ethanol_pct=o.flex_fuel.sample.observation.ethanol_pct;
  selection_input.map_qualified=s.map_qualified;selection_input.emap_qualified=s.aux_pressure_qualified&&t.load_model.aux_role==load::AuxRole::Emap;
  selection_input.maximum_map_kpa=maximum_map_kpa(t);
  selection_input.ethanol_qualified=o.flex_fuel.value_qualified;selection_input.switches=s.table_switches;
  const bool crank_selection=was_crank_?s.rpm<t.cranking_rpm+100:s.rpm<t.cranking_rpm;
  auto second_fuel=secondary_control_.select(secondary::Kind::Fuel,t.secondary_tables.fuel,selection_input,now,crank_selection);
  auto second_spark=secondary_control_.select(secondary::Kind::Spark,t.secondary_tables.spark,selection_input,now,crank_selection);
  const bool ethanol_ok=!extra.ethanol||o.flex_fuel.value_qualified;
  if(!ethanol_ok){
   const secondary::Rule*rules[]={&t.secondary_tables.fuel,&t.secondary_tables.spark};secondary::Selection*observations[]={&second_fuel,&second_spark};
   for(unsigned n=0;n<2;++n)if(rules[n]->mode==secondary::Mode::Conditional&&rules[n]->condition==secondary::Condition::Ethanol){observations[n]->ok=observations[n]->observation.valid=false;observations[n]->observation.reason=secondary::Reason::RequiredEthanol;}
  }
  o.secondary_fuel=second_fuel.observation;o.secondary_spark=second_spark.observation;
  const auto model=load::evaluate(t.load_model,{s.map_kpa,s.tps_pct,s.aux_pressure_kpa,s.map_qualified,s.aux_pressure_qualified,t.cylinder_trims_enabled,t.transient_enrichment.mode==transient::Mode::MapRate,t.ego_enabled,extra.map||t.boost_control.pressure_enabled,extra.emap,maximum_map_kpa(t)});
  o.load_model=model.observation;
  if(!timing)o.faults|=Timing;
  const bool sensor_ok=s.sensors_valid&&model.ok()&&second_fuel.ok&&second_spark.ok&&ethanol_ok&&o.flex_fuel.control_ok&&range(s.rpm,0,12000)&&range(s.tps_pct,0,100)&&range(s.clt_c,-40,140)&&range(s.iat_c,-40,110)&&range(s.battery_v,7,18)&&range(s.sensor_v,4.75,5.25);
  if(!sensor_ok)o.faults|=BadSensor;
  if(now<s.sampled_us||now-s.sampled_us>20000)o.faults|=Stale;
  if(s.clt_c>=115)o.faults|=OverTemp;
  if(s.clt_c>=t.fan_on_c)fan_=true;else if(s.clt_c<=t.fan_off_c)fan_=false;o.fan=fan_;
  if(sensor_ok&&s.rpm>=t.rpm_limit)rev_cut_=true;
  if(sensor_ok&&s.rpm<t.rpm_limit-t.rpm_hysteresis)rev_cut_=false;
  if(rev_cut_)o.faults|=OverRev;
  const bool stopped=finite(s.rpm)&&s.rpm<=0;
  o.pump=((o.faults&~std::uint32_t(OverRev))==0)&&((now>=boot_&&(now-boot_)/1e6<t.pump_prime_s)||(s.synced&&s.rpm>0));
  if(!stopped&&!s.synced)o.faults|=NoSync;
  if(!stopped&&t.strategy==Strategy::Sequential&&!s.phase_synced)o.faults|=CamPhase;
  if(o.faults){o.state=State::Faulted;o.fuel_cut=o.spark_cut=true;ego_i_=0;ae_=1;dfco_=false;dfco_since_=0;return finish();}
  if(stopped){o.state=State::Stopped;o.fuel_cut=o.spark_cut=true;ego_i_=0;ae_=1;was_crank_=true;dfco_=false;dfco_since_=0;return finish();}
  const bool cranking=was_crank_?s.rpm<t.cranking_rpm+100:s.rpm<t.cranking_rpm;
  if(was_crank_&&!cranking)started_=now;
  was_crank_=cranking;
  if(cranking)afr_running_=false;
  else if(!afr_running_){afr_started_=now;afr_running_=true;}
  o.state=cranking?State::Cranking:(s.clt_c<70?State::Warmup:State::Running);
  const double primary_ve=lookup(t.ve,s.rpm,model.coordinates[0]);
  const double secondary_ve=second_fuel.observation.active?lookup(t.secondary_ve,s.rpm,second_fuel.coordinate):NAN;
  o.ve_pct=secondary::fuel(second_fuel,primary_ve,secondary_ve);o.secondary_fuel=second_fuel.observation;
  o.target_lambda=finite(model.coordinates[2])?lookup(t.lambda,s.rpm,model.coordinates[2]):NAN;
  const double raw_advance=cranking?t.crank_advance_deg:lookup(t.spark,s.rpm,model.coordinates[1]);
  o.flex_fuel.spark_bypassed=cranking;
  const bool flex_active=t.flex_fuel.correction.enabled;
  const double flex_spark=flex_active&&!cranking?o.flex_fuel.corrections.spark_add_deg:0;
  const double primary_advance=flex_active&&!cranking?std::clamp(raw_advance+flex_spark,-5.,40.):raw_advance;
  o.flex_fuel.spark_clamped=primary_advance!=raw_advance+flex_spark;
  const double retard=!cranking&&t.soft_limit_band>0&&s.rpm>t.rpm_limit-t.soft_limit_band?10*(s.rpm-(t.rpm_limit-t.soft_limit_band))/t.soft_limit_band:0;
  const double secondary_spark=second_spark.observation.active?lookup(t.secondary_spark,s.rpm,second_spark.coordinate):NAN;
  const bool switched_spark=second_spark.observation.active&&(t.secondary_tables.spark.mode==secondary::Mode::Conditional||t.secondary_tables.spark.mode==secondary::Mode::Input);
  const double chosen_secondary=flex_active&&!cranking&&switched_spark?std::clamp(secondary_spark+flex_spark,-5.,40.):secondary_spark;
  if(flex_active&&!cranking&&switched_spark)o.flex_fuel.spark_clamped|=chosen_secondary!=secondary_spark+flex_spark;
  o.advance_deg=secondary::spark(second_spark,raw_advance,std::max(-5.0,primary_advance-retard),chosen_secondary,retard);
  if(switched_spark&&flex_active)second_spark.observation.secondary=static_cast<float>(secondary_spark);
  o.secondary_spark=second_spark.observation;
  if(!second_fuel.ok||!second_spark.ok){o.faults|=BadSensor;o.state=State::Faulted;o.fuel_cut=o.spark_cut=true;return finish();}
  o.deadtime_ms=interpolate(t.battery_v,t.deadtime_ms,s.battery_v);
  o.dwell_ms=interpolate(t.battery_v,t.dwell_ms,s.battery_v);
  o.warmup=interpolate(t.coolant_c,cranking?t.crank_pct:t.warmup_pct,s.clt_c)/100;
  if(!cranking&&t.afterstart_s>0&&now>=started_){const double elapsed=(now-started_)/1e6;o.afterstart=1+t.afterstart_pct/100*std::clamp(1-elapsed/t.afterstart_s,0.0,1.0);}
  const bool want_dfco=t.dfco_enabled&&!cranking&&s.clt_c>=60&&s.tps_pct<=t.dfco_tps&&s.rpm>=t.dfco_rpm;
  if(!dfco_&&!want_dfco)dfco_since_=0;
  if(want_dfco){if(!dfco_since_)dfco_since_=now;if(now>=dfco_since_&&(now-dfco_since_)/1e6>=t.dfco_delay_s)dfco_=true;}
  else if(s.tps_pct>t.dfco_tps+.5||s.rpm<t.dfco_rpm-t.dfco_hysteresis||cranking||s.clt_c<60||!t.dfco_enabled){dfco_=false;dfco_since_=0;}
  const bool legacy_transient=t.transient_enrichment.mode==transient::Mode::LegacyTps;
  if(legacy_transient){
   if(!cranking&&dt>0){ae_=1+(ae_-1)*std::exp(-dt/t.accel_decay_s);if(rate>t.accel_threshold_pct_s)ae_=std::max(ae_,1+std::min(.5,rate*t.accel_gain));}else ae_=1;o.accel=ae_;
   o.transient_enrichment=transient_control_.inhibit(t.transient_enrichment,transient::Reason::Legacy);
   if(!cranking&&dt>0){auto&d=o.transient_enrichment;d.values[transient::TpsDot]=static_cast<float>(rate);d.values[transient::WindowMs]=static_cast<float>(dt*1000);d.values[transient::CorrectionPct]=d.values[transient::UnclampedPct]=static_cast<float>(ae_*100);d.flags=finite(rate)?transient::RateValid:0;if(ae_>1.000001){d.phase=transient::Phase::Acceleration;d.flags|=transient::Active;}}
  }else{
   ae_=1;const bool optional_map=!(o.load_model.flags&load::MapRequired);
   transient::Input input{s.tps_pct,s.map_qualified&&range(s.map_kpa,10,maximum_map_kpa(t))?s.map_kpa:NAN,s.rpm,s.clt_c,s.sampled_us,!cranking&&!dfco_,optional_map,maximum_map_kpa(t)};
   o.transient_enrichment=transient_control_.step(t.transient_enrichment,input,now);o.accel=o.transient_enrichment.correction();
  }
  transient_evaluated=true;
  const bool ego=t.ego_enabled&&s.lambda_ready&&range(s.lambda,.65,1.5)&&s.clt_c>=t.ego_min_clt&&!cranking&&!dfco_&&o.ve_pct>0&&s.tps_pct<60&&o.afterstart<=1.001&&(legacy_transient?ae_<1.02:!o.transient_enrichment.active());
  if(ego){const double e=s.lambda/o.target_lambda-1;ego_i_=std::clamp(ego_i_+e*t.ego_ki*dt,-double(t.ego_limit),double(t.ego_limit));o.ego=std::clamp(1+e*t.ego_kp+ego_i_,1-double(t.ego_limit),1+double(t.ego_limit));}else ego_i_=0;
  // Modeled charge basis per cylinder/cycle. Pure Alpha-N uses100kPa;
  // the original MAP path retains its input precision and operation order.
  const double afr=load::afr_factor(o.load_model,t.load_model,o.target_lambda,s.lambda,s.lambda_ready,cranking,afr_running_&&now>=afr_started_?(now-afr_started_)/1e6:NAN);
  o.air_mg=model.fuel_pressure_kpa*1000*(t.displacement_cc/t.cylinders*1e-6)*(o.ve_pct/100)/(287.05*(s.iat_c+273.15))*1e6;
  double base=t.load_model.afr==load::Afr::Target?o.air_mg/(t.stoich_afr*o.target_lambda)*o.warmup*o.afterstart*o.ego:o.air_mg/t.stoich_afr*afr*o.warmup*o.afterstart*o.ego;
  double fuel_mg=t.load_model.afr==load::Afr::Target?o.air_mg/(t.stoich_afr*o.target_lambda)*o.warmup*o.afterstart*o.accel*o.ego:o.air_mg/t.stoich_afr*afr*o.warmup*o.afterstart*o.accel*o.ego;
  // Preserve the exact historical Off arithmetic. Enabled factors precede
  // the reference AE adder; neither deadtime nor that adder is multiplied.
  if(flex_active){base*=o.flex_fuel.corrections.fuel_factor;base*=o.flex_fuel.corrections.temperature_factor;fuel_mg*=o.flex_fuel.corrections.fuel_factor;fuel_mg*=o.flex_fuel.corrections.temperature_factor;}
  if(base==0)o.load_model.flags|=load::ZeroBaseFuel;
  if(!legacy_transient&&t.transient_enrichment.apply==transient::Apply::AddReference&&o.transient_enrichment.phase==transient::Phase::Acceleration&&o.accel>1){
   // Reference adder is a full-cycle dose at100kPa,25C,100%VE,lambda1.
   // It is independent of current MAP/VE/WUE/EGO. Split by actual openings
   // below, scale the complete dose by cylinder trim, then add deadtime once.
   const double reference=100000*(t.displacement_cc/t.cylinders*1e-6)/(287.05*298.15)*1e6/t.stoich_afr;
   const double added=o.flex_fuel.zero_factor?0:reference*(o.accel-1);fuel_mg=base+added;
   o.transient_enrichment.values[transient::AddedFuelMg]=static_cast<float>(added);
   o.accel=base>0?fuel_mg/base:NAN;
   if(!finite(o.accel)||o.accel>std::numeric_limits<float>::max()){o.accel=NAN;o.load_model.flags|=load::AccelRatioUnavailable;}
  }
  const bool transient_cut=!legacy_transient&&o.transient_enrichment.phase==transient::Phase::Deceleration&&o.transient_enrichment.correction()==0;
  const bool zero_fuel=transient_cut||o.flex_fuel.zero_factor||fuel_mg==0;
  const double flow_mg_ms=t.injector_cc_min*t.fuel_density_g_cc/60;
  // Dead time belongs to each opening, not to the four-stroke fuel mass.
  const double openings=t.strategy==Strategy::Sequential?1:2;
  o.pulse_ms=fuel_mg/(openings*flow_mg_ms)+o.deadtime_ms;
  const double rev_ms=60000/s.rpm,interval_ms=rev_ms*(t.strategy==Strategy::Sequential?2:1);o.duty_pct=o.pulse_ms/interval_ms*100;
  if(zero_fuel){o.fuel_cut=true;o.pulse_ms=o.duty_pct=0;}
  o.cylinder_data=true;o.cylinder_trims_enabled=t.cylinder_trims_enabled;
  for(unsigned cylinder=0;cylinder<t.cylinders;++cylinder){
   const double pct=t.cylinder_trims_enabled?lookup(t.cylinder_fuel[cylinder],s.rpm,model.coordinates[3]):100;
   const bool switched=second_spark.observation.active&&(t.secondary_tables.spark.mode==secondary::Mode::Conditional||t.secondary_tables.spark.mode==secondary::Mode::Input);
   double demand=(switched?secondary_spark:raw_advance)+(t.cylinder_trims_enabled?t.cylinder_spark_deg[cylinder]:0);
   if(flex_active&&!cranking)demand+=flex_spark;
   const double nominal=std::clamp(demand,-5.0,cranking?15.0:40.0);
   const double advance=nominal-retard;
   o.cylinder_fuel_pct[cylinder]=pct;
   const double corrected=std::clamp(advance,-5.0,40.0);auto cylinder_selection=second_spark;
   o.cylinder_advance_deg[cylinder]=secondary::spark(cylinder_selection,nominal,corrected,switched?nominal:secondary_spark,retard);
   if(demand!=nominal||cylinder_selection.observation.clamped)o.cylinder_spark_clamp_mask|=1U<<cylinder;
   if(advance!=corrected)o.cylinder_retard_floor_mask|=1U<<cylinder;
   const double pulse=zero_fuel?0:fuel_mg/(openings*flow_mg_ms)*(pct/100)+o.deadtime_ms;
   const double duty=pulse/interval_ms*100;
   o.cylinder_pulse_ms[cylinder]=pulse;o.cylinder_duty_pct[cylinder]=duty;
   if(!finite(pulse)||pulse>t.max_injection_ms||duty>t.max_duty*100)o.cylinder_capacity_mask|=1U<<cylinder;
  }
  // Judge capacity on actual channel demand, so safe negative trims can reduce
  // an otherwise excessive base demand. One failed cylinder inhibits every channel.
  if(o.cylinder_capacity_mask||o.dwell_ms>t.max_dwell_ms||o.dwell_ms>=rev_ms){o.faults|=Capacity;o.state=State::Faulted;o.fuel_cut=o.spark_cut=true;o.pulse_ms=o.dwell_ms=0;o.cylinder_pulse_ms.fill(0);o.cylinder_duty_pct.fill(0);return finish();}
  if(dfco_){o.state=State::Overrun;o.fuel_cut=true;o.pulse_ms=0;o.duty_pct=0;o.cylinder_pulse_ms.fill(0);o.cylinder_duty_pct.fill(0);}

  return finish();
 }
};
struct Edge {std::uint64_t time_us=0;unsigned channel=0;bool high=false;};
template<std::size_t CylinderCapacity>struct BasicPlan {std::array<Edge,4*CylinderCapacity> edges{};unsigned count=0;bool valid=false;};
using LegacyPlan=BasicPlan<4>;
using ExpandedPlan=BasicPlan<8>;
using Plan=ExpandedPlan;
template<std::size_t CylinderCapacity>inline BasicPlan<CylinderCapacity> plan_revolution(const BasicTune<CylinderCapacity>&t,const BasicOutput<CylinderCapacity>&o,std::uint64_t gap_us){
 BasicPlan<CylinderCapacity> p;if(t.strategy==Strategy::Sequential||!o.proposed_enabled()||!demand_valid(t,o,o.rpm)||validate(t))return p;
 const double rev_us=60000000/o.rpm;
 auto add=[&](unsigned channel,double start_deg,double width_us){
  start_deg=std::fmod(start_deg,360.0);if(start_deg<0)start_deg+=360;
  const auto offset=std::uint64_t(std::llround(start_deg/360*rev_us));
  const auto width=std::uint64_t(std::llround(width_us));
  if(!width||gap_us>std::numeric_limits<std::uint64_t>::max()-offset-width)return false;
  const auto start=gap_us+offset;
  p.edges[p.count++]={start,channel,true};p.edges[p.count++]={start+width,channel,false};return true;
 };
 const auto phase=channels::compression_phases(t.firing_order,t.cylinders);
 for(unsigned cylinder=0;cylinder<t.cylinders;++cylinder)if(!o.fuel_cut){
  // Semi-sequential pairs share a closing angle every crank revolution. The
  // full four-stroke mass is divided between two openings by Controller.
  const double start=t.strategy==Strategy::SemiSequential?
    t.tooth1_btdc_deg+phase[cylinder]+t.injection_end_deg-o.pulse_for(cylinder)*1000/rev_us*360:t.tooth1_btdc_deg+180;
  if(!add(channels::injector(cylinder),start,o.pulse_for(cylinder)*1000))return BasicPlan<CylinderCapacity>{};
 }
 // A dedicated coil command per cylinder. Even cylinder counts have opposing
 // compression phases modulo360; odd counts have no opposing-cylinder pairs.
 for(unsigned cylinder=0;cylinder<t.cylinders;++cylinder)if(!o.spark_cut&&!add(channels::coil(cylinder),t.tooth1_btdc_deg+phase[cylinder]-o.advance_for(cylinder)-o.dwell_ms*1000/rev_us*360,o.dwell_ms*1000))return BasicPlan<CylinderCapacity>{};
 std::sort(p.edges.begin(),p.edges.begin()+p.count,[](const Edge&a,const Edge&b){return a.time_us<b.time_us||(a.time_us==b.time_us&&a.high<b.high);});p.valid=true;return p;
}
}
