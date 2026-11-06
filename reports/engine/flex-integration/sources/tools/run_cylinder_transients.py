#!/usr/bin/env python3
"""Coupling convergence, transients and cam policy with independent cylinders."""
import argparse,copy,hashlib,json,time
from pathlib import Path
import compare_engine_controllers as benchmark
from engine_research_plant import ResearchPlant
from run_target_scenarios import TargetController,audit as batch_audit
from run_sequential_scenarios import audit
from run_cylinder_scenarios import FLOW,SPARK,trims,R
from speeduino_runtime import SpeeduinoRuntime

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(baseline,output):
 output.mkdir(parents=True,exist_ok=True);started=time.monotonic();failures=[];checks=[];cases=[];attest=[]
 source=json.loads((baseline/'summary.json').read_text())
 for name,value in source['source_hashes'].items():
  if digest(R/name)!=value:raise RuntimeError('Baseline source changed: '+name)
 if not source['passed']:raise RuntimeError('Baseline comparison did not pass')
 # Replay all nine independent edge streams rather than trusting summaries.
 for row in source['rows']:
  name=row['controller']+'-'+row['mode'];raw=json.loads((baseline/(name+'.json')).read_text());check=audit(raw,row['controller']=='ours');checks.append(dict(case=name,kind='baseline_edge_replay',**check))
  if not check['passed']:failures.append(dict(case=name,errors=check['errors']))
 for who in ('ours','speeduino'):
  a=json.loads((baseline/(who+'-disabled.json')).read_text());b=json.loads((baseline/(who+'-neutral.json')).read_text())
  same=a['edges']==b['edges'] and a['combustions']==b['combustions'];checks.append(dict(case=who,kind='disabled_stored_values_vs_enabled_neutral',passed=same))
  if not same:failures.append(dict(case=who,errors=['Neutral changes execution']))
 neutral_pw=next(row['calibration']['neutral_pw_us'] for row in source['rows'] if row['mode']=='total_pw_adjusted')
 original=benchmark.OurController,benchmark.SpeeduinoRuntime,benchmark.ResearchPlant
 def run(who,scenario,step=250,sequential=True,bits=16):
  mode='corrected' if who=='ours' else 'total_pw_adjusted';active=trims(mode,neutral_pw)
  if not sequential:active['enabled']=False
  class Unequal(ResearchPlant):
   def __init__(self):super().__init__(injector_flow_factors=FLOW,optimum_spark_offsets=SPARK)
  class Project(TargetController):
   def __init__(self,tune=None):
    t=copy.deepcopy(tune or benchmark.benchmark_tune());t['cylinder_trims']=copy.deepcopy(active);super().__init__(t)
  class Reference(SpeeduinoRuntime):
   def __init__(self,**kwargs):
    super().__init__(**kwargs);self.cylinder_trims(active)
    manifest=R/('.cache/engine/speeduino-sim16/build-manifest.json' if self.timer_bits==16 else '.cache/engine/speeduino-sim/build-manifest.json')
    binary=digest(Path('/proc')/str(self.process.pid)/'exe')
    if json.loads(manifest.read_text())['binary_sha256']!=binary:raise RuntimeError('Running reference differs from build manifest')
    attest.append(dict(timer_bits=self.timer_bits,live_executable_sha256=binary,manifest_sha256=digest(manifest)))
  benchmark.OurController=Project;benchmark.SpeeduinoRuntime=Reference;benchmark.ResearchPlant=Unequal
  label=f'{who}-{scenario}-{step}-'+('sequential' if sequential else 'batch')+f'-timer{bits}'
  print('Running',label,flush=True)
  result=benchmark.run(who,scenario,10,step,control_period_us=5000,sequential=sequential,reference_timer_bits=bits)
  check=audit(result,who=='ours') if sequential else batch_audit(result,True)
  result['audit']=check;(output/(label+'.json')).write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n');cases.append(dict(label=label,controller=who,scenario=scenario,sequential=sequential,timer_bits=bits,step_us=step,summary=result['summary'],audit=check))
  if not check['passed']:failures.append(dict(case=label,errors=check['errors']))
  return result
 try:
  for who in ('ours','speeduino'):
   fine=run(who,'warm_start',125);mode='corrected' if who=='ours' else 'total_pw_adjusted';coarse=next(row['summary'] for row in source['rows'] if row['controller']==who and row['mode']==mode);f=fine['summary']
   diffs=dict(rpm=abs(coarse['mean_final_second_rpm']-f['mean_final_second_rpm'])/max(1,abs(f['mean_final_second_rpm'])))
   for key in ('fuel_in_mg','combustion_shaft_j'):diffs[key]=abs(coarse['ledger'][key]-f['ledger'][key])/max(1,abs(f['ledger'][key]))
   passed=max(diffs.values())<.03;checks.append(dict(case=who,kind='250_vs125us_coupling',relative_differences=diffs,tolerance=.03,passed=passed))
   if not passed:failures.append(dict(case=who,errors=['Coupling convergence']))
   run(who,'throttle_step');run(who,'cam_dropout')
  for scenario in ('warm_start','throttle_step'):run('ours',scenario,sequential=False)
  run('speeduino','warm_start',bits=32)
 finally:benchmark.OurController,benchmark.SpeeduinoRuntime,benchmark.ResearchPlant=original
 paths=['tools/run_cylinder_transients.py','tools/run_cylinder_scenarios.py','tools/engine_research_plant.py','tools/compare_engine_controllers.py','tools/run_target_scenarios.py','tools/run_sequential_scenarios.py','tools/target_runtime.py','tools/target_timing_bridge.cpp','tools/speeduino_runtime.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','config/engine/defaults.json','simulation/modelica/EngineAirPath.mo']
 paths+=sorted(str(p.relative_to(R)) for p in (R/'firmware/include/ecu').glob('*.hpp'))
 report=dict(passed=not failures,failures=failures,checks=checks,cases=cases,live_reference_binaries=attest,baseline_summary_sha256=digest(baseline/'summary.json'),source_hashes={p:digest(R/p) for p in paths},runtime_seconds=time.monotonic()-started,scope='Uncalibrated external MVEM air path plus local empirical combustion/free shaft; native source controllers, zero CPU/IRQ execution cost. No electrical or physical engine qualification.')
 (output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--baseline-dir',type=Path,required=True);p.add_argument('--report-dir',type=Path,default=R/'.cache/engine/cylinder-transients');a=p.parse_args();r=validate(a.baseline_dir,a.report_dir);print(json.dumps(dict(passed=r['passed'],failures=r['failures']),indent=2));raise SystemExit(0 if r['passed'] else 1)
