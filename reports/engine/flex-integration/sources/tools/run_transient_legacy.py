#!/usr/bin/env python3
"""Replay old full-engine profiles against immutable pre-transient evidence."""
import argparse,gzip,hashlib,json
from pathlib import Path
import compare_engine_controllers as benchmark
ROOT=Path(__file__).resolve().parents[1]

def validate(output):
 output.mkdir(parents=True,exist_ok=True);cases=[]
 for mode in ('batch','sequential'):
  for label,controller,target,bits in (('portable','ours',False,32),('target','ours',True,32),('reference32','speeduino',False,32),('reference16','speeduino',False,16)):
   name='legacy-'+mode+'-'+label;path=ROOT/'reports/engine/semi-sequential/legacy'/(name+'.json.gz');old=json.loads(gzip.decompress(path.read_bytes()));s=old['summary']
   print('Running',name,flush=True)
   new=benchmark.run(controller,'warm_start',s['duration_s'],s['step_us'],control_period_us=s['control_period_us'],sequential=mode=='sequential',target_dispatcher=target,reference_timer_bits=bits)
   checks={k:new[k]==old[k] for k in ('edges','triggers','cams','dwell','spark_timing','injection_timing')}
   checks.update(ledger=new['summary']['ledger']==s['ledger'],final_rpm=new['summary']['final_rpm']==s['final_rpm'])
   record=dict(name=name,passed=all(checks.values()),checks=checks,baseline_path=str(path.relative_to(ROOT)),baseline_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),executed_edges=len(new['edges']))
   (output/(name+'.json')).write_text(json.dumps(new,separators=(',',':'),allow_nan=False)+'\n');cases.append(record);print(record,flush=True)
 result=dict(passed=all(c['passed'] for c in cases),cases=cases,scope='Exact actuator/trigger/cam/combustion ledger regression, new diagnostic fields are additive',baseline_commit='64c21ed29d5bf5b5a44c471bcc321b88c8ac5d38')
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=ROOT/'.cache/engine/transient/legacy');a=p.parse_args()
 if not validate(a.output_dir)['passed']:raise SystemExit(1)
