#!/usr/bin/env python3
"""Declared load/pressure/AFR comparisons on the independent free-shaft plant.

Passing means ledger, actuation and declared protection checks passed. It does
not mean a tune is ideal, an engine is qualified, or reference policies match.
"""
import argparse,copy,gzip,hashlib,json,statistics,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_target_scenarios import audit as edge_audit

ROOT=Path(__file__).resolve().parents[1]
PROFILES=(('ours',False,32,'portable'),('ours',True,32,'target'),('speeduino',False,32,'speeduino32'),('speeduino',False,16,'speeduino16'))
CASES=('map_target','tps_map','alpha','alpha_no_map','alpha_guard','ratio_mixed','baro_fixed','baro_live','baro_wrong_datum','afr_off','afr_target','afr_measured','zero_fuel','alpha_uncalibrated')

def configuration(case,calibration):
 t=benchmark.benchmark_tune();t['transient_enrichment']['mode']='off';c=t['load_model'];options=dict(tune=t)
 if case.startswith('alpha'):
  c.update(fuel_source='tps',spark_source='tps',pressure='none',ve_axis='tps_pct',spark_axis='tps_pct',lambda_axis='tps_pct',trim_axis='tps_pct')
  for name,m in t['maps'].items():m['rpm']=list(calibration['rpm']);m['load']=list(calibration['tps_pct']);m['cells']=list(calibration['cells']) if name=='ve' and case!='alpha_uncalibrated' else m['cells']
  for m in t['cylinder_trims']['fuel_maps']:m['load']=[0,20,40,60,80,100]
  if case=='alpha_no_map':options['map_unavailable_window']=[3.2,4.2]
  if case=='alpha_guard':options['known_overpressure_window']=[4,4.25]
 elif case=='tps_map':
  c.update(fuel_source='tps',ve_axis='tps_pct',lambda_axis='tps_pct',trim_axis='tps_pct')
  for name in ('ve','lambda'):t['maps'][name]['load']=list(calibration['tps_pct'])
  for m in t['cylinder_trims']['fuel_maps']:m['load']=[0,20,40,60,80,100]
 elif case=='ratio_mixed':
  c.update(fuel_source='imap_emap',spark_source='tps',ve_axis='imap_emap_pct',spark_axis='tps_pct',lambda_axis='imap_emap_pct',trim_axis='imap_emap_pct',aux_role='emap')
  t['maps']['spark']['load']=list(calibration['tps_pct']);options['emap_kpa']=125
 elif case.startswith('baro'):
  c.update(pressure='map_baro',fixed_baro_kpa=100 if case=='baro_wrong_datum' else 80)
  if case=='baro_live':c.update(baro_source='aux',aux_role='baro')
  options['ambient_kpa']=80
  # Explicit benchmark calibration, not an implemented baro correction curve:
  # the100kPa reference dose needs a0.8 coefficient at80kPa when MAP/baro is used.
  t['maps']['ve']['cells']=[68]*256
 elif case.startswith('afr'):
  c.update(afr=case[4:],afr_delay_s=1);t['maps']['lambda']['cells']=[.9]*256
 elif case=='zero_fuel':t['maps']['ve']['cells']=[0]*256
 return options

def metrics(result):
 burns=[r for r in result['combustions'] if r['time_s']>=4 and r['lambda_value'] is not None]
 return dict(mean_cylinder_lambda_after4=statistics.mean(r['lambda_value'] for r in burns) if burns else None,
             mean_abs_lambda1_error_after4=statistics.mean(abs(r['lambda_value']-1) for r in burns) if burns else None,
             cylinder_observations_after4=len(burns),
             minimum_map=min(r['map_kpa'] for r in result['trace']),maximum_map=max(r['map_kpa'] for r in result['trace']))

