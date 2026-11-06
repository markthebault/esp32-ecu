#!/usr/bin/env python3
"""Verify cached upstream blobs against pinned Git trees, including MSL dependencies."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
SOURCES=(('mvem','modelica-3rdparty/Modelica-MVEM','57c7aa394d70bffe6106afb2703b92bc532a05d1',
          '84f70c58f44316f440f9133beeb23b0ee19a1551'),
         ('msl','OpenModelica/OpenModelica-ModelicaStandardLibrary','72bc91df9d48f91525651ed8d1fc7bceeec67661',
          '02fd40876199909c0fd5b79a3d022097b66552cf'))


def git_hash(kind,data):
    return hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()


def verified_tree(document,root_sha):
    if document.get('truncated'):raise RuntimeError('Incomplete source Git tree')
    entries=document['tree'];by_path={e['path']:e for e in entries}
    if len(by_path)!=len(entries):raise RuntimeError('Duplicate Git tree entry')
    parents={'':root_sha,**{e['path']:e['sha'] for e in entries if e['type']=='tree'}}
    for parent,expected in parents.items():
        children=[e for e in entries if ('' if Path(e['path']).parent==Path('.') else Path(e['path']).parent.as_posix())==parent]
        children.sort(key=lambda e:(Path(e['path']).name+('/' if e['type']=='tree' else '')).encode())
        raw=b''.join(e['mode'].lstrip('0').encode()+b' '+Path(e['path']).name.encode()+b'\0'+bytes.fromhex(e['sha']) for e in children)
        if git_hash('tree',raw)!=expected:raise RuntimeError('Pinned Git tree mismatch: '+parent)
    return entries


def verify():
    cache=ROOT/'.cache/engine/modelica-mvem';result={}
    for name,repo,pin,tree_sha in SOURCES:
        tree_file=cache/(name+'-verified-tree.json')
        if not tree_file.exists():
            data=urllib.request.urlopen(f'https://api.github.com/repos/{repo}/git/trees/{pin}?recursive=1',timeout=30).read()
            tree_file.write_bytes(data)
        entries=verified_tree(json.loads(tree_file.read_text()),tree_sha)
        expected={};hashes={}
        for entry in entries:
            if entry['type']!='blob':continue
            path=entry['path']
            if name=='mvem':target=cache/'source'/path
            elif path.startswith('Modelica/'):
                target=cache/'libraries/libraries/Modelica 3.2.3+maint.om'/path.removeprefix('Modelica/')
            elif path.startswith('ModelicaServices/'):
                target=cache/'libraries/libraries/ModelicaServices 3.2.3+maint.om'/path.removeprefix('ModelicaServices/')
            elif path=='Complex.mo':target=cache/'libraries/libraries/Complex 3.2.3+maint.om/package.mo'
            else:continue
            expected[target.resolve()]=path
            data=target.read_bytes()
            if git_hash('blob',data)!=entry['sha']:raise RuntimeError('Cached research source differs from pin: '+str(target))
            hashes[path]=hashlib.sha256(data).hexdigest()
        roots=[cache/'source'] if name=='mvem' else [cache/'libraries/libraries'/f'{pkg} 3.2.3+maint.om' for pkg in ('Modelica','ModelicaServices','Complex')]
        for root in roots:
            for target in root.rglob('*'):
                if target.is_file() and target.name!='openmodelica.metadata.json' and target.resolve() not in expected:
                    raise RuntimeError('Unexpected cached research file: '+str(target))
        result[name]=dict(commit=pin,tree_sha=tree_sha,files_verified=len(hashes),
                          content_manifest_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest())
    return result


if __name__=='__main__':print(json.dumps(verify(),indent=2))
