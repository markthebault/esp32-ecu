"""Interactive raw-input/PWM coupling to pinned production Speeduino.

Uses the original numerical runtime's IPC, engine channel mapping and status
decoder, with an explicit1.8L profile and separate actual boost edge records.
"""
import hashlib,json,math,subprocess
from pathlib import Path
from speeduino_runtime import SpeeduinoRuntime

class SpeeduinoTurboRuntime(SpeeduinoRuntime):
 def __init__(self,executable,mode='off',duty=40,target=150,default_unarmed_compare=False,loop_period_us=1000,cut_kpa=220,protection_rpm=6500):
  if mode not in ('off','open_loop','closed_loop') or type(duty) is not int or not 0<=duty<=90 or duty%2 or type(target) is not int or not 50<=target<=210 or target%2 or type(default_unarmed_compare) is not bool:raise ValueError('Unrepresentable production boost profile')
  if type(loop_period_us) is not int or not 100<=loop_period_us<=10000:raise ValueError('Invalid declared native main-loop cadence')
  if type(cut_kpa) is not int or not 100<=cut_kpa<=300 or cut_kpa%2:raise ValueError('Unrepresentable production pressure limit')
  if type(protection_rpm) is not int or not 0<=protection_rpm<=6500 or protection_rpm%100:raise ValueError('Unrepresentable production protection RPM cap')
  executable=Path(executable).resolve();manifest=json.loads(executable.with_name('build-manifest.json').read_text())
  if manifest['unit_test'] is not False or manifest['speeduino_sha']!='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20' or hashlib.sha256(executable.read_bytes()).hexdigest()!=manifest['binary_sha256'] or manifest['scope']!='production_loop_raw_adc_crank_full_engine_boost_PWM_and_interactive_coupling':raise ValueError('Coupled reference attestation differs')
  self.now=0;self.buffer=b'';self.process=None;self.timer_bits=32;self.sequential=self.semi_sequential=False
  self.edge_modes={};self.spark_trims=[0]*4;self.last_status={};self.secondary_channels=None;self.secondary_profile=None
  self.idle_profile=self.transient_profile=self.load_profile=None
  args=[str(executable),mode,str(duty),str(target),'--loop-period-us='+str(loop_period_us),'--cut-kpa='+str(cut_kpa),'--protect-rpm100='+str(protection_rpm//100)]+(['--default-unarmed-compare'] if default_unarmed_compare else [])
  self.process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
  try:
   # Parent requires the old107 fuel datum; this fixture explicitly uses96.
   ready=self._line();pins=self._line().split()
   if not ready.startswith('ready ') or len(pins)!=9 or pins[0]!='pins':raise RuntimeError('Invalid production startup greeting')
   canonical=(0,2,3,1,4,6,7,5);self.pin_map={int(pin):canonical[n] for n,pin in enumerate(pins[1:])}
   profile=self.command('profile');expected=[96,65,62,3,1,1]
   if len(profile)!=1 or profile[0].split()[0]!='profile' or list(map(int,profile[0].split()[1:]))!=expected:raise RuntimeError('Production setup changed engine profile')
   self.profile=dict(zip(('reqFuel_point1ms','hard_limit_rpm100','soft_limit_rpm100','protection_type','hard_limit_mode','per_tooth'),expected))
   boost=self.command('boostprofile');expected=[int(mode!='off'),int(mode=='closed_loop'),12,cut_kpa//2,0,90,10,0,0,100,1000,int(default_unarmed_compare),loop_period_us,1,cut_kpa,protection_rpm//100]
   if len(boost)!=1 or boost[0].split()[0]!='boostprofile' or list(map(int,boost[0].split()[1:]))!=expected:raise RuntimeError('Production setup changed boost profile: '+repr(boost)+' expected '+repr(expected))
   maps=self.command('boostmaps');axis=[0,10,20,40,80,120,160,200];rpm=[5+10*n for n in range(8)];bins=[n*25 for n in range(9)]
   wanted=rpm+axis+[target//2 if mode=='closed_loop' else duty//2]*64+rpm+[50+25*n for n in range(8)]+[duty*2]*64+bins+[math.floor(100*298.15/(273.15+n-40)+.5) for n in bins]
   if len(maps)!=1 or maps[0].split()[0]!='boostmaps' or list(map(int,maps[0].split()[1:]))!=wanted:raise RuntimeError('Production table/density readback changed')
   self.profile.update(boost_raw=expected,boost_mode=mode,frequency_hz=24,target_kpa=target,duty_pct=duty,cut_kpa=cut_kpa,protection_max_rpm=protection_rpm,boost_and_density_raw_maps=wanted,
    source_pin=manifest['speeduino_sha'],binary_sha256=manifest['binary_sha256'],
    iat_density_profile='9-point integer lookup approximating298.15/T, explicit ADC/table quantization',
    native_timer_initial_compare='UINT32_MAX negative control' if default_unarmed_compare else 'explicit zero fixture',
    main_loop_period_us=loop_period_us,main_loop_clock='Fixed absolute microsecond calendar independent of plant integration calls; authored zero CPU-time assumption',
    adc_conversion='Bounded research inputs; counts clamp to0..1023 before production analogRead; cold/hot model temperatures may rail the declared sensor curve',
    temperature_fixture_bounds_c=[-273.15,2000],physical_execution=False)
  except BaseException:self.close();raise
 def sensors(self,sample):
  fields=('map_kpa','tps_pct','clt_c','iat_c','battery_v','lambda')
  limits=((0,400),(0,100),(-273.15,2000),(-273.15,2000),(0,24),(5/14.7,40/14.7))
  values=[sample[k] for k in fields]
  if any(type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high for v,(low,high) in zip(values,limits)):raise ValueError('Unrepresentable production sensor input')
  values[-1]*=14.7
  if self.command('sensors '+' '.join(format(v,'.12g') for v in values)):raise RuntimeError('Unexpected edges while setting raw sensors')
  rows=self.command('adcstatus')
  if len(rows)!=1 or rows[0].split()[0]!='adcstatus':raise RuntimeError('Missing native ADC readback')
  counts=list(map(int,rows[0].split()[1:]))
  if len(counts)!=6 or any(not 0<=value<=1023 for value in counts):raise RuntimeError('Invalid native ADC readback')
  self.raw_adc_counts=dict(zip(('map','tps','clt','iat','battery','wideband'),counts))
 def advance(self,time_us,tooth=False):
  if type(time_us) is not int or not self.now<=time_us<=60000000 or type(tooth) is not bool:raise ValueError('Native benchmark time must be monotonic0..60s')
  rows=self._edges(self.command(('tooth' if tooth else 'advance')+' '+str(time_us)))
  previous=self.now
  for row in rows:
   if not previous<=row[0]<=time_us:raise RuntimeError('Native output outside ordered advance interval')
   previous=row[0]
  self.now=time_us;return rows
 def _edges(self,lines):
  result=[]
  for line in lines:
   if line.startswith('boostedge '):
    fields=line.split()
    if len(fields)!=3 or fields[2] not in ('0','1'):raise RuntimeError('Invalid production boost edge')
    result.append((int(fields[1]),9,bool(int(fields[2])),None,None))
   else:
    fields=line.split()
    if len(fields)!=6 or fields[0]!='edge':raise RuntimeError('Invalid production engine edge')
    stamp,pin,level,sync,span=map(int,fields[1:])
    if pin not in self.pin_map or level not in (0,1) or sync not in (0,1,2) or span not in (0,360,720):raise RuntimeError('Invalid production engine edge fields')
    result.extend(super()._edges([line]))
   if not 0<=result[-1][0]<=60000000:raise RuntimeError('Invalid production edge time')
  return result
 def boost_status(self):
  lines=self.command('booststatus');keys=('time_us','map_kpa','tps_raw_half_pct','rpm','duty_raw_point01pct','target_kpa','pin_high','boost_cut','timer_counter','timer_compare','iat_correction_pct')
  if len(lines)!=1 or lines[0].split()[0]!='booststatus':raise RuntimeError('Missing production boost status')
  values=list(map(int,lines[0].split()[1:]))
  if len(values)!=len(keys):raise RuntimeError('Incomplete production boost status')
  result=dict(zip(keys,values))
  if result['time_us']!=self.now or result['pin_high'] not in (0,1) or result['boost_cut'] not in (0,1) or not 0<=result['duty_raw_point01pct']<=10000 or not 0<=result['tps_raw_half_pct']<=200 or not 0<=result['map_kpa']<=400 or not 0<=result['rpm']<=65535 or any(not 0<=result[key]<=4294967295 for key in ('timer_counter','timer_compare')):raise RuntimeError('Invalid production boost status fields')
  result.update(duty_pct=result['duty_raw_point01pct']/100,tps_pct=result['tps_raw_half_pct']/2,physical_execution=False);return result
 def halt(self):
  rows=self._edges(self.command('halt'))
  if any(row[0]!=self.now or row[2] for row in rows):raise RuntimeError('Invalid production halt edges')
  return rows
