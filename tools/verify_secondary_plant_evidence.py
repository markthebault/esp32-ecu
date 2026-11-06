#!/usr/bin/env python3
"""Verify the immutable enabled-secondary plant packet and replay its audits."""
import argparse,gzip,hashlib,importlib,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/engine/secondary-plant'
def sha(body):return hashlib.sha256(body).hexdigest()
def document(path):return json.loads(path.read_text())
def verify(report=REPORT,live=False,replay=False):
 manifest=document(report/'artifact-manifest.json');entries={e['path']:e for e in manifest['artifacts']}
 files={str(p.relative_to(report))for p in report.rglob('*')if p.is_file()and p!=report/'artifact-manifest.json'}
 assert files==set(entries),'Artifact set differs'
 for name,e in entries.items():
  assert not Path(name).is_absolute()and '..'not in Path(name).parts
  body=(report/name).read_bytes();assert len(body)==e['bytes']and sha(body)==e['sha256'],name
 summary=document(report/'summary.json');assert summary['scope']=='enabled_secondary_coupled_plant'and summary['passed']
 assert not summary['physical_qualification']and not summary['full_speeduino_parity']and not summary['online_tunerstudio_accepted']
 for name,e in summary['sources'].items():
  body=(report/e['snapshot']).read_bytes();assert sha(body)==e['sha256'],name
  if live:assert (ROOT/name).read_bytes()==body,('Live source changed',name)
 for name in('matrix','fine'):
  d=document(report/name/'summary.json');assert d['passed']and d['source_bindings_stable']and not d['failures']
  assert len(d['runs'])==(128 if name=='matrix'else 20)
  b=document(report/name/'source-bindings.json')
  for p,digest in b['sources'].items():
   if p=='tools/verify_secondary_plant_evidence.py':
    delta=summary['tooling_source_delta'];assert delta['path']==p and delta['before_sha256']==digest
    assert sha((report/delta['before_snapshot']).read_bytes())==digest
    assert summary['sources'][p]['sha256']==delta['after_sha256']
   else:assert summary['sources'][p]['sha256']==digest,(name,p)
  for row in d['runs']:
   body=(report/name/row['trace_file']).read_bytes();assert sha(body)==row['trace_sha256']
   r=json.loads(gzip.decompress(body));assert row['audit']['passed']and r['summary']['audit']==row['audit']
   assert row['summary']==r['summary']
 checks=document(report/'checks/summary.json');assert checks['passed']and checks['source_bindings_stable']
 assert len(checks['mutations']['checks'])==20 and all(r['rejected']for r in checks['mutations']['checks'])
 assert len(checks['checks'])==24 and all(r['passed']for r in checks['checks'])
 core=document(report/'reviews/crank/independent-review.json');assert not core['open_findings']and core['sanitizers']['passed']
 for p,digest in core['frozen_files'].items():assert summary['sources'][p]['sha256']==digest,p
 integration=document(report/'reviews/integration/independent-review.json');assert integration['accepted']and not integration['open_findings']
 for p,digest in integration['frozen_source_hashes'].items():assert summary['sources'][p]['sha256']==digest,('Integration review source differs',p)
 for p,digest in document(report/'checks/source-bindings.json')['sources'].items():
  expected=summary['tooling_source_delta']['before_sha256']if p=='tools/verify_secondary_plant_evidence.py'else summary['sources'][p]['sha256']
  assert expected==digest,('Check execution source differs',p)
 assert summary['tests']['python']==205 and summary['tests']['secondary_native']==790 and summary['tests']['engine_secondary_native']==172
 assert document(report/'validation/ui/ui-tests.json')['passed']
 for environment in('compact_a3_web','compact_n16r8_web','compact_a3_timing_bench'):
  a=document(report/'validation/build-audits'/environment/'audit.json');assert a['passed']and a['app_image_bytes']<=2097152
  if environment!='compact_a3_timing_bench':assert a['policy']=='engine_scheduler_physical_writes_compile_time_inhibited'
 assert document(report/'validation/isr-audit/closure.json')['passed_static_placement']
 if replay:
  sys.path.insert(0,str(report/'sources/tools'));runner=importlib.import_module('run_secondary_scenarios');checker=importlib.import_module('check_secondary_experiments');cases=0
  for name in('matrix','fine'):
   for row in document(report/name/'summary.json')['runs']:
    result=json.loads(gzip.decompress((report/name/row['trace_file']).read_bytes()));a=runner.audit(result,row['case'],row['label']in('portable','target'))
    assert a==row['audit'],(name,row['name'],a);cases+=1
  assert checker.mutations(report/'matrix')==checks['mutations']
  with tempfile.TemporaryDirectory(prefix='ecu-secondary-plant-replay-')as temporary:
   for test in('secondary_tables','engine_secondary'):
    binary=Path(temporary)/test
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(report/'sources/firmware/include'),str(report/'sources/firmware/tests'/(test+'_test.cpp')),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
  print('Replayed',cases,'saved coupled audits,20 negative controls and frozen native core tests')
 print('Verified',len(entries),'artifacts and',len(summary['sources']),'source snapshots; physical/full parity gates remain open')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--replay',action='store_true');a=p.parse_args();verify(a.report,a.check_live_sources,a.replay)
