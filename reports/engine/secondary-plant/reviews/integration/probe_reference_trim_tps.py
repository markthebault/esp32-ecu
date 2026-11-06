"""Independent actual production-loop trim and sensor-unit probes."""
import copy,hashlib,json,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent;ROOT=BASE.parents[2];sys.path.insert(0,str(ROOT/'tools'))
from compare_engine_controllers import benchmark_tune
from speeduino_runtime import SpeeduinoRuntime

def drive(r,end):
 start=r.now;events=[(u,False)for u in range(((start//250)+1)*250,end+1,250)]
 events.extend((u,1)for u in range(((start//1000)+1)*1000,end+1,1000)if(u//1000)%60<58)
 if r.sequential:events.extend((u,2)for u in range(90000,end+1,120000)if u>start)
 for u,kind in sorted(events):
  if kind==2:r.input_edge(u,1,True);r.input_edge(u,1,False)
  else:r.advance(u,tooth=bool(kind))

def tune(mode):
 t=benchmark_tune();t['transient_enrichment']['mode']='off'
 for kind,r in t['secondary_tables'].items():
  r.update(mode=mode,cells='multiplier'if mode=='multiply'else'absolute',condition='tps_pct',threshold=20)
  r['map']['load']=[10+6*i for i in range(16)];r['map']['cells']=[110 if kind=='fuel'and mode=='multiply'else 150 if mode=='multiply'else 100 if kind=='fuel'else 18]*256
 return t

def main(out):
 checks=[];details=[]
 def check(ok,label,**data):checks.append(dict(passed=bool(ok),label=label,**data))
 for bits in(32,16):
  t=tune('multiply');t['strategy']='sequential_4cyl';t['cylinder_trims']['enabled']=True;t['cylinder_trims']['spark_deg']=[2,-2,0,0]
  for m,pct in zip(t['cylinder_trims']['fuel_maps'],(110,90,100,100)):m['cells']=[pct]*36
  r=SpeeduinoRuntime(timer_bits=bits,secondary_channels=(0,1),sequential=True)
  try:
   r.configure_load(t,allow_cylinder_trims=True);r.configure_secondary(t);r.cylinder_trims(t['cylinder_trims']);r.pressures(125,100);r.sensors(dict(map_kpa=60,tps_pct=12.5,clt_c=85,iat_c=25,battery_v=14,**{'lambda':1}));drive(r,500000)
   pw=r.channel_pulses();base=pw[2]
   check(r.status()['sync']==2,'native'+str(bits)+' fixed-speed trim probe achieves production cam phase sync')
   # Production percentageApprox<uint8_t> uses a9-bit fraction here:
   #110% ->563/512;90% ->461/512. Entire PW includes opening time.
   expected=[(base*563+256)//512,(base*461+256)//512,base,base]
   check(pw==expected,'native'+str(bits)+' actual fuel trims scale the full pulse with declared fixed-point coefficients',actual=pw,expected=expected)
   check(r.secondary_status()['combined_advance']==15,'native'+str(bits)+' secondary spark composition precedes individual trims')
   details.append(dict(bits=bits,kind='trim',status=r.secondary_status(),pulses=pw,expected_full_pulse=expected,load_profile=r.load_profile,secondary_profile=r.secondary_profile))
  finally:r.close()
  r=SpeeduinoRuntime(timer_bits=bits,secondary_channels=(0,1))
  try:
   t=tune('conditional');r.configure_load(t);r.configure_secondary(t);r.pressures(125,100)
   samples=[]
   for physical,end in((5,200000),(20,400000),(25,600000),(20,800000),(0,1000000)):
    r.sensors(dict(map_kpa=60,tps_pct=physical,clt_c=85,iat_c=25,battery_v=14,**{'lambda':1}));drive(r,end);s=r.secondary_status();samples.append(dict(physical_tps_pct=physical,status=s))
    if physical==20:check(s['tps_raw_half_pct']==40 and not s['fuel_active']and not s['spark_active'],'native'+str(bits)+' exact interior TPS20 plateau obeys strict greater-than')
    if physical==25:check(s['tps_raw_half_pct']>40 and s['fuel_active']and s['spark_active'],'native'+str(bits)+' above-threshold TPS activates both tables')
   details.append(dict(bits=bits,kind='tps',samples=samples))
  finally:r.close()
 report=dict(passed=all(c['passed']for c in checks),scope='Independent diagnostic fixed1000rpm real production setup/loop/sensor/scheduler execution; not free-shaft coupled or physical ECU qualification.',checks=checks,details=details,source_bindings={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in('tools/speeduino_runtime.py','tools/speeduino_sim.cpp')})
 if out.exists():raise SystemExit('Preserve earlier evidence')
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=report['passed'],checks=checks),indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main(BASE/(sys.argv[1]if len(sys.argv)>1 else'reference-trim-tps001.json'))
