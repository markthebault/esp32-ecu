#!/usr/bin/env python3
"""Verify the scoped secondary core evidence; optionally rebuild its native probes."""
import argparse,gzip,hashlib,json,subprocess,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/engine/secondary-core'
def sha(body):return hashlib.sha256(body).hexdigest()
def verify(live=False,index=False,replay=False):
 manifest=json.loads((REPORT/'artifact-manifest.json').read_text())
 expected={entry['path'] for entry in manifest['artifacts']}
 actual={str(p.relative_to(REPORT)) for p in REPORT.rglob('*') if p.is_file() and p!=REPORT/'artifact-manifest.json'}
 assert actual==expected,('Artifact file set changed',actual^expected)
 for entry in manifest['artifacts']:
  p=REPORT/entry['path'];body=p.read_bytes()
  assert len(body)==entry['bytes'] and sha(body)==entry['sha256'],entry['path']
  if index:assert subprocess.check_output(['git','show',':'+str(p.relative_to(ROOT))],cwd=ROOT)==body,('Index artifact differs',entry['path'])
 summary=json.loads((REPORT/'summary.json').read_text())
 assert summary['scope']=='secondary_core_foundation' and summary['operator_configurable'] is False and summary['physical_qualification'] is False
 assert summary['tests']['python']==173 and summary['tests']['secondary']==738 and summary['tests']['engine_secondary']==148
 assert summary['tests']['native_sanitizers'] and summary['tests']['selected_target_build']
 for source in summary['sources']:
  body=(REPORT/source['snapshot']).read_bytes();assert sha(body)==source['sha256'],source['path']
  if live:assert (ROOT/source['path']).read_bytes()==body,('Live source changed',source['path'])
  if index:assert subprocess.check_output(['git','show',':'+source['path']],cwd=ROOT)==body,('Index source differs',source['path'])
 baseline=json.loads((REPORT/'before/manifest.json').read_text())
 assert baseline['head']==summary['baseline_commit']
 for path,digest in baseline['sources'].items():assert sha((REPORT/'before/sources'/path).read_bytes())==digest,path
 before=gzip.decompress((REPORT/'before/observations.csv.gz').read_bytes())
 after=gzip.decompress((REPORT/'after/observations.csv.gz').read_bytes())
 assert before==after and before.count(b'\n')==7776 and sha(before)==baseline['observations_sha256']==summary['disabled_observations_sha256']
 for review in summary['reviews']:
  directory=REPORT/'reviews'/review['name']
  original=(directory/'original-artifact-manifest.json').read_bytes();assert sha(original)==review['manifest_sha256']
  original_manifest=json.loads(original)
  original_entries={entry['path']:entry for entry in original_manifest['artifacts']} if 'artifacts' in original_manifest else original_manifest['files']
  for entry in json.loads((directory/'selection.json').read_text())['included']:
   body=(directory/entry['stored_path']).read_bytes()
   if entry['compressed']:body=gzip.decompress(body)
   item=original_entries[entry['original_path']]
   assert len(body)==item['bytes'] and sha(body)==item['sha256'],entry['stored_path']
 core=json.loads((REPORT/'reviews/core/review.json').read_text())
 assert core['passed'] and core['independent_checks']['total']==3224 and core['exact_own008_pages']==108 and not core['remaining_medium_high_in_reviewed_scope']
 sources={entry['path']:entry['sha256'] for entry in summary['sources']}
 for rel,digest in core['source_bindings'].items():assert sources[rel]==digest,('Independent review binding differs',rel)
 wire=json.loads((REPORT/'reviews/core/wire-comparison.json').read_text())
 assert wire['passed'] and (REPORT/'reviews/core/frozen-pages.bin').read_bytes()==(REPORT/'reviews/core/current-pages.bin').read_bytes()
 assert sha((REPORT/'reviews/core/current-pages.bin').read_bytes())==wire['reports']['current']['sha256']
 policy=json.loads((REPORT/'target/policy/audit.json').read_text())
 assert policy['passed'] and policy['on_alarm_GPIO_literal_references']==0 and policy['compiled_engine_output_pins'] is None
 assert policy['policy']=='engine_scheduler_physical_writes_compile_time_inhibited'
 native=(REPORT/'validation/native-tests-final.log').read_text();python=(REPORT/'validation/python-tests-final.log').read_text()
 assert '"secondary_checks":738' in native and '"engine_secondary_checks":148' in native and '"allocation_failures":4' in native
 assert 'Actual task logger:' in native and 'Ran 173 tests' in python and '\nOK\n' in python
 if replay:
  directory=ROOT/'.cache/engine/secondary/replays'/str(uuid.uuid4());directory.mkdir(parents=True)
  source=REPORT/'before/sources/tools/secondary_legacy_probe.cpp';outputs=[];receipts=[]
  for label,include in [('before',REPORT/'before/sources/firmware/include'),('after',REPORT/'sources/firmware/include')]:
   exe=directory/label
   argv=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(include),str(source),'-o',str(exe)]
   subprocess.run(argv,check=True);body=subprocess.check_output([str(exe)]);(directory/(label+'.csv')).write_bytes(body);outputs.append(body)
   receipts.append({'label':label,'argv':argv,'rows':body.count(b'\n'),'sha256':sha(body)})
  assert outputs[0]==outputs[1]==before,'Disabled probe replay differs'
  for name in ('secondary_tables','engine_secondary','tuning_allocation'):
   exe=directory/(name+'-test');source=REPORT/'sources/firmware/tests'/(name+'_test.cpp')
   argv=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(REPORT/'sources/firmware/include'),str(source),'-o',str(exe)]
   if name=='tuning_allocation':argv.append('-Wl,--wrap=malloc')
   subprocess.run(argv,check=True);body=subprocess.check_output([str(exe)],text=True);assert json.loads(body)['passed'];(directory/(name+'.log')).write_text(body);receipts.append({'label':name,'argv':argv,'result':json.loads(body)})
  (directory/'replay.json').write_text(json.dumps(receipts,indent=2)+'\n')
 return {'passed':True,'artifacts':len(expected),'source_snapshots':len(summary['sources']),'exact_disabled_observations':7776,'live_sources_checked':live,'index_checked':index,'native_replayed':replay,'operator_configurable':False,'physical_qualification':False}
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--check-live-sources',action='store_true');parser.add_argument('--check-index',action='store_true');parser.add_argument('--replay',action='store_true')
 args=parser.parse_args();print(json.dumps(verify(args.check_live_sources,args.check_index,args.replay),indent=2))
