#include "ecu/switch_acquisition.hpp"
#include "ecu/engine.hpp"
#include <cstdio>
#include <cstdlib>
#include <array>

using namespace ecu;
namespace si=ecu::switch_input;
unsigned checks=0;
void check(bool value,const char*why){++checks;if(!value){std::fprintf(stderr,"Check%u failed: %s\n",checks,why);std::abort();}}
// Independent register/pin fixture. No electrical transistor, timing, I2C
// peripheral or physical target qualification is implied by this model.
struct Device {
 std::array<std::uint8_t,11> registers{};std::uint8_t contacts=0,marker=0x28;
 int stuck_loop=-1;bool reset_before_guard=false;unsigned writes=0;
 Device(){reset();}
 void reset(){registers.fill(0);registers[0]=0xff;}
 std::uint8_t gpio()const{
  unsigned pins=marker|contacts;
  const bool driven_high=!(registers[0]&0x80)&&bool(registers[10]&0x80);
  if(driven_high)pins|=0x80;
  if(stuck_loop<0?driven_high:stuck_loop!=0)pins|=0x40;
  return static_cast<std::uint8_t>(pins^registers[1]);
 }
 si::Reply execute(const si::Request&op){
  si::Reply r;r.result=si::Result::Ok;r.size=op.read_size;
  if(op.write_size){
   ++writes;for(unsigned i=0;i<op.write_size;++i)registers[op.reg+i]=op.data[i];
  }else if(op.kind==si::Kind::Marker)r.data[0]=gpio();
  else if(op.kind==si::Kind::GuardedRead){
   for(unsigned i=0;i<11;++i)r.data[i]=i==9?gpio():registers[i];
   if(reset_before_guard){reset();reset_before_guard=false;}
   r.data[11]=registers[0];
  }
  return r;
 }
};
struct Rig {
 si::Acquisition acquisition;Device device;std::uint64_t now=100000,last_end=0;std::uint8_t mask=3;
 explicit Rig(secondary::InputSource source=secondary::InputSource::Synthetic):acquisition(source){}
 si::Kind tick(si::Result result=si::Result::Ok,std::uint64_t duration=0){
  const auto op=acquisition.next(mask,now);si::Kind kind=op.kind;
  if(op){auto reply=device.execute(op);reply.result=result;last_end=now+(duration?duration:op.kind==si::Kind::GuardedRead?1800:200);check(acquisition.complete(op.token,reply,now,last_end),"Owned completion accepted");}
  now+=5000;return kind;
 }
 void ready(){for(unsigned n=0;n<80&&!acquisition.snapshot().ready;++n)tick();check(acquisition.snapshot().ready,"Fixture reached ready");}
 void read(){auto count=acquisition.snapshot().reads;for(unsigned n=0;n<80&&acquisition.snapshot().reads==count;++n)tick();check(acquisition.snapshot().reads>count,"Fresh GPIO read completed");}
};

