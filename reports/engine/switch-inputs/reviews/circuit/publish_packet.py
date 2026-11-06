#!/usr/bin/env python3
"""Create a standalone metadata-only-reference publication packet.

Preserves this research cache. Omits manufacturer PDFs/page renders and
compiled binaries; compresses numerical text losslessly with explicit hashes.
"""
import argparse,gzip,hashlib,json
from pathlib import Path
source=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True);a=p.parse_args();out=a.destination.resolve()
assert out!=source and source not in out.parents and not out.exists();out.mkdir(parents=True)
projection=dict(source_research_manifest_sha256=hashlib.sha256((source/'artifact-manifest.json').read_bytes()).hexdigest(),references='Manufacturer PDFs/page renders remain in local research cache; publication contains primary URL/hash metadata only',compiled_binaries='omitted',omitted=[],compressed=[],modified_metadata=[])
for f in sorted(source.rglob('*')):
 if not f.is_file()or f==source/'artifact-manifest.json':continue
 rel=f.relative_to(source);data=f.read_bytes();entry=dict(path=str(rel),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
 if rel.suffix.lower()=='.pdf' or str(rel).startswith('references/render/'):
  projection['omitted'].append({**entry,'reason':'manufacturer reference remains research-cache-only'});continue
 if rel.suffix.lower()in('.o','.a','.so','.bin','.elf','.exe','.class','.jar'):
  projection['omitted'].append({**entry,'reason':'compiled binary not distributed'});continue
 dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
 if f.name=='values.txt':
  dest=dest.with_suffix('.txt.gz');compressed=gzip.compress(data,compresslevel=9,mtime=0);dest.write_bytes(compressed)
  projection['compressed'].append({**entry,'published_path':str(dest.relative_to(out)),'published_sha256':hashlib.sha256(compressed).hexdigest(),'published_bytes':len(compressed),'compression':'gzip,mtime0,lossless'});continue
 if rel in (Path('reference-index.json'),Path('references/jst-reference-index.json')):
  records=json.loads(data)
  for r in records:
   if r.get('path','').endswith('.pdf'):r['research_cache_path_not_distributed']=r.pop('path');r['distribution']='primary URL/hash metadata only'
  data=(json.dumps(records,indent=2)+'\n').encode();projection['modified_metadata'].append({**entry,'reason':'make cache-only PDF paths explicit'})
 dest.write_bytes(data)
(out/'publication-projection.json').write_text(json.dumps(projection,indent=2)+'\n')
files=[]
for f in sorted(out.rglob('*')):
 if f.is_file():
  data=f.read_bytes();files.append(dict(path=str(f.relative_to(out)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
(out/'artifact-manifest.json').write_text(json.dumps(dict(files=files),indent=2)+'\n')
print(json.dumps(dict(artifacts=len(files),omitted=len(projection['omitted']),compressed=len(projection['compressed']),manifest_sha256=hashlib.sha256((out/'artifact-manifest.json').read_bytes()).hexdigest(),published_bytes=sum(r['bytes']for r in files))))