def audit(result,case,ours):
 a=edge_audit(result,False,expect_running=case not in ('zero_fuel','alpha_uncalibrated'),expect_all_channels=case!='zero_fuel');errors=a['errors'];s=result['summary'];edges=result['edges']
 def require(ok,message):
  if not ok:errors.append(message)
 require(s['final_outputs_high']==0,'simulation termination left software outputs high')
 if ours:
  require(s['max_injector_high_us']<=15000 and s['max_dwell_high_us']<=3500,'project scheduled high-time limit')
  require(all(not r['ecu'].get('physical_outputs_enabled',False) for r in result['trace']),'physical outputs policy')
  if case!='alpha_uncalibrated':require(s['project_fault_mask_seen']==(4 if case=='alpha_guard' else 0),'missing or unexpected project fault')
  if case=='alpha_no_map':
   rows=[r for r in result['trace'] if 3.2<=r['time']<4.2]
   require(rows and all(r['sensor_map_kpa'] is None and not(r['ecu']['load_model']['flags']&256) and r['ecu']['faults']==0 for r in rows),'optional MAP was fabricated or faulted')
  if case=='alpha_guard':
   rows=[r for r in result['trace'] if 4<=r['time']<4.25]
   require(rows and all(r['ecu']['load_model']['reason']=='known_map_above_na_limit' for r in rows),'known overpressure did not fault the TPS model')
   require(not any(4000000<t<4250000 and high for t,_,high,_ in edges),'output start after the known guard observation')
  if case=='zero_fuel':
   require(s['ledger']['fuel_in_mg']==0 and not any(ch<4 and high for _,ch,high,_ in edges),'zero coefficient opened an injector')
   require(s['sparks']>0,'zero fuel failed to exercise cranking spark')
  if case=='afr_measured':require(any(r['ecu']['load_model']['afr_state']=='measured_ratio' for r in result['trace']),'measured AFR never became active')
  if case not in ('zero_fuel','alpha_guard','alpha_uncalibrated'):require(s['final_rpm']>500,'qualified benchmark case failed to remain running')
 a['passed']=not errors;return a

def validate(output,calibration_path):
 if output.exists():raise ValueError('Scenario output exists; preserve it and choose a new directory')
 output.mkdir(parents=True);cal=json.loads(calibration_path.read_text());rows=[];refinements=[];failures=[];started=time.monotonic()
 def execute(profile,case,step=250):
  who,target,bits,label=profile;name=label+'-'+case+'-'+str(step);print('Running',name,flush=True)
  r=benchmark.run(who,'throttle_step',6,step,target_dispatcher=target,reference_timer_bits=bits,load_options=configuration(case,cal))
  a=audit(r,case,who=='ours');m=metrics(r);r['summary'].update(case=case,label=label,audit=a,metrics=m)
  path=output/(name+'.json.gz');path.write_bytes(gzip.compress((json.dumps(r,separators=(',',':'),allow_nan=False)+'\n').encode(),mtime=0))
  record=dict(name=name,case=case,label=label,step_us=step,summary=r['summary'],metrics=m,audit=a,trace_file=path.name,trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
  if not a['passed']:failures.append(dict(name=name,errors=a['errors']))
  print('Result',name,round(r['summary']['final_rpm'],1),'RPM / lambda',m['mean_cylinder_lambda_after4'],a['errors'],flush=True);return record
 for profile in PROFILES:
  for case in CASES:rows.append(execute(profile,case))
 for profile in PROFILES:
  for case in ('alpha','ratio_mixed'):
   fine=execute(profile,case,125);coarse=next(r for r in rows if r['case']==case and r['label']==profile[3]);differences={}
   for key in ('mean_final_second_rpm',):differences[key]=abs(fine['summary'][key]-coarse['summary'][key])/max(1,abs(fine['summary'][key]))
   for key in ('fuel_in_mg','combustion_shaft_j'):differences[key]=abs(fine['summary']['ledger'][key]-coarse['summary']['ledger'][key])/max(1,abs(fine['summary']['ledger'][key]))
   record=dict(name=fine['name'],relative_differences=differences,tolerance=.03,passed=max(differences.values())<.03 and fine['audit']['passed']);refinements.append(record);rows.append(fine)
   if not record['passed']:failures.append(record)
 result=dict(passed=not failures,failures=failures,runs=rows,refinements=refinements,runtime_seconds=time.monotonic()-started,
             calibration_sha256=hashlib.sha256(calibration_path.read_bytes()).hexdigest(),calibration_statuses={k:sum(p['status']==k for p in cal['points']) for k in sorted({p['status'] for p in cal['points']})},
             scope='Source/pressure/AFR behavior on fixed independent empirical plant, not engine qualification or an ideal tune. Project transient mode is explicitly Off; reference empty AE curves remain neutral. Native reference CPU/IRQ cost is zero;16bit reference models timer width only. Half step also changes native main-loop polling cadence. EMAP is an exogenous sensor stimulus, not exhaust thermodynamics. Manual baro coefficient scaling is a declared fixture, not a production correction feature. Zero fuel and unchanged-coefficient Alpha-N are calibration-failure controls with outcomes reported per controller; edge/ledger checks still apply.')
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--calibration',type=Path,required=True);a=p.parse_args()
 if not validate(a.output,a.calibration)['passed']:raise SystemExit(1)
