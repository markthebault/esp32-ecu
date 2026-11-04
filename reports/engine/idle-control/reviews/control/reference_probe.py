"""Isolated idle controller/HAL probe. No upstream or production sources edited."""
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
source=subprocess.check_output(['git','show','cbfbe4a:tools/speeduino_sim.cpp'],cwd=ROOT,text=True)
source=source.replace('#include "globals.h"','#include "globals.h"\n#include "src/controllers/idle/idle.h"')
start=source.index('extern "C" void speeduino_sim_observe()')
source=source[:start]+r'''
namespace {
bool review_observe=false,review_previous=false,review_armed=false;
unsigned review_rises=0;uint64_t review_first_rise=0,review_last_rise=0;
uint64_t review_last=0,review_high_us=0;
unsigned review_edges=0;
bool review_pin(){return (*portOutputRegister(digitalPinToPort(pinNumbers.pinIdle1))&digitalPinToBitMask(pinNumbers.pinIdle1))!=0;}
void begin_window(){review_previous=review_pin();review_last=speeduino_sim_micros();review_high_us=0;review_edges=0;review_rises=0;review_first_rise=review_last_rise=0;review_observe=true;}
void finish_window(const char* stage,unsigned algorithm){
 auto now=speeduino_sim_micros();if(review_previous)review_high_us+=now-review_last;review_last=now;review_observe=false;
 std::cout<<"window "<<algorithm<<' '<<review_armed<<' '<<stage<<' '<<unsigned(currentStatus.idleLoad)<<' '<<review_high_us<<' '<<review_edges<<' '<<review_pin()<<' '<<(review_rises>1?(review_last_rise-review_first_rise)/(review_rises-1):0)<<'\n';
}
}
extern "C" void speeduino_sim_observe(){
 if(!review_observe)return;auto now=speeduino_sim_micros();auto high=review_pin();
 if(high!=review_previous){if(review_previous)review_high_us+=now-review_last;if(high){if(!review_rises)review_first_rise=now;review_last_rise=now;review_rises++;}review_last=now;review_previous=high;review_edges++;}
}
int main(){
 setenv("GCOV_PREFIX",("/home/mark/persospace/esp32-ecu/.cache/engine/idle-control-review/gcov").c_str(),1);
 prepare_hal();configure();setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();
 for(bool arm:{false,true})for(unsigned algorithm:{unsigned(IAC_ALGORITHM_PWM_OL),unsigned(IAC_ALGORITHM_PWM_CL),unsigned(IAC_ALGORITHM_PWM_OLCL)}){
  configPage6.iacAlgorithm=algorithm;configPage6.idleFreq=25;configPage6.iacPWMdir=0;configPage6.iacChannels=0;configPage6.iacPWMrun=0;
  configPage6.idleKP=0;configPage6.idleKI=0;configPage6.idleKD=0;configPage2.iacCLminValue=0;configPage2.iacCLmaxValue=100;
  for(unsigned n=0;n<4;n++){configPage6.iacCrankBins[n]=n*70;configPage6.iacCrankDuty[n]=50;}
  for(unsigned n=0;n<10;n++){configPage6.iacBins[n]=n*25;configPage6.iacOLPWMVal[n]=50;}
  currentStatus.coolant=85;currentStatus.RPM=300;currentStatus.rotationStatus=EngineRotationStatus::Cranking;
  initialiseIdle(true);review_armed=arm;
  std::cout<<"registers "<<ECU_SIM_TIMER_BITS<<' '<<algorithm<<' '<<arm<<' '<<speeduino_sim_micros()<<' '<<IDLE_COUNTER.load()<<' '<<IDLE_COMPARE.load()<<' '<<review_pin()<<'\n';
  if(arm)IDLE_COMPARE=static_cast<software_timer_t::counter_t>(IDLE_COUNTER.load()+1);
  idleControl();begin_window();speeduino_sim_advance(speeduino_sim_micros()+200000);finish_window("cranking",algorithm);
  disableIdle();begin_window();speeduino_sim_advance(speeduino_sim_micros()+200000);finish_window("after_disable",algorithm);
 }
}
'''
# c_str() needs an actual string object, keep the path visibly fixed.
source=source.replace('("/home/mark/persospace/esp32-ecu/.cache/engine/idle-control-review/gcov").c_str()','"/home/mark/persospace/esp32-ecu/.cache/engine/idle-control-review/gcov"')
(OUT/'reference_probe.cpp').write_text(source)
for bits in (32,16):
 cache=ROOT/('.cache/engine/speeduino-sim' if bits==32 else '.cache/engine/speeduino-sim16')
 m=json.loads((cache/'build-manifest.json').read_text())
 obj=OUT/f'probe{bits}.o';binary=OUT/f'probe{bits}'
 subprocess.run(['c++',*m['compile_flags'],'-c',str(OUT/'reference_probe.cpp'),'-o',str(obj)],check=True,capture_output=True)
 objs=[p for p in sorted((cache/'obj').glob('*.o')) if p.name!='tools_speeduino_sim.cpp.o']
 libs=sorted(p for p in (ROOT.parent/'speeduino/.pio/build/native_code_coverage').rglob('*.a') if p.name not in ('libArduinoFake.a','libUnity.a'))
 subprocess.run(['c++',*map(str,objs),str(obj),'-Wl,--start-group',*map(str,libs),'-Wl,--end-group','-lgcov','-pthread','-o',str(binary)],check=True,capture_output=True)
 result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
 (OUT/f'reference-probe-{bits}.txt').write_text(result.stdout)
 print(bits,result.stdout,sep='\n')
