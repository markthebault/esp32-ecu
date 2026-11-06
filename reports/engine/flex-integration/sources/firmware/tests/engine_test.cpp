#include "ecu/engine.hpp"
#include "ecu/engine_scheduler.hpp"
#include "ecu/engine_binding.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::engine;
Inputs good(std::uint64_t now,double rpm=1000){return {rpm,45,10,85,25,1,13.8,5,now,true,true,true};}
int main(){
 Tune t;assert(!validate(t));auto boundary=t;boundary.lambda.cells[0]=1.2f;boundary.max_duty=.85f;assert(!validate(boundary));Map m;for(unsigned y=0;y<bins;++y)for(unsigned x=0;x<bins;++x)m.cells[y*bins+x]=m.rpm[x]/1000+m.load[y];
 assert(std::abs(lookup(m,1500,42)-43.5)<1e-5);assert(lookup(m,0,0)==m.cells[0]);
 auto bad=t;bad.max_dwell_ms=4;assert(validate(bad));bad=t;bad.ve.rpm[1]=bad.ve.rpm[0];assert(validate(bad));bad=t;bad.spark.cells[0]=NAN;assert(validate(bad));
 Controller c;auto s=good(1000);auto o=c.step(t,s,1000);assert(o.faults==0&&o.pulse_ms>1&&o.pulse_ms<5&&o.dwell_ms<=3.5);
 auto p=plan_revolution(t,o,10000);assert(p.valid&&p.count==16);unsigned mask=0;for(unsigned i=0;i<p.count;++i){assert(p.edges[i].channel<8);if(i)assert(p.edges[i].time_us>=p.edges[i-1].time_us);mask|=1<<p.edges[i].channel;}assert(mask==255);
 // Fuel mass really scales with MAP and inverse injector flow, not fixed demo readings.
 Controller a,b;auto oa=a.step(t,good(1000),1000);s=good(1000);s.map_kpa=90;auto ob=b.step(t,s,1000);assert(std::abs((ob.pulse_ms-ob.deadtime_ms)/(oa.pulse_ms-oa.deadtime_ms)-2)<1e-6);
 for(auto fault:{BadSensor,Stale,NoSync,OverTemp,OverRev,Timing}){
  Controller ctrl;s=good(1000);ctrl.step(t,s,1000);s=good(6000);std::uint64_t now=6000;
  switch(fault){case BadSensor:s.map_kpa=NAN;break;case Stale:s.sampled_us=0;now=30000;break;case NoSync:s.synced=false;break;case OverTemp:s.clt_c=120;break;case OverRev:s.rpm=6600;break;case Timing:now=1000;break;default:break;}
  auto f=ctrl.step(t,s,now);assert(f.faults&fault);assert(f.fuel_cut&&f.spark_cut);assert(!plan_revolution(t,f,now).valid);
 }
 Controller cr;auto cold=good(1000,200);cold.clt_c=0;auto co=cr.step(t,cold,1000);assert(co.state==State::Cranking&&co.advance_deg==5&&co.warmup>2);
 cold=good(6000,1000);cold.clt_c=0;co=cr.step(t,cold,6000);assert(co.state==State::Warmup&&co.afterstart>1);
 // Rev limit latches with hysteresis, then recovers without stale trim.
 Controller rc;s=good(1000,6600);auto limited=rc.step(t,s,1000);assert(limited.faults&OverRev);assert(limited.pump);s=good(6000,6400);assert(rc.step(t,s,6000).faults&OverRev);s=good(11000,6200);assert(!(rc.step(t,s,11000).faults&OverRev));
 // A running engine recovering from a temporary rev cut must not restart ASE.
 Controller ase;auto ase_tune=t;ase_tune.afterstart_s=.05f;
 for(unsigned i=1;i<=100;++i){s=good(i*1000);o=ase.step(ase_tune,s,i*1000);}assert(o.afterstart==1);
 s=good(101000,6600);assert(ase.step(ase_tune,s,101000).faults&OverRev);
 s=good(102000,1000);o=ase.step(ase_tune,s,102000);assert(o.afterstart==1);
 // Delayed DFCO, then immediate fuel restoration after a throttle opening.
 t.afterstart_pct=0;Controller df;
 for(unsigned i=1;i<=700;++i){s=good(i*1000,3000);s.tps_pct=0;o=df.step(t,s,i*1000);}assert(o.state==State::Overrun&&o.fuel_cut&&o.pulse_ms==0);
 s=good(701000,2500);s.tps_pct=10;o=df.step(t,s,701000);assert(!o.fuel_cut&&o.pulse_ms>0);
 // DFCO entry delay must be continuous; inactive hysteresis cannot accumulate time.
 Controller delayed;for(unsigned i=1;i<=300;++i){s=good(i*1000,2100);s.tps_pct=0;delayed.step(t,s,i*1000);}
 for(unsigned i=301;i<=700;++i){s=good(i*1000,1900);s.tps_pct=0;delayed.step(t,s,i*1000);}
 s=good(701000,2100);s.tps_pct=0;assert(!delayed.step(t,s,701000).fuel_cut);
 // Lambda feedback corrects lean error in the right direction and stays bounded.
 t.ego_enabled=true;Controller ego;
 for(unsigned i=1;i<=5000;++i){s=good(i*1000);s.lambda=1.1;o=ego.step(t,s,i*1000);}assert(o.ego>1&&o.ego<=1.100001);
 s=good(5001000);s.lambda_ready=false;o=ego.step(t,s,5001000);assert(o.ego==1);
 // Missing trigger does not count as synchronization even with a valid tune.
 s=good(1000);s.synced=false;Controller nosync;assert(nosync.step(t,s,1000).faults&NoSync);
 // Generic display units/confirmation cannot turn raw volts into physical inputs.
 for(double rail:{4.74,5.26}){Controller power;s=good(1000);s.sensor_v=rail;assert(power.step(t,s,1000).faults&BadSensor);}
 ecu::config::Config profile;ecu::web::Sample raw;raw.adc_ok=true;raw.synced=true;raw.rpm=1000;
 const char*ids[]={"map","tps","clt","iat","wideband","postcat"};const char*units[]={"kPa","%","C","C","lambda","V"};
 for(unsigned i=0;i<6;++i){auto&sensor=profile.sensors[i];std::strcpy(sensor.id,ids[i]);std::strcpy(sensor.label,ids[i]);std::strcpy(sensor.unit,units[i]);sensor.mode=ecu::config::Mode::Linear;sensor.confirmed=true;sensor.points[0]={.5,0};sensor.points[1]={4.5,100};raw.raw[i]=1489;}
 profile.sensors[0].y0=10;profile.sensors[0].y1=110;raw.raw[6]=1317;raw.raw[7]=3723;
 assert(ecu::config::valid(profile));assert(bind_inputs(raw,profile,1000).input.sensors_valid);
 profile.sensors[1].mode=ecu::config::Mode::Voltage;assert(ecu::config::valid(profile));assert(!bind_inputs(raw,profile,1000).input.sensors_valid);
 profile.sensors[1].mode=ecu::config::Mode::Linear;profile.sensors[2].confirmed=false;assert(!bind_inputs(raw,profile,1000).input.sensors_valid);
 // Advance crossing 0/360 must not skip an ignition or double-fire a coil.
 for(double offset:{5.,10.,90.,185.,190.}){
  Tune timing_tune;timing_tune.tooth1_btdc_deg=offset;Output demand;
  demand.state=State::Running;demand.rpm=1000;demand.pulse_ms=2;demand.dwell_ms=2.8;demand.advance_deg=5;
  AngleScheduler scheduler;std::array<std::uint64_t,4> last_spark{};std::array<unsigned,4> sparks{};
  for(unsigned tooth=0;tooth<600;++tooth){
   const auto now=std::uint64_t(std::llround(tooth*1000000.0/1000));
   while(scheduler.next_time()<=now){Edge edge;assert(scheduler.pop(edge));if(edge.channel>=4&&!edge.high){unsigned ch=edge.channel-4;if(last_spark[ch])assert(edge.time_us-last_spark[ch]<65000);last_spark[ch]=edge.time_us;++sparks[ch];}}
   if(tooth==100)demand.advance_deg=15;
   if(tooth==220)demand.advance_deg=5;
   assert(scheduler.tooth(timing_tune,demand,now,tooth%60,60,now,now));
  }
  for(auto n:sparks)assert(n>=9);
 }
 // Sweep every trigger offset and tooth phase for legal late advance changes.
 // A full-dwell committed event may retain its old advance for one firing.
 for(unsigned scenario=0;scenario<2;++scenario)for(unsigned offset=0;offset<360;++offset)for(unsigned change=60;change<120;++change){
  Tune timing_tune;timing_tune.tooth1_btdc_deg=offset;Output demand;
  demand.state=State::Running;demand.rpm=scenario?1000:500;demand.pulse_ms=2;demand.dwell_ms=2.8;demand.advance_deg=scenario?-5:5;
  AngleScheduler scheduler;std::array<std::uint64_t,8> on{};std::array<bool,8> high{};
  for(unsigned tooth=0;tooth<180;++tooth){
   const auto now=std::uint64_t(tooth)*(scenario?1000:2000);
   while(scheduler.next_time()<=now){Edge edge;assert(scheduler.pop(edge));assert(!scheduler.event_forced_cut());
    assert(high[edge.channel]!=edge.high);high[edge.channel]=edge.high;
    if(edge.high)on[edge.channel]=edge.time_us;else assert(edge.time_us-on[edge.channel]<=(edge.channel>=4?3500:15000));
   }
   if(tooth==change)demand.advance_deg=scenario?40:15;
   assert(scheduler.tooth(timing_tune,demand,now,tooth%60,60,now,now));
  }
 }
 // Selective fuel/spark cuts must retain the closing edge of an active pulse,
 // suppress new starts, then resume cleanly even after several revolutions.
 for(bool coil:{false,true}){
  Tune timing_tune;Output demand;demand.state=State::Running;demand.rpm=1000;
  demand.pulse_ms=10;demand.dwell_ms=2.8;demand.advance_deg=15;
  AngleScheduler scheduler;std::array<bool,8> high{};bool cut_active=false,saw_active=false,saw_resume=false;
  const unsigned cut_tooth=coil?130:166;
  for(unsigned tooth=0;tooth<400;++tooth){
   const auto now=std::uint64_t(tooth)*1000;
   while(scheduler.next_time()<=now){Edge edge;assert(scheduler.pop(edge));assert(!scheduler.event_forced_cut());
    assert(edge.high!=high[edge.channel]);high[edge.channel]=edge.high;
    if((edge.channel>=4)==coil&&edge.high){assert(!cut_active);if(tooth>260)saw_resume=true;}
   }
   if(tooth==cut_tooth){for(unsigned ch=coil?4:0;ch<(coil?8:4);++ch)saw_active|=high[ch];cut_active=true;}
   if(tooth==260){for(unsigned ch=coil?4:0;ch<(coil?8:4);++ch)assert(!high[ch]);cut_active=false;}
   demand.fuel_cut=!coil&&cut_active;demand.spark_cut=coil&&cut_active;
   demand.pulse_ms=demand.fuel_cut?0:10;
   assert(scheduler.tooth(timing_tune,demand,now,tooth%60,60,now,now));
  }
  assert(saw_active&&saw_resume);
 }
 std::cout<<"Engine maps, mass/flow, correction states, virtual events, supervision, rev hysteresis, DFCO and lambda tests passed\n";
}
