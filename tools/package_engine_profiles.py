#!/usr/bin/env python3
"""Publish the source-bound public-cylinder development packet; no vendor apps."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.cache/engine'
SAFE={'.json','.py','.cpp','.hpp','.h','.mo','.log','.txt','.md','.ini','.msq','.msl','.bin','.csv','.png','.gz','.sh'}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())

def main(output):
 output=output.resolve();assert not output.exists(),'Choose a new output directory'
 groups={name:{} for name in ('sources','validation','plants','applications')}
 def add(group,source,destination):
  source=Path(source);assert source.is_file(),source
  destination=str(destination);assert not destination.startswith('/') and '..' not in Path(destination).parts
  assert destination not in groups[group],destination
  groups[group][destination]=source
 def tree(group,base,prefix,suffixes=SAFE):
  for path in sorted(base.rglob('*')):
   if path.is_file() and path.suffix in suffixes:add(group,path,Path(prefix)/path.relative_to(base))
 sources=read(CACHE/'cylinder-public-packet-001/owned-sources.json')
 sources=sorted(set(sources)|{'tools/package_engine_profiles.py'})
 for name in sources:add('sources',ROOT/name,name)
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 assert head=='5c132ee6c08e135343cc904aae4d3754204ec699','Packet is an overlay on its declared baseline'
 matrix=CACHE/'profile-plants-004';m=read(matrix/'summary.json');assert m['passed'] and m['tests']==9 and len(m['results'])==53
 for name,value in m['source_sha256'].items():assert sha(ROOT/name)==value,('Matrix source changed',name)
 tree('plants',matrix,'matrix');add('plants',CACHE/'profile-plants-004.log','matrix-run.log')
 # The plant reviewer publishes source identities rather than an artifact
 # allowlist. Its evidence directory contains only probes/results from this
 # review; no app, physical acquisition or private fixture is included.
 plant=CACHE/'cylinder-plant-review-001';assert read(plant/'assessment.json')['open_findings']==[]
 tree('plants',plant,'independent-review')
 for label in ('cylinder-public-contract-review','cylinder-radio-review','cylinder-app-review'):
  base=CACHE/(label+'-001');assert read(base/'assessment.json')['open_findings']==[]
  whitelist=read(base/'whitelist.json')
  for item in whitelist['files']:
   source=base/item['path'];assert source.stat().st_size==item['bytes'] and sha(source)==item['sha256'],source
   if source.suffix not in SAFE:continue
   add('applications' if 'app-review' in label else 'validation',source,Path(label)/item['path'])
  add('applications' if 'app-review' in label else 'validation',base/'whitelist.json',Path(label)/'whitelist.json')
 tree('validation',CACHE/'cylinder-target-audit-001','target-static-audits')
 tree('validation',CACHE/'cylinder-memory-001','memory-format')
 add('validation',CACHE/'cylinder-public-packet-001/generators.json','generated-source-parity.json')
 tree('validation',CACHE/'cylinder-radio-service-001','sender-service',{'.json','.bin','.log'})
 assert read(CACHE/'cylinder-radio-service-001/summary.json')['passed']
 assert read(CACHE/'cylinder-radio-service-001/receiver.json')['passed']
 for name in ('cylinder-ui-profiles-003','cylinder-ui-tuning-001','cylinder-ui-logger-002','cylinder-ui-radio-001','cylinder-ui-cylinder-regression-004','cylinder-ui-sequential-regression-001','cylinder-ui-semi-regression-001','cylinder-ui-boost-regression-001'):
  base=CACHE/name;report=read(base/('sequential-ui-tests.json' if 'ui-sequential-' in name else 'ui-tests.json'));assert report['passed'],name
  tree('applications',base,'browser/'+name)
 required=['cylinder-firmware-004.log','cylinder-target-build-001.log','cylinder-tuning-suite-001.log','cylinder-boundaries-001.log','cylinder-radio7-tests-001.log']
 required += ['cylinder-regression-'+name+'-'+run+'.log' for name,run in (('engine','001'),('cyl','001'),('seq','001'),('semi','001'),('obs','001'),('flex','002'),('boost','003'),('idle','003'),('load_model','002'),('secondary_model','002'),('transient','002'),('boost_radio','001'),('flex_radio','001'))]
 for name in required:
  text=(CACHE/name).read_text();assert 'FAILED (' not in text and 'Aborted' not in text and 'Traceback' not in text,name
  assert ('OK' in text or '3 succeeded' in text or '"passed": true' in text),name
  add('validation',CACHE/name,'runs/'+name)
 # Task-service fixtures are written into fresh timestamped paths by the
 # full suite. Include only its explicit terminal summary/commands/logs.
 import re
 full=(CACHE/'cylinder-firmware-004.log').read_text()
 assert 'All16 sparse engine outputs executed' in full
 for line in full.splitlines():
  if line.startswith('{"passed": true, "output": '):
   item=json.loads(line);base=Path(item['output']);assert base.parent==CACHE and read(base/'summary.json')['passed']
   tree('validation',base,'full-suite-services/'+base.name,{'.json','.log','.bin'})
 for name in ('compact_a3_web','compact_n16r8_web','compact_n16r8_flex_dev'):
  base=CACHE/'cylinder-target-build-001'/name
  for leaf in ('firmware.elf','firmware.bin'):assert (base/leaf).is_file()
 identities={p:dict(bytes=(ROOT/p).stat().st_size,sha256=sha(ROOT/p)) for p in sources}
 manifest=dict(status='reviewed_development_checkpoint_goal_still_active',baseline_commit=head,
  formats=dict(tune_schema=11,own_identity='ESP32ECU DEV 012 INHIBITED',coherent_data_schema=3,screen_schema=7,engine_msl_columns=265,direct_sil_columns=245),
  software_cylinders=[1,8],fitted_injector_commands=4,fitted_coil_commands=4,
  engine_outputs_inhibited=True,physical_operation_verified=False,goal_complete=False,
  scope='1..8 even-fire logical software profiles, coupled project research plants and read-only tuning/diagnostics; expanded genuine Speeduino/turbo comparison and hardware remain open',
  source_identities=identities,archives={})
 output.mkdir(parents=True,exist_ok=False)
 for group,files in groups.items():
  destination=output/(group+'.zip')
  with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
   for name,source in sorted(files.items()):archive.write(source,name)
  # Reopen each archive and compare every payload byte with its source.
  with zipfile.ZipFile(destination) as archive:
   assert archive.testzip() is None and set(archive.namelist())==set(files)
   payloads={name:dict(bytes=source.stat().st_size,sha256=sha(source)) for name,source in sorted(files.items())}
   for name,identity in payloads.items():assert hashlib.sha256(archive.read(name)).hexdigest()==identity['sha256']
  manifest['archives'][group]=dict(file=destination.name,bytes=destination.stat().st_size,sha256=sha(destination),payloads=payloads)
 (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (output/'README.md').write_text('''# Public cylinder integration development packet

Tune schema11 / own012, coherent data3, screen schema7 and MSL009 add1..8 logical cylinders to configuration, virtual execution, UI, tuning and debugging. The existing PCB has4 injector and4 coil commands. All normal images inhibit engine outputs; physical qualification and the full Speeduino goal remain unfinished.

- `sources.zip`: current source overlay on commit5c132ee, with per-file identities in the manifest. Apply only to a separate checkout; preserve existing work.
- `validation.zip`: sanitized firmware/regression results, shared-codec/CAS/legacy probes, independent radio checks, actual sender API-model bytes/replay, linked static audits and memory/formatter checks.
- `plants.zip`:53 raw cases,9 coupled/geometry/log tests and independent plant evidence. The48 normal cases cover1..8 cylinders in all3 modes on two uncalibrated plants. Wrong-order/reference and fault controls retain fixed physical geometry. No expanded Speeduino engine-run or turbo result is claimed.
- `applications.zip`: actual own012 TunerStudio C8 edits/page-byte validation, MegaLogViewer009 field plots, current Chrome checks and reviewer closure receipts. Proprietary executables, user profiles, registration and copied vendor projects are excluded.

Reproduce in the pinned Linux workspace with `CXX=g++ CC=gcc sh scripts/test_firmware.sh`, `python3 tools/test_engine_profile_boundaries.py`, `python3 tools/test_cylinder_radio.py`, and `uv run --with fmpy==0.3.26 python tools/test_engine_profile_plants.py --output NEW-DIRECTORY`. Build the separate profile FMU first with `python3 scripts/build_engine_airpath.py --profiles`; prerequisites/pins are documented in the repository's research-benchmark guide. Chrome scripts require Playwright and the installed Chrome. Vendor applications require their separate unmodified installations and fresh owned profiles.

The4-part sender replay is a deterministic SDK API model, not RF or RTOS measurement. Target audits prove linked source/layout/policy properties, not runtime heap/stack, timer latency or physical behavior. Own012 offline editing is verified; supported online onboarding remains unresolved. Known derived-AFR/unknown-lambda viewer caveats remain. No device was connected or flashed, and no vendor message was sent.

Remaining: distinct16-output genuine Speeduino fixture and generalized coupled comparison; matching turbo geometry; additional protected PCB drivers/connectors/enclosure; target/HIL, electrical/environment/fit tests; online vendor integration and the broader control/trigger/configuration/debug feature gaps.
''')
 print(json.dumps(dict(output=str(output),archives={key:dict(bytes=value['bytes'],files=len(value['payloads'])) for key,value in manifest['archives'].items()})))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();main(args.output)
