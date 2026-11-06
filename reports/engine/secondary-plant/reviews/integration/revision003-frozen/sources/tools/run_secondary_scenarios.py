#!/usr/bin/env python3
"""Enabled secondary-table coupled engine experiments, with policy differences.

Each controller drives its own uncalibrated MVEM-airpath/empirical free-shaft
plant through executed actuator edges. Passing declared invariants does not
establish an ideal tune, physical qualification or full Speeduino equivalence.
"""
import argparse,copy,gzip,hashlib,json,math,statistics,subprocess,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_target_scenarios import audit as edge_audit
from secondary_audit import arithmetic_audit,causal_audit
ROOT=Path(__file__).resolve().parents[1]
PROFILES={'portable':('ours',False,32),'target':('ours',True,32),'speeduino32':('speeduino',False,32),'speeduino16':('speeduino',False,16)}
CASES=('off','off_metadata','neutral_multiply','neutral_add','multiply','add','fuel_only','spark_only','conditional_tps','conditional_rpm','conditional_map','conditional_near_quantization','input','input_shared','input_inverted','input_bounce','input_semi','input_sequential','nack','timeout','underfill','mid_read_reset','producer_pause','control_busy','ratio_mixed','tps_mixed','zero_fuel','capacity','trim_multiply')
def bindings():
 paths=set()
 for directory,patterns in(('firmware/include/ecu',('*.hpp',)),('firmware/main',('*.hpp','*.cpp')),('tools',('*.py','*.cpp','*.hpp')),('simulation/modelica',('*.mo',))):
  for pattern in patterns:paths.update((ROOT/directory).glob(pattern))
 paths.update(ROOT/p for p in('config/engine/defaults.json','scripts/build_speeduino_sim.py','scripts/build_engine_airpath.py','firmware/platformio.ini'))
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(paths)}

def execution_bindings():
 # Warm the actual native bridges before hashing the executable artifacts.
 from engine_runtime import EngineRuntime
 from target_runtime import TargetRuntime
 from switch_acquisition_runtime import AcquisitionRuntime
 for cls in(EngineRuntime,TargetRuntime,AcquisitionRuntime):
  runtime=cls();runtime.close()
 paths=['.cache/engine/libengine.so','.cache/engine/target-native/libtarget_engine.so','.cache/engine/switch-acquisition-native/libswitch_acquisition.so','.cache/engine/modelica-mvem/airpath/EngineAirPath.fmu','.cache/engine/modelica-mvem/airpath/manifest.json']
 for folder in('speeduino-sim','speeduino-sim16'):
  manifest=ROOT/'.cache/engine'/folder/'build-manifest.json';m=json.loads(manifest.read_text());binary=manifest.parent/'speeduino-sim'
  if m['unit_test']or m['speeduino_sha']!='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'or hashlib.sha256(binary.read_bytes()).hexdigest()!=m['binary_sha256']:raise ValueError('Reference executable attestation failed')
  for name in('tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp'):
   if m['source_hashes'].get(name)!=hashlib.sha256((ROOT/name).read_bytes()).hexdigest():raise ValueError('Reference executable adapter source changed: '+name)
  paths.extend(str(p.relative_to(ROOT))for p in(manifest,binary))
 return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in paths}
