#!/usr/bin/env python3
"""Verify immutable secondary software evidence; optionally replay frozen C++."""
import argparse,csv,gzip,hashlib,io,json,subprocess,tarfile,uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/engine/secondary-integration'
def sha(body):return hashlib.sha256(body).hexdigest()
def read_json(path):return json.loads(path.read_text())
def verify(live=False,index=False,replay=False):
 manifest=read_json(REPORT/'artifact-manifest.json')
 if index:assert subprocess.check_output(['git','show',':'+str((REPORT/'artifact-manifest.json').relative_to(ROOT))],cwd=ROOT)==(REPORT/'artifact-manifest.json').read_bytes(),'Index manifest differs'
 expected={entry['path']:entry for entry in manifest['artifacts']}
 actual={str(p.relative_to(REPORT)) for p in REPORT.rglob('*') if p.is_file() and p!=REPORT/'artifact-manifest.json'}
 assert actual==set(expected),('Artifact file set changed',actual^set(expected))
 for rel,entry in expected.items():
  assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
  body=(REPORT/rel).read_bytes();assert len(body)==entry['bytes'] and sha(body)==entry['sha256'],rel
  if index:assert subprocess.check_output(['git','show',':'+str((REPORT/rel).relative_to(ROOT))],cwd=ROOT)==body,('Index artifact differs',rel)
 summary=read_json(REPORT/'summary.json')
 assert summary['scope']=='secondary_software_integration' and summary['operator_configurable']
 assert not any(summary[key] for key in ('secondary_feature_complete','protected_switch_target','secondary_enabled_external_plant','online_tunerstudio','physical_qualification'))
 assert (summary['schema_version'],summary['page_bytes'],summary['runtime_bytes'])==(8,8192,640)
 assert summary['identity']=='ESP32ECU DEV 009 INHIBITED'
 assert summary['tests']['python']==189 and summary['tests']['secondary']==738 and summary['tests']['engine_secondary']==148
 source_map={entry['path']:entry for entry in summary['sources']}
 for source in summary['sources']:
  body=(REPORT/source['snapshot']).read_bytes();assert len(body)==source['bytes'] and sha(body)==source['sha256'],source['path']
  if live:assert (ROOT/source['path']).read_bytes()==body,('Live source changed',source['path'])
  if index:assert subprocess.check_output(['git','show',':'+source['path']],cwd=ROOT)==body,('Index source differs',source['path'])
 for review in summary['reviews']:
  directory=REPORT/'reviews'/review['name'];original=(directory/'original-artifact-manifest.json').read_bytes();assert sha(original)==review['manifest_sha256']
  original_json=json.loads(original)
  entries={entry['path']:entry for entry in original_json['artifacts']} if 'artifacts' in original_json else original_json['files']
  selection=read_json(directory/'selection.json')
  for name in ('review.json','final-source-bindings.json','source-bindings.json','software-readme-delta.json','receipt-probe.json'):
   if (directory/name).exists():assert sha((directory/name).read_bytes())==entries[name]['sha256'],('Review copy differs',name)
  with tarfile.open(directory/'inputs-and-probes.tar.gz','r:gz') as archive:
   members={m.name:m for m in archive.getmembers()};assert set(members)=={entry['original_path'] for entry in selection['included']}
   for item in selection['included']:
    member=members[item['original_path']];assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
    body=archive.extractfile(member).read();entry=entries[item['original_path']]
    assert len(body)==entry['bytes'] and sha(body)==entry['sha256'],member.name
 software=read_json(REPORT/'reviews/software/review.json')
 assert software['status'].startswith('complete') and not software['remaining_medium_high_findings'] and not software['live_differences_at_finish']
 assert len(software['checks'])==14 and all(check['result']=='pass' for check in software['checks'])
 bindings=read_json(REPORT/'reviews/software/final-source-bindings.json')['files']
 doc_bindings=read_json(REPORT/'reviews/documentation/source-bindings.json')
 documentation=read_json(REPORT/'reviews/documentation/review.json')
 assert documentation['status'].startswith('complete') and not documentation['remaining_medium_high_findings']
 assert len(documentation['checks'])==8 and all(check['result']=='pass' for check in documentation['checks'])
 assert doc_bindings['software_review_packet']['sha256']==next(r['manifest_sha256'] for r in summary['reviews'] if r['name']=='software')
 delta=doc_bindings['software_source_delta']
 assert doc_bindings['all_software_source_deltas']==['tuning/README.md'] and delta['path']=='tuning/README.md'
 assert delta['old_sha256']==bindings['tuning/README.md']['sha256'] and delta['new_sha256']==source_map['tuning/README.md']['sha256']
 for rel,item in bindings.items():
  if rel!='tuning/README.md':assert source_map[rel]['sha256']==item['sha256'],('Independent software review source differs',rel)
 receipt_paths={'.cache/engine/secondary-integration/application-checks.json':'validation/application-checks.json','.cache/engine/secondary-integration/engine188.msl':'applications/engine188.msl','.cache/engine/secondary-integration/direct145.msl':'applications/direct145.msl','.cache/engine/secondary-integration/ui/browser006.msl':'browser/secondary/browser006.msl'}
 for rel,item in doc_bindings['files'].items():
  if rel in source_map:assert source_map[rel]['sha256']==item['sha256'],('Independent documentation review source differs',rel)
  else:assert sha((REPORT/receipt_paths[rel]).read_bytes())==item['sha256'],('Independent receipt review differs',rel)
 assert read_json(REPORT/'reviews/documentation/receipt-probe.json')['passed']
 contract=read_json(REPORT/'reviews/contract/review.json')
 assert not contract['implementation_acceptance'] and contract['contract_viable_with_required_changes']
 assert contract['document_limit_recommendation']==49152 and contract['nvs_partition_recommendation']['bytes']==131072
 native=(REPORT/'validation/native-tests-final.log').read_text();python=(REPORT/'validation/python-tests-final.log').read_text()
 assert '"secondary_checks":738' in native and '"engine_secondary_checks":148' in native and 'Actual task logger:' in native
 assert 'Ran 189 tests' in python and '\nOK\n' in python and '\nFAILED' not in python
 disabled=gzip.decompress((REPORT/'validation/legacy-disabled-observations.csv.gz').read_bytes());check=read_json(REPORT/'validation/legacy-disabled-check.json')
 assert check['passed'] and disabled.count(b'\n')==7776 and sha(disabled)==check['sha256']==summary['disabled_observations_sha256']
 for item in read_json(REPORT/'validation/historical-records.json'):
  assert (REPORT/item['before']).read_bytes()==(REPORT/source_map[item['after']]['snapshot']).read_bytes(),item['after']
 sizes=read_json(REPORT/'target/actual-sizes.json');assert sizes['passed'] and not sizes['runtime_heap_stack_measured']
 for key,value in dict(tune=7204,observation=64,sample=528,row=544,page=8792,recorder=139352,session=8272).items():assert sizes['native'][key]==sizes['target'][key]==value
 partitions=read_json(REPORT/'target/partition-layout.json');assert partitions['passed'] and not partitions['flash_written']
 for entry in partitions['partitions']:assert entry['engine_nvs_offset']==0x210000 and entry['engine_nvs_bytes']==0x20000
 selected=read_json(REPORT/'target/policy/audit.json');isr=read_json(REPORT/'target/isr/closure.json');usb=read_json(REPORT/'target/usb/audit.json')
 assert selected['passed'] and selected['policy']=='engine_scheduler_physical_writes_compile_time_inhibited' and selected['on_alarm_GPIO_literal_references']==0 and selected['compiled_engine_output_pins'] is None
 assert isr['passed_static_placement'] and not isr['failures'] and selected['elf_sha256']==isr['elf_sha256']==usb['elf_sha256']
 assert usb['exclusive_usb'] and usb['source_budgets']['rx_ring_bytes']==usb['source_budgets']['tx_ring_bytes']==1024
 for path in ('target/generic-policy/audit.json','target/bench-policy/audit.json'):
  policy=read_json(REPORT/path);assert policy['passed'] and policy['app_image_bytes']<=2097152
 assert read_json(REPORT/'target/bench-policy/audit.json')['policy']=='gated_engine_dummy_loads_only'
 apps=read_json(REPORT/'validation/application-checks.json');assert apps['passed'] and apps['owned_applications_closed']
 ts=apps['tunerstudio'];assert ts['complete_f32_page_exact'] and ts['page_bytes']==8192 and ts['base_revision_supplied']==37 and ts['origin_omitted_by_application']
 assert ts['definition_parser_errors']==ts['unit_warnings']==0
 assert (REPORT/'applications/application-page.bin').read_bytes()==(REPORT/'applications/expected-edited-page.bin').read_bytes()
 assert sha((REPORT/'applications/application-page.bin').read_bytes())==ts['sha256']
 assert source_map['tuning/esp32-ecu-secondary.ini']['sha256']==ts['definition_sha256'] and source_map['tuning/examples/tunerstudio-secondary-roundtrip.msq']['sha256']==ts['file_sha256']
 tree=ET.fromstring((REPORT/'applications/tunerstudio-secondary-roundtrip.msq').read_bytes());ns={'m':'http://www.msefi.com/:msq'}
 assert tree.find('m:versionInfo',ns).get('signature')==summary['identity']
 constants={e.get('name'):e for e in tree.findall('m:page/m:constant',ns)}
 assert 'baseRevision' not in constants and constants['secondary_spark_mapTable'].get('units')=='deg delta'
 assert float(constants['secondary_spark_mapTable'].text.split()[0])==-3.75 and float(constants['secondary_fuel_mapTable'].text.split()[0])==124.5
 for rel,fields in [('applications/engine188.msl',188),('applications/direct145.msl',145),('browser/secondary/browser006.msl',188)]:
  rows=list(csv.reader(io.StringIO((REPORT/rel).read_text()),delimiter='\t'));assert all(len(row)==fields for row in rows[2:]),rel
 for path in summary['browser_reports']:
  browser=read_json(REPORT/path);assert browser.get('passed',not browser.get('page_errors')) and not browser['page_errors']
 if replay:
  directory=ROOT/'.cache/engine/secondary-integration/replays'/str(uuid.uuid4());directory.mkdir(parents=True);receipts=[]
  include=REPORT/'sources/firmware/include'
  for name in ('secondary_tables','engine_secondary','tuning_allocation'):
   exe=directory/name;argv=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(include),str(REPORT/'sources/firmware/tests'/(name+'_test.cpp')),'-o',str(exe)]
   if name=='tuning_allocation':argv.append('-Wl,--wrap=malloc')
   subprocess.run(argv,check=True);body=subprocess.check_output([str(exe)],text=True);assert json.loads(body)['passed'];(directory/(name+'.log')).write_text(body);receipts.append(dict(argv=argv,result=json.loads(body)))
  exe=directory/'disabled';argv=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(include),str(REPORT/'sources/tools/secondary_legacy_probe.cpp'),'-o',str(exe)]
  subprocess.run(argv,check=True);body=subprocess.check_output([str(exe)]);assert body==disabled;receipts.append(dict(argv=argv,rows=7776,sha256=sha(body)))
  (directory/'replay.json').write_text(json.dumps(receipts,indent=2)+'\n')
 return dict(passed=True,artifacts=len(expected),source_snapshots=len(source_map),independent_source_bindings=len(bindings),python_tests=189,exact_disabled_observations=7776,live_sources_checked=live,index_checked=index,native_replayed=replay,secondary_feature_complete=False,physical_qualification=False)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check-live-sources',action='store_true');parser.add_argument('--check-index',action='store_true');parser.add_argument('--replay',action='store_true');args=parser.parse_args()
 print(json.dumps(verify(args.check_live_sources,args.check_index,args.replay),indent=2))
