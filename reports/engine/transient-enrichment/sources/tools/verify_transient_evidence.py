#!/usr/bin/env python3
"""Check immutable transient evidence and optional current/index bindings."""
import argparse,csv,gzip,hashlib,io,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/engine/transient-enrichment'
sha=lambda b:hashlib.sha256(b).hexdigest()

def verify(live=False,index=False):
 manifest=json.loads((OUT/'artifact-manifest.json').read_text())['files_sha256']
 expected={str((OUT/name).relative_to(ROOT)):digest for name,digest in manifest.items()}
 assert set(manifest)=={str(p.relative_to(OUT)) for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'},'Unlisted evidence file'
 for name,digest in expected.items():assert sha((ROOT/name).read_bytes())==digest,'Artifact differs: '+name
 summary=json.loads((OUT/'validation-summary.json').read_text());sources=summary['source_sha256'];assert summary['passed']
 for name,digest in sources.items():
  assert sha((OUT/'sources'/name).read_bytes())==digest,'Source snapshot differs: '+name
  if live:assert sha((ROOT/name).read_bytes())==digest,'Live source differs: '+name
 matrix=json.loads((OUT/'matrix/summary.json').read_text());assert matrix['passed'] and len(matrix['runs'])==64
 assert len(matrix['refinement'])==len(matrix['negative'])==8 and all(r['passed'] for r in matrix['refinement']+matrix['negative'])
 for row in matrix['runs']:
  path=OUT/'matrix'/(row['path']+'.gz');data=gzip.decompress(path.read_bytes());assert sha(data)==row['trace_sha256'];result=json.loads(data)
  assert row['audit']['passed'] and result['summary']['audit']['passed'] and result['summary']['final_outputs_high']==0
 for name,digest in matrix['source_hashes'].items():assert sources[name]==digest,'Matrix source differs: '+name
 first=json.loads((OUT/'initial-matrix/summary.json').read_text());assert not first['passed'] and first['failures']
 assert sha((OUT/'initial-matrix/run_transient_scenarios.py').read_bytes())==first['source_hashes']['tools/run_transient_scenarios.py']
 for name,digest in first['source_hashes'].items():
  if name!='tools/run_transient_scenarios.py':assert sources[name]==digest,'Initial source differs: '+name
 for row in first['runs']:assert sha(gzip.decompress((OUT/'initial-matrix'/(row['path']+'.gz')).read_bytes()))==row['trace_sha256']
 legacy=json.loads((OUT/'legacy/summary.json').read_text());assert legacy['passed'] and len(legacy['cases'])==8 and all(row['passed'] and all(row['checks'].values()) for row in legacy['cases'])
 for row in legacy['cases']:assert sha((ROOT/row['baseline_path']).read_bytes())==row['baseline_sha256'],'Legacy baseline differs'
 apps=summary['applications'];assert apps['passed'] and apps['owned_applications_closed']
 assert sha((OUT/'applications/ts/transient-app.msq').read_bytes())==apps['tunerstudio']['file_sha256']
 assert sha((OUT/'applications/esp32-ecu-transient.ini').read_bytes())==apps['tunerstudio']['definition_sha256']
 for name,count in (('engine105.msl',105),('sil62.msl',62)):
  rows=list(csv.reader(io.StringIO((OUT/'applications'/name).read_text()),delimiter='\t'));assert len(rows[2])==count and all(len(r)==count for r in rows[3:])
 for folder in ('ui-app-final','ui-logger-final','ui-tuning','ui-semi','ui-idle','ui-cylinder','ui-sequential-fixed'):
  report='sequential-ui-tests.json' if folder=='ui-sequential-fixed' else 'ui-tests.json'
  assert json.loads((OUT/'browser'/folder/report).read_text())['passed']
 if index:
  expected[str((OUT/'artifact-manifest.json').relative_to(ROOT))]=sha((OUT/'artifact-manifest.json').read_bytes())
  if live:
   tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'));expected.update((name,digest) for name,digest in sources.items() if name in tracked)
  for name,digest in expected.items():assert sha(subprocess.check_output(['git','show',':'+name],cwd=ROOT))==digest,'Git index differs: '+name
 return dict(passed=True,artifacts=len(manifest),source_snapshots=len(sources),qualified_runs=64,legacy_runs=8,live_sources_checked=live,index_checked=index,physical_qualification=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--check-index',action='store_true');a=p.parse_args();print(json.dumps(verify(a.check_live_sources,a.check_index),indent=2))
