"""Independent cache-only controlled probes of pinned production secondary tables.

Links unchanged production functions and current native HAL. No UNIT_TEST, no
ECU algorithm replacement, no plant/physical qualification claim.
"""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path('/home/mark/persospace/esp32-ecu');OUT=Path(__file__).resolve().parent
BASE='e2b7c832b92384caae6cf379092ac6944129e237'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
prefix=subprocess.check_output(['git','show',BASE+':tools/speeduino_sim.cpp'],cwd=ROOT,text=True)
prefix=prefix.replace('#include "sensors.h"','#include "sensors.h"\n#include "load_source.h"\n#include "secondaryTables.h"\n#include "corrections.h"')
prefix=prefix[:prefix.index('int main(')]
body=r'''
unsigned checks=0;
void check(const char* kind,unsigned mode,int v1,int v2,int actual,int expected,bool active,bool expected_active,int info=0){
 ++checks;
 std::cout<<kind<<','<<mode<<','<<v1<<','<<v2<<','<<actual<<','<<expected<<','<<active<<','<<expected_active<<','<<info<<'\n';
 if(actual!=expected||active!=expected_active){std::cerr<<"probe mismatch "<<kind<<' '<<mode<<' '<<v1<<' '<<v2<<' '<<actual<<' '<<expected<<' '<<active<<' '<<expected_active<<'\n';std::exit(2);}
}
int main(){
 setenv("GCOV_PREFIX","/home/mark/persospace/esp32-ecu/.cache/engine/secondary-architecture-review/gcov",1);
 prepare_hal();configure();setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();
 currentStatus.RPM=1000;currentStatus.RPMdiv100=10;currentStatus.rotationStatus=EngineRotationStatus::Running;
 currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.EMAP=200;currentStatus.ethanolPct=35;currentStatus.LOOP_TIMER=0;
 for(unsigned i=0;i<16;++i){fuelTable2.axisX[i]=ignitionTable2.axisX[i]=(i+1)*5;fuelTable2.axisY[i]=ignitionTable2.axisY[i]=(i+1)*8;}
 configPage10.fuel2Algorithm=LOAD_SOURCE_MAP;configPage10.spark2Algorithm=LOAD_SOURCE_MAP;
 pinNumbers.pinFuel2Input=25;pinNumbers.pinSpark2Input=26;
 std::cout<<"kind,mode,primary,secondary,actual,expected,active,expected_active,info\n";
 for(unsigned mode:{0,1,2,5,7})for(unsigned v1:{0,1,85,100,150,255})for(unsigned v2:{0,1,50,100,150,255}){
  configPage10.fuel2Mode=mode;fuelTable2.values.fill(v2);invalidate_cache(&fuelTable2.get_value_cache);
  currentStatus.VE1=currentStatus.VE=v1;calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  int expected=mode==1?std::min(255u,(v1*v2+50)/100):mode==2?std::min(255u,v1+v2):v1;
  check("fuel_arithmetic",mode,v1,v2,currentStatus.VE,expected,currentStatus.secondFuelTableActive,mode==1||mode==2,currentStatus.VE2);
  if(currentStatus.VE2!=((mode==1||mode==2)?v2:0))return 5;
 }
 for(unsigned variable=0;variable<4;++variable)for(int delta:{-1,0,1}){
  configPage10.fuel2Mode=FUEL2_MODE_CONDITIONAL_SWITCH;configPage10.fuel2SwitchVariable=variable;
  configPage10.fuel2SwitchValue=variable==0?1000:variable==1?50:variable==2?100:35;
  currentStatus.RPM=1000;currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.ethanolPct=35;
  if(variable==0)currentStatus.RPM+=delta;else if(variable==1)currentStatus.MAP+=delta;else if(variable==2)currentStatus.TPS+=delta;else currentStatus.ethanolPct+=delta;
  fuelTable2.values.fill(65);invalidate_cache(&fuelTable2.get_value_cache);currentStatus.VE1=currentStatus.VE=85;
  calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  check("fuel_condition",variable,configPage10.fuel2SwitchValue,delta,currentStatus.VE,delta>0?65:85,currentStatus.secondFuelTableActive,delta>0,currentStatus.TPS);
 }
 for(unsigned polarity:{0,1})for(unsigned level:{0,1}){
  configPage10.fuel2Mode=FUEL2_MODE_INPUT_SWITCH;configPage10.fuel2InputPolarity=polarity;pins[25]=level;
  fuelTable2.values.fill(65);invalidate_cache(&fuelTable2.get_value_cache);currentStatus.VE1=currentStatus.VE=85;
  calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  check("fuel_input",4,polarity,level,currentStatus.VE,polarity==level?65:85,currentStatus.secondFuelTableActive,polarity==level,currentStatus.VE2);
 }
 // Establish actual production soft-retard correction; all remaining fixture
 // corrections are neutral from the original persisted benchmark setup.
 currentStatus.RPM=6300;currentStatus.RPMdiv100=63;currentStatus.rotationStatus=EngineRotationStatus::Running;
 configPage2.fixAngEnable=0;configPage4.SoftRevLim=62;configPage4.SoftLimRetard=10;configPage4.SoftLimMax=255;configPage2.SoftLimitMode=SOFT_LIMIT_RELATIVE;
 const int corrected=correctionsIgn(20);if(corrected!=10){std::cerr<<"neutral correction profile failed "<<corrected<<'\n';return 3;}
 for(unsigned mode:{0,1,2,3,4,5,7}){
  configPage10.spark2Mode=mode;configPage10.spark2SwitchVariable=SPARK2_CONDITION_RPM;configPage10.spark2SwitchValue=6000;
  configPage10.spark2InputPolarity=1;pins[26]=1;
  const int second=mode==1?150:20;
  ignitionTable2.values.fill(second+40);invalidate_cache(&ignitionTable2.get_value_cache);
  currentStatus.advance1=corrected;currentStatus.advance=corrected;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  const int expected=mode==1?15:mode==2?30:(mode==3||mode==4)?10:corrected;
  check("spark_correction_order",mode,corrected,second,currentStatus.advance,expected,currentStatus.secondSparkTableActive,mode>=1&&mode<=4,currentStatus.advance2);
 }
 for(unsigned mode:{1,2,3,4})for(unsigned inhibit:{1,2}){
  configPage2.fixAngEnable=inhibit==1;currentStatus.rotationStatus=inhibit==2?EngineRotationStatus::Cranking:EngineRotationStatus::Running;
  configPage10.spark2Mode=mode;currentStatus.advance1=currentStatus.advance=5;currentStatus.advance2=111;currentStatus.secondSparkTableActive=true;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  check("spark_inhibited",mode,inhibit,20,currentStatus.advance,5,currentStatus.secondSparkTableActive,false,currentStatus.advance2);
 }
 configPage2.fixAngEnable=0;currentStatus.rotationStatus=EngineRotationStatus::Running;currentStatus.RPM=1000;currentStatus.RPMdiv100=10;
 for(unsigned variable=0;variable<4;++variable)for(int delta:{-1,0,1}){
  configPage10.spark2Mode=SPARK2_MODE_CONDITIONAL_SWITCH;configPage10.spark2SwitchVariable=variable;
  configPage10.spark2SwitchValue=variable==0?1000:variable==1?50:variable==2?100:35;
  currentStatus.RPM=1000;currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.ethanolPct=35;
  if(variable==0)currentStatus.RPM+=delta;else if(variable==1)currentStatus.MAP+=delta;else if(variable==2)currentStatus.TPS+=delta;else currentStatus.ethanolPct+=delta;
  ignitionTable2.values.fill(60);invalidate_cache(&ignitionTable2.get_value_cache);currentStatus.advance1=currentStatus.advance=10;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  check("spark_condition",variable,configPage10.spark2SwitchValue,delta,currentStatus.advance,delta>0?20:10,currentStatus.secondSparkTableActive,delta>0,currentStatus.TPS);
 }
 for(unsigned polarity:{0,1})for(unsigned level:{0,1}){
  configPage10.spark2Mode=SPARK2_MODE_INPUT_SWITCH;configPage10.spark2InputPolarity=polarity;pins[26]=level;
  ignitionTable2.values.fill(60);invalidate_cache(&ignitionTable2.get_value_cache);currentStatus.advance1=currentStatus.advance=10;
  calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  check("spark_input",4,polarity,level,currentStatus.advance,polarity==level?20:10,currentStatus.secondSparkTableActive,polarity==level,currentStatus.advance2);
 }
 for(unsigned mode:{1,2})for(int v1:{-128,-40,-5,0,20,70,127})for(int v2:{-40,-1,0,1,50,100,150,215}){
  configPage10.spark2Mode=mode;ignitionTable2.values.fill(v2+40);invalidate_cache(&ignitionTable2.get_value_cache);
  currentStatus.advance1=currentStatus.advance=v1;calculateSecondarySpark(configPage2,configPage10,ignitionTable2,currentStatus);
  const int percent=std::max(0,v2);
  // Exact rounded signed div100 behavior is probed, not assumed truncation.
  const int num=percent*v1;
  const int product=num>=0?(num+50)/100:(num-50)/100;
  const int sum=v1+std::max(-128,std::min(127,v2));
  const int expected=std::max(-128,std::min(127,mode==1?product:sum));
  check("spark_arithmetic",mode,v1,v2,currentStatus.advance,expected,currentStatus.secondSparkTableActive,true,currentStatus.advance2);
 }
 // Secondary load source is independent and does not change primary fuelLoad.
 for(unsigned row=0;row<16;++row)for(unsigned col=0;col<16;++col)fuelTable2.values[row*16+col]=10+row*4;
 invalidate_cache(&fuelTable2.get_value_cache);currentStatus.MAP=50;currentStatus.TPS=100;currentStatus.EMAP=200;currentStatus.RPM=1000;currentStatus.fuelLoad=50;
 configPage10.fuel2Mode=FUEL2_MODE_INPUT_SWITCH;configPage10.fuel2InputPolarity=1;pins[25]=1;
 for(auto source:{LOAD_SOURCE_MAP,LOAD_SOURCE_TPS,LOAD_SOURCE_IMAPEMAP}){
  configPage10.fuel2Algorithm=source;currentStatus.VE1=currentStatus.VE=85;calculateSecondaryFuel(configPage10,fuelTable2,currentStatus);
  const int expected=source==LOAD_SOURCE_MAP?18:source==LOAD_SOURCE_TPS?56:12;
  check("fuel_independent_source",source,50,getLoad(source,currentStatus),currentStatus.VE,expected,currentStatus.secondFuelTableActive,true,currentStatus.fuelLoad);
  if(currentStatus.fuelLoad!=50)return 4;
 }
 std::cerr<<"PASSED "<<checks<<" controlled production secondary-table checks\n";
}
'''
src=OUT/'reference_probe.cpp';src.write_text(prefix+body)
cache=ROOT/'.cache/engine/speeduino-sim';manifest=json.loads((cache/'build-manifest.json').read_text())
objects=[p for p in sorted((cache/'obj').glob('*.o')) if p.name!='tools_speeduino_sim.cpp.o']
libs=sorted(p for p in (ROOT.parent/'speeduino/.pio/build/native_code_coverage').rglob('*.a') if p.name not in ('libArduinoFake.a','libUnity.a'))
input_hashes={str(p):sha(p) for p in objects+libs};obj=OUT/'reference_probe.o';binary=OUT/'reference_probe'
subprocess.run(['c++',*manifest['compile_flags'],'-c',str(src),'-o',str(obj)],check=True)
subprocess.run(['c++',*map(str,objects),str(obj),'-Wl,--start-group',*map(str,libs),'-Wl,--end-group','-lgcov','-pthread','-o',str(binary)],check=True)
assert all(sha(Path(p))==s for p,s in input_hashes.items()),'Linked objects changed during probe build'
run=subprocess.run([str(binary)],capture_output=True,text=True)
(OUT/'reference-probe.csv').write_text(run.stdout);(OUT/'reference-probe.stderr').write_text(run.stderr)
report=dict(project_commit=BASE,reference_commit=manifest['speeduino_sha'],unit_test=False,compile_flags=manifest['compile_flags'],linked_input_hashes=input_hashes,probe_source_sha256=sha(src),binary_sha256=sha(binary),exit_code=run.returncode,scope='Controlled production secondary fuel/spark functions, actual correction chain, production table interpolation, native virtual input pins. Not sampled-loop/plant or physical qualification.',stderr=run.stderr)
(OUT/'reference-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('compile_flags','linked_input_hashes')},indent=2))
raise SystemExit(run.returncode)
