#include "ecu/idle_pwm.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace ecu::idle;
struct IO {bool high=false,fail=false;std::vector<bool>edges;bool write(bool v){if(fail)return false;high=v;edges.push_back(v);return true;}void all_low(){if(high)edges.push_back(false);high=false;}};
int main(){
 PwmExecutor p;IO io;PwmCommand c;c.sequence=1;c.tune_revision=c.sensor_revision=1;c.enabled=true;c.high_us=5000;c.supervised_stop=false;
 assert(p.submit(c,0,io)&&io.high&&p.next_alarm()==5000);
 p.dispatch(5000,io);assert(!io.high);c.sequence++;c.command_us=c.sampled_us=5000;c.high_us=2500;assert(p.submit(c,5000,io));p.dispatch(10000,io);assert(io.high&&p.stats().high_us==2500);p.dispatch(12500,io);assert(!io.high);
 c.sequence++;c.command_us=c.sampled_us=15000;c.high_us=10000;assert(p.submit(c,15000,io));p.dispatch(20000,io);assert(io.high);p.dispatch(30000,io);assert(io.high&&p.stats().high_us==10000);
 p.dispatch(35000,io);assert(!io.high&&p.stats().fault==PwmCause::CommandExpired);
 c.sequence++;c.command_us=c.sampled_us=35000;assert(!p.submit(c,35000,io)&&!io.high);
 c.enabled=false;c.high_us=0;c.supervised_stop=true;for(unsigned t=35000;t<=60000;t+=5000){c.sequence++;c.command_us=c.sampled_us=t;assert(p.submit(c,t,io));}
 assert(p.stats().fault==PwmCause::None&&p.stats().recoveries==1);
 c.enabled=true;c.high_us=5000;c.supervised_stop=false;c.sequence++;c.command_us=c.sampled_us=65000;assert(p.submit(c,65000,io));p.dispatch(70026,io);assert(!io.high&&p.stats().fault==PwmCause::LateInterrupt);
 p.configuration(71000,io);assert(p.stats().fault==PwmCause::None&&!io.high&&p.next_alarm()==UINT64_MAX);
 c.sequence++;c.command_us=c.sampled_us=72000;assert(p.submit(c,72000,io));p.dispatch(71000,io);assert(p.stats().fault==PwmCause::Clock&&!io.high);
 p.configuration(73000,io);c.sequence++;c.command_us=c.sampled_us=74000;c.high_us=c.period_us+1;assert(!p.submit(c,74000,io)&&!io.high);
 PwmExecutor pending;IO pending_io;PwmCommand d;d.sequence=1;d.tune_revision=d.sensor_revision=1;d.enabled=true;d.high_us=5000;assert(pending.submit(d,0,pending_io));
 d.sequence=2;d.command_us=d.sampled_us=1000;d.high_us=2500;assert(pending.submit(d,1000,pending_io));assert(pending.stats().sequence==1&&pending.stats().pending_sequence==2&&pending.stats().high_us==5000);
 pending.dispatch(5000,pending_io);pending.dispatch(10020,pending_io);assert(pending.stats().sequence==2&&pending.stats().high_us==2500&&pending.stats().observed_us==10020);
 d.sequence=3;d.command_us=d.sampled_us=11000;d.enabled=false;d.supervised_stop=true;d.high_us=5000;assert(!pending.submit(d,11000,pending_io));assert(pending.stats().fault==PwmCause::InvalidCommand);
 std::cout<<"Idle PWM cycle latching, full duty, expiry-before-refresh, zero-demand recovery, lateness, clock reversal and malformed-command tests passed\n";
}
