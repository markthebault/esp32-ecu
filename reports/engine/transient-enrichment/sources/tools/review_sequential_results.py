#!/usr/bin/env python3
"""Reclassify saved event metadata without rerunning or changing engine traces.

Execution and analysis source hashes remain separate. Raw trace files are kept.
"""
import argparse,copy,hashlib,json
from pathlib import Path
from sequential_metrics import sequential_metrics
from run_sequential_scenarios import audit
from engine_runtime import R

def review(source,output):
 report=json.loads((source/'summary.json').read_text());report['execution_source_hashes']=report.pop('source_hashes');report['analysis_source_hashes']={p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in ['tools/sequential_metrics.py','tools/review_sequential_results.py','tools/run_sequential_scenarios.py','tools/compare_engine_controllers.py']}
 report['analysis_note']='Strict Partial-sync fallback counting applied from saved per-event mode metadata. Timelines, controller execution, actuator edges and plant states are unchanged; original execution source hashes retained.'
 output.mkdir(parents=True,exist_ok=True);failures=[];changes=[]
 for row in report['rows']:
  name=row['label']+'-'+row['scenario']+'-250.json';path=source/name;result=json.loads(path.read_text());metrics=sequential_metrics(result['spark_timing']);before={k:row.get(k) for k in metrics};row.update(metrics);result['summary'].update(metrics);row['audit']=audit(result,row['label']=='native_esp32_dispatcher');row['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();row['raw_trace_file']=name
  changed={k:dict(before=before[k],after=v) for k,v in metrics.items() if before[k]!=v}
  if changed:changes.append(dict(case=name,metrics=changed))
  if not row['audit']['passed']:failures.append(dict(case=name,errors=row['audit']['errors']))
 report['metadata_reclassification_changes']=changes;report['passed']=report['passed'] and not failures;report['failures']+=failures
 (output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();r=review(a.source,a.output);print('Saved-mode analysis:',r['controller_cases'],'cases; passed',r['passed'])
 if not r['passed']:raise SystemExit(1)
