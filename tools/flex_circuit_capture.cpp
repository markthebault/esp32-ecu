// Replay circuit-derived digital edges through the actual portable Capture.
// This is a synthetic source, not an ESP32 GPIO/RTOS or physical-input test.
#include "ecu/flex_fuel.hpp"
#include <cmath>
#include <array>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>

static void number(double value){if(std::isfinite(value))std::cout<<value;else std::cout<<"null";}
int main(int argc,char**argv){
 if(argc!=2)return 2;
 const double end=std::stod(argv[1]);
 if(!std::isfinite(end)||end<0||end>1e12)return 2;
 std::array<ecu::flex::Capture,10>captures;double time=0;unsigned level=0,edges=0;
 while(std::cin>>time>>level){
  if(!std::isfinite(time)||time<0||time>end||level>1||++edges>100000)return 2;
  for(unsigned n=0;n<captures.size();++n)captures[n].edge(static_cast<std::uint64_t>(std::floor(time+n/10.)),level!=0,ecu::flex::Source::Synthetic);
 }
 if(!std::cin.eof())return 2;
 std::cout<<'[';
 for(unsigned n=0;n<captures.size();++n){
 const auto o=captures[n].observe(static_cast<std::uint64_t>(std::floor(end+n/10.)));
 if(n)std::cout<<',';
 std::cout<<std::setprecision(17)<<"{\"clock_phase_us\":"<<n/10.<<",\"valid\":"<<(o.valid?"true":"false")
  <<",\"source\":\""<<ecu::flex::source_name(o.source)<<"\",\"reason\":\""<<ecu::flex::reason_name(o.reason)
  <<"\",\"edges\":"<<edges<<",\"cycles\":"<<unsigned(o.window_cycles)<<",\"low_pulse_us\":";
 number(o.low_pulse_us);std::cout<<",\"frequency_hz\":";number(o.frequency_hz);
 std::cout<<",\"ethanol_pct\":";number(o.ethanol_pct);std::cout<<",\"fuel_temp_c\":";number(o.fuel_temp_c);
 std::cout<<",\"pending_fault\":"<<(o.pending_fault?"true":"false")<<'}';
 }
 std::cout<<"]\n";
}
