#!/usr/bin/env python3
"""Sequential target core and production Speeduino on an independent research plant.

The16bit reference is a Mega-like timer model, not AVR CPU/IRQ emulation.
The32bit profile retains upstream-native timer range for a sensitivity check.
"""
import argparse,hashlib,json,math,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_target_scenarios import TargetController
from engine_runtime import R


def audit(result,ours):
 s=result['summary'];errors=[];high={};width=[0]*8;previous=0;channels=set()
 def require(ok,message):
  if not ok:errors.append(message)
 for us,ch,value,cause in result['edges']:
  require(previous<=us<=round(s['duration_s']*1e6),'edge time/order');previous=us;channels.add(ch)
  if ch not in range(8):errors.append('edge channel');continue
  if value:require(ch not in high,'duplicate rise');high[ch]=us
  else:
   require(ch in high,'fall without rise')
   if ch in high:width[ch]=max(width[ch],us-high.pop(ch))
 require(not high and not s['final_outputs_high'],'termination high output')
 require(width[:4] and max(width[:4])==s['max_injector_high_us'] and max(width[4:])==s['max_dwell_high_us'],'pulse summary differs')
 for key,tol in [('fuel_residual_mg',1e-6),('chemical_residual_j',1e-4),('shaft_residual_j',1e-4),('air_residual_kg',1e-7),('air_energy_residual_j',.05)]:require(math.isfinite(s['ledger'][key]) and abs(s['ledger'][key])<tol,key+' balance')
 require(s['max_trigger_quantization_deg']<.05,'trigger quantization')
 scenario=s['scenario']
 if scenario in ('warm_start','stall_restart'):require(650<s['mean_final_second_rpm']<1500,'sustained/recovered idle absent')
 if scenario=='throttle_step':require(s['mean_final_second_rpm']>1500,'throttle response absent')
 if ours:
  require(max(width[:4])<=15000 and max(width[4:])<=3500,'target high-time bounds')
  if scenario=='cam_wrong_phase':
   require(s['wrong_stroke_sparks']>0 and s['max_spark_720_error_deg']>350,'wrong360 reference negative control hidden')
   require(s['final_rpm']<40,'wrong360 calibration sustained combustion')
  else:require(s['wrong_stroke_sparks']==0 and s['max_spark_720_error_deg']<.2,'sequential spark phase error')
  if scenario=='cam_missing_start':require(not result['edges'] and s['first_sync_s'] is None,'missing startup cam allowed output')
  if scenario in ('cam_dropout','cam_extra'):
   require(result['final_ecu']['phase_losses']==1 and result['final_ecu']['timing_stop_reason']=='cam_phase_lost','cam loss did not latch')
   require(result['final_ecu']['timing_recoveries']==1 and s['final_rpm']<40,'cam loss did not coast/recover at stop')
  if scenario not in ('cam_missing_start',):require(channels==set(range(8)),'not all eight virtual channels exercised')
 else:
  require(all('effective_sequential' in e and e['sync_status'] in (0,1,2) and e['ignition_cycle_deg'] in (360,720) for e in result['spark_timing']),'missing event mode evidence')
  if scenario=='cam_missing_start':require(s['first_sync_s'] is None and s['wasted_fallback_discharges']>0 and s['wrong_stroke_sparks']==0,'Partial-sync fallback misclassified')
  if scenario=='cam_dropout':require(s['final_rpm']>650,'declared upstream retained-phase policy changed')
 return dict(passed=not errors,errors=errors,replayed_edges=len(result['edges']),replayed_max_high_us=width)


def validate(output):
 output.mkdir(parents=True,exist_ok=True);original=benchmark.OurController;benchmark.OurController=TargetController;rows=[];checks=[];failures=[];started=time.monotonic()
 try:
  for who,bits,label in [('ours',32,'native_esp32_dispatcher'),('speeduino',32,'speeduino_native32'),('speeduino',16,'speeduino_megalike16')]:
   for scenario in benchmark.SCENARIOS+benchmark.CAM_SCENARIOS:
    print('Running',label,scenario,flush=True)
    result=benchmark.run(who,scenario,12 if scenario=='stall_restart' else 10,250,control_period_us=5000,sequential=True,reference_timer_bits=bits)
    summary=result['summary'];summary['label']=label;summary['audit']=audit(result,who=='ours');path=output/(label+'-'+scenario+'-250.json');path.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n');summary['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();rows.append(summary)
    if not summary['audit']['passed']:failures.append(dict(label=label,scenario=scenario,errors=summary['audit']['errors']))
    print('Result',label,scenario,round(summary['final_rpm'],1),'RPM',summary['audit'],flush=True)
   for scenario in ('warm_start','throttle_step'):
    print('Convergence',label,scenario,flush=True)
    result=benchmark.run(who,scenario,10,125,control_period_us=5000,sequential=True,reference_timer_bits=bits);fine=result['summary'];coarse=next(row for row in rows if row['label']==label and row['scenario']==scenario)
    differences={key:abs(coarse[key]-fine[key])/max(1,abs(fine[key])) for key in ('mean_final_second_rpm',)}
    for key in ('fuel_in_mg','combustion_shaft_j'):differences[key]=abs(coarse['ledger'][key]-fine['ledger'][key])/max(1,abs(fine['ledger'][key]))
    passed=max(differences.values())<.03 and audit(result,who=='ours')['passed'];checks.append(dict(label=label,scenario=scenario,relative_differences=differences,tolerance=.03,passed=passed));(output/(label+'-'+scenario+'-125.json')).write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    if not passed:failures.append(dict(label=label,scenario=scenario,errors=['step convergence or fine audit']))
  paths=['tools/run_sequential_scenarios.py','tools/compare_engine_controllers.py','tools/run_target_scenarios.py','tools/engine_research_plant.py','tools/target_runtime.py','tools/target_timing_bridge.cpp','tools/speeduino_runtime.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','scripts/build_speeduino_sim.py','config/engine/defaults.json']
  paths+=sorted(str(p.relative_to(R)) for p in (R/'firmware/include/ecu').glob('*.hpp'))
  report=dict(scope='Four-cylinder sequential software/source comparison, uncalibrated independent MVEM air path + local empirical fuel/combustion/free shaft',physical_outputs_enabled=False,control_period_us=5000,producer_period_us=1000,cam='fixed450deg ATDC C1 compression; wrong-phase negative control90deg',cpu_model='zero execution/IRQ cost; no physical measurements',reference_scope='Unchanged pinned Speeduino production algorithms; native32 and Mega-like16bit/4us/equality timer HALs. Neither is AVR emulation.',event_classification='720deg error uses actual event syncFull/span720. Partial360 wasted fallback and unsynced720 pending discharges are separate. No elapsed-time heuristic.',controller_cases=len(rows),convergence_cases=len(checks),passed=not failures,failures=failures,runtime_seconds=time.monotonic()-started,source_hashes={p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in paths},rows=rows,convergence=checks)
  (output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report
 finally:benchmark.OurController=original

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=R/'.cache/engine/sequential-final');args=parser.parse_args();report=validate(args.output_dir);print('Sequential comparison:',report['controller_cases'],'cases;',report['convergence_cases'],'convergence checks; passed',report['passed'],flush=True)
 if not report['passed']:raise SystemExit(1)
