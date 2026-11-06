#include "ecu/load_model.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::load;
Config alpha(){Config c;c.fuel_source=c.spark_source=Source::Tps;c.ve_axis=c.spark_axis=c.lambda_axis=c.trim_axis=Axis::TpsPercent;c.pressure=Pressure::None;return c;}
Input input(){Input i;i.map_kpa=45.123456789;i.tps_pct=12.234567891;i.map_qualified=true;return i;}
void sources_and_units(){
 Config c;auto i=input();assert(valid(c));auto e=evaluate(c,i);assert(e.ok()&&e.coordinates[0]==i.map_kpa&&e.fuel_pressure_kpa==i.map_kpa);
 c=alpha();assert(valid(c));i.map_kpa=NAN;i.map_qualified=false;e=evaluate(c,i);assert(e.ok()&&e.coordinates[0]==i.tps_pct&&e.fuel_pressure_kpa==100);
 assert(!(e.observation.flags&(MapRequired|MapCalibrated|PressureGuardAvailable))&&std::isnan(e.observation.values[EmapKpa]));
 c.spark_source=Source::Map;assert(!valid(c));c.spark_axis=Axis::MapKpa;assert(valid(c));e=evaluate(c,i);assert(!e.ok()&&e.observation.reason==Reason::RequiredMap);
 c=Config{};c.fuel_source=Source::PressureRatio;c.ve_axis=c.lambda_axis=c.trim_axis=Axis::PressureRatioPercent;c.aux_role=AuxRole::Emap;
 i=input();i.map_kpa=100;i.aux_kpa=80;i.aux_qualified=true;e=evaluate(c,i);assert(e.ok()&&e.coordinates[0]==125&&e.coordinates[1]==100&&e.coordinates[2]==125);
 for(double bad:std::array<double,6>{0.,-1.,19.,501.,INFINITY,NAN}){i.aux_kpa=bad;e=evaluate(c,i);assert(!e.ok()&&e.observation.reason==Reason::RequiredEmap);}
 assert(axis_min(Axis::TpsPercent)==0&&axis_max(Axis::TpsPercent)==100&&axis_max(Axis::PressureRatioPercent)==600);
}
void pressure_and_roles(){
 auto c=alpha();c.pressure=Pressure::MapBaro;c.fixed_baro_kpa=75;auto i=input();i.map_kpa=75;auto e=evaluate(c,i);assert(e.ok()&&e.fuel_pressure_kpa==100&&e.observation.flags&ManualBaro);
 c.baro_source=BaroSource::Aux;assert(!valid(c));c.aux_role=AuxRole::Baro;assert(valid(c));i.aux_kpa=90;i.aux_qualified=true;e=evaluate(c,i);assert(e.ok()&&e.fuel_pressure_kpa==100*i.map_kpa/90&&!(e.observation.flags&ManualBaro));
 i.aux_qualified=false;e=evaluate(c,i);assert(!e.ok()&&e.observation.reason==Reason::RequiredBaro);
 c.fuel_source=Source::PressureRatio;c.ve_axis=c.lambda_axis=c.trim_axis=Axis::PressureRatioPercent;assert(!valid(c)); // A single J16 role cannot supply two pressures.
 c=alpha();i=input();i.map_kpa=111;e=evaluate(c,i);assert(!e.ok()&&e.observation.reason==Reason::KnownOverpressure);
 i.map_kpa=0;e=evaluate(c,i);assert(e.ok()&&!(e.observation.flags&PressureGuardAvailable));
 i.map_qualified=false;i.map_kpa=111;e=evaluate(c,i);assert(e.ok()&&!(e.observation.flags&PressureGuardAvailable));
 c=alpha();c.trim_source=Source::Map;c.trim_axis=Axis::MapKpa;assert(!requirements(c,false).map&&requirements(c,true).map&&requirements(alpha(),false,true).map);
}
void afr_and_validation(){
 auto c=alpha();auto e=evaluate(c,input());auto&o=e.observation;
 assert(afr_factor(o,c,.8,1.1,false,true,0)==1/.8&&o.afr_state()==AfrState::Target);
 c.afr=Afr::Off;assert(afr_factor(o,c,.8,1.1,true,false,20)==1&&!(o.flags&(MeasuredAfrActive|AfrWaiting))&&o.afr_state()==AfrState::Off);
 c.afr=Afr::Measured;assert(afr_factor(o,c,.8,1.1,true,false,9.999)==1&&o.flags&AfrWaiting);
 assert(afr_factor(o,c,.8,1.1,true,false,10)==1.1/.8&&o.flags&MeasuredAfrActive);
 for(bool ready:{false,true})for(bool cranking:{false,true})if(!ready||cranking)assert(afr_factor(o,c,.8,1.1,ready,cranking,20)==1&&o.flags&AfrWaiting);
 for(double bad:std::array<double,4>{.64,1.51,INFINITY,NAN})assert(afr_factor(o,c,.8,bad,true,false,20)==1&&o.flags&AfrWaiting);
 for(double bad:std::array<double,4>{0.,-1.,INFINITY,NAN})assert(std::isnan(afr_factor(o,c,bad,1,true,false,20))&&o.reason==Reason::InvalidConfig);
 for(float bad:{49.f,111.f,INFINITY,NAN}){auto t=c;t.fixed_baro_kpa=bad;assert(!valid(t));}
 c.afr=static_cast<Afr>(3);assert(!valid(c));
}
int main(){sources_and_units();pressure_and_roles();afr_and_validation();std::cout<<"Load sources/units, independent pressure factors, shared-role rejection, optional-MAP guard and AFR readiness passed\n";}
