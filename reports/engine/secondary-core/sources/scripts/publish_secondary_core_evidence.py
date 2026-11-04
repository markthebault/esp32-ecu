#!/usr/bin/env python3
"""Freeze the scoped core foundation; this does not publish a full feature acceptance."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache/engine/secondary';OUT=ROOT/'reports/engine/secondary-core'
def sha(body):return hashlib.sha256(body).hexdigest()
def write(path,body):
 p=OUT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
def copy(source,destination):write(destination,source.read_bytes())
def review(name,directory):
 body=(directory/'artifact-manifest.json').read_bytes();manifest=json.loads(body)
 entries=manifest.get('artifacts') or [dict(path=path,**entry) for path,entry in manifest['files'].items()]
 selected=[];excluded=[]
 for entry in entries:
  rel=entry['path'];p=directory/rel;data=p.read_bytes()
  assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],p
  # Keep pinned upstream vendor snapshots and compiled executables in cache;
  # their hashes/rebuild recipes remain in the original reviewer manifest.
  if rel.startswith('reference-source/') or data.startswith((b'\x7fELF',b'!<arch>')):
   excluded.append(rel);continue
  compressed=rel.endswith('.csv') and len(data)>250000
  stored=rel+'.gz' if compressed else rel
  write('reviews/'+name+'/'+stored,gzip.compress(data,mtime=0) if compressed else data)
  selected.append(dict(original_path=rel,stored_path=stored,compressed=compressed))
 write('reviews/'+name+'/original-artifact-manifest.json',body)
 write('reviews/'+name+'/selection.json',(json.dumps({'included':selected,'cache_only':excluded},indent=2)+'\n').encode())
 return dict(name=name,manifest_sha256=sha(body),verified_original_artifacts=len(entries),archived_artifacts=len(selected),cache_only=len(excluded))
def main():
 if OUT.exists():raise SystemExit('Evidence destination already exists; preserve it and use a new reviewed publication path.')
 native=(CACHE/'native-tests-final.log').read_text();python=(CACHE/'python-tests-final.log').read_text()
 assert '"secondary_checks":738' in native and '"engine_secondary_checks":148' in native and '"allocation_failures":4' in native and 'Actual task logger:' in native
 assert 'Ran 173 tests' in python and '\nOK\n' in python
 assert '[SUCCESS]' in (CACHE/'selected-build-final.log').read_text()
 assert 'Static placement checks: PASS' in (CACHE/'isr-audit-final.log').read_text()
 core=json.loads((ROOT/'.cache/engine/secondary-core-review/review.json').read_text())
 assert core['passed'] and core['independent_checks']['total']==3224 and core['exact_own008_pages']==108 and not core['remaining_medium_high_in_reviewed_scope']
 for rel,digest in core['source_bindings'].items():assert sha((ROOT/rel).read_bytes())==digest,('Reviewed source drift',rel)
 reviews=[review('architecture',ROOT/'.cache/engine/secondary-architecture-review'),review('core',ROOT/'.cache/engine/secondary-core-review')]
 baseline=CACHE/'core-baseline';metadata=json.loads((baseline/'manifest.json').read_text());copy(baseline/'manifest.json','before/manifest.json')
 for path,digest in metadata['sources'].items():
  body=(baseline/'source-snapshots'/path).read_bytes();assert sha(body)==digest;write('before/sources/'+path,body)
 before=(baseline/'observations.csv').read_bytes();after=(CACHE/'core-candidate/legacy-observations-final.csv').read_bytes()
 assert before==after and before.count(b'\n')==7776
 write('before/observations.csv.gz',gzip.compress(before,mtime=0));write('after/observations.csv.gz',gzip.compress(after,mtime=0))
 copy(CACHE/'core-candidate/legacy-replay-final.json','after/execution.json')
 for name in ('native-tests-final.log','python-tests-final.log','selected-build-final.log','isr-audit-final.log'):
  copy(CACHE/name,'validation/'+name)
 for source,name in ((CACHE/'selected-policy-final','target/policy'),(CACHE/'isr-audit-final','target/isr')):
  for p in source.rglob('*'):
   if p.is_file():copy(p,name+'/'+str(p.relative_to(source)))
 paths=set()
 for folder in ('firmware/include','firmware/main','firmware/tests','tools'):
  for p in (ROOT/folder).rglob('*'):
   if p.is_file() and p.suffix in ('.hpp','.h','.cpp','.py'):paths.add(p)
 paths.update((ROOT/'config/engine').rglob('*.json'))
 paths.update(ROOT/rel for rel in core['source_bindings'])
 for rel in ('firmware/platformio.ini','scripts/test_firmware.sh','scripts/generate_tuning_wire.py','scripts/audit_engine_build.py','scripts/audit_target_isr.py','scripts/publish_secondary_core_evidence.py','docs/engine-secondary-tables.md','docs/engine-feature-coverage.md','config/engine/defaults.json','hardware/a4-n16r8/net_contract.json','hardware/a5-idle-interface/net_contract.json'):
  paths.add(ROOT/rel)
 sources=[]
 for p in sorted(paths):
  rel=str(p.relative_to(ROOT));body=p.read_bytes();snapshot='sources/'+rel;write(snapshot,body);sources.append(dict(path=rel,snapshot=snapshot,sha256=sha(body)))
 copy(ROOT/'.gitattributes','source-metadata/root.gitattributes')
 sources.append(dict(path='.gitattributes',snapshot='source-metadata/root.gitattributes',sha256=sha((ROOT/'.gitattributes').read_bytes())))
 summary=dict(scope='secondary_core_foundation',operator_configurable=False,physical_qualification=False,baseline_commit=metadata['head'],speeduino_commit='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20',disabled_observations_sha256=sha(before),tests=dict(python=173,native_sanitizers=True,secondary=738,engine_secondary=148,allocation_failure_positions=4,selected_target_build=True),reviews=reviews,sources=sources)
 write('summary.json',(json.dumps(summary,indent=2)+'\n').encode())
 write('README.md',b'''# Secondary-table core foundation evidence

This packet proves scoped core progress. It does not establish an operator-ready secondary-table feature or full Speeduino equivalence. Schema7/own008 keep secondary tables Off. Versioned UI/configuration/tuning, coherent logs/radio, protected switch acquisition/accessory and new coupled plant comparisons remain pending. Engine/idle physical outputs remain inhibited.

The native sanitizer suite passes, including738 secondary-module checks,148 integrated-controller checks and four deliberate workspace-allocation failures. All173 existing Python tests pass. The selected N16R8 web target builds; linked policy and ISR-placement checks pass. Native lifetime/size checks and static images do not prove ESP32 runtime heap/stack, physical timing or electrical/engine behavior.

The same frozen probe produces7776 exactly identical disabled-path observations before/after, with source snapshots and raw compressed output retained. The earlier baseline's probe source is unchanged in this replay; the public helper only separates adjacent statements for strict compiler diagnostics. Independent architecture probes execute unchanged pinned-production Speeduino functions, not a whole coupled engine. Independent implementation/binding/allocation/legacy-wire review is archived under reviews.

Each review original manifest was fully verified before selection. selection.json identifies every archived original and its optional lossless CSV compression. Upstream vendor source snapshots and compiled executables/archives remain in the local review cache; their hashes and rebuild recipes remain recorded. Project source snapshots, probe source, result data and reports are archived. Do not mistake an original reviewer manifest for a claim that every cache artifact is redistributed here.

Run python3 tools/verify_secondary_core_evidence.py. Add --check-live-sources --check-index before committing this revision. Add --replay to rebuild both frozen/current disabled probes and three sanitized core/allocation tests from this packet; the replay requires a compatible compiler/libm and retains its receipts in .cache/engine/secondary/replays. Full regression reproduction: CXX=g++ CC=gcc sh scripts/test_firmware.sh and uv run --with fmpy==0.3.26 --with playwright python -m unittest discover -s tools -p 'test_*.py'. Browser workflows and actual tuning applications were not rerun for this core-only phase. No manufacturing/case/manual artifact changed.

See ../../../docs/engine-secondary-tables.md for the full remaining implementation gates.
''')
 entries=[]
 for p in sorted(OUT.rglob('*')):
  if p.is_file():
   body=p.read_bytes();entries.append(dict(path=str(p.relative_to(OUT)),bytes=len(body),sha256=sha(body)))
 write('artifact-manifest.json',(json.dumps({'scope':'secondary_core_foundation','artifacts':entries},indent=2)+'\n').encode())
 print(json.dumps({'artifacts':len(entries),'sources':len(sources),'reviews':reviews},indent=2))
if __name__=='__main__':main()
