#include "ecu/engine.hpp"
#include <iostream>
using namespace ecu;
int main(){
 engine::Tune t;t.afterstart_pct=0;t.dfco_enabled=false;t.warmup_pct.fill(100);t.flex_fuel.correction.enabled=t.flex_fuel.correction.temperature_enabled=true;
 t.flex_fuel.correction.fuel_pct={{100,110,120,130,140,150}};t.flex_fuel.correction.temperature_pct={{80,90,95,100,110,120}};
 engine::Inputs s;s.rpm=2000;s.map_kpa=50;s.tps_pct=10;s.clt_c=85;s.iat_c=25;s.lambda=1;s.battery_v=14;s.sensor_v=5;s.synced=s.phase_synced=s.sensors_valid=true;s.sampled_us=1000000;
 flex::Capture c(t.flex_fuel.capture);c.edge(920000,true);for(unsigned n=1;n<=8;++n){c.edge(920000+n*10000-3000,false);c.edge(920000+n*10000,true);}s.flex_sample={c.observe(1000000),t.flex_fuel.capture,t.revision};
 for(unsigned mutation=0;mutation<5;++mutation){auto x=s;auto&o=x.flex_sample.observation;const char*name="";
  switch(mutation){case 0:name="frequency400_above_fault_and_width_above_period";o.frequency_hz=400;o.window_start_us=980000;break;
   case 1:name="frequency10_below_calibration";o.frequency_hz=10;o.window_start_us=200000;break;
   case 2:name="ethanol99_from100Hz_filterOff";o.ethanol_pct=99;break;
   case 3:name="temperature120_from3ms_filterOff";o.fuel_temp_c=120;break;
   case 4:name="unfiltered_values_NaN";o.unfiltered_ethanol_pct=o.unfiltered_fuel_temp_c=NAN;break;}
  engine::Controller controller;const auto out=controller.step(t,x,1000000);
  std::cout<<name<<" faults="<<out.faults<<" control_ok="<<out.flex_fuel.control_ok<<" raw_qualified="<<out.flex_fuel.raw_qualified<<" fuel_factor="<<out.flex_fuel.corrections.fuel_factor<<" temp_factor="<<out.flex_fuel.corrections.temperature_factor<<" reason="<<flex::reason_name(out.flex_fuel.reason)<<"\n";
 }
}
