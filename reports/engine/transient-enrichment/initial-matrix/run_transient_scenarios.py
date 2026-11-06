#!/usr/bin/env python3
"""Declared transient profiles on independent pulse-driven research plants.

Runs project portable/target and pinned Speeduino32/16 production controllers.
The external MVEM air path, empirical film/combustion and fixed cylinder order
are independent of ECU settings. This is no calibrated engine qualification.
"""
import argparse,copy,hashlib,json,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_target_scenarios import audit as edge_audit

ROOT=Path(__file__).resolve().parents[1]
PROFILES=(('ours',False,32,'portable'),('ours',True,32,'target'),('speeduino',False,32,'speeduino32'),('speeduino',False,16,'speeduino16'))
CASES=(
 ('tps_multiply','transient_tip','tps_rate','multiply',100,False),
 ('tps_adder','transient_tip','tps_rate','add_reference',100,False),
 ('map_multiply','transient_tip','map_rate','multiply',100,False),
 ('map_adder','transient_tip','map_rate','add_reference',100,False),
 ('weak_reverse','transient_reverse','tps_rate','multiply',80,False),
 ('decel_zero','transient_tip','tps_rate','add_reference',0,False),
 ('map_decel','transient_tip','map_rate','multiply',80,False),
 ('small_noise','transient_noise','tps_rate','multiply',100,False),
 ('map_load','transient_load','map_rate','multiply',100,False),
 ('sensor_fault','sensor_short','tps_rate','multiply',100,False),
 ('trigger_loss','trigger_dropout','tps_rate','multiply',100,False),
 ('cold_adder','transient_tip','tps_rate','add_reference',100,True),
)

def config(case,disabled=False):
 c=copy.deepcopy(benchmark.benchmark_tune()['transient_enrichment'])
 c.update(mode='off' if disabled else case[2],apply=case[3],decel_fuel_pct=case[4],
          tps_added_pct=[0,2,4,6],map_added_pct=[0,2,4,6])
 return c

def observations(result):
 out=[]
 for row in result['trace']:
  d=row['ecu']['transient_enrichment'];ours='available' in d
  out.append(dict(time=row['time'],phase=d['phase_code'] if ours else 1 if d['accelerating'] else 2 if d['decelerating'] else 0,
                  correction_pct=d['correction_pct'],tps_dot=d['tps_dot_pct_s'],map_dot=d['map_dot_kpa_s']))
 return out

def metrics(result):
 rows=observations(result);active=[r for r in rows if r['time']>=3 and r['phase']]
 burn=[r for r in result['combustions'] if 3<=r['time_s']<4.5 and r['lambda_value'] is not None]
 return dict(active_samples_after3=len(active),first_active_after3_s=active[0]['time'] if active else None,
             min_correction_after3=min((r['correction_pct'] for r in rows if r['time']>=3),default=None),
             max_correction_after3=max((r['correction_pct'] for r in rows if r['time']>=3),default=None),
             mean_abs_cylinder_lambda_error_3_to4_5=sum(abs(r['lambda_value']-1) for r in burn)/len(burn) if burn else None,
             cylinder_combustions_3_to4_5=len(burn))

def audit(result,case,ours,disabled=False):
 a=edge_audit(result,False);errors=a['errors'];s=result['summary'];rows=observations(result)
 def require(ok,msg):
  if not ok:errors.append(msg)
 if ours:
  require(s['max_injector_high_us']<=15000 and s['max_dwell_high_us']<=3500,'project electrical high-time bound')
  expected=4 if case[1]=='sensor_short' else 128 if case[1]=='trigger_dropout' and s['project_runtime']=='target_dispatcher' else 0
  require(s['project_fault_mask_seen']==expected,'missing or unexpected project fault')
  require(all(not r['ecu'].get('physical_outputs_enabled',False) for r in result['trace']),'physical output policy')
  if case[0]=='decel_zero':
   require(any(r['time']>=3 and r['ecu'].get('fuel_cut') and not r['ecu'].get('spark_cut') for r in result['trace']),'decel fuel-only cut not exercised')
 if disabled:require(all(r['correction_pct']==100 and not r['phase'] for r in rows if r['time']>=3),'disabled negative control has a transient correction')
 elif case[0]=='small_noise':require(not any(r['phase'] for r in rows if 3<=r['time']<5),'sub-minimum TPS noise triggered event')
 elif case[0] not in ('sensor_fault','trigger_loss'):require(any(r['phase'] for r in rows if r['time']>=3),'requested transient mode was not exercised')
 a['passed']=not errors;return a

