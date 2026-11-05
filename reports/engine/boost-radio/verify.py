"""Verify frozen schema6 payloads; optional current project source comparison."""
import argparse,gzip,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
def sha(b):return hashlib.sha256(b).hexdigest()
def safe(name):
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe payload path')
 return p.as_posix()
def verify(root,repo=None):
 m=json.loads((root/'artifact-manifest.json').read_text());names={r['path'] for r in m['files']}
 assert len(names)==len(m['files'])
 assert not any(p.is_symlink() for p in root.rglob('*'))
 assert {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==names|{'artifact-manifest.json'}
 for r in m['files']:
  b=(root/safe(r['path'])).read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256'],r['path']
 for archive in m['archives']:
  rows={r['path']:r for r in archive['payloads']};assert len(rows)==len(archive['payloads'])
  with tarfile.open(root/safe(archive['path']),'r:gz') as tar:
   members=tar.getmembers();assert len(members)==len(rows) and {x.name for x in members}==set(rows)
   for member in members:
    assert member.isfile() and safe(member.name)==member.name
    b=tar.extractfile(member).read();r=rows[member.name];assert len(b)==r['bytes'] and sha(b)==r['sha256'],member.name
 s=json.loads((root/'summary.json').read_text());assert s['checks_passed'] and not s['full_speeduino_parity'] and not s['actual_RF'] and not s['flashed']
 if repo:
  for name,digest in s['source_hashes'].items():assert sha((repo/safe(name)).read_bytes())==digest,name
 return {'passed':True,'archives':len(m['archives']),'payloads':sum(len(a['payloads']) for a in m['archives']),'live_sources_checked':bool(repo)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path);a=p.parse_args();print(json.dumps(verify(Path(__file__).resolve().parent,a.repo)))
