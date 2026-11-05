#include "ecu/idle_control.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::idle;
int main(){
 Config c;Base b;Input in;Controller controller;
 auto step=[&](std::uint64_t us){in.sampled_us=us;return controller.step(c,b,in,us);};
 assert(valid(c,b));assert(step(0).state==State::Disabled);
 b.enabled=true;in.valid=true;assert(step(5000).state==State::Stopped);
 in.cranking=true;in.rpm=250;auto out=step(10000);assert(out.state==State::Cranking&&out.duty_pct==35);
 in.cranking=false;in.running=true;in.rpm=900;out=step(15000);assert(out.state==State::Taper&&out.duty_pct==35);
 for(unsigned i=4;i<600;++i){out=step(i*5000);}assert(out.state==State::ClosedLoop&&out.pid_updates>0);
 in.rpm=700;const double before=out.duty_pct;for(unsigned i=600;i<1000;++i)out=step(i*5000);assert(out.duty_pct>before&&out.duty_pct<=100);
 in.tps_pct=10;out=step(5000000);assert(out.state==State::Throttle&&out.duty_pct==0);
 in.tps_pct=0;in.rpm=1800;out=step(5005000);assert(out.state==State::Waiting&&out.reason==Reason::Speed);
 in.overrun=true;out=step(5010000);assert(out.reason==Reason::Overrun&&out.duty_pct==0);
 in.overrun=false;in.engine_fault=true;out=step(5015000);assert(out.state==State::Fault&&out.duty_pct==0);
 in.engine_fault=false;out=controller.step(c,b,in,5040001);assert(out.reason==Reason::Stale&&out.duty_pct==0);
 out=step(5030000);assert(out.reason==Reason::Clock&&out.duty_pct==0);
 Config bad=c;bad.coolant_c[2]=bad.coolant_c[1];assert(!valid(bad,b));bad=c;bad.max_pct=25;assert(!valid(bad,b));bad=c;bad.control_period_ms=NAN;assert(!valid(bad,b));
 c.algorithm=Algorithm::OnOff;controller.reset();in.running=true;in.rpm=900;in.clt_c=40;assert(step(0).duty_pct==100);in.clt_c=52;assert(step(5000).duty_pct==100);in.clt_c=55;assert(step(10000).duty_pct==0);
 c.algorithm=Algorithm::ClosedLoop;c.entry_delay_s=0;c.afterstart_taper_s=0;c.dashpot_pct=0;c.run_pct.fill(20);c.target_add_rpm.fill(0);controller.reset();in.clt_c=85;in.rpm=100;in.tps_pct=0;
 for(unsigned i=0;i<4000;++i){out=step(i*5000);}assert(out.duty_pct<=100&&out.i_term<=c.integral_limit_pct);
 in.rpm=1100;for(unsigned i=4000;i<4400;++i)out=step(i*5000);assert(out.duty_pct<100);
 // A valid pure-I increment larger than one slew step must still progress.
 c=Config{};c.entry_delay_s=0;c.afterstart_taper_s=0;c.dashpot_pct=0;c.run_pct.fill(20);c.crank_pct.fill(20);c.target_add_rpm.fill(0);c.slew_pct_s=1;b.kp=0;b.ki=.02;
 controller.reset();in.rpm=250;in.cranking=true;in.running=false;out=step(0);in.cranking=false;in.running=true;in.rpm=800;
 for(unsigned i=1;i<=1000;++i){out=step(i*5000);}assert(out.duty_pct>24.5&&out.duty_pct<=25.1&&out.i_term>4.5);
 // Large I increments must reach a hard bound instead of staying at feedforward.
 c.slew_pct_s=1000;c.integral_limit_pct=100;c.control_period_ms=250;c.target_add_rpm.fill(1000);b.target_rpm=1500;b.ki=.2;
 controller.reset();in.rpm=250;in.cranking=true;in.running=false;out=step(0);in.cranking=false;in.running=true;in.rpm=600;
 for(unsigned i=1;i<=1000;++i){out=step(i*5000);}assert(out.duty_pct==100&&out.i_term==80);
 // After reset, entry hysteresis requires actually crossing the entry TPS.
 c=Config{};b=Base{true,900,.03,.02};c.entry_delay_s=0;controller.reset();in.rpm=900;in.tps_pct=2.25;out=step(0);assert(out.state==State::Throttle&&out.duty_pct==0);
 std::cout<<"Idle configuration, crank/run taper, entry, closed-loop response, throttle, overrun, faults, stale clocks, thermostat and windup tests passed\n";
}
