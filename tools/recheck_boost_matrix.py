"""Fresh-process audit of every completed case, preserving initial audit output.

Use this after an audit-code correction. No run, trace or original result is
overwritten; the new result binds the original summary and every raw payload.
"""
import argparse
import json
from pathlib import Path
from boost_engine_provenance import digest
from verify_boost_engine import verify


def recheck(study):
    study=Path(study).resolve()
    original=study/'result.json';plan=study/'plan.json'
    old=json.loads(original.read_text());cases=json.loads(plan.read_text())['cases']
    inputs={str(original):digest(original),str(plan):digest(plan)}
    records=[];sources=None
    for case in cases:
        folder=study/case['name']/'run'
        result=json.loads((folder/'result.json').read_text())
        if sources is None:sources=result['source_hashes']
        assert result['source_hashes']==sources, 'Mixed controller sources'
        for name in ('tune.json','result.json','progress.json','trace.jsonl','edges.jsonl','trigger-stimuli.jsonl','provenance/manifest.json'):
            path=folder/name;inputs[str(path)]=digest(path)
        records.append(dict(name=case['name'],audit=verify(folder,current_inputs=True)))
    for path,expected in inputs.items():
        assert digest(path)==expected, 'Run data changed during re-audit'
    result=dict(run_invariants_passed=True,initial_run_invariants_passed=old['run_invariants_passed'],
                same_executing_sources=True,records=records,input_sha256=inputs,
                verification_source_sha256=digest(Path(__file__).with_name('verify_boost_engine.py')),
                recheck_source_sha256=digest(Path(__file__)),physical_execution=False,
                qualification='New audit result only. Original data and initial audit records retained unchanged.')
    with (study/'verification-result.json').open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('study',type=Path)
    args=parser.parse_args();result=recheck(args.study)
    print(json.dumps(dict(passed=True,cases=len(result['records']),initial_pass=result['initial_run_invariants_passed']),indent=2))
