"""Freeze a completed reviewed turbo study without upstream linked binaries."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from boost_engine_provenance import digest

ROOT=Path(__file__).resolve().parents[1]


def package(study,analysis,review,output,history=None,history_review=None):
    study,analysis,review,output=[Path(p).resolve() for p in (study,analysis,review,output)]
    verification=study/'verification-result.json'
    result=json.loads((verification if verification.exists() else study/'result.json').read_text())
    if result['run_invariants_passed'] is not True:raise ValueError('Cannot publish a failed study as accepted')
    assessment=json.loads((review/'assessment.json').read_text())
    if assessment.get('accepted') is not True or assessment.get('open_findings')!=[]:raise ValueError('Independent reviewed scope is not accepted')
    output.mkdir(parents=True,exist_ok=False)
    manifest=dict(files=[],archives=[])

    def archive(name,role,rows):
        entries=[]
        with tarfile.open(output/name,'w:gz',compresslevel=9) as dest:
            for rel,path in sorted(rows.items()):
                content=path.read_bytes();info=tarfile.TarInfo(rel);info.size=len(content);info.mode=0o644
                info.mtime=0;dest.addfile(info,io.BytesIO(content))
                entries.append(dict(path=rel,bytes=len(content),sha256=hashlib.sha256(content).hexdigest()))
        manifest['archives'].append(dict(path=name,role=role,payloads=entries))

    plan=json.loads((study/'plan.json').read_text());case_names=[row['name'] for row in plan['cases']]
    data={'study/plan.json':study/'plan.json','study/result.json':study/'result.json'}
    if verification.exists():
        for path,expected in result['input_sha256'].items():
            if digest(path)!=expected:raise ValueError('Re-audited run data changed: '+path)
        data['study/verification-result.json']=verification
    first=study/case_names[0]/'run'
    sources=json.loads((first/'result.json').read_text())['source_hashes']
    for name in case_names:
        directory=study/name;run=directory/'run'
        current=json.loads((run/'result.json').read_text())
        if current['source_hashes']!=sources:raise ValueError('Mixed source snapshots')
        for file in ('tune.json','result.json','progress.json','trace.jsonl','edges.jsonl','trigger-stimuli.jsonl'):
            data['cases/'+name+'/'+file]=run/file
        for file in ('command.json','command.log','audit.json'):
            data['cases/'+name+'/'+file]=directory/file
        for path in (run/'provenance').iterdir():
            if path.is_file() and path.suffix not in ('.so','.o'):
                data['cases/'+name+'/provenance/'+path.name]=path
    archive('study.tar.gz','study',data)

    source_payload={name:first/'provenance/sources'/name for name in sources}
    extras=('scripts/prepare_tcsi_source.py','tools/test_tcsi_source.py','tools/test_boost_valve_plant.py',
            'tools/test_turbo_gas_path.py','tools/test_boost_research_plant.py','tools/test_speeduino_turbo.py',
            'tools/run_boost_matrix.py','tools/verify_boost_engine.py','tools/analyse_boost_runs.py',
            'tools/plot_turbo_study.py','tools/package_turbo_study.py','tools/verify_turbo_packet.py','tools/recheck_boost_matrix.py')
    for name in extras:source_payload[name]=ROOT/name
    for path in (first/'provenance/model-inputs').glob('*.json'):
        source_payload['model-source-identities/'+path.name]=path
    cjson=first/'provenance/external/cJSON'
    if cjson.exists():
        for path in cjson.iterdir():source_payload['external/cJSON/'+path.name]=path
    archive('sources.tar.gz','sources',source_payload)

    # The reviewer's whitelist is the authority. An ELF is never silently
    # substituted or redistributed; callers must provide a source-only packet.
    whitelist=review/'whitelist.json'
    rows=json.loads(whitelist.read_text())
    if isinstance(rows,dict):rows=rows.get('files',rows.get('payloads'))
    if not isinstance(rows,list):raise ValueError('Unrecognized independent review whitelist')
    review_payload={}
    for row in rows:
        rel=row.get('path',row.get('name'));path=review/rel
        content=path.read_bytes()
        if content.startswith(b'\x7fELF'):raise ValueError('Review whitelist contains an upstream linked binary: '+rel)
        if path.suffix.lower() in ('.zip','.mdl'):raise ValueError('Upstream model archives remain fetched separately: '+rel)
        if row.get('sha256') and digest(path)!=row['sha256']:raise ValueError('Review payload changed: '+rel)
        review_payload[rel]=path
    review_payload['whitelist.json']=whitelist
    archive('independent-review.tar.gz','review',review_payload)

    history_summary=None
    if history is not None:
        history=Path(history).resolve()
        old=json.loads((history/'result.json').read_text())
        if old['run_invariants_passed'] is not False:raise ValueError('Expected explicitly rejected historical study')
        historical={}
        for file in ('plan.json','result.json','progress.json'):
            historical['study/'+file]=history/file
        old_plan=json.loads((history/'plan.json').read_text())
        first_old=None
        for case in old_plan['cases']:
            directory=history/case['name'];run=directory/'run'
            if first_old is None and (run/'provenance/sources').exists():first_old=run
            for file in ('command.json','command.log','audit.json'):
                if (directory/file).exists():historical['cases/'+case['name']+'/'+file]=directory/file
            for file in ('tune.json','result.json','progress.json','trace.jsonl','edges.jsonl','trigger-stimuli.jsonl','provenance/manifest.json'):
                if (run/file).exists():historical['cases/'+case['name']+'/'+file]=run/file
        for path in (first_old/'provenance/sources').rglob('*'):
            if path.is_file():historical['sources/'+str(path.relative_to(first_old/'provenance/sources'))]=path
        if history_review is not None:
            history_review=Path(history_review).resolve()
            old_rows=json.loads((history_review/'whitelist.json').read_text())
            if isinstance(old_rows,dict):old_rows=old_rows.get('files',old_rows.get('payloads'))
            for row in old_rows:
                rel=row.get('path',row.get('name'));path=history_review/rel;content=path.read_bytes()
                if content.startswith(b'\x7fELF') or path.suffix.lower() in ('.zip','.mdl'):raise ValueError('Historical review must contain source/evidence only')
                if row.get('sha256') and digest(path)!=row['sha256']:raise ValueError('Historical review changed: '+rel)
                historical['review/'+rel]=path
            historical['review/whitelist.json']=history_review/'whitelist.json'
        archive('rejected-history.tar.gz','history',historical)
        history_summary=dict(run_invariants_passed=False,cases=len(old_plan['cases']),
                             rejected_cases=sum(not row.get('audit',{}).get('audit_passed',False) for row in old['records']))

    shutil.copy2(analysis/'comparison.json',output/'comparison.json')
    if (analysis/'figures').exists():shutil.copytree(analysis/'figures',output/'figures')
    shutil.copy2(ROOT/'tools/verify_turbo_packet.py',output/'verify.py')
    summary=dict(base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                 case_names=case_names,run_invariants_passed=True,independent_review_accepted=True,source_hashes=sources,
                 initial_runner_invariants_passed=json.loads((study/'result.json').read_text())['run_invariants_passed'],
                 fresh_verification_sha256=digest(verification) if verification.exists() else None,
                 physical_execution=False,full_speeduino_parity=False,
                 upstream_linked_binaries_included=False,upstream_model_archive_included=False,
                 rejected_history=history_summary,
                 qualification='Native research evidence; source model is fetched and verified separately')
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    # README and optional historical payloads are added before final sealing.
    (output/'archive-inventory.json').write_text(json.dumps(manifest['archives'],indent=2)+'\n')
    return manifest


def seal(output):
    output=Path(output)
    archives=json.loads((output/'archive-inventory.json').read_text())
    files=[dict(path=str(path.relative_to(output)),bytes=path.stat().st_size,sha256=digest(path))
           for path in sorted(output.rglob('*')) if path.is_file() and path.name!='artifact-manifest.json']
    with (output/'artifact-manifest.json').open('x') as stream:stream.write(json.dumps(dict(files=files,archives=archives),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path)
    parser.add_argument('--analysis',type=Path)
    parser.add_argument('--review',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--history',type=Path)
    parser.add_argument('--history-review',type=Path)
    parser.add_argument('--seal',action='store_true')
    args=parser.parse_args()
    if args.seal:seal(args.output)
    else:package(args.study,args.analysis,args.review,args.output,args.history,args.history_review)
