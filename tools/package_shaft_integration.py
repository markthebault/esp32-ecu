"""Publish the reviewed shaft/intake correction and its finite comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from verify_boost_engine import verify

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.cache/engine'
BASELINE='bbf7ba55a29932c8fdccad7c7a9c63c79c095c65'
SAFE={'.json','.jsonl','.py','.cpp','.hpp','.h','.c','.m','.mdl','.d','.log','.txt','.md','.inc','.so','.zip','.gz'}
SOURCES=('tools/engine_research_plant.py','tools/boost_research_plant.py','tools/run_boost_engine.py',
 'tools/verify_boost_engine.py','tools/test_engine_profile_plants.py','tools/test_turbo_geometry.py',
 'tools/shaft_dynamics.py','tools/test_shaft_dynamics.py','tools/test_intake_integration.py',
 'tools/plot_shaft_integration.py','tools/package_shaft_integration.py',
 'docs/engine-shaft-integration.md','docs/engine-expanded-boost-reference.md','docs/engine-feature-coverage.md')
CASES=('ours-eight-open-500','ours-eight-open','reference-eight-open-500','reference-eight-open',
       'reference-eight-open-125','ours-eight-charged-rail')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())


def main(output):
 output=output.resolve()
 if output.exists():raise RuntimeError('Choose a new output directory')
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=BASELINE:
  raise RuntimeError('This source overlay requires its explicit historical baseline')
 groups={key:{}for key in ('sources','validation','runs')}
 def add(group,path,name):
  path=Path(path);name=str(name)
  assert path.is_file()and not path.is_symlink(),path
  assert not Path(name).is_absolute()and'..'not in Path(name).parts and name not in groups[group],name
  groups[group][name]=path
 def tree(group,base,prefix):
  for path in sorted(base.rglob('*')):
   if path.is_file()and not path.is_symlink()and path.suffix in SAFE:
    add(group,path,Path(prefix)/path.relative_to(base))
 identities={name:dict(bytes=(ROOT/name).stat().st_size,sha256=sha(ROOT/name))for name in SOURCES}
 for name in SOURCES:add('sources',ROOT/name,name)
 tests={}
 for name,count in (('shaft-tests-005',7),('intake-tests-003',7),('shaft-geometry-regression-004',8),('shaft-profile-regression-004',9)):
  base=CACHE/name;summary=read(base/'summary.json')
  assert summary['passed']and summary['tests']==count and not summary['failures']and not summary['errors'],name
  assert summary.get('source_unchanged',True),name
  for source,expected in summary['source_sha256'].items():assert sha(ROOT/source)==expected,source
  tests[name]=dict(groups=count,summary_sha256=sha(base/'summary.json'))
  tree('validation',base,'tests/'+name);add('validation',base.with_suffix('.log'),'tests/'+name+'.log')
 for name,count in (('shaft-composition-regression-004',5),('shaft-mvem-regression-004',7)):
  path=CACHE/(name+'.log');text=path.read_text()
  assert f'Ran {count} tests'in text and'\nOK\n'in text and'FAILED'not in text,name
  add('validation',path,'tests/'+path.name);tests[name]=dict(groups=count,log_sha256=sha(path))

 review=CACHE/'shaft-review-001';assessment=read(review/'assessment.json');whitelist=read(review/'whitelist.json')
 assert assessment['open_findings']==0 and assessment['reviewer_processes_terminal']is True
 for name,expected in read(review/'revision4-sources.json').items():assert sha(ROOT/name)==expected,name
 for item in whitelist['files']:
  path=review/item['path'];assert path.resolve().is_relative_to(review.resolve())
  assert path.stat().st_size==item['bytes']and sha(path)==item['sha256'],path
  add('validation',path,Path('independent')/item['path'])
 add('validation',review/'whitelist.json','independent/whitelist.json')

 analysis=CACHE/'shaft-analysis-004';comparison=read(analysis/'comparison.json')
 assert comparison['analysis_source_sha256']==sha(ROOT/'tools/analyse_boost_runs.py')
 assert len(comparison['records'])==5 and len(comparison['refinement'])==3
 reference_checks=[row for row in comparison['refinement']if row['controller']=='speeduino']
 assert len(reference_checks)==2
 tree('validation',analysis,'analysis')
 # Preserve rejected development stages with original snapshots and explicit
 # failed status. Their cached full raw runs are not standalone public packets.
 for name in ('shaft-analysis-001/comparison.json','shaft-v2-audit-failures.json',
              'intake-fractional-boundary-failure.json','shaft-profile-regression-003.log'):
  add('validation',CACHE/name,'rejected-history/'+name)
 prior=read(CACHE/'shaft-intake-probe-001/result.json');assert prior['passed']is False
 tree('validation',CACHE/'shaft-intake-probe-001','rejected-history/intake-causality')
 for name in ('tools/shaft_dynamics.py','tools/engine_research_plant.py','tools/boost_research_plant.py','tools/run_boost_engine.py'):
  add('validation',CACHE/'shaft-boost-pair-001/reference-eight-open-500/provenance/sources'/name,
      'rejected-history/stage-one-sources/'+name)

 folders={name:CACHE/'shaft-boost-pair-004'/name for name in CASES}
 folders['independent-reference-one-batch']=review/'reference-one-batch-v4'
 cases={}
 for name,folder in folders.items():
  cases[name]=verify(folder,current_inputs=True)
  assert cases[name]['audit_passed']and cases[name]['post_halt_audited']and cases[name]['physical_event_counts']
  tree('runs',folder,name)
 figure=CACHE/'shaft-figure-001';plot=read(figure/'manifest.json')
 assert plot['plot_source_sha256']==sha(ROOT/'tools/plot_shaft_integration.py')
 for name,expected in plot['inputs'].items():assert sha(name)==expected,name
 assert plot['image_sha256']==sha(figure/'refinement.png')
 add('validation',figure/'manifest.json','plot-inputs.json')
 manifest=dict(status='reviewed_numerical_correction_goal_active',baseline_commit=BASELINE,
  goal_complete=False,engine_outputs_inhibited=True,physical_operation_verified=False,
  fitted_injector_commands=4,fitted_coil_commands=4,source_identities=identities,tests=tests,
  review_assessment_sha256=sha(review/'assessment.json'),review_whitelist_sha256=sha(review/'whitelist.json'),
  cases=cases,refinement=comparison['refinement'],
  finite_reference_refinement_passed=all(row['within_declared_two_percent']for row in reference_checks),
  rejected_history_has_complete_raw_packets=False,archives={},
  limits=['Empirical uncalibrated engine/gas/actuator hypotheses; zero native CPU/IRQ execution cost',
   'Finite refinement is distinct from uniform convergence, controller equivalence or pressure tracking',
   'Turbo/map matching, full feature parity, hardware expansion and online tuning remain unfinished',
   'No target/HIL, physical engine, vehicle, electrical, EMI/surge, thermal, splash, RF or printed-fit qualification'])
 output.mkdir(parents=True,exist_ok=False)
 for group,files in groups.items():
  payloads={name:dict(bytes=path.stat().st_size,sha256=sha(path))for name,path in sorted(files.items())}
  archive=output/(group+'.zip')
  with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as stream:
   for name,path in sorted(files.items()):
    info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
    stream.writestr(info,path.read_bytes(),compresslevel=9)
  with zipfile.ZipFile(archive)as stream:
   assert stream.testzip()is None and set(stream.namelist())==set(files)
   for name,path in files.items():assert sha(path)==payloads[name]['sha256']==hashlib.sha256(stream.read(name)).hexdigest()
  manifest['archives'][group]=dict(file=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),payloads=payloads)
 with tempfile.TemporaryDirectory(prefix='shaft-packet-audit-',dir=CACHE)as temp:
  with zipfile.ZipFile(output/'runs.zip')as stream:stream.extractall(temp)
  for name in folders:assert verify(Path(temp)/name)==cases[name],name
 manifest['packet_only_audits_passed']=len(cases)
 shutil.copyfile(figure/'refinement.png',output/'refinement.png');manifest['figure_sha256']=sha(output/'refinement.png')
 for name,identity in identities.items():assert sha(ROOT/name)==identity['sha256'],name
 (output/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
 state='pass'if manifest['finite_reference_refinement_passed']else'fail'
 (output/'README.md').write_text(f'''# Research shaft and intake correction

The engine research plant now resolves intake closing before trapping fuel, integrates constant-source wall transport, and advances starter/friction with an analytical linear solution and conservative power step. Local elapsed durations preserve pending gas/shaft energy exchange. These numerical fixes improve the test method; the full ECU goal remains active and normal engine outputs remain inhibited.

![Actual saved finite-step histories](refinement.png)

The two finite reference-refinement checks **{state}** the unchanged2% gate. The manifest retains each result separately; neither the figure nor a passing invariant audit establishes calibrated physics, controller equivalence or positive-boost tracking.

- `sources.zip`: source overlay on `bbf7ba5`, reproduction and method limits.
- `validation.zip`: analytical/ODE/causal-boundary tests, all48 quick/MVEM cylinder-strategy profiles, integrated regressions and independent review. Rejected stages retain their own source snapshots and counterexamples; their full raw cached histories are not standalone public packets here.
- `runs.zip`: six final parent cases plus an independent one-cylinder reference case, with full source/model inputs and actual intake/combustion records. Project shared libraries permit packet-only auditing; reference binaries, object/coverage files and proprietary applications are excluded.

The event audit independently replays actual injector transitions through dead time, wall/port fuel, intake closing, combustion/discard and final storage. It checks distinct actual coil falls and separate scheduled-work/conversion-heat inventories. Earlier rejected time/accounting and event-tamper cases stay rejected. Seven extracted case packets must pass the same audit before publication.

See `docs/engine-shaft-integration.md` in the source overlay. Matched turbo/maps, remaining engine features, protected PCB expansion, supported online tuning and target/physical validation remain unfinished. The fitted carrier is still4+4. No physical engine, vehicle, electrical, EMI/surge, thermal, splash, RF or printed-fit qualification is claimed.
''')
 print(json.dumps(dict(output=str(output),cases=len(cases),finite_reference_refinement_passed=manifest['finite_reference_refinement_passed'],
                       archives={k:dict(bytes=v['bytes'],files=len(v['payloads']))for k,v in manifest['archives'].items()})))


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
 main(parser.parse_args().output)
