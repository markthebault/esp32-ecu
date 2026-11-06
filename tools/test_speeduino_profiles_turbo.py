"""Native production16-output/boost fixture acceptance, without an engine plant."""
import argparse,gzip,hashlib,json,os,subprocess,unittest
from pathlib import Path
from engine_geometry import EngineGeometry
from speeduino_profiles_turbo_runtime import SpeeduinoProfilesTurboRuntime
from speeduino_turbo_runtime import SpeeduinoTurboRuntime
from test_speeduino_profiles import prescribed

ROOT=Path(__file__).resolve().parents[1];BINARY=None;OUTPUT=None;CASES={}
LEGACY=ROOT/'.cache/engine/speeduino-turbo-011/speeduino-turbo-sim'

def sample(**changes):return dict(dict(map_kpa=150,tps_pct=60,clt_c=85,iat_c=25,battery_v=14,**{'lambda':1}),**changes)
def geometry(n):return EngineGeometry(n,(1,*range(n,1,-1)),500*n)


class ExpandedBoostTests(unittest.TestCase):
 def runtime(self,n=8,engine='sequential',**options):
  r=SpeeduinoProfilesTurboRuntime(BINARY,geometry(n),engine,**options);self.addCleanup(r.close);return r
 def test_all72_requested_startup_profiles_read_back_config_and_tables(self):
  for n in range(1,9):
   for engine in ('sequential','semi','wasted_cop'):
    for mode in ('off','open_loop','closed_loop'):
     with self.subTest(n=n,engine=engine,mode=mode):
      r=self.runtime(n,engine,mode=mode)
      self.assertEqual(r.profile['reqFuel_point1ms'],107);self.assertEqual(len(r.profile['boost_and_density_raw_maps']),178)
      self.assertEqual(r.profile['representable_ignition_geometry'],not(n in (2,7)and engine!='sequential'))
      self.assertEqual(bool(r.profile['injection_bank_caveat']),n==5 and engine!='sequential')
      CASES[f'startup-{n}-{engine}-{mode}']=dict(profile=r.profile);r.close()
 def test_all24_profiles_execute_actual_engine_ports_and_PWM(self):
  for n in range(1,9):
   for engine in ('sequential','semi','wasted_cop'):
    with self.subTest(n=n,engine=engine):
     r=self.runtime(n,engine,mode='open_loop');r.sensors(sample())
     edges=prescribed(r,cam=engine=='sequential');status=r.status();boost=r.boost_status()
     high=set();used=set()
     for us,ch,value,_,_ in edges:
      self.assertNotEqual(ch in high,value)
      if value:high.add(ch)
      else:high.remove(ch)
      used.add(ch)
     expected=set(r.geometry.injector_channels+r.geometry.coil_channels+(9,))
     if n==7 and engine!='sequential':expected={r.pin_map[p]for p in (22,23,25,31,32,33)}|{9}
     self.assertEqual(used,expected);self.assertEqual(status['rpm'],1000);self.assertEqual(boost['duty_pct'],40)
     actual=[e for e in edges if e[1]==9];self.assertGreater(len(actual),10)
     self.assertTrue(all(e[0]%4==0 for e in actual))
     falls=r.halt();self.assertEqual({e[1]for e in falls},high-{9});self.assertFalse(any(e[2]for e in falls))
     self.assertEqual(r.boost_status()['duty_pct'],40)
     CASES[f'motion-{n}-{engine}']=dict(profile=r.profile,edges=edges,status=status,boost=boost,halt=falls);r.close()
 def test_calendar_history_is_exact_across_solver_partition_opportunities(self):
  histories=[]
  for period in (250,500,1000):
   r=self.runtime(mode='open_loop');r.sensors(sample());edges=prescribed(r,cam=True,period_us=period)
   histories.append((edges,r.status(),r.boost_status()));r.close()
  self.assertEqual(histories[0],histories[1]);self.assertEqual(histories[0],histories[2])
 def test_exact_historical_four_cylinder_raw96_engine_and_boost_behavior(self):
  for mode in ('off','open_loop','closed_loop'):
   old=SpeeduinoTurboRuntime(LEGACY,mode=mode);new=SpeeduinoProfilesTurboRuntime(BINARY,EngineGeometry(4,(1,3,4,2),1800),'wasted_cop',mode=mode)
   try:
    old.sensors(sample());new.sensors(sample())
    a=prescribed(old,until_us=3600000,period_us=1000);b=prescribed(new,until_us=3600000,period_us=1000)
    self.assertEqual(a,b);a_status=old.status();b_status=new.status()
    self.assertEqual(a_status,{k:b_status[k]for k in a_status});self.assertEqual(old.boost_status(),new.boost_status())
    self.assertEqual(old.raw_adc_counts,new.raw_adc_counts);self.assertEqual(old.halt(),new.halt())
    if mode=='closed_loop':self.assertTrue(any(e[1]==9 for e in b))
   finally:old.close();new.close()
 def test_explicit_timer_negative_control_separates_demand_and_actual_PWM(self):
  observed=[]
  for unarmed in (False,True):
   r=self.runtime(mode='open_loop',default_unarmed_compare=unarmed);r.sensors(sample());edges=prescribed(r,cam=True)
   self.assertEqual(r.boost_status()['duty_pct'],40);observed.append(sum(e[1]==9 for e in edges));r.close()
  self.assertGreater(observed[0],10);self.assertEqual(observed[1],0)
 def test_raw_ADC_rails_and_production_pressure_cut(self):
  r=self.runtime(mode='open_loop',target=130,cut_kpa=140,protection_rpm=0)
  r.sensors(sample(iat_c=-100,map_kpa=400));self.assertEqual(r.raw_adc_counts['iat'],0);self.assertEqual(r.raw_adc_counts['map'],1023)
  r.sensors(sample(iat_c=1000,**{'lambda':2}));self.assertEqual(r.raw_adc_counts['iat'],1023);self.assertEqual(r.raw_adc_counts['wideband'],1023)
  r.sensors(sample());prescribed(r,cam=True)
  self.assertEqual(r.boost_status()['boost_cut'],1);s=r.status();self.assertEqual(s['fuel_channels'],0);self.assertEqual(s['ignition_channels'],0)
 def test_invalid_python_inputs_leave_child_clock_and_ADCs_untouched(self):
  r=self.runtime(mode='open_loop')
  for key,values in dict(map_kpa=(-1,401),tps_pct=(-1,101),clt_c=(-274,2001),iat_c=(-274,2001),battery_v=(-1,25),**{'lambda':(0,3)}).items():
   for v in (*values,True,float('nan'),float('inf'),'1'):
    with self.assertRaises(ValueError):r.sensors(sample(**{key:v}))
    self.assertEqual(r.now,0);self.assertIsNone(r.process.poll())
  for v in (-1,60000001,True,.5):
   with self.assertRaises(ValueError):r.advance(v)
  for channel,high in ((True,True),(2,True),(1,1)):
   with self.assertRaises(ValueError):r.input_edge(1000,channel,high)
  self.assertEqual(r.now,0);self.assertIsNone(r.process.poll())
 def test_complete_raw_frame_validation_precedes_any_running_mutation(self):
  prefix=['sensors 150 60 85 25 14 14.7']
  events=[(k*1000,1)for k in range(1,601)] + [(k,2)for k in range(90000,600001,120000)]
  for us,kind in sorted(events):
   if kind==2:prefix += [f'input {us} 1 1',f'input {us} 1 0']
   else:prefix.append(('tooth 'if(us//1000)%60<58 else'advance ')+str(us))
  wire='\n'.join(prefix)+'\n';args=[str(BINARY),'8','sequential','open_loop','40','150']
  baseline=subprocess.run(args,input=wire+'quit\n',text=True,capture_output=True,timeout=10)
  self.assertEqual(baseline.returncode,0,baseline.stderr)
  for bad in ('advance 640000oops','input 640000 0 1oops','sensors 150 60 85 25 14 14.7oops','halt extra','status extra',
              'advance 640000 1','advance 60000001','advance -1','advance 640000\0oops','x'*4097):
   run=subprocess.run(args,input=wire+bad+'\n',text=True,capture_output=True,timeout=10)
   self.assertEqual(run.returncode,2);self.assertEqual(run.stdout,baseline.stdout)


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a,rest=p.parse_known_args();BINARY=a.executable.resolve();OUTPUT=a.output.resolve();OUTPUT.mkdir(parents=True,exist_ok=False)
 names=('tools/test_speeduino_profiles_turbo.py','tools/speeduino_profiles_turbo_sim.cpp','tools/speeduino_profiles_turbo_runtime.py',
        'scripts/build_speeduino_profiles_turbo.py','tools/speeduino_profiles_sim.cpp','tools/speeduino_turbo_runtime.py','tools/engine_geometry.py','config/engine-profile.json')
 sources={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in names}
 result=unittest.main(argv=[__file__,*rest],exit=False,verbosity=2).result
 unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==v for n,v in sources.items())
 for name,case in CASES.items():(OUTPUT/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(case,separators=(',',':'),allow_nan=False).encode(),mtime=0))
 (OUTPUT/'summary.json').write_text(json.dumps(dict(passed=result.wasSuccessful()and unchanged,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
  source_unchanged=unchanged,source_sha256=sources,cases=len(CASES),binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
  scope='Actual production nativeGPIO/ADC/boost/timer/parser fixture acceptance; no engine plant or physical qualification'),indent=2)+'\n')
 raise SystemExit(not(result.wasSuccessful()and unchanged))
