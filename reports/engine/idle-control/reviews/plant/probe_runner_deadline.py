from pathlib import Path
import sys,json,math
base=Path(__file__).resolve().parent;snapshot=base/'sources';sys.path.insert(0,str(snapshot/'tools'))
import engine_sil,target_runtime
from idle_valve_plant import IdleValve
class Runtime:
 def __init__(self,tune):self.events=[(0,8,True,0,0),(150,None,False,0,0)]
 def wheel(self):pass
 def step(self,*args,**kw):return dict(faults=0,state='running',synced=True,advance_deg=10)
 def next_event_us(self):return self.events[0][0] if self.events else 2**64-1
 def pop_event(self):return self.events.pop(0)[1:]
 def cut(self):pass
 def data(self):return {}
 def idle_status(self):return {}
 def trigger(self,*a):return 0
 def timing_reason(self):return 'control_deadline'
 def close(self):pass
captured=[]
realplant=engine_sil.Plant
class InstrumentedPlant(realplant):
 def integrate(self,t,dt,*a,**kw):
  if t<.0003:captured.append({'start_s':t,'dt_s':dt,'idle_high':self.idle_valve.high})
  return super().integrate(t,dt,*a,**kw)
engine_sil.Plant=InstrumentedPlant;target_runtime.TargetRuntime=Runtime
cfg=json.loads((snapshot/'config/engine/defaults.json').read_text());cfg['settings']['idle_enabled']=True
out=engine_sil.Simulation(cfg,duration_s=1).run()
expected=IdleValve();expected.edge(True);expected.step(.00015,13.8);expected.cut()
for _ in range(10000):expected.step(.0001,13.8)
result={'probe':'Synthetic executed events through the unmodified runner: rise0us, deadline cut150us. No controller-performance inference.',
 'events':out['edges'][:2],'first_integrations':captured,
 'actual_valve':out['summary']['idle_valve'],'independent_150us_pulse':expected.snapshot()}
(base/'runner-deadline-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
