#!/usr/bin/env python3
"""Closed-loop gasoline-plant flex control probes, not ethanol combustion proof."""
import argparse,copy,gzip,hashlib,json
from pathlib import Path
from engine_runtime import R
from engine_sil import Simulation
from engine_log import export_msl

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(out):
 if out.exists():raise ValueError('Choose a new output directory')
 out.mkdir(parents=True)
 sources=[R/'config/engine/defaults.json',R/'tools/engine_sil.py',R/'tools/engine_runtime.py',R/'tools/engine_bridge.cpp',R/'tools/target_runtime.py',R/'tools/target_timing_bridge.cpp',R/'tools/flex_stimulus.py',Path(__file__),*sorted((R/'firmware/include/ecu').glob('*.hpp'))]
 frozen={str(p.relative_to(R)):digest(p)for p in sources};base=json.loads((R/'config/engine/defaults.json').read_text());cases=[];failures=[]
 def check(ok,label):
  if not ok:failures.append(label)
 for strategy in ('batch_wasted','semi_sequential','sequential'):
  baseline=None
  for case in ('off','neutral','neutral50','neutral150','corrected','filtered','zero','missing','dropout'):
   tune=copy.deepcopy(base);tune['strategy']=strategy;f=tune['flex_fuel'];f['correction']['enabled']=case!='off'
   stimulus=dict(frequency_hz=50 if case=='neutral50' else 150 if case=='neutral150' else 100,low_pulse_us=3000)
   if case in ('corrected','filtered'):
    f['correction'].update(temperature_enabled=True,fuel_pct=[150]*6,temperature_pct=[80]*6,spark_deg=[5]*6)
   if case=='filtered':f['capture']['filter_ms']=125.5
   if case=='zero':f['correction']['fuel_pct']=[0]*6
   if case=='missing':stimulus=None
   if case=='dropout':stimulus['dropout_at_s']=2
   result=Simulation(tune,'warm_start',4,1,stimulus).run();summary=result['summary'];name=strategy+'-'+case
   record=dict(name=name,case=case,strategy=strategy,tune=tune,request=dict(scenario='warm_start',duration_s=4,seed=1,flex_stimulus=stimulus),summary=summary)
   body=json.dumps(result,separators=(',',':'),allow_nan=False).encode()
   with (out/(name+'.json.gz')).open('xb')as file:file.write(gzip.compress(body,mtime=0))
   (out/(name+'.msl')).write_text(export_msl(result['trace'],name,strategy))
   check(not summary['physical_outputs_enabled']and summary['final_outputs_high']==0,name+' inhibition/end cut')
   if case=='off':baseline=result
   elif case=='missing':check(summary['fuel_mg']==0 and all(row['fuel_cut']and row['spark_cut']for row in result['trace']),name+' required missing sensor cut')
   elif case=='zero':check(summary['fuel_mg']==0 and all(row['pulse_ms']==0 for row in result['trace']),name+' zero suppresses all delivered fuel')
   elif case=='dropout':
    tail=[row for row in result['trace']if row['time']>=2.3];check(bool(tail)and all(row['fuel_cut']and row['spark_cut']and row['pulse_ms']==0 and not row['flex_fuel']['control_ok']for row in tail),name+' stale waveform cut')
   else:
    check(summary['final_faults']==0 and summary['fuel_mg']>0 and result['final']['flex_fuel']['raw_capture_qualified'],name+' qualified operation')
    if case=='neutral':
     record['neutral_off_same_virtual_edges']=result['edges']==baseline['edges']
     record['neutral_off_final_rpm_delta']=summary['final_rpm']-baseline['summary']['final_rpm']
     record['neutral_off_fuel_mg_delta']=summary['fuel_mg']-baseline['summary']['fuel_mg']
     check(record['neutral_off_same_virtual_edges']and record['neutral_off_final_rpm_delta']==0 and record['neutral_off_fuel_mg_delta']==0,name+' neutral causal control')
   cases.append(record)
 check(frozen=={str(p.relative_to(R)):digest(p)for p in sources},'Source changed during matrix')
 report=dict(passed=not failures,failures=failures,cases=cases,source_sha256=frozen,scope='Native controller/scheduler with independent reduced-order fixed-gasoline plant and raw sensor stimulus. No production Speeduino execution in this matrix, no ethanol chemistry or target/HIL qualification. Separate pinned production raw-edge comparisons remain in reports/engine/flex-core.')
 (out/'index.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();r=run(a.output);print(json.dumps(dict(passed=r['passed'],cases=len(r['cases']),failures=r['failures'])));raise SystemExit(0 if r['passed']else 1)
