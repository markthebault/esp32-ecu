#include "ecu/idle_control.hpp"
#include "ecu/idle_pwm.hpp"
#include <iostream>
#include <cassert>
#include <cmath>
#include <vector>
using namespace ecu::idle;
struct IO {bool high=false,fail=false;unsigned writes=0;std::uint64_t clock=0,last_write=0;bool write(bool v){if(fail)return false;high=v;last_write=clock;writes++;return true;}void all_low(){if(high){high=false;last_write=clock;writes++;}}};
int main(){
 Config c;c.entry_delay_s=0;c.afterstart_taper_s=0;c.dashpot_pct=0;c.target_add_rpm.fill(0);c.run_pct.fill(20);c.crank_pct.fill(35);
 Base b;b.enabled=true;Input in;in.valid=in.running=true;in.rpm=900;in.tps_pct=2.25;in.clt_c=85;
 Controller control;Output out;
 for(unsigned t=0;t<=300000;t+=5000){in.sampled_us=t;out=control.step(c,b,in,t);}
 std::cout<<"fresh_throttle_band tps="<<in.tps_pct<<" entry_threshold="<<c.tps_closed_pct<<" state="<<state_name(out.state)<<" duty="<<out.duty_pct<<"\n";
 control.reset();c.algorithm=Algorithm::OpenLoop;c.run_pct.fill(80);c.crank_pct.fill(80);in.tps_pct=0;
 for(unsigned t=0;t<=500000;t+=5000){in.sampled_us=t;out=control.step(c,b,in,t);}
 const double before=out.duty_pct;c.max_pct=25;c.run_pct.fill(25);c.crank_pct.fill(25);assert(valid(c,b));in.sampled_us=505000;out=control.step(c,b,in,505000);
 std::cout<<"changed_limit before="<<before<<" configured_max="<<c.max_pct<<" actual="<<out.duty_pct<<" flags="<<out.flags<<"\n";
 PwmExecutor p;IO io;PwmCommand command;command.sequence=1;command.tune_revision=command.sensor_revision=1;command.enabled=true;command.high_us=5000;
 assert(p.submit(command,0,io));p.trip(1000,PwmCause::EngineFault,io);command.enabled=false;command.supervised_stop=true;
 for(unsigned t=1000;t<=21000;t+=5000){command.sequence++;command.command_us=command.sampled_us=t;assert(p.submit(command,t,io));}
 std::cout<<"nonzero_disabled_recovery high_us="<<command.high_us<<" fault="<<pwm_cause_name(p.stats().fault)<<" recoveries="<<p.stats().recoveries<<"\n";
 PwmExecutor q;IO sink;command={};command.sequence=1;command.tune_revision=command.sensor_revision=1;command.enabled=true;command.high_us=5000;assert(q.submit(command,0,sink));sink.clock=5000;q.dispatch(5000,sink);
 command.sequence++;command.command_us=command.sampled_us=6000;sink.clock=6000;assert(q.submit(command,6000,sink));sink.clock=10020;q.dispatch(10020,sink);
 std::cout<<"late_boundary actual_write="<<sink.last_write<<" stats_observed="<<q.stats().observed_us<<" lateness="<<q.stats().max_lateness_us<<" high="<<sink.high<<"\n";
 PwmExecutor applied;IO output;command={};command.sequence=1;command.tune_revision=command.sensor_revision=1;command.enabled=true;command.high_us=5000;assert(applied.submit(command,0,output));command.sequence=2;command.tune_revision=2;command.command_us=command.sampled_us=1000;command.high_us=2500;assert(applied.submit(command,1000,output));
 std::cout<<"mixed_applied_observation sequence="<<applied.stats().sequence<<" tune="<<applied.stats().tune_revision<<" actual_latched_high="<<applied.stats().high_us<<" sequence2_requested_high="<<command.high_us<<"\n";
 // Sweep every numeric Config member and every curve cell through NaN and infinity.
 unsigned invalids=0;float Config::*fields[]={&Config::frequency_hz,&Config::control_period_ms,&Config::min_pct,&Config::max_pct,&Config::tps_closed_pct,&Config::tps_hysteresis_pct,&Config::entry_rpm_above,&Config::exit_rpm_above,&Config::entry_delay_s,&Config::afterstart_taper_s,&Config::dashpot_pct,&Config::dashpot_decay_pct_s,&Config::slew_pct_s,&Config::integral_limit_pct,&Config::kd,&Config::derivative_filter_s,&Config::fast_idle_temp_c,&Config::fast_idle_hysteresis_c};
 for(auto field:fields)for(float value:{NAN,INFINITY,-INFINITY}){Config v;v.*field=value;assert(!valid(v,b));invalids++;}
 for(auto member:{&Config::coolant_c,&Config::run_pct,&Config::crank_pct,&Config::target_add_rpm})for(unsigned i=0;i<6;i++)for(float value:{NAN,INFINITY,-INFINITY}){Config v;(v.*member)[i]=value;assert(!valid(v,b));invalids++;}
 for(auto field:{&Base::target_rpm,&Base::kp,&Base::ki})for(double value:{double(NAN),double(INFINITY),double(-INFINITY)}){Base v=b;v.*field=value;assert(!valid(Config{},v));invalids++;}
 std::cout<<"nonfinite_validation_passes="<<invalids<<"\n";
 for(double supply:{8.999,9.,12.,16.,16.001,double(NAN),double(INFINITY),double(-INFINITY)}){Config v;Controller model;Input sample=in;sample.sampled_us=0;sample.battery_v=supply;sample.cranking=true;sample.running=false;sample.rpm=300;auto output=model.step(v,b,sample,0);assert((output.reason==Reason::Supply)==!(supply>=9&&supply<=16));}
 std::cout<<"supply_boundary_cases=8\n";
 unsigned invalid_inputs=0;
 for(auto field:{&Input::rpm,&Input::tps_pct,&Input::clt_c,&Input::battery_v})for(double value:{double(NAN),double(INFINITY),double(-INFINITY)}){Config config;Controller model;Input sample;sample.valid=sample.running=true;sample.rpm=900;sample.*field=value;auto output=model.step(config,b,sample,0);assert(output.state==State::Fault&&output.duty_pct==0);invalid_inputs++;}
 for(unsigned age:{20000U,20001U}){Config config;Controller model;Input sample;sample.valid=sample.running=true;sample.rpm=900;auto output=model.step(config,b,sample,age);assert((output.reason==Reason::Stale)==(age>20000));}
 {Config config;Controller model;Input sample;sample.valid=sample.running=true;sample.rpm=900;sample.sampled_us=1;auto output=model.step(config,b,sample,0);assert(output.reason==Reason::Stale&&output.duty_pct==0);}
 std::cout<<"invalid_input_cases="<<invalid_inputs<<" freshness_boundary_cases=3\n";
 for(float period:{10.f,100.f,250.f}){Config config;config.entry_delay_s=config.afterstart_taper_s=config.dashpot_pct=0;config.control_period_ms=period;config.run_pct.fill(20);config.crank_pct.fill(20);config.target_add_rpm.fill(0);Base base{true,900,0,.02};Controller model;Input sample;sample.valid=sample.cranking=true;sample.rpm=250;auto output=model.step(config,base,sample,0);sample.cranking=false;sample.running=true;sample.rpm=800;for(unsigned t=500;t<=2000500;t+=1000){sample.sampled_us=t;output=model.step(config,base,sample,t);}assert(std::abs(output.i_term-4)<1e-8);}
 std::cout<<"normalized_integral_period_cases=3\n";
 for(bool hard_limit:{false,true}){Config config;config.entry_delay_s=config.afterstart_taper_s=config.dashpot_pct=0;config.control_period_ms=hard_limit?250:100;config.slew_pct_s=hard_limit?1000:1;config.integral_limit_pct=100;config.run_pct.fill(20);config.crank_pct.fill(20);config.target_add_rpm.fill(hard_limit?1000:0);Base base{true,hard_limit?1500.:900.,0,hard_limit?.2:.02};assert(valid(config,base));Controller model;Input sample;sample.valid=sample.cranking=true;sample.rpm=250;auto output=model.step(config,base,sample,0);sample.cranking=false;sample.running=true;sample.rpm=hard_limit?600:800;for(unsigned t=500;t<=5000500;t+=1000){sample.sampled_us=t;output=model.step(config,base,sample,t);}std::cout<<"antiwindup_no_progress hard_limit="<<hard_limit<<" target="<<output.target_rpm<<" rpm="<<sample.rpm<<" duty="<<output.duty_pct<<" integral="<<output.i_term<<" flags="<<output.flags<<"\n";}
}
