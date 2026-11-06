"""Independent instrumented coupling probes; all modifications are local wrappers."""
import copy,gzip,hashlib,json,math,pathlib,sys,time
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2];sys.path.insert(0,str(ROOT/'tools'))
import compare_engine_controllers as b
import secondary_stimulus as ss
from engine_research_plant import ResearchPlant
ORIGINALS=(b.ResearchPlant,b.OurController,b.SpeeduinoRuntime,ss.ContactProgram,ss.SecondaryMonitor)
checks=[];rows=[];instances=[];events=[]
def check(ok,label,**data):checks.append(dict(passed=bool(ok),label=label,**data))
def now_us():return instances[-1].air.time*1e6 if instances else None
def stamp(kind,us,**extra):
 physical=now_us();events.append(dict(kind=kind,source_time_us=us,physical_time_us=physical,**extra))
 if physical is not None and abs(physical-us)>1e-5:raise AssertionError('Future or stale physical sampling: '+str(events[-1]))
class ObservedPlant(ORIGINALS[0]):
 def __init__(self,*args,**kw):super().__init__(*args,**kw);self.integration_ends=[];instances.append(self)
 def integrate(self,t,dt,*args,**kw):
  if dt>0:self.integration_ends.append(round((t+dt)*1e6))
  return super().integrate(t,dt,*args,**kw)
 def sample(self,t):stamp('sensor_sample',round(t*1e6));return super().sample(t)
 def edge(self,ch,high,t,*args,**kw):stamp('plant_edge',round(t*1e6),channel=ch,high=high);return super().edge(ch,high,t,*args,**kw)
class ObservedProgram(ORIGINALS[3]):
 def levels(self,now):stamp('contact_sample',now);return super().levels(now)
class ObservedMonitor(ORIGINALS[4]):
 def progress(self,now):
  if self.stages and self.stages[0][0]==now:stamp('acquisition_stage',now,stage=self.stages[0][1],operation=self.pending['request']['kind'])
  return super().progress(now)
 def observe(self,now):stamp('control_observe',now);return super().observe(now)
class ObservedController(ORIGINALS[1]):
 def sample(self,sample,us):stamp('project_control',us);return super().sample(sample,us)
class ObservedReference(ORIGINALS[2]):
 def sensors(self,sample):stamp('reference_adc_write',self.now);return super().sensors(sample)
 def contacts(self,levels):stamp('reference_gpio_write',self.now,levels=levels);return super().contacts(levels)
def sources():
 names=['tools/compare_engine_controllers.py','tools/secondary_stimulus.py','tools/switch_acquisition_runtime.py','tools/switch_acquisition_bridge.cpp','tools/engine_research_plant.py','tools/engine_runtime.py','tools/engine_bridge.cpp','tools/target_runtime.py','tools/target_timing_bridge.cpp','tools/speeduino_runtime.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','firmware/include/ecu/secondary_tables.hpp','firmware/include/ecu/engine.hpp','firmware/include/ecu/switch_acquisition.hpp']
 return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in names}
