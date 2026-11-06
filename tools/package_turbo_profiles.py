"""Publish the reviewed turbo-geometry/project-coupling foundation and limits."""
import argparse,gzip,hashlib,json,subprocess,zipfile
from pathlib import Path
from verify_turbo_geometry_run import audit

ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache/engine'
BASELINE='4daa4d8aadd05675759cc1f330d232bd331a304b'
SAFE={'.json','.jsonl','.py','.cpp','.hpp','.h','.c','.m','.mdl','.d','.log','.txt','.md','.gz'}
SOURCES=('tools/turbo_components.py','tools/turbo_gas_path.py','tools/boost_research_plant.py',
 'tools/run_boost_engine.py','tools/boost_engine_provenance.py','tools/test_engine_profile_plants.py',
 'tools/test_turbo_geometry.py','tools/verify_turbo_geometry_run.py','tools/package_turbo_profiles.py',
 'docs/engine-turbo-profiles.md','docs/engine-cylinder-profiles.md','docs/engine-feature-coverage.md')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def main(output):
 output=output.resolve()
 if output.exists():raise RuntimeError('Choose a new output directory')
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=BASELINE:
  raise RuntimeError('This packet overlays its explicit historical baseline')
 groups={k:{}for k in ('sources','validation','runs')}
 def add(group,path,name):
  path=Path(path);name=str(name)
  assert path.is_file()and not path.is_symlink(),path
  assert not Path(name).is_absolute()and'..'not in Path(name).parts and name not in groups[group],name
  groups[group][name]=path
 def tree(group,base,prefix):
  for p in sorted(base.rglob('*')):
   if p.is_file()and not p.is_symlink()and p.suffix in SAFE:add(group,p,Path(prefix)/p.relative_to(base))
 identities={n:dict(bytes=(ROOT/n).stat().st_size,sha256=sha(ROOT/n))for n in SOURCES}
 for n in SOURCES:add('sources',ROOT/n,n)
 tests=CACHE/'turbo-profiles-tests-001';t=read(tests/'summary.json')
 assert t['passed']and t['tests']==8 and t['source_unchanged']
 for name,value in t['source_sha256'].items():assert sha(ROOT/name)==value,name
 tree('validation',tests,'geometry-tests');add('validation',tests.with_suffix('.log'),'geometry-tests.log')
 for name in ('turbo-profiles-gas-regression-001.log','turbo-profiles-composition-regression-002.log','turbo-profiles-integration-001.log'):
  text=(CACHE/name).read_text();assert 'OK'in text and'FAILED'not in text and'Traceback'not in text,name
  add('validation',CACHE/name,'regression/'+name)
 tree('validation',CACHE/'turbo-profiles-integration-001','integration-readback')
 baseline=CACHE/'turbo-profiles-baseline-001'
 before=json.loads(gzip.decompress((baseline/'before.json.gz').read_bytes()))
 after=json.loads(gzip.decompress((baseline/'after-clock-fix.json.gz').read_bytes()))
 assert before==after and sum(map(len,before.values()))==200
 tree('validation',baseline,'historical-default-replay')
 reviews={}
 for label,sourcekey in (('turbo-profile-review-001','working_tree_source_sha256'),('turbo-coupling-review-001','reviewed_working_tree_source_sha256')):
  base=CACHE/label;a=read(base/'assessment.json');h=read(base/'source_hashes.json')
  assert a['verdict'].startswith('pass within')and a['outstanding_findings']==[]
  for name,value in h[sourcekey].items():assert sha(ROOT/name)==value,('Reviewed source changed',name)
  for name,value in a['artifact_sha256'].items():assert sha(base/name)==value,(label,name)
  for name in a['publication_whitelist']:
   path=ROOT/name;assert path.resolve().is_relative_to(base.resolve())
   add('validation',path,Path('independent')/path.relative_to(CACHE))
  reviews[label]=dict(assessment_sha256=sha(base/'assessment.json'),scope=a['scope'])
 # Only these two runs prove post-halt physical inventories. Earlier prefixes
 # are retained with their actual versions and explicitly narrower scope.
 cases={}
 for name,cylinder in (('turbo-profiles-controller-003',8),('turbo-coupling-review-001/n7-semi-charged-cut-final',7)):
  result=audit(CACHE/name,charged_cylinder=cylinder)
  assert result['passed']and result['current_source_differences']==[] and result['post_halt_physics_verified']
  cases[name]=result;tree('runs',CACHE/name,'current/'+name)
 for name in ('turbo-profiles-single-001','turbo-profiles-open-loop-001'):
  result=audit(CACHE/name,prefix_only=True)
  assert result['passed']and result['current_source_differences']==['tools/run_boost_engine.py']
  cases[name]=result;tree('runs',CACHE/name,'prefix-only/'+name)
 # Failed high-load experiment is an observed model/hardware-domain limit,
 # never accepted as a successful controller/boost comparison.
 failed=CACHE/'turbo-profiles-open-loop-002';f=read(failed/'progress.json')
 assert f['status']=='failed'and not f['complete']and not(failed/'result.json').exists()
 assert f['time_us']==4730343 and f['error']['message']=='Turbo speed outside declared0..24000rad/s'
 fp=read(failed/'provenance/manifest.json')
 for name,value in fp['source_hashes'].items():
  assert sha(failed/'provenance/sources'/name)==value and sha(ROOT/name)==value,name
 tree('runs',failed,'failed-source-map-domain')
 manifest=dict(status='reviewed_research_foundation_goal_active',baseline_commit=BASELINE,
  goal_complete=False,engine_outputs_inhibited=True,physical_operation_verified=False,
  fitted_injector_commands=4,fitted_coil_commands=4,source_identities=identities,reviews=reviews,
  cases=cases,failed_experiment=dict(time_us=f['time_us'],error=f['error'],accepted_as_passing_evidence=False),archives={},
  limits=['Uncalibrated source-backed gas graph/empirical combustion and native zero-CPU-time dispatcher',
   'Fixed source turbo/maps/volumes are not automatically matched to every engine displacement',
   'Project1/7/8-cylinder cases, not an expanded genuine Speeduino turbo comparison',
   'Prefix-only histories do not establish post-halt physical inventories',
   'No dynamic cam-dropout, expanded closed-loop tracking, target/HIL or physical qualification'])
 output.mkdir(parents=True,exist_ok=False)
 for group,files in groups.items():
  payloads={n:dict(bytes=p.stat().st_size,sha256=sha(p))for n,p in sorted(files.items())}
  archive=output/(group+'.zip')
  with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
   for n,p in sorted(files.items()):z.write(p,n)
  with zipfile.ZipFile(archive)as z:
   assert z.testzip()is None and set(z.namelist())==set(files)
   for n,p in files.items():assert sha(p)==payloads[n]['sha256']==hashlib.sha256(z.read(n)).hexdigest()
  manifest['archives'][group]=dict(file=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),payloads=payloads)
 for n,i in identities.items():assert sha(ROOT/n)==i['sha256']
 (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (output/'README.md').write_text('''# Turbo profile research foundation

Explicit1..8-cylinder geometry now binds actual pumping displacement, per-cylinder air, sparse actuators and conservative gas/heat inventories. Native project coupling adds sequential cam events, full-channel cut records and loaded-layout provenance. The full ECU goal remains active; PCB capacity stays4+4 and normal engine outputs stay inhibited.

- `sources.zip`: source overlay on commit4daa4d8, tools, reproduction and limits.
- `validation.zip`: eight geometry/atomicity tests, existing regressions,200 exact parent state replays, independent48 analytical flow cases/1002 numerical values, and separate model/controller-coupling reviews with resolved findings.
- `runs.zip`: current8-cylinder sequential and independent7-cylinder semi charged-cut evidence; source-bound1-cylinder and8-cylinder open-loop prefixes; explicitly failed4L high-throttle source-map experiment. Compiled binaries/gcov and the upstream archive ZIP are excluded; source/model inputs and identities are retained.

Current charged stops retain actual COIL17/COIL16 discharges and closed post-cut ledgers. Earlier prefixes have their original source versions and cannot prove post-halt inventories. The8-second20%-throttle run records234 PWM edges while manifold pressure stays below ambient; it does not establish pressure tracking. The80%-throttle4L run exceeds the source turbo's24000rad/s domain at4.730343s and is excluded from passing evidence.

See `docs/engine-turbo-profiles.md` for commands and physical assumptions. Matched turbo/map hypotheses, a16-output genuine production boost fixture, paired normal/fault/refinement comparisons, further controls/UI/configuration/debug/PCB work, online tuning support and target/physical qualification remain unfinished. No physical engine, vehicle, electrical, EMI/surge, thermal, splash, RF or printed-fit qualification is claimed.
''')
 print(json.dumps(dict(output=str(output),archives={k:dict(bytes=v['bytes'],files=len(v['payloads']))for k,v in manifest['archives'].items()})))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 main(p.parse_args().output)
