#!/usr/bin/env python3
"""Independent simplified conditioner experiment, intentionally not vendor SPICE.

This model uses a different assumed BJT/diode set from the root experiment.
Negative controls demonstrate why correct pinout and an actual contact test
are required even when expander marker/configuration/loopback all pass.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ngspice',type=Path,required=True);parser.add_argument('--report-dir',type=Path,required=True);args=parser.parse_args()
binary=args.ngspice.resolve();out=args.report_dir.resolve();out.mkdir(parents=True,exist_ok=False)
cases=[]
for temp in (-20,25,85):
 for resistance in (.1,100,1e12):cases.append((f'normal-{temp}-{resistance}',temp,resistance,False,False,None))
cases.extend([('swapped-collector-emitter',25,1e12,True,False,None),('negative18-clamped',25,1e12,False,False,-18),('negative18-without-clamp',25,1e12,False,True,-18),('positive18',25,1e12,False,False,18)])
rows=[]
for name,temp,contact,swapped,no_clamp,fault in cases:
 folder=out/name;folder.mkdir(exist_ok=True)
 q='0 b c' if swapped else 'c b 0'
 lines=[f'Independent SW2 analog polarity experiment {name}',
  '* Assumed NPN/diode parameters, not manufacturer guarantees.',f'.temp {temp}',
  '.model NPNCOND NPN(IS=1e-15 BF=40 BR=2 VAF=50 RB=100 RC=10 RE=1 CJE=10p CJC=5p TF=.5n TR=100n)',
  '.model CLAMP D(IS=2e-9 N=1.7 RS=1 CJO=3p TT=5n)',
  'Vrail rail 0 3.3','Dfeed rail feed CLAMP','Rbias feed sw 2200',
  'RbaseA sw mid 4990','RbaseB mid b 4990','Roff b 0 100k',
  'Rcollector rail c 4700','Rprotect c gp 1000','Ccollector c 0 10n',
  f'Qinput {q} NPNCOND','Iinput gp 0 -1u']
 if not no_clamp:lines.append('Dnegative 0 b CLAMP')
 if fault is None:lines.append(f'Rcontact sw 0 {contact}')
 else:lines.extend([f'Vfault outside 0 {fault}','Rfault outside sw 1'])
 lines.extend(['.control','set wr_singlescale','set wr_vecnames','op','wrdata values.txt v(sw) v(b) v(c) v(gp) i(Vrail)','quit','.endc','.end',''])
 (folder/'experiment.cir').write_text('\n'.join(lines))
 run=subprocess.run([str(binary),'-b','experiment.cir'],cwd=folder,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (folder/'ngspice.log').write_text(run.stdout);assert run.returncode==0
 fields=(folder/'values.txt').read_text().splitlines()[-1].split();values=list(map(float,fields));assert len(values)==6
 row=dict(name=name,temperature_c=temp,contact_ohm=contact,sw_v=values[1],base_v=values[2],collector_v=values[3],gp_v=values[4],rail_current_ma=-values[5]*1000,
  low=values[4]<=.66,high=values[4]>=2.64)
 if name.startswith('normal-'):assert row['low'] if contact>1e6 else row['high'],row
 elif name=='swapped-collector-emitter':assert not row['low'],row
 elif name=='negative18-clamped':assert abs(row['base_v'])<1,row
 elif name=='negative18-without-clamp':assert abs(row['base_v'])>6,row
 elif name=='positive18':assert row['low'],row
 rows.append(row)
report=dict(passed_declared_model_checks=True,cases=len(rows),physical_qualification=False,manufacturer_model=False,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
 rationale='Analog negative controls: swapped E/C fails the open-contact low check, and omitted negative clamp exceeds the quoted6V emitter-base stress limit in this assumed model. Expander selftest cannot establish input analog correctness.',
 assumptions='Generic independent semiconductor parameters at3.3V, intact common ground. No actual device leakage, unpowered behavior, parasitics, surge/EMI/thermal or printed fit is established.',results=rows)
(out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed_declared_model_checks':True,'cases':len(rows),'negative_controls':2,'physical_qualification':False}))