def save(out,name,value):
 p=out/(name+'.json.gz');p.write_bytes(gzip.compress((json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode(),mtime=0));return dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def replay(result):
 starts={};mass=0.;spark_falls=0;flow=300*.745/60*1000
 for us,ch,high,cause in result['edges']:
  if high:starts[ch]=us
  else:
   start=starts.pop(ch)
   if ch<4:mass+=flow*max(0,(us-start)*1e-6-.0009)
   elif cause=='scheduled':spark_falls+=1
 return dict(edge_replayed_fuel_mg=mass,plant_fuel_mg=result['summary']['ledger']['fuel_in_mg'],fuel_delta_mg=mass-result['summary']['ledger']['fuel_in_mg'],edge_replayed_sparks=spark_falls,plant_sparks=result['summary']['sparks'],open_channels=list(starts))
def main(out):
 start=sources();out.mkdir(parents=True,exist_ok=False)
 b.ResearchPlant=ObservedPlant;b.OurController=ObservedController;b.SpeeduinoRuntime=ObservedReference;ss.ContactProgram=ObservedProgram;ss.SecondaryMonitor=ObservedMonitor
 t=b.benchmark_tune();t['transient_enrichment']['mode']='off'
 for kind,r in t['secondary_tables'].items():
  r.update(mode='input',debounce_ms=20);r['map']['load']=[10+6*i for i in range(16)];r['map']['cells']=[95 if kind=='fuel'else 14]*256
 spec=dict(initial=[False,False],edges=[dict(at_us=21199,channel=0,level=True),dict(at_us=21201,channel=0,level=False),dict(at_us=100001,channel=0,level=True),dict(at_us=102999,channel=1,level=True)])
 for label,who,target,bits in [('portable','ours',False,32),('target','ours',True,32),('speeduino32','speeduino',False,32),('speeduino16','speeduino',False,16)]:
  print('Running causal',label,flush=True);events.clear()
  result=b.run(who,'throttle_step',1,250,control_period_us=5000,target_dispatcher=target,reference_timer_bits=bits,secondary_options=dict(tune=t,stimulus=spec),load_options=dict(tune=t,emap_kpa=125))
  physical_ends=set(instances[-1].integration_ends)
  check(set(e['at_us']for e in spec['edges'])<=physical_ends,label+' integration lands on every independent contact edge')
  stages=[e for e in events if e['kind']=='acquisition_stage']
  if who=='ours':
   check(bool(stages)and all(e['source_time_us']in physical_ends for e in stages),label+' integration lands on actual acquisition stages before sampling')
   check(not any(x['acquisition']['ready']and int(x['acquisition']['read_completed_us'])>x['control_attempt_us']for x in result['secondary_monitor']),label+' no unfinished acquisition published')
  replayed=replay(result)
  check(abs(replayed['fuel_delta_mg'])<1e-6 and replayed['edge_replayed_sparks']==replayed['plant_sparks']and not replayed['open_channels'],label+' independent complete-edge replay explains plant fuel and spark totals',replay=replayed)
  row=dict(label=label,summary=result['summary'],event_count=len(events),stages=len(stages),replay=replayed,trace=save(out,label+'-causal',result),instrumentation=save(out,label+'-causal-events',events));rows.append(row)
 # Exact secondary-disabled replay: the same exogenous timing program is used,
 # so it adds identical numerical integration boundaries to each pair.
 for label,target in [('portable',False),('target',True)]:
  common=b.benchmark_tune();common['transient_enrichment']['mode']='off';mutated=copy.deepcopy(common)
  f=mutated['secondary_tables']['fuel'];f.update(source='tps',axis='tps_pct',cells='multiplier',condition='tps_pct',threshold=37,debounce_ms=7,input_channel=1,active_high=False);f['map']['load']=[i*100/15 for i in range(16)];f['map']['cells']=[200-(i%16)for i in range(256)]
  s=mutated['secondary_tables']['spark'];s.update(source='imap_emap',axis='imap_emap_pct',cells='multiplier',condition='ethanol_pct',threshold=80,debounce_ms=99,input_channel=0,active_high=False);s['map']['load']=[i*20 for i in range(16)];s['map']['cells']=[150+(i%16)for i in range(256)]
  pair=[]
  for variant,tune in [('default',common),('nondefault',mutated)]:
   print('Running Off',label,variant,flush=True);events.clear()
   result=b.run('ours','throttle_step',3,250,control_period_us=5000,target_dispatcher=target,secondary_options=dict(tune=tune,stimulus=spec),load_options=dict(tune=tune,emap_kpa=125))
   pair.append(result);rows.append(dict(label=label+'-off-'+variant,summary=result['summary'],trace=save(out,label+'-off-'+variant,result),replay=replay(result)))
  a,c=pair;check(a['edges']==c['edges'] and a['summary']['ledger']==c['summary']['ledger'] and a['summary']['final_rpm']==c['summary']['final_rpm'],label+' disabled secondary nondefault metadata preserves complete actuator sequence and plant state',edge_count=len(a['edges']))
 end=sources();check(start==end,'review run source bindings stayed unchanged',changed=[p for p in start if start[p]!=end[p]])
 report=dict(passed=all(x['passed']for x in checks),scope='Independent instrumented coupling, sampling/physical-clock assertions, complete executed-edge replay, and exact project Off-metadata regression. Native target timing is synthetic; not physical qualification.',checks=checks,runs=rows,source_hashes_start=start,source_hashes_end=end)
 (out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(passed=report['passed'],checks=checks),indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main(BASE/(sys.argv[1]if len(sys.argv)>1 else'coupling-probe001'))
