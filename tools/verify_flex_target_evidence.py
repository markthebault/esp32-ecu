#!/usr/bin/env python3
"""Verify/replay frozen GPIO38 capture software evidence without any device."""
import argparse,gzip,hashlib,importlib.util,json,os,re,subprocess,sys,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/engine/flex-target-capture'
ENVS=('compact_n16r8_flex_dev','compact_n16r8_web','compact_a3_web','compact_a3_timing_bench')
REVIEW_REQUIRED=set('''firmware/include/ecu/capture_clock.hpp firmware/include/ecu/flex_ingress.hpp
firmware/include/ecu/flex_fuel.hpp firmware/include/ecu/flex_capture_owner.hpp
firmware/include/ecu/flex_capture_json.hpp firmware/include/ecu/flex_engine.hpp
firmware/include/ecu/flex_hardware.hpp firmware/include/ecu/engine.hpp
firmware/include/ecu/engine_target.hpp firmware/main/engine_target.cpp
firmware/main/engine_service.cpp web/flex_fuel_logic.js'''.split())
REQUIRED=REVIEW_REQUIRED|set('''scripts/audit_target_isr.py scripts/build_firmware_preserved.py
scripts/test_flex_target_service.py scripts/test_firmware.sh firmware/platformio.ini
firmware/tests/flex_capture_owner_test.cpp firmware/tests/flex_target_service_test.cpp
firmware/tests/target_fakes/fake_target.hpp firmware/main/web_assets.hpp
tools/test_flex_capture_ui.py tools/verify_flex_target_evidence.py web/index.html web/flex_fuel.js
hardware/flex-input/architecture.json config/interface-guide-development.json'''.split())

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def safe(name):
 p=Path(name);require(not p.is_absolute() and '..' not in p.parts,'Unsafe path');return p

