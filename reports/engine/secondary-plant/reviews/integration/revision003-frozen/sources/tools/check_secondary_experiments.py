#!/usr/bin/env python3
"""Saved-result mutation sensitivity, disabled-path replay and step refinement."""
import argparse,copy,gzip,hashlib,json,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_secondary_scenarios import PROFILES,audit,bindings,execution_bindings,configuration
from secondary_audit import causal_audit

def read(path):return json.loads(gzip.decompress(path.read_bytes()))
def save(path,result):
 path.write_bytes(gzip.compress((json.dumps(result,separators=(',',':'),allow_nan=False)+'\n').encode(),mtime=0))
 return dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def mutations(matrix):
 rows=[]
 for label in PROFILES:
  ours=label in('portable','target');source=matrix/(label+'-multiply-250.json.gz')
  if not source.exists():continue
  for mutation in('inactive_selection','uncombined_value'):
   d=read(source)
   if ours:
    observations=[h['control']['secondary_tables']['fuel']for h in d['secondary_monitor']if h['control']]
    observations.extend(f['ecu']['secondary_tables']['fuel']for f in d['trace'])
    for o in observations:
     if mutation=='inactive_selection':o['active']=False
     elif o['evaluated']:o['combined']=o['primary_corrected']
   else:
    for f in d['trace']:
     o=f['ecu']['secondary_reference']
     if mutation=='inactive_selection':o['fuel_active']=0
     else:o['combined_ve']=o['primary_ve']
   a=audit(d,'multiply',ours);rows.append(dict(label=label,mutation=mutation,rejected=not a['passed'],errors=a['errors']))
  d=read(matrix/(label+'-off-250.json.gz'))
  a=causal_audit({label:dict(off=d,multiply=copy.deepcopy(d))});rows.append(dict(label=label,mutation='inert_actuators_and_plant',rejected=not a['passed']))
  if ours:
   d=read(matrix/(label+'-nack-250.json.gz'));d['summary']['secondary_applied_faults']=[]
   a=audit(d,'nack',True);rows.append(dict(label=label,mutation='unexercised_fault',rejected=not a['passed'],errors=a['errors']))
   d=read(matrix/(label+'-ratio_mixed-250.json.gz'))
   for h in d['secondary_monitor']:
    if h['control']:
     o=h['control']['secondary_tables']['fuel']
     if o['evaluated']and o['active']:o['coordinate']+=100
   a=audit(d,'ratio_mixed',True);rows.append(dict(label=label,mutation='wrong_load_coordinate',rejected=not a['passed'],errors=a['errors']))
 return dict(passed=all(r['rejected']for r in rows)and bool(rows),checks=rows)

def run(matrix,fine,output,legacy=True):
 if output.exists():raise ValueError('Output exists; preserve earlier evidence')
 output.mkdir(parents=True);started=time.monotonic();sources=bindings();executables=execution_bindings();rows=[]
 (output/'source-bindings.json').write_text(json.dumps(dict(sources=sources,executables=executables),indent=2)+'\n')
 mutation=mutations(matrix)
 for label,(who,target,bits)in PROFILES.items():
  basefile=matrix/(label+'-off-250.json.gz')
  if not basefile.exists():continue
  if legacy:
   print('Disabled legacy replay',label,flush=True);options=configuration('off');t=options['tune']
   d=benchmark.run(who,'throttle_step',6,250,tune=t if who=='ours'else None,control_period_us=5000,target_dispatcher=target,reference_timer_bits=bits,transient_options=dict(config=t['transient_enrichment']),load_options=dict(tune=t,emap_kpa=125))
   base=read(basefile);passed=all(d[k]==base[k]for k in('edges','combustions'))and d['summary']['ledger']==base['summary']['ledger']
   artifact=save(output/(label+'-legacy-off.json.gz'),d);rows.append(dict(label=label,kind='no-secondary-adapter Off replay',passed=passed,**artifact))
  if fine is not None:
   for case in('multiply','input_bounce','ratio_mixed','trim_multiply','producer_pause'):
    coarsefile=matrix/(label+'-'+case+'-250.json.gz');finefile=fine/(label+'-'+case+'-125.json.gz')
    if not coarsefile.exists()or not finefile.exists():continue
    coarse=read(coarsefile);small=read(finefile);cs=coarse['summary'];fs=small['summary']
    deltas={'mean_final_second_rpm':abs(cs['mean_final_second_rpm']-fs['mean_final_second_rpm'])/max(1,abs(fs['mean_final_second_rpm']))}
    for key in('fuel_in_mg','combustion_shaft_j'):deltas[key]=abs(cs['ledger'][key]-fs['ledger'][key])/max(1,abs(fs['ledger'][key]))
    a=audit(small,case,who=='ours');rows.append(dict(label=label,case=case,kind='250us to125us refinement',relative_differences=deltas,tolerance=.03,passed=max(deltas.values())<.03 and a['passed'],fine_trace_sha256=hashlib.sha256(finefile.read_bytes()).hexdigest()))
 stable=sources==bindings()and executables==execution_bindings()
 report=dict(passed=stable and mutation['passed']and all(r['passed']for r in rows),source_bindings_stable=stable,mutations=mutation,checks=rows,runtime_seconds=time.monotonic()-started,physical_qualification=False,limits='Same-platform virtual loops with zero CPU/IRQ cost. Halving plant steps also changes native Speeduino loop opportunities. Not physical ECU equivalence or calibrated tuning.')
 (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('matrix',type=Path);p.add_argument('output',type=Path);p.add_argument('--fine',type=Path);p.add_argument('--no-legacy',action='store_true');a=p.parse_args()
 if not run(a.matrix,a.fine,a.output,not a.no_legacy)['passed']:raise SystemExit(1)
