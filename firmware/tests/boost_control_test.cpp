#include "ecu/boost_control.hpp"
#include "ecu/boost_pwm.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <vector>
namespace b=ecu::boost;
struct IO {
 bool high=false,fail=false;std::vector<std::pair<std::uint64_t,bool>> edges;std::uint64_t now=0;
 bool write(bool v){if(fail)return false;high=v;edges.emplace_back(now,v);return true;}
 void all_low(){if(high)edges.emplace_back(now,false);high=false;}
};
int main(){
 unsigned checks=0;
 auto check=[&](bool ok){++checks;assert(ok);};
 b::Config c;b::Input in;b::Controller controller;
 auto step=[&](std::uint64_t t){in.sampled_us=t;return controller.step(c,in,t);};
 check(b::valid(c));check(step(0).reason==b::Reason::Disabled);
 b::Table surface;
 for(unsigned row=0;row<b::bins;++row)for(unsigned col=0;col<b::bins;++col)surface.cells[row*b::bins+col]=surface.rpm[col]/100+surface.axis[row]*.2f;
 check(std::abs(b::lookup(surface,1700,35)-24)<1e-5);
 check(b::lookup(surface,0,-1)==surface.cells.front());
 check(b::lookup(surface,20000,200)==surface.cells.back());
 c.mode=b::Mode::OpenLoop;check(!b::valid(c));c.pressure_enabled=true;check(b::valid(c));
 in.map_kpa=100;in.map_qualified=in.tps_qualified=in.baro_qualified=true;
 in.rpm=2000;in.tps_pct=50;in.running=true;c.open_duty.cells.fill(60);
 auto o=step(5000);check(o.duty_pct==.5&&o.demand_pct==60&&o.reason==b::Reason::Ready);
 for(unsigned n=2;n<=200;++n)o=step(n*5000);
 check(o.duty_pct==60&&o.pid_updates==0);
 in.tps_pct=0;o=step(1005000);check(o.duty_pct==0&&!(o.flags&b::ValveAllowed));
 in.tps_pct=50;in.engine_fault=true;o=step(1010000);check(o.reason==b::Reason::EngineFault&&o.duty_pct==0);
 in.engine_fault=false;in.cranking=true;o=step(1015000);check(o.reason==b::Reason::Cranking&&o.duty_pct==0);
 in.cranking=false;in.overrun=true;check(step(1020000).reason==b::Reason::Overrun);in.overrun=false;
 in.running=false;check(step(1025000).reason==b::Reason::Stopped);in.running=true;
 o=controller.step(c,in,1050001);check(o.reason==b::Reason::Stale&&o.inhibit_engine);
 o=step(1040000);check(o.reason==b::Reason::Clock&&o.inhibit_engine);
 // Timestamp regressions within an otherwise fresh20ms window are faults.
 controller.reset();in.sampled_us=10000;controller.step(c,in,10000);in.sampled_us=9999;
 o=controller.step(c,in,15000);check(o.reason==b::Reason::Clock&&o.inhibit_engine);
 // Pressure protection operates even with valve control Off. Equality at
 // cut is allowed; release requires the hysteresis threshold and valid time.
 controller.reset();c.mode=b::Mode::Off;in.map_kpa=c.cut_kpa;
 check(!step(0).inhibit_engine);in.map_kpa=c.cut_kpa+.1;
 o=step(5000);check(o.inhibit_engine&&o.reason==b::Reason::Overboost&&o.overboost_events==1);
 in.map_kpa=c.cut_kpa-1;check(step(10000).inhibit_engine);
 in.map_kpa=c.cut_kpa-c.cut_hysteresis_kpa;
 check(step(15000).reason==b::Reason::Recovery);
 for(unsigned n=4;n<53;++n)check(step(n*5000).inhibit_engine);
 check(!step(265000).inhibit_engine);
 in.map_kpa=221;check(step(270000).overboost_events==2);
 in.map_kpa=100;check(step(275000).inhibit_engine);
 in.map_qualified=false;check(step(280000).inhibit_engine);in.map_qualified=true;
 check(step(285000).inhibit_engine); // Invalid observation restarts recovery.
 for(unsigned n=58;n<107;++n)check(step(n*5000).inhibit_engine);
 check(!step(535000).inhibit_engine);
 in.map_kpa=401;o=step(540000);check(o.inhibit_engine&&(o.flags&b::OverboostLatched)&&o.overboost_events==3);
 in.map_kpa=NAN;o=step(545000);check(o.inhibit_engine&&(o.flags&b::OverboostLatched));
 // Closed-loop feedforward, derivative on measurement and ambient gate.
 c=b::Config{};c.pressure_enabled=true;c.mode=b::Mode::ClosedLoop;c.feedforward.cells.fill(30);c.kd=.05f;
 controller.reset();in.map_kpa=120;in.tps_pct=50;
 o=step(0);check(o.target_kpa==150&&o.p_term==15&&o.d_term==0);
 for(unsigned n=1;n<=200;++n)o=step(n*5000);
 check(o.duty_pct>44&&o.duty_pct<60&&o.pid_updates==11);
 c.target.cells.fill(170);o=step(1100000);check(o.d_term==0); // No derivative kick from target-only change.
 in.map_kpa=130;o=step(1200000);check(o.d_term<0);
 in.map_kpa=90;o=step(1205000);check(o.reason==b::Reason::Activation&&o.duty_pct==0);
 in.baro_qualified=false;o=step(1210000);check(o.inhibit_engine&&o.reason==b::Reason::Baro&&!(o.flags&b::ValveAllowed));
 in.baro_qualified=true;c.target.cells.fill(90);o=step(1215000);check(o.reason==b::Reason::TargetBelowAmbient&&o.duty_pct==0);
 // Pure-I integration must advance under slew and reach a hard limit;
 // lowering MAP error after saturation must unwind rather than stay pinned.
 c=b::Config{};c.pressure_enabled=true;c.mode=b::Mode::ClosedLoop;c.kp=0;c.ki=1;c.slew_pct_s=1;c.integral_limit_pct=100;
 c.feedforward.cells.fill(20);in.map_kpa=120;controller.reset();
 for(unsigned n=0;n<=30000;++n)o=step(n*5000);
 check(o.duty_pct==c.max_pct&&o.i_term<=70.0001);
 in.map_kpa=180;for(unsigned n=30001;n<=34000;++n)o=step(n*5000);
 check(o.duty_pct<80&&o.i_term<60);
 // NaN/range/axis/target-vs-cut mismatches reject before actuation.
 auto bad=c;bad.maximum_map_kpa=NAN;check(!b::valid(bad));bad=c;bad.target.cells[0]=c.cut_kpa;check(!b::valid(bad));
 bad=c;bad.open_duty.rpm[2]=bad.open_duty.rpm[1];check(!b::valid(bad));bad=c;bad.frequency_hz=9;check(!b::valid(bad));
 // Dedicated10Hz PWM: a50ms high can span multiple fresh heartbeats,
 // but a new command cannot rescue an expired old command at20ms.
 b::PwmExecutor pwm;IO io;b::PwmCommand cmd;cmd.sequence=1;cmd.tune_revision=cmd.sensor_revision=1;cmd.enabled=true;cmd.period_us=100000;cmd.high_us=50000;
 check(pwm.submit(cmd,0,io)&&io.high);
 for(unsigned t=5000;t<=45000;t+=5000){io.now=t;cmd.sequence++;cmd.command_us=cmd.sampled_us=t;check(pwm.submit(cmd,t,io));check(io.high);}
 io.now=50000;pwm.dispatch(50000,io);check(!io.high&&pwm.stats().fault==b::PwmCause::None);
 io.now=65000;cmd.sequence++;cmd.command_us=cmd.sampled_us=65000;check(!pwm.submit(cmd,65000,io)&&pwm.stats().fault==b::PwmCause::CommandExpired);
 ecu::idle::PwmExecutor idle;IO idle_io;check(!idle.submit(cmd,65000,idle_io)); // Idle period envelope is unchanged.
 std::cout<<"Boost kernel and supervised PWM: "<<checks<<" assertions passed; no physical execution\n";
}
