#!/usr/bin/env python3
"""Check published semi evidence bytes and optional current/index bindings.

Integrity checks do not establish engine, electrical or fabrication acceptance.
"""
import argparse,gzip,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()

def verify(live=False,index=False):
 out=ROOT/'reports/engine/semi-sequential';manifest=json.loads((out/'artifact-manifest.json').read_text())
 expected={str((out/name).relative_to(ROOT)):digest for name,digest in manifest['files_sha256'].items()}
 for name,digest in expected.items():assert sha((ROOT/name).read_bytes())==digest,'Artifact differs: '+name
 summary=json.loads((out/'validation-summary.json').read_text());source=summary['source_sha256']
 for name,digest in source.items():
  assert sha((out/'sources'/name).read_bytes())==digest,'Source snapshot differs: '+name
  if live:assert sha((ROOT/name).read_bytes())==digest,'Live source differs: '+name
 matrix=json.loads((out/'matrix/summary.json').read_text());assert matrix['passed'] and matrix['controller_cases']==28 and matrix['convergence_cases']==8
 for row in matrix['rows']:
  path=out/'matrix'/f"{row['label']}-{row['scenario']}-250.json.gz"
  assert sha(gzip.decompress(path.read_bytes()))==row['trace_sha256'],'Matrix raw digest differs'
  assert row['audit']['passed'] and row['final_outputs_high']==0
 for name,digest in matrix['source_hashes'].items():assert source[name]==digest,'Matrix source differs: '+name
 legacy=json.loads((out/'legacy/summary.json').read_text());assert legacy['passed'] and len(legacy['cases'])==8
 for report in ('ui-semi','ui-tuning','ui-sequential','ui-idle'):
  assert json.loads((out/f'browser/{report}.json').read_text())['passed']
 if index:
  expected[str((out/'artifact-manifest.json').relative_to(ROOT))]=sha((out/'artifact-manifest.json').read_bytes())
  if live:
   tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))
   # Generated sdkconfig inputs are retained as hashed snapshots; only repo
   # sources present in the index can also have a live Git byte binding.
   expected.update((name,digest) for name,digest in source.items() if name in tracked)
  for name,digest in expected.items():assert sha(subprocess.check_output(['git','show',':'+name],cwd=ROOT))==digest,'Git index differs: '+name
 return dict(passed=True,artifacts=len(manifest['files_sha256']),source_snapshots=len(source),live_sources_checked=live,index_checked=index,physical_qualification=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-live-sources',action='store_true');p.add_argument('--check-index',action='store_true');a=p.parse_args()
 print(json.dumps(verify(a.check_live_sources,a.check_index),indent=2))