def configuration(case):
 if case not in CASES:raise ValueError('Unknown secondary experiment')
 t=benchmark.benchmark_tune();t['transient_enrichment']['mode']='off';mode='input'if case.startswith('input')or case in('fuel_only','spark_only','nack','timeout','underfill','mid_read_reset','producer_pause','control_busy','zero_fuel')else'conditional'if case.startswith('conditional')or case=='capacity'else'multiply'if case in('ratio_mixed','tps_mixed','trim_multiply','neutral_multiply')else'add'if case=='neutral_add'else'off'if case=='off_metadata'else case
 spec={'initial':[False,False],'edges':[],'faults':[]}
 for kind in('fuel','spark'):
  r=t['secondary_tables'][kind];r.update(mode=mode,cells='multiplier'if mode=='multiply'else'adder'if mode=='add'else'absolute',condition='tps_pct',threshold=5,debounce_ms=20)
  r['map']['load']=[10+6*i for i in range(16)]
  r['map']['cells']=[110 if mode=='multiply'and kind=='fuel'else 120 if mode=='multiply'else 5 if mode=='add'and kind=='fuel'else-3 if mode=='add'else 90 if kind=='fuel'else 14]*256
 if mode=='input':
  spec['edges']=[dict(at_us=3000000,channel=0,level=True),dict(at_us=3050000,channel=1,level=True),dict(at_us=4000000,channel=0,level=False),dict(at_us=4050000,channel=1,level=False)]
 if case=='off_metadata':
  for kind in('fuel','spark'):
   r=t['secondary_tables'][kind];r.update(source='tps',axis='tps_pct',condition='ethanol_pct',threshold=99,debounce_ms=497,active_high=False,input_channel=1);r['map']['load']=[i*6 for i in range(16)];r['map']['cells']=[0 if kind=='fuel'else-4]*256
 if case in('neutral_multiply','neutral_add'):
  for r in t['secondary_tables'].values():r['map']['cells']=[100 if mode=='multiply'else 0]*256
 if case in('fuel_only','spark_only'):t['secondary_tables']['spark'if case=='fuel_only'else'fuel']['mode']='off'
 if case=='input_semi':t['strategy']='semi_sequential_4cyl'
 if case=='input_sequential':t['strategy']='sequential_4cyl'
 if case.startswith('conditional'):
  condition='rpm'if case=='conditional_rpm'else'map_kpa'if case=='conditional_map'else'tps_pct';threshold=500 if condition=='rpm'else 60 if condition=='map_kpa'else 11.75 if case=='conditional_near_quantization'else 5
  for r in t['secondary_tables'].values():r.update(condition=condition,threshold=threshold)
 if case=='input_shared':t['secondary_tables']['spark']['input_channel']=0
 if case=='input_inverted':
  for r in t['secondary_tables'].values():r['active_high']=False
 if case=='input_bounce':
  spec['edges']=[dict(at_us=3000000+i*200,channel=0,level=not bool(i%2))for i in range(31)]+[dict(at_us=3030000,channel=1,level=True),dict(at_us=4000000,channel=0,level=False),dict(at_us=4050000,channel=1,level=False)]
 if case in('nack','timeout','underfill','mid_read_reset','producer_pause','control_busy'):
  spec['initial']=[True,True];spec['edges']=[]
  kind='reset_before_guard'if case=='mid_read_reset'else'nack'if case=='control_busy'else case
  spec['faults']=[dict(begin_us=3000000,end_us=3080000,kind=kind)]
  if case=='control_busy':spec['faults'].append(dict(begin_us=2980000,end_us=3300000,kind='control_busy'))
 if case in('ratio_mixed','tps_mixed'):
  for kind,source in(('fuel','imap_emap'if case=='ratio_mixed'else'tps'),('spark','tps'if case=='ratio_mixed'else'imap_emap')):
   r=t['secondary_tables'][kind];r.update(source=source,axis='imap_emap_pct'if source=='imap_emap'else'tps_pct');r['map']['load']=[20*i for i in range(16)]if source=='imap_emap'else[0,2,4,6,8,10,12,16,20,24,30,40,50,65,80,100]
   r['map']['cells']=[100+row//3+column%3 for row in range(16)for column in range(16)]
  t['load_model']['aux_role']='emap'
 if case=='zero_fuel':
  t['secondary_tables']['fuel']['map']['cells']=[0]*256;spec.update(initial=[True,True],edges=[])
 if case=='capacity':
  t['strategy']='sequential_4cyl'
  t['secondary_tables']['fuel']['map']['cells']=[255]*256;t['secondary_tables']['spark']['mode']='off'
 if case=='trim_multiply':
  t['strategy']='sequential_4cyl';t['secondary_tables']['spark']['map']['cells']=[150]*256;t['cylinder_trims']['enabled']=True;t['cylinder_trims']['spark_deg']=[2,-2,0,0]
  for m,pct in zip(t['cylinder_trims']['fuel_maps'],(110,90,100,100)):m['cells']=[pct]*36
 return dict(tune=t,stimulus=spec)

def metrics(result):
 rows=[r for r in result.get('combustions',[])if r['time_s']>=4];valid=[r for r in rows if r['lambda_value']is not None]
 per_cylinder=[]
 for cylinder in range(1,5):
  selected=[r for r in valid if r['cylinder']==cylinder]
  per_cylinder.append(dict(cylinder=cylinder,count=len(selected),mean_lambda=statistics.mean(r['lambda_value']for r in selected)if selected else None,mean_actual_advance_deg=statistics.mean(r['advance_deg']for r in selected)if selected else None))
 return dict(mean_lambda_after4=statistics.mean(r['lambda_value']for r in valid)if valid else None,cylinder_observations_after4=len(rows),cylinders=per_cylinder)

def audit(result,case,ours):
 negative=case in('zero_fuel','capacity','control_busy');a=edge_audit(result,False,expect_running=False,expect_all_channels=not(case=='capacity'and ours or case=='zero_fuel'and ours));errors=a['errors'];s=result['summary']
 def require(ok,message):
  if not ok:errors.append(message)
 require(len(result['trace'])>=s['duration_s']*45,'delayed-control trace cadence lost observations')
 if not negative:require(s['mean_final_second_rpm']>500 and s['sparks']>20 and s['ledger']['combustion_shaft_j']>0,'declared mild secondary case did not sustain combustion')
 if ours:
  require(s['max_injector_high_us']<=15000 and s['max_dwell_high_us']<=3500,'project high-time bounds')
  history=result['secondary_monitor'];require(history and all(h['control_attempt_us']>=h['monitor_begin_us']for h in history),'monitor completion chronology')
  allowed=(64|128)if case=='capacity'else(4|8|128)if case=='control_busy'else 4 if any(r['mode']=='input'for r in configuration(case)['tune']['secondary_tables'].values())else 0
  if s['strategy']=='sequential_4cyl':allowed|=256
  require(not(s['project_fault_mask_seen']&~allowed),'unexpected project fault bit')
  late=[h['control']for h in history if h['control']and h['control_attempt_us']>=500000]
  if case not in('nack','timeout','underfill','mid_read_reset','producer_pause','control_busy','capacity'):
   first_sync_us=round(s['first_sync_s']*1e6)if s['first_sync_s']is not None else 2**64-1
   require(all(not c['faults']or s['strategy']=='sequential_4cyl'and c['faults']==256 and c['time_us']<first_sync_us for c in late),'unexpected late control fault')
  completed=[h for h in history if h['control']]
  for index,h in enumerate(completed):
   control=h['control'];end=completed[index+1]['edge_cursor']if index+1<len(completed)else len(result['edges'])
   if control['faults']:require(not any(e[2]for e in result['edges'][h['edge_cursor']:end]),'output start after completed fault observation')
   for d in control['secondary_tables'].values():
    observed=d.get('input_observed_us')
    if observed is not None:require(int(observed)<=control['time_us'],'future source time published')
    if d.get('input_qualified'):require(d['input_valid']and d['input_source']=='synthetic_input'and 0<=d['input_age_ms']<=20,'qualified input provenance/freshness')
  if case in('nack','timeout','underfill','mid_read_reset','control_busy'):
   kind='reset_before_guard'if case=='mid_read_reset'else'nack'if case=='control_busy'else case
   require(any(r['kind']==kind for r in s['secondary_applied_faults']),'fault window did not hit an acquisition operation')
   require(any(h['acquisition']['fault_pending']for h in history),'injected fault never latched')
  if case=='producer_pause':
   require(any(h['acquisition']['fault']=='producer_gap'for h in history),'resumed producer hid its gap')
   require(any(c['secondary_tables']['fuel']['reason']=='input_stale'and c['secondary_tables']['fuel']['input_age_ms']>20 for c in late),'paused producer never exposed stale acquisition time')
  for h in history:
   if h['fault_acknowledged']:require(h['control_completed']and h['control']is not None and h['control']['faults']&4 and h['acquisition']['fault_pending']and not h['acquisition']['ready'],'fault acknowledged without completed inhibited observation')
  if case in('nack','timeout','underfill','mid_read_reset','producer_pause'):
   require(any(h['control']and h['control']['faults']&4 for h in history if 3000000<=h['control_attempt_us']<3400000),'input failure did not reach core')
   require(late and not late[-1]['faults'],'recoverable input fault did not recover by horizon')
  if all(r['mode']!='input'for r in configuration(case)['tune']['secondary_tables'].values()):require(s['secondary_monitor_operations']==0,'non-Input mode accessed device')
  if case=='zero_fuel':require(s['ledger']['fuel_in_mg']==0 and not any(ch<4 and high for _,ch,high,_ in result['edges']),'zero ordinary fuel opened injector')
  if case=='capacity':
   capacity=[h['control_attempt_us']for h in history if h['control']and h['control']['faults']&64]
   require(capacity and min(capacity)>3000000,'capacity limit not exercised after established running')
   if capacity:
    require(all(not(h['control']['faults']&~256)for h in history if h['control']and h['control_attempt_us']<min(capacity)),'capacity fixture faulted before overload')
    require(all(p['time_us']>min(capacity)and p['reason']in('cam_phase_lost','tooth_timeout')for p in s['protection_stops']),'unexpected capacity coast-down protection stop')
 else:
  snapshots=[r['ecu']['secondary_reference']for r in result['trace']]
  require(all(d['last_loop_us']<=d['time_us']for d in snapshots),'reference future loop timestamp')
  if case=='zero_fuel':require(any(ch<4 and high for _,ch,high,_ in result['edges']),'reference zero-fuel deadtime policy was not exercised')
  if case=='capacity':require(s['max_injector_high_us']>15000,'reference did not exercise its different pulse-capacity policy')
 if s['strategy']=='sequential_4cyl':
  if ours or case!='capacity':require(not s['wrong_stroke_sparks'],'sequential wrong-stroke discharge')
  if ours or case!='capacity':require(not s['unsynced_720_discharges'],'sequential unsynced discharge')
 arithmetic=arithmetic_audit(result,case,ours);errors.extend(arithmetic['errors'])
 a.update(passed=not errors,arithmetic=arithmetic,reference_unsynced_720_discharges=s.get('unsynced_720_discharges',0)if not ours else None,reference_wrong_stroke_sparks=s.get('wrong_stroke_sparks',0)if not ours else None);return a

def run(output,profiles,cases,step=250):
 if output.exists():raise ValueError('Output exists; preserve earlier runs')
 output.mkdir(parents=True);started=time.monotonic();rows=[];failures=[];sources=bindings();executables=execution_bindings()
 (output/'source-bindings.json').write_text(json.dumps(dict(sources=sources,executables=executables),indent=2)+'\n')
 for label in profiles:
  who,target,bits=PROFILES[label]
  for case in cases:
   name=f'{label}-{case}-{step}';print('Running',name,flush=True);options=configuration(case)
   result=benchmark.run(who,'secondary_cycle'if case.startswith('conditional_tps')or case=='conditional_near_quantization'else'throttle_step',6,step,control_period_us=5000,target_dispatcher=target,reference_timer_bits=bits,secondary_options=options,load_options=dict(tune=options['tune'],emap_kpa=125))
   checks=audit(result,case,who=='ours');m=metrics(result);result['summary'].update(case=case,label=label,audit=checks,metrics=m)
   path=output/(name+'.json.gz');path.write_bytes(gzip.compress((json.dumps(result,separators=(',',':'),allow_nan=False)+'\n').encode(),mtime=0))
   row=dict(name=name,case=case,label=label,step_us=step,summary=result['summary'],metrics=m,audit=checks,trace_file=path.name,trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest());rows.append(row)
   if not checks['passed']:failures.append(dict(name=name,errors=checks['errors']))
   print('Result',name,round(result['summary']['mean_final_second_rpm'],1),'RPM',checks['errors'],flush=True)
   (output/'progress.json').write_text(json.dumps(dict(runs=rows,failures=failures),indent=2)+'\n')
 grouped={label:{}for label in profiles}
 for row in rows:
  if row['case']in('off','off_metadata','neutral_multiply','neutral_add','multiply','add','fuel_only','spark_only'):grouped[row['label']][row['case']]=json.loads(gzip.decompress((output/row['trace_file']).read_bytes()))
 causal=causal_audit(grouped)
 if not causal['passed']:failures.extend(dict(name=r['label']+'-'+r['case'],errors=['neutral replay or actuator-to-shaft causality failed'])for r in causal['checks']if not r['passed'])
 stable=sources==bindings()and executables==execution_bindings()
 if not stable:failures.append(dict(name='source-binding',errors=['sources or executables changed during matrix']))
 report=dict(passed=not failures,runs=rows,failures=failures,causal=causal,source_bindings_stable=stable,runtime_seconds=time.monotonic()-started,physical_qualification=False,scope=__doc__)
 (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--profiles',nargs='+',choices=tuple(PROFILES),default=tuple(PROFILES));p.add_argument('--cases',nargs='+',choices=CASES,default=CASES);p.add_argument('--step-us',type=int,choices=(125,250),default=250);a=p.parse_args()
 if not run(a.output,a.profiles,a.cases,a.step_us)['passed']:raise SystemExit(1)
