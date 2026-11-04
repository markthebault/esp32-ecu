#!/usr/bin/env python3
"""Executed idle PWM -> fixed independent RL/NC valve -> external MVEM engine.

Pinned real controller code, separate plant instances, no imposed RPM trace.
These are uncalibrated software experiments and contain explicit failed-actuator
negative controls. Electrical accounting is not mechanical-energy validation.
"""
import argparse,copy,gzip,hashlib,json,statistics,time
from pathlib import Path
import compare_engine_controllers as benchmark
from speeduino_runtime import SpeeduinoRuntime

R=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tune(profile):
 t=benchmark.benchmark_tune();t['settings']['idle_enabled']=True
 if profile=='open_loop':t['idle_control']['algorithm']='open_loop'
 elif profile=='no_integral':t['settings']['idle_ki']=0
 elif profile=='bench_adjusted':
  # Explicit example calibration against this fixed, uncalibrated plant only.
  t['settings']['idle_kp']=.06;t['settings']['idle_ki']=.06
  t['idle_control']['run_pct']=[65,50,38,30,10,10]
 return t

def reference_pwm_checks():
 rows=[]
 for bits in (32,16):
  for seeded in (False,True):
   for mode in ('open_loop','closed_loop'):
    r=SpeeduinoRuntime(timer_bits=bits);t=tune('default');c=t['idle_control'];c['algorithm']=mode;c['run_pct']=[50]*6;c['crank_pct']=[50]*6
    try:
     initial=r.configure_idle(t,seeded=seeded);assert not initial
     assert not r.command('idleprobe 300 1 85 0')
     edges=r._edges(r.command('idleclock 100000'));before=r.idle_status();r.command('idledisable');after=r._edges(r.command('idleclock 150000'))
     starts=[e[0] for e in edges if e[1]==8 and e[2]]
     assert not starts if not seeded else starts[0]==(16 if bits==16 else 4)
     if seeded:assert all(b-a==10000 for a,b in zip(starts,starts[1:]))
     restarts=any(e[2] for e in after)
     if seeded:assert restarts==(mode=='closed_loop') # Preserve upstream OLCL disable discrepancy.
     rows.append(dict(bits=bits,seeded=seeded,mode=mode,profile=r.idle_profile,edges=edges,reported_before_disable=before,post_disable_edges=after,restarts=restarts))
    finally:r.close()
  for hz in (50,100,250):
   for duty in (0,1,50,99,100):
    r=SpeeduinoRuntime(timer_bits=bits);t=tune('open_loop');c=t['idle_control'];c['frequency_hz']=hz;c['crank_pct']=[duty]*6;c['run_pct']=[duty]*6
    try:
     initial=r.configure_idle(t);immediate=r._edges(r.command('idleprobe 300 1 85 0'));edges=initial+immediate+r._edges(r.command('idleclock 400000'))
     high=False;last=0;area=0
     for when,ch,value,_,_ in edges:
      assert ch==8 and high!=value;area+=(when-last)*high;last=when;high=value
     area+=(400000-last)*high;measured=area/4000
     assert abs(measured-duty)<.5,(bits,hz,duty,measured)
     starts=[x[0] for x in edges if x[2]]
     if 0<duty<100:assert all(abs((b-a)-1e6/hz)<=2*(16 if bits==16 else 4) for a,b in zip(starts,starts[1:]))
     rows.append(dict(bits=bits,hz=hz,duty_pct=duty,measured_gpio_duty_pct=measured,edges=edges,profile=r.idle_profile))
    finally:r.close()
 return rows

def metrics(result):
 trace=result['trace'];late=[r for r in trace if r['time']>=result['summary']['duration_s']-1]
 target=lambda r:r['ecu'].get('idle',{}).get('target_rpm',r['ecu']['idle_pwm'].get('target_rpm',0))
 errors=[abs(r['plant_rpm']-target(r)) for r in late if target(r)>0]
 return dict(final_second_target_mae_rpm=statistics.mean(errors) if errors else None,
             final_second_rpm_span=max(r['plant_rpm'] for r in late)-min(r['plant_rpm'] for r in late),
             maximum_opening_pct=max(r['ecu']['idle_valve']['opening_pct'] for r in trace),
             minimum_opening_pct=min(r['ecu']['idle_valve']['opening_pct'] for r in trace),
             maximum_current_a=max(r['ecu']['idle_valve']['current_a'] for r in trace),
             executed_idle_edges=sum(row[1]==8 for row in result['edges']))

