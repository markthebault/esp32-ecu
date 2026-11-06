#!/usr/bin/env python3
"""Steady-state fuel comparison against actual pinned Speeduino production objects.
This does not claim a full Speeduino controller/plant closed-loop comparison.
"""
import copy,json,subprocess,sys
from pathlib import Path
from engine_runtime import EngineRuntime,R
PIN='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
def compare():
 source=R.parent/'speeduino';sha=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 if sha!=PIN:raise RuntimeError('Speeduino reference SHA changed')
 base=json.loads((R/'config/engine/defaults.json').read_text());base['settings'].update(afterstart_pct=0,ego_enabled=False,dfco_enabled=False,rpm_limit=8000,max_duty=.85);base['curves']['deadtime_ms']=[.9]*5
 e=base['engine'];air=100000*(e['displacement_cc']/e['cylinders']*1e-6)/(287.05*298.15)*1e6;flow=e['injector_cc_min']*e['fuel_density_g_cc']/60
 req=int(air/e['stoich_afr']/flow*10+.5)
 rows=[];queries=[]
 for ve in [50,70,85,100,120]:
  for map_kpa in [20,40,60,80,100]:
   for rpm in [1000,3000,6000]:
    tune=copy.deepcopy(base);tune['maps']['ve']['cells']=[ve]*256
    runtime=EngineRuntime(tune);out=runtime.step(dict(rpm=rpm,map_kpa=map_kpa,synced=True),1000,use_decoder=False);runtime.close()
    if out['faults']:raise AssertionError(out)
    rows.append(dict(ve_pct=ve,map_kpa=map_kpa,rpm=rpm,ours_us=out['pulse_ms']*1000))
    queries.append(f'{req} {ve} {map_kpa} 100 900 {rpm}')
 result=subprocess.run([str(R/'.cache/engine/speeduino-reference')],input='\n'.join(queries)+'\n',text=True,capture_output=True,check=True)
 lines=result.stdout.splitlines()
 if len(lines)!=len(rows):raise RuntimeError('Reference emitted unexpected output: '+result.stdout)
 for row,line in zip(rows,lines):
  primary,secondary=map(int,line.split());assert secondary==0
  row['speeduino_us']=primary;row['difference_us']=row['ours_us']-primary
 maximum=max(abs(row['difference_us']) for row in rows)
 report=dict(scope='Compiled production computePulseWidths steady-state batch-fuel comparison only; not two full ECUs on the same plant',speeduino_commit=PIN,reqFuel_units_point1ms=req,conditions='2L/4cyl, 300cc/min, 25C IAT, lambda1, 0.9ms deadtime, corrections100%; Speeduino MAP/100 mode; no staging/nitrous',quantization='Speeduino required fuel rounded to 0.1 ms; integer percentage approximations differ from float calculation',cases=len(rows),max_absolute_difference_us=maximum,tolerance_us=75,passed=maximum<=75,rows=rows)
 (R/'reports/engine').mkdir(exist_ok=True);(R/'reports/engine/speeduino-fuel-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
 if not report['passed']:raise AssertionError(f'Fuel calculation difference {maximum:.1f} us exceeds mapped-quantization tolerance')
 print(f'Compared {len(rows)} native production fuel calculations: max difference {maximum:.2f} us (75 us mapped-quantization tolerance)')
 return report
if __name__=='__main__':compare()
