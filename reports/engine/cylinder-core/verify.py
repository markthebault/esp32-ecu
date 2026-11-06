#!/usr/bin/env python3
"""Publish the internal cylinder-core checkpoint without extending its scope."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/'.cache/engine/cylinder-profiles-001'
SUITE=ROOT/'.cache/engine/cylinder-core-final-001'
TARGET=ROOT/'.cache/engine/cylinder-target-001'
REVIEW=ROOT/'.cache/engine/cylinder-core-review-001'
ARCHITECTURE=ROOT/'.cache/engine/cylinder-architecture-review-001'

def read(path):return json.loads(path.read_text())
def sha(body):return hashlib.sha256(body).hexdigest()
def safe(name):
 path=PurePosixPath(name)
 assert not path.is_absolute() and '..' not in path.parts
 return path.as_posix()

def verify(output,repo=None):
 manifest=read(output/'manifest.json');expected={row['path']:row for row in manifest['files']}
 assert len(expected)==len(manifest['files']) and not any(p.is_symlink() for p in output.rglob('*'))
 assert {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}==set(expected)|{'manifest.json'}
 for name,row in expected.items():
  body=(output/safe(name)).read_bytes();assert len(body)==row['bytes'] and sha(body)==row['sha256'],name
 payload_count=0
 for item in manifest['archives']:
  rows={row['path']:row for row in item['payloads']};assert len(rows)==len(item['payloads'])
  with tarfile.open(output/safe(item['path']),'r:gz') as stream:
   members=stream.getmembers();assert len(members)==len(rows) and {m.name for m in members}==set(rows)
   for member in members:
    assert member.isfile() and safe(member.name)==member.name
    body=stream.extractfile(member).read();row=rows[member.name]
    assert len(body)==row['bytes'] and sha(body)==row['sha256'],member.name
  payload_count+=len(rows)
 summary=read(output/'summary.json')
 assert summary['public_cylinder_support']==[4] and not summary['goal_complete'] and not summary['physical_operation_verified']
 assert not summary['expanded_public_integration_complete'] and not summary['generalized_engine_plant_verified']
 if repo:
  for name,value in summary['source_hashes'].items():assert sha((repo/safe(name)).read_bytes())==value,name
 return dict(passed=True,archives=len(manifest['archives']),payloads=payload_count,live_sources_checked=bool(repo))

def package(output):
 summary=read(MATRIX/'summary.json');review=read(REVIEW/'assessment.json')
 assert summary['kernel_cases_passed']==1296 and summary['legacy_samples_identical']==7776
 assert summary['reference_profiles_observed']==24
 assert review['accepted'] and not review['open_findings']
 assert read(SUITE/'suite-result.json')['exit_code']==0
 for name in ('public-boundary-tests','tuning-tests'):assert read(SUITE/(name+'.json'))['exit_code']==0
 builds=read(TARGET/'build-result.json');assert builds['exit_code']==0 and builds['source_headers_unchanged'] and not builds['flashed']
 target_rows=[]
 for env in builds['environments']:
  isr=read(TARGET/'isr'/env/'closure.json');policy=read(TARGET/'policy'/env/'policy/audit.json');usb=read(TARGET/'policy'/env/'usb.json')
  assert isr['passed_static_placement'] and policy['passed'] and usb['exclusive_usb']
  assert policy['policy']=='engine_scheduler_physical_writes_compile_time_inhibited'
  assert isr['elf_sha256']==policy['elf_sha256']==usb['elf_sha256']
  assert sha((TARGET/'pio-build'/env/'firmware.bin').read_bytes())==policy['binary_sha256']
  assert sha((TARGET/'pio-build'/env/'firmware.elf').read_bytes())==policy['elf_sha256']
  target_rows.append(dict(environment=env,elf_sha256=policy['elf_sha256'],binary_sha256=policy['binary_sha256'],
                          image_bytes=policy['app_image_bytes'],physical_outputs_inhibited=True,static_isr_passed=True,exclusive_usb=True))
 output.mkdir(parents=True,exist_ok=False);archives=[]
 def archive(filename,items):
  rows=[];seen=set()
  with (output/filename).open('xb') as raw,gzip.GzipFile(fileobj=raw,filename='',mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as stream:
   for name,path in sorted(items):
    name=safe(name);assert name not in seen and path.is_file() and not path.is_symlink();seen.add(name)
    body=path.read_bytes();assert not body.startswith(b'\x7fELF'),name
    info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o644;info.mtime=0
    stream.addfile(info,io.BytesIO(body));rows.append(dict(path=name,bytes=len(body),sha256=sha(body)))
  archives.append(dict(path=filename,payloads=rows))
 items=[]
 for path in MATRIX.iterdir():
  if path.is_file() and path.suffix in ('.json','.jsonl','.txt','.log'):items.append((path.name,path))
 for folder in ('before','current-source'):
  for path in (MATRIX/folder).rglob('*'):
   if path.is_file():items.append((path.relative_to(MATRIX).as_posix(),path))
 for path in SUITE.iterdir():
  if path.is_file() and path.suffix in ('.json','.log'):items.append(('suite/'+path.name,path))
 for path in (ROOT/'.cache/engine/cylinder-reference-001').glob('command-*.log'):items.append(('reference-build/'+path.name,path))
 archive('core-and-reference.tar.gz',items)
 items=[]
 for prefix,directory,filename in [('architecture',ARCHITECTURE,'final-whitelist.json'),('implementation',REVIEW,'whitelist.json')]:
  whitelist=read(directory/filename)
  for row in whitelist['files']:
   path=directory/safe(row['path']);body=path.read_bytes()
   assert len(body)==row['bytes'] and sha(body)==row['sha256'],path
   items.append((prefix+'/'+row['path'],path))
  if not any(row['path']==filename for row in whitelist['files']):items.append((prefix+'/'+filename,directory/filename))
 archive('independent-reviews.tar.gz',items)
 items=[]
 for path in TARGET.iterdir():
  if path.is_file() and path.suffix in ('.json','.log'):items.append((path.name,path))
 for folder in ('isr','policy'):
  for path in (TARGET/folder).rglob('*'):
   if path.is_file():items.append((path.relative_to(TARGET).as_posix(),path))
 archive('target-receipts.tar.gz',items)
 extras=['.gitattributes','docs/engine-cylinder-profiles.md','docs/engine-feature-coverage.md','tools/package_cylinder_core.py',
         'scripts/audit_target_isr.py','scripts/audit_engine_build.py','scripts/audit_tuning_build.py','scripts/build_speeduino_flex.py']
 summary['source_hashes'].update({name:sha((ROOT/name).read_bytes()) for name in extras})
 archive('publication-sources.tar.gz',[(name,ROOT/name) for name in extras])
 summary.update(independent_assessment=review,target_builds=target_rows,full_sanitized_suite_passed=True,
                public_boundary_tests=3,tuning_tests=13,flashed=False,
                archived_target_scope='Build logs, static closure/disassembly and policy/USB receipts; ELF/bin remain in the owned local cache.')
 (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');shutil.copyfile(Path(__file__),output/'verify.py')
 (output/'README.md').write_text('''# Internal cylinder-core checkpoint

The shared internal capacity-eight core executes1..8 even-fire four-stroke profiles. Public tune/browser/USB/radio/target interfaces and the PCB remain four-cylinder. This packet does not complete that feature or the wider ECU goal.

- 1296 motored timing cases pass across counts, strategies, orders, wheels, speed and closing angle. Maximum observed spark phase error0.07°; injector phase error2.115°, within the declared integer-capture/locked-closing-edge bounds. No sub-degree injector or physical timing claim.
- 7776 exact F64 four-cylinder controller observations match commit cdbd534. This is the stated legacy path, not every possible tune.
- 24 actual production Speeduino setup profiles disclose effective modes and schedule geometry. No shaft, sixteen-output GPIO or engine-plant execution is claimed for this new reference probe.
- Full sanitized firmware suite,3 public-boundary tests and13 tuning tests pass. Three fresh inhibited firmware builds pass ISR placement, linked policy and USB ownership checks. No target was connected or flashed.
- Independent review reproduces the original removed-cylinder ghost-edge fault and accepts the corrected configuration fence and core scope. Original failure evidence is preserved. Expanded public/UI/telemetry/target/hardware and generalized engine plants remain open.

[Design, limits and remaining integration](../../../docs/engine-cylinder-profiles.md) · [Summary](summary.json)

Archives contain sources, before/after raw observations, motored measurements, production setup readbacks, immutable reviewer-selected evidence and target build/static receipts. Target ELF/bin and upstream application/library binaries are excluded. Actual local target images are bound by SHA256 in the receipts.

```sh
python3 reports/engine/cylinder-core/verify.py --verify-only --output reports/engine/cylinder-core
```

Add `--repo .` only while live source bytes match this checkpoint. Integrity verification does not rerun the tests or establish physical/engine acceptance. Reproduction uses scripts/test_firmware.sh, scripts/build_speeduino_cylinder_geometry.py and tools/run_engine_profiles.py with the pinned native dependencies described in the design guide.
''')
 files=[dict(path=path.relative_to(output).as_posix(),bytes=path.stat().st_size,sha256=sha(path.read_bytes())) for path in sorted(output.iterdir()) if path.is_file()]
 (output/'manifest.json').write_text(json.dumps(dict(files=files,archives=archives),indent=2)+'\n')
 print(json.dumps(verify(output,ROOT)))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--verify-only',action='store_true');parser.add_argument('--repo',type=Path);args=parser.parse_args()
 if args.verify_only:print(json.dumps(verify(args.output.resolve(),args.repo.resolve() if args.repo else None)))
 else:package(args.output.resolve())
