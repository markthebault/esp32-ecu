#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace ecu::engine;
struct Input {std::uint64_t delivery,time;bool cam;double angle;};
void phase_test(unsigned slots,unsigned rpm,unsigned delay,bool second_start=false,unsigned crank_delay=0,double cam_deg=180){
 AngleConfig cfg;cfg.strategy=Strategy::Sequential;cfg.cam_sync_deg=cam_deg;PhaseDecoder phase({slots,2,8000},cfg);
 const double period=60000000.0/(rpm*slots),step=360.0/slots;std::vector<Input> stream;
 const unsigned first=second_start?slots:0;
 for(unsigned n=first;n<first+slots*10;++n)if(n%slots<slots-2){auto time=std::uint64_t(std::llround(1+n*period));stream.push_back({time+crank_delay,time,false,n*step});}
 const auto end=stream.back().time;
 for(unsigned cycle=0;cycle<6;++cycle){const double angle=std::fmod(90+cam_deg,720)+cycle*720;if(angle<first*step)continue;auto time=std::uint64_t(std::llround(1+angle/step*period));if(time<=end)stream.push_back({time+delay,time,true,angle});}
 std::sort(stream.begin(),stream.end(),[](const auto&a,const auto&b){return a.delivery<b.delivery||(a.delivery==b.delivery&&a.cam<b.cam);});
 bool locked=false;
 for(const auto&e:stream){
  if(e.cam)phase.cam(e.time,e.delivery);else{
   phase.edge(e.time,e.delivery);
   if(phase.phase_synced()){
    const auto expected=unsigned(std::llround(e.angle/step))%(slots*2);
    assert(phase.phase_tooth()==expected);locked=true;
   }
  }
  phase.tick(e.delivery);assert(!phase.faulted());
 }
 if(!(locked&&phase.phase_synced()&&phase.accepted()>=3&&phase.rejected()==0))std::cerr<<"phase case slots="<<slots<<" rpm="<<rpm<<" cam_delay="<<delay<<" crank_delay="<<crank_delay<<" second="<<second_start<<" cam="<<cam_deg<<" accepted="<<phase.accepted()<<" rejected="<<phase.rejected()<<" reason="<<PhaseDecoder::reason_name(phase.reason())<<"\n";
 assert(locked&&phase.phase_synced()&&phase.accepted()>=3&&phase.rejected()==0);
 // A same-timestamp duplicate after acquisition must never change parity.
 assert(!phase.cam(phase.last_cam_us()));assert(phase.faulted()&&phase.losses()==1);
 const auto losses=phase.losses();phase.reset();assert(!phase.faulted()&&!phase.phase_synced()&&phase.losses()==losses);
}
void transient_test(double ramp,unsigned crank_delay,unsigned cam_delay){
 AngleConfig cfg;cfg.strategy=Strategy::Sequential;PhaseDecoder phase({60,2,8000},cfg);std::vector<Input> stream;
 auto clock=[&](double a){return std::uint64_t(std::llround(1+a*(1000./6)+ramp*a*a+300*std::sin(a*3.141592653589793/90)));};
 for(unsigned n=0;n<1200;++n)if(n%60<58){const auto us=clock(n*6.);stream.push_back({us+crank_delay,us,false,n*6.});}
 for(unsigned cycle=0;cycle<10;++cycle){const double angle=540+cycle*720;const auto us=clock(angle);stream.push_back({us+cam_delay,us,true,angle});}
 std::sort(stream.begin(),stream.end(),[](const auto&a,const auto&b){return a.delivery<b.delivery||(a.delivery==b.delivery&&a.cam<b.cam);});
 bool locked=false;for(const auto&e:stream){if(e.cam)phase.cam(e.time,e.delivery);else{phase.edge(e.time,e.delivery);if(phase.phase_synced()){assert(phase.phase_tooth()==unsigned(std::llround(e.angle/6))%120);locked=true;}}phase.tick(e.delivery);assert(!phase.faulted());}
 assert(locked&&phase.phase_synced()&&phase.rejected()==0);
}
void acquisition_noise_test(){
 AngleConfig cfg;cfg.strategy=Strategy::Sequential;PhaseDecoder phase({60,2,8000},cfg);
 for(unsigned n=0;n<500;++n){const auto us=std::uint64_t(n*1000+1);if(n%60<58)phase.edge(us);if(n==90||n==210||n==270||n==330||n==450)phase.cam(us);if(n<450)assert(!phase.phase_synced());}
 assert(phase.phase_synced()&&phase.rejected()==1);
 const auto due=phase.deadline();assert(!phase.cam(due,due));assert(phase.faulted());
}
void missing_cam_test(){
 AngleConfig cfg;cfg.strategy=Strategy::Sequential;cfg.cam_sync_deg=180;PhaseDecoder phase({60,2,8000},cfg);
 bool locked=false,failed=false;std::uint64_t previous_deadline=UINT64_MAX;
 for(unsigned n=0;n<600;++n){
  auto time=std::uint64_t(1+n*1000);
  if(n%60<58)phase.edge(time);
  if(n==45||n==165||n==285)phase.cam(time);
  if(phase.phase_synced()){locked=true;previous_deadline=phase.deadline();}
  phase.tick(time);
  if(phase.faulted()){failed=true;assert(time>=previous_deadline&&time-previous_deadline<=1000);break;}
 }
 assert(locked&&failed&&phase.reason()==PhaseDecoder::Reason::Timeout&&phase.losses()==1);
}
void scheduler_test(){
 Tune t;t.strategy=Strategy::Sequential;Output out;out.state=State::Running;out.rpm=1000;out.advance_deg=10;out.pulse_ms=3;out.dwell_ms=2.8;
 AngleScheduler scheduler;std::array<unsigned,8> counts{};std::array<std::uint64_t,8> rise{};
 constexpr double compression[4]={90,630,270,450};
 for(unsigned n=0;n<600;++n){
  const auto time=std::uint64_t(1+n*1000);Edge e;
  while(scheduler.next_time()<=time){assert(scheduler.pop(e));assert(!scheduler.event_forced_cut());
   if(e.high)rise[e.channel]=e.time_us;
   else{
    assert(e.time_us-rise[e.channel]==(e.channel<4?3000:2800));
    if(e.time_us>240001&&e.time_us<=480001){
     ++counts[e.channel];double angle=std::fmod((e.time_us-1)*.006,720);
     const double goal=std::fmod(compression[e.channel%4]+(e.channel<4?540:-10)+720,720);
     assert(std::abs(angle-goal)<.007);
    }
   }
  }
  if(n%60<58)assert(scheduler.tooth(t,out,time,n%120,60,time,time));
 }
 for(auto count:counts)assert(count==2);
 assert(!scheduler.failed());
 // The legacy one-revolution preview must not misrepresent a720-degree plan.
 assert(!plan_revolution(t,out,0).valid);
}
void mass_test(){
 Tune batch,seq;seq.strategy=Strategy::Sequential;Inputs in;in.rpm=1000;in.map_kpa=45;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.battery_v=14;in.sensor_v=5;in.synced=in.sensors_valid=in.phase_synced=true;in.sampled_us=1;
 Controller a,b;auto x=a.step(batch,in,1),y=b.step(seq,in,1);assert(!x.faults&&!y.faults);
 assert(std::abs(y.pulse_ms-y.deadtime_ms-2*(x.pulse_ms-x.deadtime_ms))<1e-9);
 assert(std::abs(y.duty_pct-y.pulse_ms/120*100)<1e-9);
 in.phase_synced=false;in.sampled_us=1001;y=b.step(seq,in,1001);assert(y.faults&CamPhase);assert(y.fuel_cut&&y.spark_cut);
}
struct IO {unsigned mask=0;void all_low(){mask=0;}bool write(unsigned ch,bool high){if(high)mask|=1U<<ch;else mask&=~(1U<<ch);return true;}};
void watchdog_test(){
 using namespace ecu::timing;Executor core;IO io;Command cmd;cmd.angle.strategy=Strategy::Sequential;cmd.sequence=1;cmd.tune_revision=cmd.sensor_revision=1;cmd.command_us=cmd.sampled_us=1;
 core.progress(1,io);core.command(cmd,1,io);core.phase(true,3001,1,io);
 cmd.sequence++;cmd.command_us=cmd.sampled_us=2;cmd.output.state=State::Running;cmd.output.rpm=1000;cmd.output.pulse_ms=3;cmd.output.dwell_ms=2.8;
 core.command(cmd,2,io);assert(core.next_alarm()==3001);
 core.dispatch(3001,io);assert(core.stats().fault==Cause::CamPhase&&!io.mask);
 core.phase(true,10000,3002,io);assert(core.stats().fault==Cause::CamPhase);
 Executor renewal;IO other;cmd.output.state=State::Stopped;cmd.sequence=1;cmd.command_us=cmd.sampled_us=1;
 renewal.progress(1,other);renewal.command(cmd,1,other);renewal.phase(true,3001,1,other);
 cmd.output.state=State::Running;cmd.sequence++;renewal.command(cmd,2,other);
 renewal.phase(true,10000,3001,other);assert(renewal.stats().fault==Cause::CamPhase);
}
int main(){for(auto slots:{36U,60U,120U})for(auto rpm:{80U,1000U,8000U})for(auto delay:{0U,750U,1000U})for(bool second:{false,true})for(auto crank_delay:{0U,750U,1000U})phase_test(slots,rpm,delay,second,crank_delay);
 for(double cam:{0.,1.,269.,270.,359.,450.,629.,630.,719.})phase_test(60,1000,750,false,1000,cam);
 for(double ramp:{-.005,.005})for(auto crank:{0U,1000U})for(auto cam:{0U,1000U})transient_test(ramp,crank,cam);
 acquisition_noise_test();missing_cam_test();scheduler_test();mass_test();watchdog_test();std::cout<<"720-degree phase, ordering, missing cam, sequential pulses, fuel mass and independent watchdog tests passed\n";}
