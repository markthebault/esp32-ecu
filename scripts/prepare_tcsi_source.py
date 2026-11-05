#!/usr/bin/env python3
"""Fetch/verify one pinned research source, without executing its MATLAB code.

Existing inputs are verified read-only; failures are retained for inspection.
The earlier research cache is preserved and may supply matching source bytes.
"""
import argparse,hashlib,json,sys,urllib.request
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from tcsi_mdl import PIN,TREE,ARCHIVE_BLOB,CACHE,verify_archive

def prepare(output):
 output=output.resolve()
 if output.exists():return verify_archive(output)
 output.mkdir(parents=True,exist_ok=False)
 api='https://api.github.com/repos/nkymark/TCSISimTestbed/git/'
 def document(name,url):
  body=urllib.request.urlopen(url,timeout=30).read();(output/name).write_bytes(body);return json.loads(body)
 commit=document('commit.json',api+'commits/'+PIN)
 if commit['sha']!=PIN or commit['tree']['sha']!=TREE:raise ValueError('Unexpected pinned TCSI commit')
 tree=document('tree.json',api+'trees/'+TREE+'?recursive=1')
 if tree['sha']!=TREE or tree.get('truncated'):raise ValueError('Incomplete or changed source tree')
 original=ROOT/'.cache/engine/TCSISimTestbed-66a972d.zip'
 data=original.read_bytes() if original.exists() else urllib.request.urlopen('https://raw.githubusercontent.com/nkymark/TCSISimTestbed/'+PIN+'/TCSISimTestbed.zip',timeout=30).read()
 if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=ARCHIVE_BLOB:raise ValueError('Source archive differs from pinned Git blob')
 archive=output/'TCSISimTestbed.zip';archive.write_bytes(data);source=output/'source';source.mkdir()
 with ZipFile(archive) as z:
  for name in ('Engine.mdl','EngineData.m','RunEngine.m'):(source/name).write_bytes(z.read(name))
 result=verify_archive(output)
 (output/'provenance.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=CACHE);a=p.parse_args();print(json.dumps(prepare(a.output),indent=2))
