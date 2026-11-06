#!/usr/bin/env python3
"""Verify the immutable SW2 development packet; optionally replay frozen code.

Default is archival. Live-source equality is an explicit additional check so
later feature work cannot silently replace what an earlier report tested.
"""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
def require(ok,message):
 if not ok:raise ValueError(message)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def member(root,relative):
 path=PurePosixPath(relative)
 require(not path.is_absolute() and '..' not in path.parts,'Unsafe evidence path')
 p=root/path
 require(p.resolve().is_relative_to(root.resolve()) and not p.is_symlink() and p.is_file(),'Missing/unsafe evidence member: '+relative)
 return p
def verify(folder,live=False):
 manifest=json.loads((folder/'artifact-manifest.json').read_text());listed={}
 for row in manifest['artifacts']:
  require(row['path']not in listed,'Duplicate artifact path');p=member(folder,row['path'])
  require(p.stat().st_size==row['bytes'] and digest(p)==row['sha256'],'Artifact mismatch: '+row['path']);listed[row['path']]=row
 # Nested original manifests are ordinary bound artifacts, not this manifest.
 actual={str(p.relative_to(folder))for p in folder.rglob('*')if p.is_file()and p!=folder/'artifact-manifest.json'}
 require(actual==set(listed),'Unlisted or missing evidence files')
 sources=json.loads((folder/'source-bindings.json').read_text())['sources']
 for row in sources:
  p=member(folder,'sources/'+row['path']);require(digest(p)==row['sha256'],'Frozen source mismatch')
  if live:require(digest(member(ROOT,row['path']))==row['sha256'],'Live source changed: '+row['path'])
 checks=json.loads((folder/'checks.json').read_text());require(checks['passed'] and checks['physical_qualification']is False,'Invalid scope/result')
 for name in ('erc','drc'):
  d=json.loads((folder/'validation/cad'/f'{name}.json').read_text())
  if name=='erc':require(not any(s['violations']for s in d['sheets']),'ERC violations')
  else:require(not(d['violations']or d['unconnected_items']or d['schematic_parity']),'DRC/connectivity/parity violations')
 model=json.loads((folder/'validation/circuit/results.json').read_text());require(model['cases']==95 and model['passed_declared_model_checks'] and not model['physical_qualification']and not model['manufacturer_models'],'Wrong model scope')
 for relative,sha in model['sources'].items():require(digest(member(folder,'sources/'+relative))==sha,'Model/source binding changed: '+relative)
 review=folder/'reviews/software';bindings=json.loads((review/'source-bindings.json').read_text());deltas=[]
 for row in bindings['sources']:
  old=member(review,'sources/'+row['path']);require(digest(old)==row['sha256'],'Reviewed source mismatch')
  now=member(folder,'sources/'+row['path']);sha=digest(now)
  if sha!=row['sha256']:deltas.append(dict(path=row['path'],reviewed_sha256=row['sha256'],published_sha256=sha))
 require(deltas==checks['software_review_documentation_delta'],'Undeclared independent review delta')
 require({d['path']for d in deltas}=={'docs/engine-secondary-tables.md'},'Software review acceptance cannot cover changed code')
 require(json.loads((review/'review.json').read_text())['open_medium_high_software_findings']==0,'Open software finding')
 return dict(passed=True,artifacts=len(listed),sources=len(sources),manifest_sha256=digest(folder/'artifact-manifest.json'),live_sources_checked=live,physical_qualification=False)
def replay(folder,ngspice=None):
 with tempfile.TemporaryDirectory(prefix='ecu-switch-replay-')as directory:
  task=Path(directory);sources=task/'sources';shutil.copytree(folder/'sources',sources)
  review=task/'software-review';shutil.copytree(folder/'reviews/software',review)
  run=subprocess.run(['python3',str(review/'run_review.py')],text=True,capture_output=True,timeout=240)
  require(run.returncode==0,run.stdout[-2000:]+run.stderr[-2000:]);independent=json.loads(run.stdout.strip().splitlines()[-1])
  require(independent['assertions']==12278 and independent['passed'],'Independent frozen replay failed')
  results=[];inc=sources/'firmware/include'
  flags=['-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer']
  for name in ('switch_acquisition','switch_transport'):
   binary=task/name;subprocess.run(['g++',*flags,'-I'+str(inc),str(sources/f'firmware/tests/{name}_test.cpp'),'-o',str(binary)],check=True,timeout=90)
   r=subprocess.run([str(binary)],check=True,capture_output=True,text=True,timeout=30);results.append(json.loads(r.stdout))
  cjson=review/'external/json/cJSON';cobject=task/'cjson.o';subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-c',str(cjson/'cJSON.c'),'-o',str(cobject)],check=True,timeout=60)
  binary=task/'service';subprocess.run(['g++',*flags,'-pthread','-I'+str(inc),'-I'+str(cjson),'-I'+str(sources/'firmware/tests/switch_fakes'),str(sources/'firmware/tests/switch_service_test.cpp'),str(sources/'firmware/main/switch_service.cpp'),str(cobject),'-o',str(binary)],check=True,timeout=90)
  r=subprocess.run([str(binary)],check=True,capture_output=True,text=True,timeout=30);results.append(json.loads(r.stdout))
  if ngspice:
   r=subprocess.run(['python3',str(sources/'tools/run_switch_circuit.py'),'--ngspice',str(ngspice.resolve()),'--report-dir',str(task/'circuit')],capture_output=True,text=True,timeout=120)
   require(r.returncode==0,r.stdout[-2000:]+r.stderr[-2000:]);rerun=json.loads((task/'circuit/results.json').read_text());original=json.loads((folder/'validation/circuit/results.json').read_text())
   require(rerun['binary_sha256']==original['binary_sha256'],'Circuit replay requires the recorded ngspice binary')
   require(rerun['results']==original['results'],'Conditional circuit results changed')
  return dict(passed=True,independent_assertions=independent['assertions'],root_probes=results,circuit_replayed=bool(ngspice),physical_qualification=False)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=ROOT/'reports/engine/switch-inputs');p.add_argument('--check-live-sources',action='store_true');p.add_argument('--replay',action='store_true');p.add_argument('--ngspice',type=Path);a=p.parse_args()
 result=verify(a.directory.resolve(),a.check_live_sources)
 if a.replay:result['replay']=replay(a.directory.resolve(),a.ngspice)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
