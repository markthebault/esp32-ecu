#!/usr/bin/env python3
"""Reproducible regression evidence. The plant is explicitly unvalidated."""
import argparse
import json
from pathlib import Path
from engine_runtime import R
from engine_sil import SCENARIOS,Simulation
from engine_log import export_msl

def run(seeds):
 tune=json.loads((R/'config/engine/defaults.json').read_text());rows=[]
 cache=R/'.cache/engine/scenarios';cache.mkdir(parents=True,exist_ok=True)
 for seed in seeds:
  for name in SCENARIOS:
   result=Simulation(tune,name,12,seed).run();summary=result['summary'];mask=0
   for us,ch,high,cause in result['edges']:
    if bool(mask&(1<<ch))==high:raise AssertionError('Duplicate edge in saved evidence')
    mask=mask|(1<<ch) if high else mask&~(1<<ch)
   if mask or summary['final_outputs_high'] or summary['max_injector_high_us']>15000 or summary['max_dwell_high_us']>3500:raise AssertionError(summary)
   summary['saved_edges']=len(result['edges']);summary['trace_reconstructed_final_mask']=mask
   summary['regression_bounds_passed']=True;summary['timing_stops']=result['timing_stops'];summary['unexpected_scheduler_failure']=any(not (name in ('load_step','load_stall_restart') and p['reason']=='dwell_limit' and p['plant_rpm']<tune['settings']['cranking_rpm']+100) for p in result['timing_stops']);summary['regression_passed']=not summary['unexpected_scheduler_failure'];rows.append(summary)
   (cache/f'{name}-seed{seed}.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
   (cache/f'{name}-seed{seed}.msl').write_text(export_msl(result['trace'],name))
   print(f'{name:18s} seed={seed:3d} final={summary["final_rpm"]:7.1f} rpm, timing={summary["max_spark_error_to_latest_demand_deg"]:.4f} deg to latest demand, edges={len(result["edges"])}',flush=True)
 report=dict(passed=all(row['regression_passed'] for row in rows),allowed_protection='Dwell-limit stops only in explicit load-stall cases below the crank/run threshold. Other scheduler failures fail the sweep.',scope='Shared native ECU core and per-tooth virtual scheduler on an independent unvalidated reduced-order plant; no GPIO, target ISR, calibrated engine, or full Speeduino execution',default_tune_revision=tune['revision'],seeds=seeds,cases=len(rows),regression_bounds='No duplicate/lost closing edges; final reconstructed mask zero; injector <=15ms, coil <=3.5ms; timing protection stops retained with reasons and recovery counts',limitations=['A stalled load-step is recorded, not hidden: default idle control is disabled.','Seeded hard load can trigger bounded dwell protection while stalling. This is reported, not suppressed.',
' Soft rev retard can prevent the default overrev scenario reaching the hard limit. The hard-cut regression explicitly configures 3000rpm.','Latest-demand error and latched-event error are different metrics.','These constraints do not establish successful real-engine operation.'],rows=rows)
 path=R/'reports/engine/sil-scenarios.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')
 return report
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seeds',type=int,nargs='+',default=[1,3,17]);args=parser.parse_args();report=run(args.seeds)
 if not report['passed']:raise SystemExit('Unexpected scheduler failure; inspect reports/engine/sil-scenarios.json')
