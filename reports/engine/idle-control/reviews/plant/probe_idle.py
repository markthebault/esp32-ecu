import sys,math,json,copy,hashlib,random
from pathlib import Path
base=Path(__file__).resolve().parent;snapshot=base/'sources'
sys.path.insert(0,str(snapshot/'tools'))
from idle_valve_plant import IdleValve
from speeduino_runtime import SpeeduinoRuntime

def advance_valve(v,seconds,step=0.000125,battery=14):
    elapsed=0.
    while elapsed<seconds-1e-12:
        dt=min(step,seconds-elapsed);v.step(dt,battery);elapsed+=dt

result={}
for mode in IdleValve.MODES:
    v=IdleValve(mode);v.edge(True);advance_valve(v,.1)
    driven=v.snapshot();v.cut();advance_valve(v,.6)
    result['mode_'+mode]={'after_100ms_drive':driven,'after_600ms_low':v.snapshot()}
for dt in (.001,.00025,.000125,.0000625):
    v=IdleValve();v.edge(True);advance_valve(v,.1,dt)
    result['steady_dt_'+str(dt)]=v.snapshot()
rng=random.Random(643);v=IdleValve()
for n in range(2000):
    if rng.random()<.12:v.edge(not v.high)
    v.step(rng.uniform(1e-6,.001),rng.uniform(8,16))
result['random_electrical_balance']=v.snapshot()
for filename in ('first-ours.json','first-speeduino.json','half-step-ours.json','half-step-speeduino.json'):
    data=json.loads((snapshot.parents[0]/'../idle'/filename).resolve().read_text()) if False else json.loads((base.parent/'idle'/filename).read_text())
    v=IdleValve();now=0;transitions=[]
    for event in data['edges']:
        us,ch,high,*reason=event
        if ch!=8:continue
        advance_valve(v,(us-now)/1e6);v.edge(high);now=us;transitions.append(event)
    advance_valve(v,data['summary']['duration_s']-now/1e6)
    predicted=v.snapshot();reported=data['summary']['idle_valve']
    result['replay_'+filename]={'transition_count':len(transitions),'first':transitions[:3],
       'source_delta_j':predicted['source_j']-reported['source_j'],
       'copper_delta_j':predicted['copper_j']-reported['copper_j'],
       'flyback_delta_j':predicted['flyback_j']-reported['flyback_j'],
       'opening_delta_pct':predicted['opening_pct']-reported['opening_pct'],
       'current_delta_a':predicted['current_a']-reported['current_a'],
       'replayed_final':predicted}
tune=json.loads((snapshot/'config/engine/defaults.json').read_text());tune['settings']['idle_enabled']=True
for bits in (16,32):
    for seed in (False,True):
        rt=SpeeduinoRuntime(timer_bits=bits)
        try:
            initial=rt.configure_idle(tune,seeded=seed)
            probe=rt._edges(rt.command('idleprobe 200 1 85 0'))
            clock=rt._edges(rt.command('idleclock 25000'))
            before=rt.idle_status();halt=rt.halt();after=rt.idle_status()
            after_clock=rt._edges(rt.command('idleclock 50000'))
            result[f'reference_{bits}_seed_{seed}']={'profile':rt.idle_profile,'initial':initial,'probe':probe,'clock':clock,'before_halt':before,'halt':halt,'after_halt':after,'post_halt_clock':after_clock,'post_halt_status':rt.idle_status()}
        finally:rt.close()
(base/'idle-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({key:val for key,val in result.items() if key.startswith('reference_') or key.startswith('replay_')},indent=2))
