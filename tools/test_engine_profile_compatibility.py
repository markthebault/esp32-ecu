"""Exact before/after regression of the preserved four-cylinder coupling path."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import types
from compare_engine_controllers import run,ROOT

BASELINE='c0d7d0fe1c96a9f783bc89591d8be1b09195f612'


def main(output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    name='tools/compare_engine_controllers.py';current=(ROOT/name).read_bytes()
    historical=subprocess.check_output(['git','show',BASELINE+':'+name],cwd=ROOT)
    before=types.ModuleType('preserved_four_cylinder_comparison');before.__file__=str(ROOT/name)
    exec(compile(historical,str(ROOT/name),'exec'),before.__dict__)
    cases=[]
    for controller in ('ours','speeduino'):
        for mode in ('batch','sequential','semi'):
            options=dict(sequential=mode=='sequential',semi_sequential=mode=='semi')
            for scenario,duration in (('warm_start',4),('trigger_dropout',6)):
                a=before.run(controller,scenario,duration,250,**options)
                b=run(controller,scenario,duration,250,**options)
                label=f'{controller}-{mode}-{scenario}'
                equal=a==b
                encoded=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
                cases.append(dict(case=label,equal=equal,before_sha256=hashlib.sha256(encoded(a)).hexdigest(),
                                  after_sha256=hashlib.sha256(encoded(b)).hexdigest()))
                (output/(label+'.json.gz')).write_bytes(gzip.compress(encoded(b),mtime=0))
                if not equal:raise RuntimeError('Four-cylinder coupling behavior changed: '+label)
    unchanged=(ROOT/name).read_bytes()==current
    result=dict(passed=unchanged and all(c['equal']for c in cases),cases=cases,baseline_commit=BASELINE,
        baseline_source_sha256=hashlib.sha256(historical).hexdigest(),current_source_sha256=hashlib.sha256(current).hexdigest(),
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_unchanged=unchanged,
        scope='Exact full-result equality for original4-cylinder coupling API, three strategies/two scenarios/both native controllers; no new physical qualification')
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:raise RuntimeError('Source changed during regression')
    print(json.dumps(dict(passed=True,cases=len(cases))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
