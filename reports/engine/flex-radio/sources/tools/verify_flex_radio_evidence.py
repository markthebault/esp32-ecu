#!/usr/bin/env python3
"""Verify/replay frozen coherent flex-radio software evidence without a device."""
import argparse,gzip,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/engine/flex-radio'
ENVS=('compact_n16r8_flex_dev','compact_n16r8_web','compact_a3_web','compact_a3_timing_bench')
CRITICAL=set('''config/engine-radio-v5.json firmware/include/ecu/engine_radio.hpp
firmware/include/ecu/engine_radio_flex.hpp firmware/include/ecu/engine_radio_health.hpp
firmware/include/ecu/espnow_protocol.hpp firmware/include/ecu/flex_engine.hpp
firmware/include/ecu/flex_runtime.hpp firmware/include/ecu/flex_runtime_json.hpp
firmware/include/ecu/engine_data_json.hpp firmware/main/espnow.cpp
firmware/tests/engine_radio_flex_test.cpp firmware/tests/radio_service_test.cpp
scripts/test_radio_service.py tools/engine_observability.py
tools/engine_observability_bridge.cpp tools/engine_receiver.py tools/flex_radio.py
tools/radio_simulator.py tools/test_flex_radio.py web/index.html'''.split())

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def safe(name):
 p=Path(name);require(not p.is_absolute() and '..' not in p.parts,'Unsafe artifact path');return p
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def verify(report=REPORT,live=False,replay=False):
 report=report.resolve();rows=read(report/'artifact-manifest.json')['artifacts'];names={r['path'] for r in rows}
 require(len(names)==len(rows),'Duplicate artifact')
 paths=list(report.rglob('*'));require(not any(p.is_symlink() for p in paths),'Symlink artifact')
 actual={str(p.relative_to(report)) for p in paths if p.is_file() and p!=report/'artifact-manifest.json'}
 require(actual==names,'Artifact set differs')
 for row in rows:
  p=report/safe(row['path']);require(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Changed artifact: '+row['path'])
 s=read(report/'summary.json');require(s['scope']=='coherent_flex_radio_software' and s['checks_passed'] is True,'Scope/checks differ')
 for flag in ('flashed','target_execution','actual_RF','screen_application','physical_qualification','ethanol_chemistry_validated','new_production_speeduino_comparison','full_speeduino_parity'):
  require(s[flag] is False,'Overstated qualification: '+flag)
 hashes=s['source_hashes'];require(CRITICAL<=set(hashes),'Missing critical execution source')
 for name,digest in hashes.items():
  require(sha(report/'sources'/safe(name))==digest,'Source snapshot differs: '+name)
  if live:require((ROOT/name).is_file() and sha(ROOT/name)==digest,'Live source differs: '+name)
 reviews=report/'reviews/independent';review=read(reviews/'review.json');update=read(reviews/'review-ui-recheck.json')
 for record in (review,update):require(record['accepted'] is True and record['open_findings']==[],'Independent acceptance missing')
 require(update['supersession']['previous_review_sha256']==sha(reviews/'review.json'),'Review supersession differs')
 effective={**review['source_hashes'],**update['source_hashes']};require(CRITICAL<=set(effective),'Independent critical scope missing')
 for name,digest in effective.items():require(hashes.get(name)==digest,'Reviewed source differs: '+name)
 for name,digest in review['evidence_hashes'].items():require(sha(reviews/safe(name))==digest,'Reviewer evidence differs: '+name)
 legacy=read(reviews/'legacy-comparison-001.json')
 require(legacy['accepted'] is True and legacy['vectors']==417 and legacy['byte_captures_equal'] is True and legacy['each_legacy_required_flex_gate_checked'] is True,'Legacy preservation differs')
 require(sha(reviews/'legacy-wire-002.bin')==sha(reviews/'legacy-wire-003.bin')==legacy['capture_sha256'],'Legacy bytes differ')
 contract=read(report/'sources/config/engine-radio-v5.json')
 require(contract['schema']==5 and contract['max_datagram_bytes']==250 and contract['base']['bytes']==250 and contract['flex']['bytes']==232,'Wire contract differs')
 require(contract['sender']['pending_pairs_per_peer']==1 and contract['receiver']['pending_pairs']==2,'Buffer scope differs')
 require(contract['receiver']['partial_data_is_observation'] is False and contract['receiver']['partial_data_refreshes_gap_or_ack'] is False,'Partial qualification differs')
 build=read(report/'build/summary.json');require(type(build['exit_code']) is int and build['exit_code']==0,'Build failed')
 for flag in ('source_inputs_unchanged','default_cache_retained','default_cache_unchanged','generation_only_declared_output'):require(build[flag] is True,'Build attestation failed: '+flag)
 require(set(build['environments'])==set(ENVS) and len(build['environments'])==4,'Build environment set')
 before=read(report/'build/sources-before.json');require(before==read(report/'build/sources-after.json'),'Compilation inputs changed')
 for name,digest in before.items():require(hashes.get(name)==digest,'Compilation source differs: '+name)
 require(read(report/'build/default-cache-before.json')==read(report/'build/default-cache-after.json'),'Default cache changed')
 require(set(build['declared_generation_changes'])<={'firmware/main/web_assets.hpp'},'Undeclared asset generation')
 require(hashes['firmware/main/web_assets.hpp']==build['generated_assets_sha256'] and hashes['web/index.html']==build['web_index_sha256'],'Embedded source binding')
 artifacts={r['path']:r for r in build['artifacts']};archives={r['environment']:r for r in build['elf_archives']}
 require(set(archives)==set(ENVS),'ELF archive set differs')
 helper=module('frozen_radio_build',report/'sources/scripts/build_firmware_preserved.py')
 replay_root=ROOT/'.cache/engine'/('flex-radio-replay-'+uuid.uuid4().hex)
 if replay:replay_root.mkdir(parents=True,exist_ok=False)
 for env in ENVS:
  a=archives[env];archive=report/'build'/safe(a['path']);require(sha(archive)==a['sha256'] and archive.stat().st_size==a['bytes'],'ELF archive differs')
  raw=gzip.decompress(archive.read_bytes());digest=hashlib.sha256(raw).hexdigest()
  require(len(raw)==a['elf_bytes'] and digest==a['elf_sha256']==artifacts['build/'+env+'/firmware.elf']['sha256'],'Raw ELF differs')
  image=report/'build/images'/(env+'.bin');require(sha(image)==artifacts['build/'+env+'/firmware.bin']['sha256'] and image.stat().st_size<=2097152,'Image differs/too large')
  with tempfile.NamedTemporaryFile(suffix='.elf') as temporary:
   temporary.write(raw);temporary.flush()
   require(helper.embedded_index(Path(temporary.name),(report/'sources/web/index.html').read_bytes())==(env!='compact_a3_timing_bench'),'Mapped HTML differs')
  placement=read(report/'audits'/env/'isr/closure.json')
  require(placement['elf_sha256']==digest and placement['passed_static_placement'] is True and placement['failures']==[] and placement['floating_point_instructions']==[],'ISR audit failed')
  require(len(placement['roots'])==(6 if env=='compact_n16r8_flex_dev' else 4 if env=='compact_a3_timing_bench' else 5),'ISR root scope differs')
  policy=read(report/'audits'/env/'policy/audit.json')
  require(policy['passed'] is True and policy['elf_sha256']==digest and policy['binary_sha256']==sha(image),'Policy binding differs')
  require(policy['policy']==('gated_engine_dummy_loads_only' if env=='compact_a3_timing_bench' else 'engine_scheduler_physical_writes_compile_time_inhibited'),'Actuation policy differs')
  for name,value in policy['source_sha256'].items():require(hashes.get(name)==value,'Policy source differs')
  if env!='compact_a3_timing_bench':
   usb=read(report/'audits'/env/'usb.json');config=report/'build/sdkconfigs-after'/('sdkconfig.'+env)
   require(usb['elf_sha256']==digest and usb['binary_sha256']==sha(image) and usb['sdkconfig_sha256']==sha(config) and usb['exclusive_usb'] is True,'USB ownership differs')
   require(hashes.get(usb['project_driver_source'])==usb['project_driver_sha256'],'USB source differs')
  if replay:
   elf=replay_root/(env+'.elf');elf.write_bytes(raw)
   with (replay_root/(env+'-isr.log')).open('xb') as log:subprocess.run([sys.executable,'-B',str(report/'sources/scripts/audit_target_isr.py'),str(elf),str(replay_root/(env+'-isr'))],stdout=log,stderr=subprocess.STDOUT,check=True)
 adapters=read(report/'audits/adapters.json')
 for row in adapters['adapters']:
  original=report/'sources'/safe(row['source']);adapted=report/'audits'/Path(row['source']).name
  require(sha(original)==row['original_sha256'] and sha(adapted)==row['adapter_sha256'],'Audit adapter source differs')
  require(original.read_text().count(row['old'])==row['occurrences']==1 and original.read_text().replace(row['old'],row['new'])==adapted.read_text(),'Adapter changed audit logic')
 native=read(report/'native/summary.json');require(native['passed'] is True and all(x['returncode']==0 for x in native['runs']),'Actual-source native run failed')
 require(len(native['runs'])==3 and '81' in (report/'native/2.log').read_text(),'Native service checks differ')
 partial=read(report/'native/partial.json')['peers'][0];complete=read(report/'native/complete.json')['peers'][0]
 require(partial['connected'] is True and partial['engine_connected'] is False and partial['engine_pair_pending'] is True and partial['engine_base_submitted'] is True,'Partial ACK labeling differs')
 require(complete['engine_connected'] is True and complete['engine_pair_pending'] is False,'Complete ACK labeling differs')
 require(read(report/'native/engine-ack-missing.json')['peers'][0]['engine_connected'] is False,'Family ACK fault differs')
 for name in ('held-expired','engine-ack-missing'):require(read(report/'native'/(name+'.json'))['led']=='red_blink','Fault policy differs')
 interop=read(report/'validation/sender-receiver.json')
 require(interop['passed'] is True and interop['decoded']['complete_observation'] is True and interop['decoded']['flex_fuel']['ethanol_pct']==50,'Causal frame interpretation differs')
 require(interop['decoded']['flex_sample_age_ms']==30 and interop['status_at_380_ms']['flex_value_qualified'] is False and interop['status_at_380_ms']['fresh'] is True,'Independent raw expiry differs')
 browser=read(report/'browser/radio/ui-tests.json');require(browser['passed'] is True and browser['page_errors']==[] and len(browser['checks'])>=8,'Browser checks failed')
 for name,digest in browser['source_sha256'].items():require(hashes.get(name)==digest,'Browser source differs')
 for name,digest in browser['fixture_sha256'].items():require(sha(report/'native'/safe(name))==digest,'Browser fixture differs')
 plant=read(report/'plant/index.json');require(plant['passed'] is True and plant['failures']==[] and len(plant['cases'])==27,'Plant matrix differs')
 for name,digest in plant['source_sha256'].items():require(hashes.get(name)==digest,'Plant source differs')
 require(all(c['neutral_off_same_virtual_edges'] and c['neutral_off_final_rpm_delta']==0 and c['neutral_off_fuel_mg_delta']==0 for c in plant['cases'] if c['case']=='neutral'),'Neutral causal control differs')
 if replay:
  # All generated native libraries, coverage and test outputs belong to the new
  # replay root. Frozen report files are never used as a writable checkout.
  sources=replay_root/'project';shutil.copytree(report/'sources',sources)
  cjson=report/'dependencies/cJSON';flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
  sdk=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
  for name in ('cJSON.c','cJSON.h'):require(sha(sdk/name)==sha(cjson/name),'Installed cJSON differs from frozen Python bridge dependency')
  fixtures=replay_root/'fixtures';fixtures.mkdir()
  commands=[['cc',*flags,'-c',str(cjson/'cJSON.c'),'-o',str(replay_root/'cjson.o')],
   ['g++','-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-I',str(sources/'firmware/include'),str(sources/'firmware/tests/engine_radio_flex_test.cpp'),'-o',str(replay_root/'pair')],
   [str(replay_root/'pair')],
   ['g++','-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-pthread','-DECU_COMPACT_A3=1','-DECU_SELECTED_N16R8=1','-DECU_FLEX_G38_DRAFT=1','-I',str(cjson),'-I',str(sources/'firmware/tests/radio_fakes'),'-I',str(sources/'firmware/tests/target_fakes'),'-I',str(sources/'firmware/include'),str(sources/'firmware/tests/radio_service_test.cpp'),str(replay_root/'cjson.o'),'-lcrypto','-o',str(replay_root/'service')],
   [str(replay_root/'service'),str(fixtures)],
   [sys.executable,'-B',str(sources/'tools/check_radio_service_fixtures.py'),str(fixtures),str(replay_root/'interop.json')],
   [sys.executable,'-B','-m','unittest','test_flex_radio','test_engine_observability','test_load_radio','test_secondary_radio']]
  environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GCOV_PREFIX':str(replay_root/'gcov'),'PYTHONPATH':str(sources/'tools')}
  receipts=[]
  for n,command in enumerate(commands):
   with (replay_root/(str(n)+'.log')).open('xb') as log:result=subprocess.run(command,cwd=sources,env=environment,stdout=log,stderr=subprocess.STDOUT)
   receipts.append(dict(command=command,returncode=result.returncode));(replay_root/'commands.json').write_text(json.dumps(receipts,indent=2)+'\n')
   require(result.returncode==0,'Frozen replay failed: '+str(replay_root/(str(n)+'.log')))
  expected={p.name for p in (report/'native').glob('*.bin')};require(expected=={p.name for p in fixtures.glob('*.bin')},'Replayed frame set differs')
  for name in expected:require(sha(report/'native'/name)==sha(fixtures/name),'Replayed wire bytes differ: '+name)
  for name in ('partial','complete','engine-ack-missing','held-expired'):require(read(report/'native'/(name+'.json'))==read(fixtures/(name+'.json')),'Replayed service readback differs')
  require(read(replay_root/'interop.json')==interop,'Replayed receiver interpretation differs')
 print(json.dumps(dict(passed=True,artifacts=len(rows),sources=len(hashes),independent_paths=len(effective),replay_output=str(replay_root) if replay else None,qualification='Native API models, fixed-gasoline SIL and static linked evidence only; actual target/RF/screen/hardware and full parity remain open')))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--replay',action='store_true');a=p.parse_args();verify(a.report,a.check_live_sources,a.replay)
