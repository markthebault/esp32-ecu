// Portable boost/PWM development replay, with authored RPM/synchronization.
// This does not execute the full engine Controller, target, GPIO or plant.
#include "ecu/boost_control.hpp"
#include "ecu/boost_pwm.hpp"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
namespace b=ecu::boost;
namespace {
struct IO {
 std::uint64_t now=0;bool high=false;
 bool write(bool value){if(value!=high){high=value;std::cout<<"{\"kind\":\"boost_edge\",\"time_us\":"<<now<<",\"high\":"<<high<<",\"physical_execution\":false}\n";}return true;}
 void all_low(){write(false);}
};
void number(double x){if(std::isfinite(x))std::cout<<x;else std::cout<<"null";}
}
int main(int argc,char**argv){
 try{
  if(argc!=6)throw std::runtime_error("Expected mode duty target frequency cut");
  b::Config c;const std::string mode=argv[1];
  if(mode=="off")c.mode=b::Mode::Off;else if(mode=="open")c.mode=b::Mode::OpenLoop;else if(mode=="closed")c.mode=b::Mode::ClosedLoop;else throw std::runtime_error("Invalid mode");
  auto value=[](const char*text){std::size_t used=0;const double v=std::stod(text,&used);if(used!=std::string(text).size()||!std::isfinite(v))throw std::runtime_error("Invalid parameter");return v;};
  const double duty=value(argv[2]);if(duty<0||duty>100)throw std::runtime_error("Invalid duty");
  c.pressure_enabled=true;c.open_duty.cells.fill(duty);c.feedforward.cells.fill(duty);c.target.cells.fill(value(argv[3]));
  c.frequency_hz=value(argv[4]);c.cut_kpa=value(argv[5]);c.maximum_map_kpa=400;c.activation=b::Activation::Fixed;c.activation_kpa=120;
  c.max_pct=100;c.kp=.01f;c.ki=0;c.kd=0;c.slew_pct_s=2000;
  if(!b::valid(c))throw std::runtime_error("Invalid boost profile");
  b::Controller controller;b::PwmExecutor pwm;IO io;std::uint64_t sequence=0,last=0;bool seen=false;
  const auto period=static_cast<std::uint32_t>(std::llround(1e6/c.frequency_hz));
  std::cout<<std::boolalpha<<std::setprecision(17)<<"{\"kind\":\"ready\",\"physical_execution\":false,\"scope\":\"portable_boost_kernel_and_pwm_with_fixture_rpm\"}\n"<<std::flush;
  std::string command;
  while(std::cin>>command){
   if(command=="quit")break;
   if(command!="sample")throw std::runtime_error("Unsupported command");
   std::uint64_t now;unsigned running,cranking,fault,quality;b::Input in;
   if(!(std::cin>>now>>in.map_kpa>>in.tps_pct>>in.rpm>>in.baro_kpa>>running>>cranking>>fault>>quality)||now>60000000||running>1||cranking>1||fault>1||quality>7||(seen&&now<=last))throw std::runtime_error("Invalid sample");
   while(pwm.next_alarm()<=now){io.now=pwm.next_alarm();pwm.dispatch(io.now,io);}
   io.now=now;in.sampled_us=now;in.map_qualified=quality&1;in.tps_qualified=quality&2;in.baro_qualified=quality&4;
   in.running=running;in.cranking=cranking;in.engine_fault=fault;
   const auto o=controller.step(c,in,now);
   b::PwmCommand proposed;proposed.sequence=++sequence;proposed.command_us=proposed.sampled_us=now;
   proposed.tune_revision=proposed.sensor_revision=1;proposed.period_us=period;
   proposed.enabled=!o.inhibit_engine&&(o.flags&b::ValveAllowed);proposed.supervised_stop=!proposed.enabled;
   proposed.high_us=proposed.enabled?static_cast<std::uint32_t>(std::llround(o.duty_pct*period/100)):0;
   const bool accepted=pwm.submit(proposed,now,io);const auto&s=pwm.stats();
   std::cout<<"{\"kind\":\"sample\",\"time_us\":"<<now<<",\"map_kpa\":"<<in.map_kpa<<",\"tps_pct\":"<<in.tps_pct
    <<",\"rpm\":"<<in.rpm<<",\"boost_duty_pct\":"<<o.duty_pct<<",\"boost_target_kpa\":";number(o.target_kpa);
   std::cout<<",\"reason\":\""<<b::reason_name(o.reason)<<"\",\"inhibit_engine\":"<<o.inhibit_engine
    <<",\"flags\":"<<o.flags<<",\"pid_updates\":"<<o.pid_updates<<",\"p_term\":"<<o.p_term<<",\"i_term\":"<<o.i_term<<",\"d_term\":"<<o.d_term
    <<",\"boost_pin_high\":"<<io.high<<",\"pwm_accepted\":"<<accepted<<",\"pwm_fault\":"<<unsigned(s.fault)
    <<",\"applied_period_us\":"<<s.period_us<<",\"applied_high_us\":"<<s.high_us<<",\"physical_execution\":false}\n";
   last=now;seen=true;
  }
  if(!std::cin.eof()&&std::cin.fail())throw std::runtime_error("Malformed stream");
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
