#include "ecu/idle_control.hpp"
#include "ecu/idle_pwm.hpp"
#include <array>
#include <cassert>
#include <cmath>
#include <iostream>
#include <random>
using namespace ecu::idle;
struct Sink {bool high=false,fail=false;unsigned edges=0;bool write(bool v){if(fail)return false;high=v;edges++;return true;}void all_low(){if(high)edges++;high=false;}};
int main(){
 std::mt19937 random(0x1ac005);auto uniform=[&](double a,double b){return a+(b-a)*double(random())/random.max();};
 std::uint64_t samples=0;
 for(unsigned test=0;test<300;++test){
  Config config;config.algorithm=Algorithm(test%3);config.control_period_ms=uniform(10,250);config.entry_delay_s=uniform(0,.3);config.afterstart_taper_s=uniform(0,.5);config.slew_pct_s=uniform(1,1000);config.integral_limit_pct=uniform(0,100);config.kd=uniform(0,.1);config.target_add_rpm.fill(0);
  Base base{true,uniform(600,1500),uniform(0,.2),uniform(0,.2)};assert(valid(config,base));Controller controller;Input in;in.valid=true;in.rpm=250;in.cranking=true;in.clt_c=uniform(-40,140);std::uint64_t time=0,updates=0;
  for(unsigned n=0;n<3000;++n){
   time+=1000+(random()%4000);in.sampled_us=time;in.battery_v=uniform(9,16);
   if(n%31==0){in.rpm=uniform(0,4000);in.tps_pct=uniform(0,5);in.cranking=random()%10==0;in.running=!in.cranking;in.engine_fault=random()%100==0;in.overrun=random()%50==0;base.enabled=random()%30!=0;}
   auto output=controller.step(config,base,in,time);assert(std::isfinite(output.duty_pct)&&output.duty_pct>=0&&output.duty_pct<=100);assert(std::isfinite(output.target_rpm)&&std::isfinite(output.feedforward_pct)&&std::isfinite(output.p_term)&&std::isfinite(output.i_term)&&std::isfinite(output.d_term));
   assert(std::abs(output.i_term)<=config.integral_limit_pct+1e-9);assert(output.pid_updates>=updates);updates=output.pid_updates;
   if(!base.enabled||in.engine_fault||in.overrun||(!in.running&&!in.cranking))assert(output.duty_pct==0);
   if(output.state==State::ClosedLoop){assert(config.algorithm==Algorithm::ClosedLoop);assert(in.rpm<=output.target_rpm+config.exit_rpm_above);assert(in.tps_pct<=config.tps_closed_pct+config.tps_hysteresis_pct);}
   samples++;
  }
 }
 unsigned pwm_cases=0;
 for(unsigned period:{2500,4000,10000,20000,50000})for(unsigned high:{0U,1U,period/2,period-1,period}){
  PwmExecutor pwm;Sink sink;PwmCommand command;command.sequence=1;command.tune_revision=command.sensor_revision=1;command.period_us=period;command.high_us=high;command.enabled=true;assert(pwm.submit(command,0,sink));
  std::uint64_t now=0,next_heartbeat=1000,energized=0;
  while(now<1000000){auto next=std::min<std::uint64_t>(1000000,std::min(pwm.next_alarm(),next_heartbeat));assert(next>now);if(sink.high)energized+=next-now;now=next;pwm.dispatch(now,sink);assert(pwm.stats().fault==PwmCause::None);assert(sink.high==pwm.stats().high);
   if(now==next_heartbeat){command.sequence++;command.command_us=command.sampled_us=now;assert(pwm.submit(command,now,sink));next_heartbeat+=1000;}
  }
  auto ideal=1000000ULL*high/period;assert(energized==ideal);pwm.stop(now,PwmCause::Disabled,sink);assert(!sink.high&&!pwm.stats().active&&pwm.next_alarm()==UINT64_MAX);pwm_cases++;
 }
 for(bool falling:{false,true}){
  PwmExecutor pwm;Sink sink;PwmCommand c;c.sequence=1;c.tune_revision=c.sensor_revision=1;c.high_us=5000;c.enabled=true;
  if(!falling)sink.fail=true;
  bool result=pwm.submit(c,0,sink);
  if(falling){assert(result);sink.fail=true;pwm.dispatch(5000,sink);}else assert(!result);
  assert(!sink.high&&!pwm.stats().active&&pwm.stats().fault==PwmCause::OutputFault&&pwm.next_alarm()==UINT64_MAX);
 }
 unsigned invalid_pwm=0;
 for(unsigned field=0;field<12;++field){
  PwmExecutor pwm;Sink sink;PwmCommand c;c.sequence=1;c.tune_revision=c.sensor_revision=1;c.high_us=1000;c.enabled=true;std::uint64_t now=1000;c.command_us=c.sampled_us=now;
  switch(field){case 0:c.sequence=0;break;case 1:c.tune_revision=0;break;case 2:c.sensor_revision=0;break;case 3:c.command_us=now+1;break;case 4:c.sampled_us=now+1;break;case 5:now=21000;c.sampled_us=now;break;case 6:now=21000;c.command_us=now;break;case 7:c.period_us=2499;break;case 8:c.period_us=50001;break;case 9:c.high_us=c.period_us+1;break;case 10:now=UINT64_MAX-49999;c.command_us=c.sampled_us=now;break;case 11:assert(pwm.submit(c,now,sink));break;}
  assert(!pwm.submit(c,now,sink));assert(!sink.high&&pwm.stats().fault==PwmCause::InvalidCommand);invalid_pwm++;
 }
 std::cout<<"random_controller_samples="<<samples<<" constant_pwm_cases="<<pwm_cases<<" write_failure_cases=2 invalid_pwm_cases="<<invalid_pwm<<" all_passed\n";
}