int main(){
 {
  Rig r;auto s=r.acquisition.snapshot();check(s.phase==si::Phase::Disabled&&!s.raw_known&&!s.samples[0].valid,"Default unknown");
  check(!r.acquisition.next(0,1),"Off requests no transaction");
  const si::Kind expected[]={si::Kind::Marker,si::Kind::Iocon,si::Kind::Configure,si::Kind::Challenge,si::Kind::GuardedRead};
  for(auto kind:expected)check(r.tick()==kind,"Marker checked before ordered configuration/challenge/read");
  s=r.acquisition.snapshot();check(s.ready&&s.reads==1&&s.configurations==1,"Complete read establishes readiness");
  check(s.observed_us+1800==s.read_completed_us,"Timestamp is read start, not completion");
  auto stamp=s.observed_us;check(r.tick()==si::Kind::Challenge,"Alternating challenge write");
  check(r.acquisition.snapshot().observed_us==stamp,"Write-only tick cannot refresh inputs");
  for(unsigned bits=0;bits<4;++bits){r.device.contacts=bits;r.read();s=r.acquisition.snapshot();
   for(unsigned channel=0;channel<2;++channel){check(s.samples[channel].valid,"Both channels coherent");check(s.samples[channel].source==secondary::InputSource::Synthetic,"Host provenance stays synthetic");check(s.samples[channel].level==bool(bits&(1U<<channel)),"Raw high means closed contact");check(s.samples[channel].observed_us==s.observed_us,"Shared source timestamp");}
  }
  r.mask=1;r.read();s=r.acquisition.snapshot();check(s.samples[0].valid&&!s.samples[1].valid&&s.samples[1].source==secondary::InputSource::Unavailable,"Unrequested channel unknown");
  r.mask=0;check(r.tick()==si::Kind::None,"Disabled returns no operation");s=r.acquisition.snapshot();check(!s.raw_known&&!s.samples[0].valid&&s.phase==si::Phase::Disabled,"Off clears availability");
 }
 for(unsigned bit:{4U,8U,16U,32U}){
  Rig r;r.device.marker^=bit;r.tick();auto s=r.acquisition.snapshot();check(s.fault==si::Fault::Marker&&!s.ready&&r.device.writes==0,"Wrong static marker causes no register write");
 }
 for(unsigned byte=0;byte<12;++byte){
  if(byte==8||byte==9)continue;
  Rig r;for(unsigned n=0;n<4;++n)r.tick();auto op=r.acquisition.next(3,r.now);auto reply=r.device.execute(op);reply.data[byte]^=1;
  check(r.acquisition.complete(op.token,reply,r.now,r.now+1800),"Corrupted frame consumed");
  auto s=r.acquisition.snapshot();check(s.fault==si::Fault::Configuration&&!s.ready&&s.fault_pending,"Every configuration/latch/guard corruption blocks sample");
 }
 for(int stuck:{0,1}){
  Rig r;r.device.stuck_loop=stuck;
  for(unsigned n=0;n<7&&!r.acquisition.snapshot().fault_pending;++n)r.tick();
  check(r.acquisition.snapshot().fault==si::Fault::Loopback,"Alternating loopback detects held level");
 }
 {
  Rig r;r.ready();r.tick();check(!r.acquisition.snapshot().challenge_high,"Low challenge selected");r.device.reset_before_guard=true;r.tick();
  check(r.acquisition.snapshot().fault==si::Fault::Configuration,"Trailing IODIR catches reset after low GPIO/latch reads");
 }
 for(auto failure:{si::Result::Unavailable,si::Result::Timeout,si::Result::BusError}){
  Rig r;r.ready();auto old=r.acquisition.snapshot();r.tick(failure);auto failed=r.acquisition.snapshot();
  check(failed.fault_pending&&!failed.ready&&!failed.samples[0].valid,"Transport fault immediately invalidates");
  check(failed.observed_us==old.observed_us,"Failure never invents new raw time");
  check(!r.acquisition.invalid_sample_consumed(failed.fault_id+1),"Wrong observation cannot clear fault");
  auto reads=failed.reads;for(unsigned n=0;n<60&&r.acquisition.snapshot().reads==reads;++n)r.tick();
  auto recovered=r.acquisition.snapshot();check(recovered.reads>reads&&recovered.fault_pending&&!recovered.ready&&!recovered.samples[0].valid,"Recovery read cannot hide fault skipped by observer");
  check(r.acquisition.invalid_sample_consumed(failed.fault_id),"Exact completed invalid observation acknowledges fault");
  check(!r.acquisition.snapshot().ready,"Acknowledge still requires a new GPIO read");
  check(!r.acquisition.invalid_sample_consumed(failed.fault_id),"Duplicate acknowledgement rejected");
  r.ready();check(r.acquisition.snapshot().fault==si::Fault::None,"Fresh read after consumed fault recovers");
 }
 for(std::uint64_t duration:{3000ULL,3001ULL}){
  Rig r;for(unsigned n=0;n<4;++n)r.tick();r.tick(si::Result::Ok,duration);auto s=r.acquisition.snapshot();
  check(s.ready==(duration==3000),"Whole operation elapsed budget has exact boundary");check(s.max_duration_us==duration,"Observed duration retained");
 }
 {
  Rig r;auto op=r.acquisition.next(3,r.now);auto reply=r.device.execute(op);
  check(!r.acquisition.complete(op.token+1,reply,r.now,r.now+200),"Foreign completion rejected");
  check(r.acquisition.complete(op.token,reply,r.now,r.now+200),"Foreign completion cannot replace pending request");
  check(!r.acquisition.next(3,r.now+201),"Polling cannot run faster than configured interval");
  op=r.acquisition.next(3,r.now+5000);reply=r.device.execute(op);reply.size=1;
  check(r.acquisition.complete(op.token,reply,r.now+5000,r.now+5200),"Bad write reply consumed");check(r.acquisition.snapshot().fault==si::Fault::Reply,"Unexpected reply size rejects");
 }
 {
  Rig r;r.ready();const auto stamp=r.acquisition.snapshot().observed_us;r.now=stamp+20001;
  check(!r.acquisition.next(3,r.now),"Producer gap suppresses new request");check(r.acquisition.snapshot().fault==si::Fault::PollGap&&!r.acquisition.snapshot().samples[0].valid,"Gap cannot be hidden by immediate new sample");
 }
 {
  Rig r;auto op=r.acquisition.next(3,r.now);auto reply=r.device.execute(op);r.acquisition.complete(op.token,reply,r.now,r.now-1);
  check(r.acquisition.snapshot().phase==si::Phase::Fatal&&r.acquisition.snapshot().fault==si::Fault::Clock,"Reversed transaction clock requires reset");
  check(!r.acquisition.invalid_sample_consumed(r.acquisition.snapshot().fault_id),"Observer cannot clear clock fault");
  check(!r.acquisition.next(0,r.now+5000)&&!r.acquisition.next(3,r.now+10000),"Off/Input cannot clear fatal clock latch");
  check(r.acquisition.snapshot().fault==si::Fault::Clock,"Fatal reason survives Off");
 }
 {
  Rig r(secondary::InputSource::TargetProtected);r.device.contacts=1;r.ready();
  engine::Tune tune;tune.afterstart_pct=0;tune.secondary_tables.fuel.mode=secondary::Mode::Input;
  engine::Controller controller;engine::Output output;unsigned valid=0;
  auto inputs=[&](){engine::Inputs input;input.rpm=1200;input.map_kpa=45;input.tps_pct=10;input.clt_c=85;input.iat_c=25;input.battery_v=13.8;input.sensor_v=5;input.sensors_valid=true;input.synced=true;input.sampled_us=r.now;input.table_switches=r.acquisition.snapshot().samples;return input;};
  for(unsigned n=0;n<8;++n){r.tick();output=controller.step(tune,inputs(),r.now);valid+=output.secondary_fuel.input_qualified;}
  check(valid>0&&output.secondary_fuel.active&&output.secondary_fuel.input_source==secondary::InputSource::TargetProtected,"Production filter consumes genuine adapter sample shape");
  r.tick(si::Result::Timeout);auto failed=r.acquisition.snapshot();
  output=controller.step(tune,inputs(),r.now);check(!output.secondary_fuel.input_qualified&&(output.faults&engine::BadSensor),"Adapter failure reaches core cut/qualification reset");
  check(r.acquisition.invalid_sample_consumed(failed.fault_id),"Control consumption acknowledges exact failure");
 }
 std::printf("{\"passed\":true,\"switch_acquisition_checks\":%u,\"physical_qualification\":false}\n",checks);
}
