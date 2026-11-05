"""Verify frozen calibration evidence; --current also binds it to this worktree."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import tarfile

R=Path(__file__).resolve().parents[1]


def digest(data):return hashlib.sha256(data).hexdigest()


def rodata(body):
    assert body[:6]==b'\x7fELF\x01\x01','expected ESP32 little-endian32-bit ELF'
    offset=struct.unpack_from('<I',body,32)[0]
    step,count,string_index=struct.unpack_from('<HHH',body,46)
    sections=[struct.unpack_from('<IIIIIIIIII',body,offset+n*step) for n in range(count)]
    strings=sections[string_index];names=body[strings[4]:strings[4]+strings[5]]
    found=[s for s in sections if names[s[0]:].split(b'\0',1)[0]==b'.flash.rodata']
    assert len(found)==1,'flash rodata section missing/ambiguous'
    section=found[0];return body[section[4]:section[4]+section[5]]


def verify(folder,current=False):
    manifest=json.loads((folder/'manifest.json').read_text())
    checksums={}
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);assert name not in checksums
        assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
        checksums[name]=expected
    files={str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    assert files==set(checksums),'checksum inventory differs'
    for name,expected in checksums.items():assert digest((folder/name).read_bytes())==expected,name
    payloads={}
    for name,expected in manifest['archives'].items():
        with tarfile.open(folder/name,'r:xz') as archive:
            members=archive.getmembers();assert all(m.isfile() for m in members)
            assert len({m.name for m in members})==len(members)
            assert {m.name for m in members}==set(expected)
            for member in members:
                path=PurePosixPath(member.name)
                assert not path.is_absolute() and '..' not in path.parts and path.name!='AGENTS.md'
                body=archive.extractfile(member).read();record=expected[member.name]
                assert len(body)==record['bytes'] and digest(body)==record['sha256'],member.name
                payloads[(name,member.name)]=body
    images=0
    for build in manifest['firmware_builds']:
        for artifact in build['artifacts']:
            body=payloads[(build['archive'],build['prefix']+'/'+artifact['path'])]
            assert len(body)==artifact['bytes'] and digest(body)==artifact['sha256']
        for item in build['elf_archives']:
            packed=payloads[(build['archive'],build['prefix']+'/'+item['path'])]
            body=gzip.decompress(packed)
            assert len(body)==item['elf_bytes'] and digest(body)==item['elf_sha256']
            section=rodata(body)
            for source in ('web/index.html','config/defaults.json','config/interface-guide.json'):
                text=payloads[(build['source_archive'],build['source_prefix']+'/'+source)]
                assert text+b'\0' in section,(item['environment'],source)
            images+=1
    review=json.loads((folder/'independent-review.json').read_text())
    assert not review['decision']['open_publication_blockers']
    assert not review['decision']['physical_operation_qualified']
    assert not review['decision']['full_nonideal_sweep_accepted']
    differences={name for name,value in review['source_sha256_final'].items()
        if manifest['current_sources'].get(name)!=value}
    assert differences==set(manifest['post_review_followup']['changed_reviewed_files'])
    if current:
        for name,expected in manifest['current_sources'].items():assert digest((R/name).read_bytes())==expected,name
    assert manifest['physical_outputs_inhibited'] and not manifest['physical_qualification']
    assert manifest['nonideal_circuit_study_included'] is False
    result=dict(passed=True,files=len(files)+1,archive_members=sum(len(v) for v in manifest['archives'].values()),
        verified_elf_images=images,current_sources_checked=current,physical_qualification=False)
    print(json.dumps(result));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report-dir',type=Path,default=R/'reports/engine/sensor-ratiometric')
    p.add_argument('--current',action='store_true');args=p.parse_args();verify(args.report_dir.resolve(),args.current)
