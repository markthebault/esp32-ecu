#!/usr/bin/env python3
"""Independently re-read raw ngspice vectors and arithmetic summaries.

This validates a declared assumed model run, never a real circuit or engine.
"""
import argparse,gzip,hashlib,json,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('report',type=Path);p.add_argument('--frozen-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
folder=a.report.resolve();report=json.loads((folder/'results.json').read_text());checks=0;raw_rows=0
def check(ok,why):
 global checks
 checks+=1
 if not ok:raise AssertionError(why)
check(report['cases']==95 and len(report['results'])==95,'declared case count')
check(report['physical_qualification'] is False and report['manufacturer_models'] is False,'honest model scope')
for name,sha in report['sources'].items():check(hashlib.sha256((a.frozen_root/name).read_bytes()).hexdigest()==sha,'model/source binding '+name)
names=set();transient=[];dc_checks=0
for result in report['results']:
 case=result['case'];name=case['name'];check(name not in names,'unique case');names.add(name)
 raw=folder/name/'values.txt'
 lines=(raw.read_text()if raw.exists()else gzip.decompress(raw.with_suffix('.txt.gz').read_bytes()).decode()).splitlines();headers=lines[0].split();check(len(headers)==15,'one scale plus14observations')
 rows=[list(map(float,line.split()))for line in lines[1:]if line.strip()];raw_rows+=len(rows)
 check(len(rows)==result['rows'] and all(len(r)==15 and all(math.isfinite(v)for v in r)for r in rows),'finite complete raw vectors')
 r=rows[-1];close=lambda x,y:math.isclose(x,y,rel_tol=1e-8,abs_tol=1e-10)
 check(close(r[1],result['rail_v']) and all(close(r[8+i],result['gp_v'][i])for i in(0,1)),'rail and GP summaries from raw data')
 check(close(-r[13]*1000,result['carrier_3v3_feed_current_ma']) and close(-r[14]*1000,result['bus_feed_current_ma']),'independent feed-current signs/units')
 for i in(0,1):check(close((r[10+i]-r[2+i])**2/2200,result['bias_resistor_w'][i]),'independent bias power')
 if case['power_connected']and case['fault0']is None and case['fault1']is None:
  for i,contact in enumerate((case['contact0'],case['contact1'])):
   if case['transition']and i==0:continue
   check(r[8+i]<=.2*r[1] if contact>1e6 else r[8+i]>=.8*r[1],'declared static logic margin');dc_checks+=1
 if case['transition']:
  for lo,hi,high in ((.001,.0019,False),(.0022,.0059,True),(.0063,.0099,False)):
   window=[r for r in rows if lo<=r[0]<=hi];check(len(window)>10,'settled interval has samples')
   check(all(r[8]>=.8*r[1]if high else r[8]<=.2*r[1]for r in window),'settled transition levels')
  crossing=next(r for r in rows if r[0]>=.002 and r[8]>=.8*r[1]);rise=(crossing[0]-.002)*1e6
  check(close(rise,result['conditional_rise_to_0_8vdd_us']),'rise time from raw samples');transient.append((case['max_step_us'],rise))
for case_name in ('poweroff-1','poweroff-bus3.63'):
 result=next(x for x in report['results']if x['case']['name']==case_name)
 check(result['rail_v']>.5 and result['bus_feed_current_ma']>.5 and abs(result['carrier_3v3_feed_current_ma'])<1e-6,'model retains bus-fed floating rail rather than zero-backfeed fiction')
transient.sort();delta=abs(transient[0][1]-transient[1][1]);check(delta<2,'declared half-step crossing consistency only')
check(all(not x['case']['power_connected']or max(x['bias_resistor_w'])<=.215 for x in report['results']),'conditional fault power below separate resistor-only bound')
summary=dict(passed_raw_model_checks=True,checks=checks,cases=len(names),raw_rows=raw_rows,static_channel_checks=dc_checks,transient_crossings_us=transient,half_step_crossing_delta_us=delta,physical_qualification=False,manufacturer_models=False)
a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