def validate(output):
 output.mkdir(parents=True,exist_ok=True);started=time.monotonic();runs=[];failures=[];refinement=[];negative=[]
 def execute(profile,case,step=250,disabled=False):
  who,target,bits,label=profile;name=label+'-'+case[0]+('-off' if disabled else '')+'-'+str(step)
  print('Running',name,flush=True)
  options=dict(config=config(case,disabled),cold=case[5],reference_map_sampling=0)
  r=benchmark.run(who,case[1],6,step,control_period_us=5000,semi_sequential=True,target_dispatcher=target,reference_timer_bits=bits,transient_options=options)
  s=r['summary'];s.update(label=label,case=case[0],disabled=disabled,metrics=metrics(r),audit=audit(r,case,who=='ours',disabled))
  path=output/(name+'.json');path.write_text(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')
  row=copy.deepcopy(s);row['path']=path.name;row['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();runs.append(row)
  if not s['audit']['passed']:failures.append(dict(name=name,errors=s['audit']['errors']))
  print('Result',name,round(s['final_rpm'],1),'RPM',s['audit']['errors'],flush=True);return row
 for profile in PROFILES:
  for case in CASES:execute(profile,case)
  for case in (CASES[0],CASES[4]):
   fine=execute(profile,case,125);coarse=next(r for r in runs if r['label']==profile[3] and r['case']==case[0] and r['step_us']==250 and not r['disabled'])
   differences={k:abs(coarse['ledger'][k]-fine['ledger'][k])/max(1,abs(fine['ledger'][k])) for k in ('fuel_in_mg','combustion_shaft_j')}
   differences['mean_final_second_rpm']=abs(coarse['mean_final_second_rpm']-fine['mean_final_second_rpm'])/max(1,abs(fine['mean_final_second_rpm']))
   check=dict(label=profile[3],case=case[0],relative_differences=differences,tolerance=.03,passed=max(differences.values())<.03 and fine['audit']['passed']);refinement.append(check)
   if not check['passed']:failures.append(dict(name=profile[3]+'-'+case[0]+'-refinement',errors=['step refinement exceeds3%']))
  for case in (CASES[1],CASES[-1]):
   off=execute(profile,case,disabled=True);on=next(r for r in runs if r['label']==profile[3] and r['case']==case[0] and r['step_us']==250 and not r['disabled'])
   check=dict(label=profile[3],case=case[0],fuel_difference_mg=on['ledger']['fuel_in_mg']-off['ledger']['fuel_in_mg'],on_metrics=on['metrics'],off_metrics=off['metrics'],passed=on['metrics']['active_samples_after3']>0 and off['metrics']['active_samples_after3']==0 and abs(on['ledger']['fuel_in_mg']-off['ledger']['fuel_in_mg'])>.01)
   negative.append(check)
   if not check['passed']:failures.append(dict(name=profile[3]+'-'+case[0]+'-negative',errors=['disabled sensitivity not exercised']))
 paths=['tools/run_transient_scenarios.py','tools/compare_engine_controllers.py','tools/run_target_scenarios.py','tools/engine_research_plant.py','tools/engine_runtime.py','tools/engine_bridge.cpp','tools/target_runtime.py','tools/target_timing_bridge.cpp','tools/speeduino_runtime.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','scripts/build_speeduino_sim.py','simulation/modelica/EngineAirPath.mo','config/engine/defaults.json']
 paths+=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'firmware/include/ecu').glob('*.hpp'))
 report=dict(passed=not failures,failures=failures,controller_cases=48,refinement_cases=len(refinement),negative_cases=len(negative),runs=runs,refinement=refinement,negative=negative,
   reference_commit='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20',
   scope='Native production controllers and schedulers, virtual GPIO, separate independent MVEM/empirical plants; no AVR CPU/IRQ model or physical qualification',
   calibration='Declared mild2/4/6% extra fuel curves are comparison profiles, not an engine base tune; fixed warm film5%/50ms, cold45%/1.5s; EGO/WUE/ASE neutral',
   differences='Acquisition windows and opposite-sign cancellation differ; upstream TPS33ms and integer MAP delta dispatch retained; own maximum-extra clamp has no reference field',
   refinement_scope='Halving coupling step also changes production reference loop cadence; not isolated solver convergence',
   runtime_seconds=time.monotonic()-started,source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
 (output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'.cache/engine/transient/matrix');a=p.parse_args();r=validate(a.output_dir);print('Passed',r['passed'],'failures',r['failures'],flush=True)
 if not r['passed']:raise SystemExit(1)