def verify(report=REPORT,live=False,replay=False):
 report=report.resolve();manifest=read(report/'artifact-manifest.json');rows=manifest['artifacts']
 names={row['path'] for row in rows};require(len(names)==len(rows),'Duplicate artifact')
 paths=list(report.rglob('*'));require(not any(p.is_symlink() for p in paths),'Symlink artifact')
 actual={str(p.relative_to(report)) for p in paths if p.is_file() and p!=report/'artifact-manifest.json'}
 require(actual==names,'Artifact set differs')
 for row in rows:
  p=report/safe(row['path']);require(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Changed artifact: '+row['path'])
 s=read(report/'summary.json');require(s['scope']=='gpio38_target_capture_software' and s['checks_passed'] is True,'Scope/checks differ')
 require(s['target_capture_code'] is True,'Target implementation missing')
 for flag in ('protected_circuit','native_CAD','flashed','target_execution','physical_qualification','ethanol_chemistry_validated','full_speeduino_parity'):
  require(s[flag] is False,'Overstated qualification: '+flag)
 hashes=s['source_hashes'];require(REQUIRED<=set(hashes),'Missing execution source binding')
 for name,digest in hashes.items():
  require(sha(report/'sources'/safe(name))==digest,'Source snapshot differs: '+name)
  if live:require((ROOT/name).is_file() and sha(ROOT/name)==digest,'Live source differs: '+name)
 review=read(report/'reviews/independent/review.json')
 require(review['accepted'] is True and not review['open_findings'],'Independent acceptance missing')
 require(REVIEW_REQUIRED<=set(review['source_hashes']),'Independent critical source scope missing')
 for name,digest in review['source_hashes'].items():require(hashes.get(name)==digest,'Reviewed source differs: '+name)
 build=read(report/'build/summary.json')
 require(type(build['exit_code']) is int and build['exit_code']==0,'Build failed')
 for flag in ('source_inputs_unchanged','default_cache_retained','default_cache_unchanged','generation_only_declared_output'):
  require(build[flag] is True,'Build attestation failed: '+flag)
 require(set(build['environments'])==set(ENVS) and len(build['environments'])==4,'Build environment set')
 before=read(report/'build/sources-before.json');require(before==read(report/'build/sources-after.json'),'Compilation inputs changed')
 require({name for name in REQUIRED if name.split('/')[0] in ('firmware','web','scripts','config')}<=set(before),'Missing compile inputs')
 for name,digest in before.items():require(hashes.get(name)==digest,'Compilation source differs: '+name)
 require(read(report/'build/default-cache-before.json')==read(report/'build/default-cache-after.json'),'Default cache changed')
 require(set(build['declared_generation_changes'])<={'firmware/main/web_assets.hpp'},'Undeclared generation output')
 require(hashes['firmware/main/web_assets.hpp']==build['generated_assets_sha256'] and hashes['web/index.html']==build['web_index_sha256'],'Embedded source binding')
 architecture=read(report/'sources/hardware/flex-input/architecture.json')['implementation']
 require(architecture['target_producer'] is True and architecture['engine_outputs_enabled'] is False,'Architecture status')
 for flag in ('protected_input_circuit','native_cad','physical_qualification'):require(architecture[flag] is False,'Architecture overclaim')
 spec=importlib.util.spec_from_file_location('frozen_capture_build',report/'sources/scripts/build_firmware_preserved.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 artifacts={row['path']:row for row in build['artifacts']};archives={row['environment']:row for row in build['elf_archives']}
 require(set(archives)==set(ENVS),'Missing ELF archive')
 replay_root=ROOT/'.cache/engine'/('flex-capture-replay-'+uuid.uuid4().hex)
 if replay:replay_root.mkdir(parents=True,exist_ok=False)
 for env in ENVS:
  a=archives[env];archive=report/'build'/safe(a['path']);require(sha(archive)==a['sha256'] and archive.stat().st_size==a['bytes'],'ELF archive differs')
  raw=gzip.decompress(archive.read_bytes());digest=hashlib.sha256(raw).hexdigest()
  require(len(raw)==a['elf_bytes'] and digest==a['elf_sha256']==artifacts['build/'+env+'/firmware.elf']['sha256'],'Raw ELF differs')
  image=report/'build/images'/(env+'.bin');require(sha(image)==artifacts['build/'+env+'/firmware.bin']['sha256'] and image.stat().st_size<=2097152,'Binary/image limit differs')
  # Both complete HTML and the actual served flex script must occur in the
  # mapped flash data, rather than an ELF debug source string.
  elf=(replay_root/(env+'.elf')) if replay else report/'build'/safe(a['path'])
  if replay:elf.write_bytes(raw)
  else:
   import tempfile
   temporary=tempfile.NamedTemporaryFile(suffix='.elf');temporary.write(raw);temporary.flush();elf=Path(temporary.name)
  for source in ('web/index.html','web/flex_fuel.js'):
   require(helper.embedded_index(elf,(report/'sources'/source).read_bytes())==(env!='compact_a3_timing_bench'),'Mapped UI mismatch: '+source)
  if not replay:temporary.close()
  placement=read(report/'audits'/env/'isr/closure.json')
  require(placement['elf_sha256']==digest and placement['passed_static_placement'] is True and not placement['failures'] and not placement['floating_point_instructions'],'ISR placement/FPU differs')
  expected_roots=6 if env=='compact_n16r8_flex_dev' else 4 if env=='compact_a3_timing_bench' else 5
  require(len(placement['roots'])==expected_roots,'ISR root scope differs')
  policy=read(report/'audits'/env/'policy/audit.json')
  require(policy['passed'] is True and policy['elf_sha256']==digest and policy['binary_sha256']==sha(image),'Policy binary differs')
  require(policy['policy']==('gated_engine_dummy_loads_only' if env=='compact_a3_timing_bench' else 'engine_scheduler_physical_writes_compile_time_inhibited'),'Actuation policy differs')
  require(set(policy['source_sha256'])=={'firmware/platformio.ini','firmware/main/engine_target.cpp','firmware/main/app.cpp','firmware/include/ecu/pins.hpp','firmware/include/ecu/idle_hardware.hpp'},'Policy source scope differs')
  for name,value in policy['source_sha256'].items():require(hashes.get(name)==value,'Policy source differs')
  if env!='compact_a3_timing_bench':
   usb=read(report/'audits'/env/'usb.json');config=report/'build/sdkconfigs-after'/('sdkconfig.'+env)
   require(usb['elf_sha256']==digest and usb['binary_sha256']==sha(image) and usb['sdkconfig_sha256']==sha(config) and usb['exclusive_usb'] is True,'USB binding differs')
   require(hashes.get(usb['project_driver_source'])==usb['project_driver_sha256'],'USB driver source differs')
  if replay:
   with (replay_root/(env+'-isr.log')).open('xb') as log:
    subprocess.run([sys.executable,'-B',str(report/'sources/scripts/audit_target_isr.py'),str(elf),str(replay_root/(env+'-isr'))],stdout=log,stderr=subprocess.STDOUT,check=True)
 native=read(report/'native/summary.json');require(native['passed'] is True and len(native['runs'])==6 and all(r['returncode']==0 for r in native['runs']),'Actual-service native run failed')
 for mode in range(4):
  log=(report/'native'/('run-'+str(mode)+'.log')).read_text();require(re.search(r'flex_target_service_checks [1-9][0-9]* mode '+str(mode),log),'Native scenario log missing')
 require('flex_capture_owner_checks '+str(s['protocol_checks']) in (report/'validation/protocol.log').read_text(),'Protocol log differs')
 ui=read(report/'browser/capture/ui-tests.json');require(ui['passed'] is True and not ui['page_errors'],'Browser check failed')
 require(set(ui['fixture_sha256'])=={p.name for p in (report/'native/fixtures-0').glob('*.json')},'Browser fixture scope differs')
 require(set(ui['source_sha256'])=={'web/index.html','web/flex_fuel.js','web/flex_fuel_logic.js','tools/test_flex_capture_ui.py'},'Browser source scope differs')
 for name,value in ui['fixture_sha256'].items():require(sha(report/'native/fixtures-0'/safe(name))==value,'Browser fixture differs')
 for name,value in ui['source_sha256'].items():require(hashes.get(name)==value,'Browser source differs')
 plant=read(report/'plant/index.json');require(plant['passed'] is True and not plant['failures'] and len(plant['cases'])==27,'Fixed-gasoline plant run failed')
 if replay:
  sources=report/'sources';cjson=report/'dependencies/cJSON';flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
  commands=[['cc',*flags,'-c',str(cjson/'cJSON.c'),'-o',str(replay_root/'cjson.o')],
   ['g++','-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-I',str(sources/'firmware/include'),str(sources/'firmware/tests/flex_capture_owner_test.cpp'),'-o',str(replay_root/'protocol')],
   [str(replay_root/'protocol')],
   ['g++','-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-pthread','-DECU_COMPACT_A3=1','-DECU_SELECTED_N16R8=1','-DECU_FLEX_G38_DRAFT=1','-I',str(cjson),'-I',str(sources/'firmware/tests/target_fakes'),'-I',str(sources/'firmware/include'),str(sources/'firmware/tests/flex_target_service_test.cpp'),str(replay_root/'cjson.o'),'-o',str(replay_root/'service')]]
  for mode in range(4):
   fixtures=replay_root/('fixtures-'+str(mode));fixtures.mkdir();commands.append([str(replay_root/'service'),str(fixtures),str(mode)])
  for n,command in enumerate(commands):
   with (replay_root/(str(n)+'.log')).open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
  for mode in range(4):
   frozen=report/'native'/('fixtures-'+str(mode));produced=replay_root/('fixtures-'+str(mode))
   require({p.name for p in frozen.glob('*.json')}=={p.name for p in produced.glob('*.json')},'Replay fixture scope differs')
   for original in frozen.glob('*.json'):require(read(original)==read(produced/original.name),'Replayed actual-service fixture differs: '+original.name)
  (replay_root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 print(json.dumps(dict(passed=True,artifacts=len(rows),sources=len(hashes),replay_output=str(replay_root) if replay else None,qualification='Native/API-model and static compiled evidence only; protected circuitry, target execution/HIL, chemistry and full parity remain open')))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--replay',action='store_true');a=p.parse_args();verify(a.report,a.check_live_sources,a.replay)