def run(out):
 out.mkdir(parents=True,exist_ok=True);started=time.monotonic();rows=[];failures=[]
 pwm=reference_pwm_checks();(out/'reference-pwm.json').write_text(json.dumps(pwm,indent=2)+'\n')
 cases=[('warm','warm_start','default','normal'),('load','idle_load_step','default','normal'),('blip','idle_throttle_blip','default','normal'),('cold','idle_cold_start','default','normal'),
        ('sensor-loss','sensor_short','default','normal'),('trigger-loss','trigger_dropout','default','normal'),
        ('disconnected','idle_load_step','default','disconnected'),('stuck-closed','idle_load_step','default','stuck_closed'),('stuck-open','idle_load_step','default','stuck_open'),
        ('inverted-drive','idle_load_step','default','inverted_drive'),('no-integral','idle_load_step','no_integral','normal'),('open-loop','idle_load_step','open_loop','normal'),('bench-adjusted','idle_load_step','bench_adjusted','normal')]
 for who in ('ours','speeduino'):
  for name,scenario,profile,valve in cases:
   print('Running',who,name,flush=True)
   result=benchmark.run(who,scenario,duration=12,step_us=250,control_period_us=5000,idle_options=dict(tune=tune(profile),valve_mode=valve))
   summary=result['summary'];m=metrics(result);key=who+'-'+name
   if summary['final_outputs_high'] or summary['max_dwell_high_us']>3504:failures.append([key,'software output bounds'])
   v=summary['idle_valve']
   if abs(v['electrical_residual_j'])>1e-7:failures.append([key,'coil electrical ledger'])
   if m['maximum_current_a']>2.01 or not 0<=m['minimum_opening_pct']<=m['maximum_opening_pct']<=100:failures.append([key,'actuator bounds'])
   if valve in ('disconnected','stuck_closed') and m['maximum_opening_pct']!=0:failures.append([key,'failed-closed negative control'])
   if valve=='disconnected' and m['maximum_current_a']!=0:failures.append([key,'disconnected coil current'])
   if valve=='stuck_open' and m['minimum_opening_pct']!=100:failures.append([key,'failed-open negative control'])
   led=summary['ledger']
   if abs(led['fuel_residual_mg'])>1e-6 or abs(led['chemical_residual_j'])>1e-5 or abs(led['air_residual_kg'])>1e-10:failures.append([key,'engine mass/chemical ledger'])
   data=json.dumps(result,separators=(',',':')).encode();path=out/(key+'.json.gz');path.write_bytes(gzip.compress(data,mtime=0))
   rows.append(dict(key=key,controller=who,case=name,scenario=scenario,profile=profile,valve_mode=valve,metrics=m,summary=summary,trace_file=path.name,trace_sha256=digest(path)))
 for who in ('ours','speeduino'):
  print('Running',who,'half-step',flush=True)
  result=benchmark.run(who,'idle_load_step',duration=12,step_us=125,control_period_us=5000,idle_options=dict(tune=tune('default')))
  path=out/(who+'-half-step.json.gz');path.write_bytes(gzip.compress(json.dumps(result,separators=(',',':')).encode(),mtime=0))
  base=next(r for r in rows if r['key']==who+'-load')['summary'];s=result['summary'];differences={k:abs(s[k]-base[k])/max(1,abs(base[k])) for k in ('final_rpm','mean_final_second_rpm')}
  if max(differences.values())>.03:failures.append([who,'coupling/main-loop cadence sensitivity >3%'])
  rows.append(dict(key=who+'-half-step',summary=s,relative_differences=differences,trace_file=path.name,trace_sha256=digest(path),scope='Plant step and reference loop cadence both change; not isolated solver convergence'))
 print('Running speeduino native16 idle load',flush=True)
 result=benchmark.run('speeduino','idle_load_step',duration=12,step_us=250,control_period_us=5000,reference_timer_bits=16,idle_options=dict(tune=tune('default')))
 path=out/'speeduino16-load.json.gz';path.write_bytes(gzip.compress(json.dumps(result,separators=(',',':')).encode(),mtime=0));rows.append(dict(key='speeduino16-load',summary=result['summary'],metrics=metrics(result),trace_file=path.name,trace_sha256=digest(path)))
 paths=['tools/idle_valve_plant.py','tools/engine_research_plant.py','tools/engine_sil.py','tools/compare_engine_controllers.py','tools/run_idle_scenarios.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_runtime.py','scripts/build_speeduino_sim.py','config/engine/defaults.json','simulation/modelica/EngineAirPath.mo','tools/target_timing_bridge.cpp']
 paths+=sorted(str(p.relative_to(R)) for p in (R/'firmware/include/ecu').glob('*.hpp'))
 manifest=dict(passed=not failures,failures=failures,runs=len(rows),reference_pwm_checks=len(pwm),rows=rows,runtime_seconds=time.monotonic()-started,
  scope='Uncalibrated external Modelica air path plus empirical combustion/free shaft and current-squared NC mechanical model. Real production controller code, virtual GPIO, zero CPU/IRQ execution cost. Electrical energy ledger only, no physical or complete electromechanical validation.',
  source_sha256={p:digest(R/p) for p in paths},runtime_sha256={str(p.relative_to(R)):digest(p) for p in [R/'.cache/engine/target-native/libtarget_engine.so',R/'.cache/engine/modelica-mvem/airpath/EngineAirPath.fmu',R/'.cache/engine/speeduino-sim/build-manifest.json',R/'.cache/engine/speeduino-sim16/build-manifest.json']})
 (out/'summary.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/idle/matrix');a=p.parse_args();r=run(a.report_dir);print(json.dumps(dict(passed=r['passed'],runs=r['runs'],failures=r['failures']),indent=2));raise SystemExit(0 if r['passed'] else 1)
