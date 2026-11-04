#!/usr/bin/env python3
"""Owned packaging/negative probes; no project report is changed."""
import copy,hashlib,json,os,shutil,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent;F=O/'freeze-003';P=O/'packet-verifier-002'
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
P.mkdir();shutil.copytree(O/'validation-final005',P/'validation')
selected=['firmware/include/ecu/flex_ingress.hpp','firmware/tests/flex_ingress_test.cpp','firmware/include/ecu/flex_fuel.hpp','firmware/include/ecu/capture_clock.hpp','firmware/include/ecu/realtime.hpp','firmware/tests/flex_ingress_xtensa_probe.cpp','scripts/check_flex_ingress.py','tools/verify_flex_ingress_evidence.py','hardware/flex-input/architecture.json','hardware/flex-input/README.md','docs/engine-flex-fuel.md','docs/engine-feature-coverage.md','scripts/test_firmware.sh']
review={'accepted':True,'open_findings':[],'scope':'Genuinely accepted portable ingress and dedicated native/static evidence only; no producer/circuit/physical acceptance. Minimal schema for owned verifier packaging probe.','source_hashes':{name:H(F/name)for name in selected}}
R=P/'reviews/ingress/review.json';R.parent.mkdir(parents=True);R.write_text(json.dumps(review,indent=2)+'\n')
(O/'verifier-minimal-acceptance-002.json').write_bytes(R.read_bytes())
def manifest():
 rows=[dict(path=str(p.relative_to(P)),bytes=p.stat().st_size,sha256=H(p))for p in sorted(P.rglob('*'))if p.is_file()and p!=P/'artifact-manifest.json']
 (P/'artifact-manifest.json').write_text(json.dumps({'artifacts':rows},indent=2)+'\n')
env=dict(os.environ,GCOV_PREFIX=str(O/'gcov'),GCOV_PREFIX_STRIP='0',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(O/'tmp'))
command=['python3','-B',str(F/'tools/verify_flex_ingress_evidence.py'),'--report',str(P),'--check-live-sources']
results=[]
def run(name,replay=False,want=None):
 cmd=command+(['--replay']if replay else[]);p=subprocess.run(cmd,cwd=F,env=env,text=True,capture_output=True)
 results.append(dict(name=name,command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 if want is None:assert p.returncode==0,(name,p.stderr)
 else:assert p.returncode!=0 and want in p.stderr,(name,p.stderr)
manifest();run('positive_native_and_four_saved_ELF_replay',True)
cases=[
 ('reviews/ingress/review.json','review_source_mismatch',lambda d:d['source_hashes'].__setitem__('firmware/include/ecu/flex_ingress.hpp','0'*64),'Independent review source mismatch'),
 ('validation/summary.json','physical_overclaim',lambda d:d.__setitem__('physical_qualification',True),'Overstated qualification'),
 ('validation/inputs-after.json','broken_source_attestation',lambda d:d[0].__setitem__('sha256','0'*64),'Input attestations differ'),
 ('validation/xtensa-unmapped-flash-negative/audit.json','forged_negative_acceptance',lambda d:d.__setitem__('passed',True),'Static positive/negative mismatch'),
 ('validation/sources/hardware/flex-input/architecture.json','unimplemented_architecture_overclaim',lambda d:d['implementation'].__setitem__('target_producer',True),'Changed source binding'),
 ('validation/native-run.stdout','native_receipt_change',lambda d:d+'extra\n','Native receipt mismatch'),
]
for rel,name,mutate,error in cases:
 p=P/rel;original=p.read_bytes()
 try:
  if p.suffix=='.json':d=json.loads(original);mutate(d);p.write_text(json.dumps(d,indent=2)+'\n')
  else:p.write_text(mutate(original.decode()))
  manifest();run(name,want=error)
 finally:p.write_bytes(original);manifest()
# Duplicate/set mismatch controls use the manifest directly, without changing
# any source snapshot or acceptance evidence.
m=P/'artifact-manifest.json';original=m.read_bytes()
try:
 d=json.loads(original);d['artifacts'].append(copy.deepcopy(d['artifacts'][0]));m.write_text(json.dumps(d));run('duplicate_artifact',want='Duplicate artifact')
finally:m.write_bytes(original)
extra=P/'unexpected';extra.write_text('owned corruption')
try:run('unexpected_artifact',want='Artifact set differs')
finally:extra.unlink()
run('restored_positive')
report={'passed':True,'negative_controls':8,'positive_replay':True,'results':results,'minimal_accepted_review_sha256':H(O/'verifier-minimal-acceptance-002.json'),'selected_source_hashes':review['source_hashes'],'environment':{k:env[k]for k in ('GCOV_PREFIX','GCOV_PREFIX_STRIP','PYTHONDONTWRITEBYTECODE','TMPDIR')},'scope':'Owned copy only. Native compiled replay and saved static ELF re-audit; no Xtensa ELF/device execution.'}
(O/'verifier-probe-002.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'negative_controls':8,'positive_replay':True,'source_hashes':len(selected)}))
