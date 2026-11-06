#!/usr/bin/env python3
"""Replay the actual native circuit/control bridge and audit all MSL008 fields.

Authored ADC/edge observations, no circuit solver or physical acquisition.
The unchanged MSL007 fixtures remain a separate legacy regression suite.
"""
import argparse,csv,gzip,hashlib,io,json,subprocess
from pathlib import Path
import run_flex_nonideal as producer
import analyze_flex_nonideal as auditor

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(output):
 output=output.resolve();output.mkdir(parents=True,exist_ok=False)
 names=[Path('tools/flex_circuit_control.cpp'),Path('tools/run_flex_nonideal.py'),Path('tools/analyze_flex_nonideal.py'),Path(__file__).relative_to(ROOT),*[p.relative_to(ROOT) for p in sorted((ROOT/'firmware/include/ecu').glob('*.hpp'))]]
 before={str(name):sha(ROOT/name) for name in names};program=producer.build_control(output)
 events=[(0,'E 0 1')]
 for time in range(10000,220001,10000):events.extend(((time-3000,f'E {time-3000} 0'),(time,f'E {time} 1')))
 for time in range(0,220001,5000):events.append((time,f'Q {time} {time} 1 3.3 2048 2048 1861 1489 1336 2048 1336 3723'))
 text='\n'.join(line for _,line in sorted(events,key=lambda x:x[0]))+'\n';(output/'stimulus.txt').write_text(text)
 cases=[];rejections=0
 for strategy in range(3):
  for basis in ('ratiometric','absolute'):
   dest=output/f'{strategy}-{basis}'
   with (output/f'{strategy}-{basis}.jsonl').open('x') as stdout,(output/f'{strategy}-{basis}.stderr.log').open('x') as stderr:
    result=subprocess.run([str(program),str(strategy),basis,str(dest)],input=text,text=True,stdout=stdout,stderr=stderr,check=True)
   (output/f'{strategy}-{basis}.jsonl').rename(dest/'control.jsonl');(output/f'{strategy}-{basis}.stderr.log').rename(dest/'stderr.log')
   frames=[json.loads(line) for line in (dest/'control.jsonl').read_text().splitlines()];phase0=[f for f in frames if f['circuit_clock_phase_us']==0]
   assert frames and all(f['schema_version']==2 and 'boost_control' in f for f in frames)
   auditor.verify_msl(dest/'engine.msl',phase0)
   rows=list(csv.reader(io.StringIO((dest/'engine.msl').read_text()),delimiter='\t'));assert len(rows[2])==245
   for index in range(229,245):
    altered=[row.copy() for row in rows];original=altered[4][index];altered[4][index]='0' if original=='NaN' else str(int(original)+1) if altered[3][index] in ('bool','code','count','bitfield') else str(float(original)+1)
    path=dest/'mutated.msl'
    with path.open('w') as file:csv.writer(file,delimiter='\t',lineterminator='\n').writerows(altered)
    try:auditor.verify_msl(path,phase0)
    except ValueError:rejections+=1
    else:raise AssertionError('Corrupt boost column accepted: '+rows[2][index])
   cases.append(dict(strategy=strategy,basis=basis,frames=len(frames),msl_rows=len(phase0),columns=len(rows[2]),msl_sha256=sha(dest/'engine.msl')))
 assert rejections==96 and before=={str(name):sha(ROOT/name) for name in names}
 report=dict(passed=True,scope=__doc__.strip(),cases=cases,corrupt_boost_columns_rejected=rejections,source_sha256=before)
 (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=True,cases=len(cases),corrupt_boost_columns_rejected=rejections)))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output)
