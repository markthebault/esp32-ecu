#include "ecu/idle_command.hpp"
#include <cassert>
#include <iostream>
struct Sink{bool high=false;bool write(bool h){high=h;return true;}void all_low(){high=false;}};
using namespace ecu;
idle::PwmCommand zero(std::uint64_t now,std::uint64_t seq){idle::PwmCommand c;c.sequence=seq;c.tune_revision=c.sensor_revision=1;c.command_us=c.sampled_us=now;c.enabled=false;c.supervised_stop=true;return c;}
int main(){
 for(unsigned mode=0;mode<4;++mode){idle::PwmExecutor pwm;Sink io;pwm.trip(0,idle::PwmCause::LateInterrupt,io);assert(pwm.submit(zero(200000,1),200000,io));auto interrupted=zero(205000,2);if(mode==0)interrupted.supervised_stop=false;if(mode==1){interrupted.enabled=true;interrupted.high_us=1000;interrupted.supervised_stop=false;}if(mode==2)interrupted.sequence=1;if(mode==3)interrupted=zero(220000,2);const auto at=mode==3?220000:205000;const bool accepted=pwm.submit(interrupted,at,io);if(mode==1||mode==2)assert(!accepted);assert(pwm.stats().fault!=idle::PwmCause::None);unsigned seq=3;const unsigned recover_at=mode==3?240000:245000;for(unsigned t=225000;t<recover_at;t+=5000){assert(pwm.submit(zero(t,seq++),t,io));assert(pwm.stats().fault!=idle::PwmCause::None&&!io.high);}assert(pwm.submit(zero(recover_at,seq),recover_at,io));assert(pwm.stats().fault==idle::PwmCause::None&&!io.high);}
 idle::PwmExecutor p;Sink sink;auto c=zero(1000,1);c.enabled=true;c.supervised_stop=false;c.high_us=5000;assert(p.submit(c,1000,sink));assert(sink.high);c=zero(2000,2);c.enabled=true;c.supervised_stop=false;assert(p.submit(c,2000,sink)&&!sink.high&&p.next_alarm()==UINT64_MAX);c=zero(3000,3);assert(p.submit(c,3000,sink)&&!sink.high);
 // Every rejected effective identity or a configuration hold must inhibit idle.
 timing::Command requested;requested.sequence=requested.tune_revision=requested.sensor_revision=1;requested.configuration_epoch=2;requested.output.state=engine::State::Running;requested.output.idle.flags=idle::Enabled;requested.idle_high_us=5000;timing::TimingStats stats;
 for(unsigned mismatch=0;mismatch<6;++mismatch){auto effective=requested;if(mismatch==0)effective.sequence=2;if(mismatch==1)effective.tune_revision=2;if(mismatch==2)effective.sensor_revision=2;if(mismatch==3)effective.configuration_epoch=3;if(mismatch==4)effective.output.faults=engine::CamPhase;auto command=idle::pwm_command(requested,effective,0,stats,mismatch==5);assert(!command.enabled&&!command.high_us&&!command.supervised_stop);}
 std::cout<<"{\"unsupervised_live_malformed_and_gap_restart_recovery\":true,\"DFCO_zero_cuts_immediately\":true,\"stopped_zero_remains_low\":true,\"effective_identity_fault_hold_gates\":6}\n";
}
