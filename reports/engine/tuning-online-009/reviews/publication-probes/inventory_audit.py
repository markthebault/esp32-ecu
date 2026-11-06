#!/usr/bin/env python3
"""Independent packet/ZIP/source audit, with no parent or archive mutations."""
from pathlib import Path
import collections,gzip,hashlib,json,re,stat,subprocess,zipfile
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[3];PACKET=BASE/'candidate-packet';sha=lambda b:hashlib.sha256(b).hexdigest()
manifest=json.loads((PACKET/'artifact-manifest.json').read_text())['artifacts']
files={str(p.relative_to(PACKET)):p for p in PACKET.rglob('*')if p.is_file()and p.name!='artifact-manifest.json'}
assert len(manifest)==186 and len(files)==186 and set(files)=={r['path']for r in manifest}
assert not any(p.is_symlink()for p in PACKET.rglob('*'))
for row in manifest:
    body=files[row['path']].read_bytes();assert len(body)==row['bytes']and sha(body)==row['sha256'],row['path']
summary=json.loads((PACKET/'summary.json').read_text());source_checks={}
for name,row in summary['sources'].items():
    archived=(PACKET/row['snapshot']).read_bytes();live=(ROOT/name).read_bytes()
    assert sha(archived)==row['sha256']and live==archived,name
    source_checks[name]=row['sha256']
assert len(source_checks)==79
upstream={}
for name,row in summary['upstream_sources'].items():
    original=subprocess.check_output(['git','-C',str(ROOT.parent/'speeduino'),'show','9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20:'+name])
    archived=(PACKET/row['snapshot']).read_bytes();assert archived==original and sha(archived)==row['sha256'];upstream[name]=row['sha256']
old=json.loads((BASE.parent/'revision005/snapshot.json').read_text())['source_sha256']
implementation=['scripts/build_speeduino_serial.py','tools/speeduino_serial_sim.cpp','tools/speeduino_serial_runtime.py','tools/test_speeduino_serial.py','tools/analyze_tuning_wire.py','tools/test_tuning_wire_analysis.py']
assert all(source_checks[name]==old[name]for name in implementation)
prior_bindings={
 'own/wire.log.gz':BASE.parent/'revision002/wire.log',
 'own/application-debug.log.gz':BASE.parent/'revision002/application-debug.log',
 'reference/wire.log.gz':BASE.parent/'revision005/reference-public-003/wire.log',
 'reference/application-debug.log.gz':BASE.parent/'revision005/reference-public-003/user/TunerStudioProjects/TunerStudioAppDebug.txt',
 'reference/native-events.log.gz':BASE.parent/'revision005/reference-public-003/native/native-events.log'}
for name,path in prior_bindings.items():assert gzip.decompress((PACKET/name).read_bytes())==path.read_bytes(),name
attachment=json.loads((PACKET/'vendor/attachment-manifest.json').read_text())['files']
zip_path=PACKET/'vendor-support.zip';assert sha(zip_path.read_bytes())=='c8679be6a7ce459c36a59612218795dae8a354c43cb041ca59177177a89c9768'
zip_checks={}
with zipfile.ZipFile(zip_path)as archive:
    assert len(archive.namelist())==len(set(archive.namelist()))==len(attachment)==19
    assert set(archive.namelist())==set(attachment)and archive.testzip()is None
    for info in archive.infolist():
        name=info.filename;assert not Path(name).is_absolute()and'..'not in Path(name).parts and'\\'not in name
        assert not stat.S_ISLNK(info.external_attr>>16)
        body=archive.read(name);row=attachment[name]
        assert sha(body)==row['sha256']and body==(PACKET/row['packet_source']).read_bytes()
        zip_checks[name]=dict(bytes=len(body),sha256=sha(body),packet_source=row['packet_source'])
    sums={}
    for line in archive.read('SHA256SUMS').decode().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line);assert match;digest,name=match.groups();assert name not in sums;sums[name]=digest
    assert set(sums)==set(attachment)-{'SHA256SUMS'}
    assert all(sha(archive.read(name))==digest for name,digest in sums.items())
    vendor_sources=json.loads(archive.read('source-hashes.json'));assert vendor_sources['sources']==summary['sources']
    assert vendor_sources['baseline_commit']==summary['baseline_commit']
assert archive.fp is None
secret_patterns={
 'github_token':rb'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
 'openai_style_key':rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}',
 'aws_access_key':rb'\bAKIA[0-9A-Z]{16}\b',
 'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
 'bearer_literal':rb'Authorization:\s*Bearer\s+[A-Za-z0-9_.-]{20,}'}
secret_hits=[];prohibited=[];readable=0
for name,path in files.items():
    body=path.read_bytes();logical=gzip.decompress(body)if name.endswith('.gz')else body
    if path.suffix.lower()in('.jar','.pdf','.class','.exe','.dll','.so')or logical.startswith((b'%PDF-',b'\x7fELF',b'\xca\xfe\xba\xbe',b'MZ')):prohibited.append(name)
    if any(part in('secrets','.env')or part.startswith('.env.')for part in Path(name).parts):prohibited.append(name)
    for label,pattern in secret_patterns.items():
        if re.search(pattern,logical):secret_hits.append(dict(path=name,pattern=label))
    if not logical.startswith((b'\x89PNG',b'PK\x03\x04')):readable+=1
assert not prohibited and not secret_hits
assert summary['checks_passed']and not any(summary[name]for name in('own_online_accepted','physical_qualification','full_speeduino_parity','vendor_request_sent'))
assert'LOCAL UNSENT DRAFT'in(ROOT/'tuning/vendor-integration-email.txt').read_text()
assert'It has not been sent'in(ROOT/'tuning/vendor-integration-request.md').read_text()
result=dict(manifest_artifacts=186,all_artifact_hashes_and_sizes_valid=True,no_symlinks=True,source_snapshots=79,all_sources_match_live=True,source_hashes=source_checks,upstream_pin_sources=upstream,six_implementation_files_unchanged_from_accepted_revision005=True,prior_review_capture_byte_bindings=list(prior_bindings),zip_sha256=sha(zip_path.read_bytes()),zip_members=zip_checks,zip_member_count=19,zip_attachment_set_and_payload_binding=True,zip_crc_valid=True,zip_sha256sums_entries=len(sums),zip_source_hashes_match_all79_snapshots=True,prohibited_binary_or_secret_file_findings=prohibited,high_confidence_secret_pattern_hits=secret_hits,secret_scan_logical_files=readable,secret_scan_scope='Filename and executable/PDF magic checks plus high-confidence credential/private-key patterns across packet files and decompressed logs; no patterns found. Historical paths/PIDs remain intentionally documented.',scope_flags_honest=True,local_unsent_status_explicit=True,verifier_audit=dict(useful_checks=['Exact artifact set/size/SHA256 and no symlink files','Current/frozen source binding, optionally live','Closed captured wire counts/identity/CRC bindings and own rejection warnings','Production source pin, launch/native input review, exact baseline relink receipt','Independent implementation/publication review bindings','Full page2 read/write/burn/controller CRC/MSQ and stopped ADC/RPM checks','ZIP set/content/source hash binding','Replay uses temporary work and -B/bytecode suppression'],expected_replay_writes='Temporary directory only; will test packet byte/file-set noninterference.',interpretation='A reproducibility/integrity checker for this manually reviewed packet. App trial, original object binding and physical limitations remain established by archived receipts; replay does not rerun the proprietary app or native production fixture.'))
(BASE/'inventory-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in('source_hashes','upstream_pin_sources','zip_members')},indent=2))
