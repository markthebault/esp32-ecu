// Separate source-bound flex fixture. The original numerical entry and HAL
// stay unchanged. Only virtual pin transitions drive production acquisition.
#define main numerical_benchmark_main
#include "speeduino_sim.cpp"
#undef main
#include "ecu/flex_fuel.hpp"
#include <iomanip>

namespace {
void coverage(){
 char buffer[PATH_MAX];const auto length=readlink("/proc/self/exe",buffer,sizeof(buffer)-1);
 if(length<=0)throw std::runtime_error("Cannot locate owned executable");
 buffer[length]='\0';const std::string path(buffer);const auto parent=path.substr(0,path.find_last_of('/'));
 if(setenv("GCOV_PREFIX",(parent+"/gcov").c_str(),1))throw std::runtime_error("Cannot isolate coverage");
}
void number(double value){if(std::isfinite(value))std::cout<<std::setprecision(17)<<value;else std::cout<<"null";}
void snapshot(ecu::flex::Capture&capture,const ecu::flex::CorrectionConfig&curves,std::uint64_t delivered,std::uint64_t trigger_edges){
 const auto now=speeduino_sim_micros();const auto o=capture.observe(now);const auto c=ecu::flex::evaluate(curves,capture.config(),o,now);
 std::cout<<"{\"kind\":\"snapshot\",\"time_us\":"<<now<<",\"reference\":{\"ethanol_pct\":"<<unsigned(currentStatus.ethanolPct)
  <<",\"fuel_temp_c\":"<<int(currentStatus.fuelTemp)<<",\"fuel_pct\":"<<unsigned(currentStatus.flexCorrection)
  <<",\"spark_add_deg\":"<<int(currentStatus.flexIgnCorrection)<<",\"temperature_pct\":"<<unsigned(currentStatus.fuelTempCorrection)
  <<",\"advance_deg\":"<<int(currentStatus.advance)<<",\"pulse_us\":"<<unsigned(fuelSchedule1.pw)
  <<",\"rpm\":"<<unsigned(currentStatus.RPM)<<",\"sync\":"<<unsigned(currentStatus.decoder.getStatus().syncStatus)
  <<",\"secl\":"<<unsigned(currentStatus.secl)<<",\"counter\":"<<unsigned(flexCounter)<<",\"low_pulse_us\":"<<flexPulseWidth
  <<"},\"own\":{\"valid\":"<<o.valid<<",\"source\":\""<<ecu::flex::source_name(o.source)<<"\",\"reason\":\""<<ecu::flex::reason_name(o.reason)<<"\",\"capture_reason\":\""<<ecu::flex::reason_name(o.capture_reason)
  <<"\",\"pending_fault\":"<<o.pending_fault<<",\"fault_generation\":"<<o.fault_generation<<",\"sample_us\":"<<o.sample_us<<",\"window_cycles\":"<<unsigned(o.window_cycles)
  <<",\"window_start_us\":"<<o.window_start_us<<",\"sample_age_ms\":";number(o.age_ms);
 std::cout<<",\"frequency_hz\":";number(o.frequency_hz);std::cout<<",\"low_pulse_us\":";number(o.low_pulse_us);
 std::cout<<",\"ethanol_pct\":";number(o.ethanol_pct);std::cout<<",\"fuel_temp_c\":";number(o.fuel_temp_c);
 std::cout<<",\"corrections_enabled\":"<<c.enabled<<",\"corrections_valid\":"<<c.valid<<",\"correction_reason\":\""<<ecu::flex::reason_name(c.reason)<<"\",\"fuel_pct\":";number(c.fuel_factor*100);
 std::cout<<",\"spark_add_deg\":";number(c.spark_add_deg);std::cout<<",\"temperature_pct\":";number(c.temperature_factor*100);
 std::cout<<"},\"delivered_flex_edges\":"<<delivered<<",\"delivered_trigger_edges\":"<<trigger_edges<<"}\n"<<std::flush;
}
}
int main(int argc,char**argv){
 try{
  coverage();std::cout<<std::boolalpha;
  unsigned low=50,high=150,filter=0;bool enabled=true,ramp=false;
  for(int n=1;n<argc;++n){const std::string flag(argv[n]);
   if(flag=="--disabled")enabled=false;else if(flag=="--ramp")ramp=true;
   else if(flag=="--low"||flag=="--high"||flag=="--reference-filter"){
    if(++n==argc)throw std::runtime_error("Missing profile value");const std::string value(argv[n]);
    if(value.empty()||value.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("Invalid profile integer");
    const auto parsed=std::stoul(value);if(parsed>250)throw std::runtime_error("Profile value too large");
    if(flag=="--low")low=parsed;else if(flag=="--high")high=parsed;else filter=parsed;
   }else throw std::runtime_error("Unsupported profile option");
  }
  ecu::flex::CaptureConfig capture_config;capture_config.low_hz=low;capture_config.high_hz=high;capture_config.fault_hz=high+20;
  if(!ecu::flex::valid(capture_config)||filter>240)throw std::runtime_error("Invalid flex profile");
  ecu::flex::Capture own(capture_config);ecu::flex::CorrectionConfig curves;curves.enabled=enabled;curves.temperature_enabled=enabled;
  if(ramp){curves.fuel_pct={{100,110,120,130,140,150}};curves.spark_deg={{0,2,4,6,8,10}};curves.temperature_pct={{80,90,95,100,110,120}};}
  prepare_hal();configure();
  configPage2.flexEnabled=enabled;configPage2.flexFreqLow=low;configPage2.flexFreqHigh=high;configPage4.FILTER_FLEX=filter;
  for(unsigned n=0;n<6;++n){
   configPage10.flexFuelBins[n]=curves.ethanol_bins[n];configPage10.flexAdvBins[n]=curves.ethanol_bins[n];
   configPage10.flexFuelAdj[n]=curves.fuel_pct[n];configPage10.flexAdvAdj[n]=curves.spark_deg[n]+40;
   configPage10.fuelTempBins[n]=curves.temperature_c[n]+40;configPage10.fuelTempValues[n]=curves.temperature_pct[n];
  }
  do{saveAllPages();}while(isEepromWritePending());
  setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();set_sensors(100,0,85,25,14,14.7);
  const auto flex_pin=pinNumbers.pinFlex;const auto flex_interrupt=digitalPinToInterrupt(flex_pin);
  if(flex_pin!=2||pinIsOutput(flex_pin)||flex_interrupt==NOT_AN_INTERRUPT||
    (enabled&&(configPage2.flexEnabled!=1||pin_modes[flex_pin]!=INPUT||interrupt_modes[flex_interrupt]!=CHANGE||interrupts_by_pin[flex_interrupt]!=flexPulse)))
   throw std::runtime_error("Production setup did not independently configure the expected flex input");
  std::cout<<"{\"kind\":\"ready\",\"time_us\":"<<speeduino_sim_micros()<<",\"flex_pin\":"<<unsigned(flex_pin)
   <<",\"flex_interrupt\":"<<flex_interrupt<<",\"enabled\":"<<enabled<<",\"callback_is_flexPulse\":"<<(interrupts_by_pin[flex_interrupt]==flexPulse)
   <<",\"low_hz\":"<<low<<",\"high_hz\":"<<high<<",\"reference_filter\":"<<filter<<",\"tick_before_input\":true}\n"<<std::flush;
  std::uint64_t delivered=0,trigger_edges=0;std::string command;
  while(std::cin>>command){
   if(command=="edge"||command=="trigger"){
    std::uint64_t time=0;unsigned level=0;
    if(!(std::cin>>time>>level)||level>1)throw std::runtime_error("Invalid raw input");
    speeduino_sim_advance(time);const auto pin=command=="edge"?flex_pin:pinNumbers.pinTrigger;
    const auto interrupt=digitalPinToInterrupt(pin);if(interrupt==NOT_AN_INTERRUPT)throw std::runtime_error("Input interrupt missing");
    const bool changed=pins[pin]!=int(level);pins[pin]=level;const auto cb=interrupts_by_pin[interrupt];const auto mode=interrupt_modes[interrupt];
    if(changed){
     if(cb&&(mode==CHANGE||(mode==RISING&&level)||(mode==FALLING&&!level))){cb();if(command=="edge")++delivered;else ++trigger_edges;}
     if(command=="edge")own.edge(time,level!=0,ecu::flex::Source::Synthetic);
    }
    run_loop();
   }else if(command=="observe"){
    std::uint64_t time=0;if(!(std::cin>>time))throw std::runtime_error("Missing observe time");
    speeduino_sim_advance(time);run_loop();snapshot(own,curves,delivered,trigger_edges);
   }else if(command=="ack"){
    std::uint64_t time=0;if(!(std::cin>>time))throw std::runtime_error("Missing ACK time");speeduino_sim_advance(time);run_loop();
    const auto o=own.observe(time);const auto accepted=own.acknowledge(o.fault_generation);
    std::cout<<"{\"kind\":\"ack\",\"time_us\":"<<time<<",\"generation\":"<<o.fault_generation<<",\"accepted\":"<<accepted<<"}\n"<<std::flush;
   }else if(command=="quit")break;
   else throw std::runtime_error("Unsupported raw fixture command");
  }
  if(!std::cin.eof()&&std::cin.fail())throw std::runtime_error("Malformed fixture stream");
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
