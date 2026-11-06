#!/usr/bin/env python3
"""Additional restart and reachable-target experiments with the fixed idle plant."""
import argparse,copy,gzip,hashlib,json
from pathlib import Path
from compare_engine_controllers import run,benchmark_tune
R=Path(__file__).resolve().parents[1]

def validate(out):
 out.mkdir(parents=True,exist_ok=True);rows=[];failures=[]
 for who in ('ours','speeduino'):
  for name,scenario,duration in [('restart','stall_restart',12),('reachable-target','idle_load_step',20)]:
   tune=benchmark_tune();tune['settings']['idle_enabled']=True
   if name=='reachable-target':tune['settings'].update(idle_target_rpm=1100,idle_kp=.06,idle_ki=.06)
   print('Running',who,name,flush=True);r=run(who,scenario,duration=duration,control_period_us=5000,idle_options=dict(tune=tune));s=r['summary']
   if name=='restart' and (s['mean_final_second_rpm']<500 or not any(e[0]>8000000 and e[1]==8 and e[2] for e in r['edges'])):failures.append([who,name,'did not resume engine/idle after supervised restart'])
   final=[x for x in r['trace'] if x['time']>=duration-1];target=1100 if name=='reachable-target' else 900
   mae=sum(abs(x['plant_rpm']-target) for x in final)/len(final)
   if name=='reachable-target' and mae>25:failures.append([who,name,'final target MAE >25RPM in this model'])
   path=out/(who+'-'+name+'.json.gz');path.write_bytes(gzip.compress(json.dumps(r,separators=(',',':')).encode(),mtime=0))
   rows.append(dict(controller=who,case=name,final_second_target_mae_rpm=mae,summary=s,profile=dict(idle_settings={k:v for k,v in tune['settings'].items() if k.startswith('idle_')},idle_control=tune['idle_control']),trace_file=path.name,trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 report=dict(passed=not failures,failures=failures,rows=rows,scope='Same fixed uncalibrated engine/valve. The1100RPM target has authority above the no-idle-valve equilibrium; normalized gains .06/.06 are an explicit model-specific calibration, not a physical engine tune.',
  source_sha256={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'tools/run_idle_followups.py',R/'tools/compare_engine_controllers.py',R/'tools/idle_valve_plant.py',R/'tools/engine_research_plant.py',R/'tools/target_timing_bridge.cpp',*sorted((R/'firmware/include/ecu').glob('*.hpp'))]})
 (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/idle/followups');a=p.parse_args();r=validate(a.report_dir);print(json.dumps(dict(passed=r['passed'],failures=r['failures']),indent=2));raise SystemExit(0 if r['passed'] else 1)
