"""Read the pinned TCSI block graph without executing MATLAB or mask code.

This is a strict source adapter, not a general Simulink implementation. Parsing
layout does not establish numerical equivalence; executable blocks need their
own explicit implementation and independent comparisons.
"""
from dataclasses import dataclass,field
import hashlib,json,re
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'.cache/engine/tcsi-inputs-v1'
PIN='66a972d6c7206d258deb0c21b4cd6aded8a827e2'
TREE='c945d3947e6b1983f74cd2f756935935b3d03a55'
ARCHIVE_BLOB='82df9d0bd457ceb2cffbc2a1ac793feab3f2f729'
TOKEN=re.compile(r'[ \t\r]+|\#[^\n]*|"(?:\\.|[^"\\])*"|[{}\[\]\n]|[^\s{}\[\]"]+')

@dataclass
class Node:
 kind:str
 line:int
 properties:dict=field(default_factory=dict)
 children:list=field(default_factory=list)
 def get(self,key,default=None):
  values=self.properties.get(key)
  if values is None:return default
  if len(values)!=1:raise ValueError(f'Expected one {key} at line{self.line}')
  return values[0]
 def nodes(self,kind):return [n for n in self.children if n.kind==kind]
 def one(self,kind):
  values=self.nodes(kind)
  if len(values)!=1:raise ValueError(f'Expected one {kind} at line{self.line}, found{len(values)}')
  return values[0]
 def walk(self):
  yield self
  for n in self.children:yield from n.walk()

def scalar_text(tokens):
 if not tokens:raise ValueError('Missing MDL property value')
 if all(t.startswith('"') for t in tokens):return ''.join(json.loads(t) for t in tokens)
 if any(t.startswith('"') for t in tokens):raise ValueError('Mixed quoted/raw MDL value')
 return ' '.join(tokens)

def parse(text):
 """Preserve ordered child blocks and exact decoded property strings."""
 tokens=[];line=1;position=0
 for match in TOKEN.finditer(text):
  if match.start()!=position:raise ValueError(f'Unparsed MDL bytes at line{line}')
  token=match.group();position=match.end()
  if not token.startswith('#') and (not token.isspace() or token=='\n'):tokens.append((token,line))
  line+=token.count('\n')
 if position!=len(text):raise ValueError('Unparsed trailing MDL bytes')
 index=0
 def skip():
  nonlocal index
  while index<len(tokens) and tokens[index][0]=='\n':index+=1
 def body(node,nested):
  nonlocal index
  while True:
   skip()
   if index==len(tokens):
    if nested:raise ValueError(f'Unclosed MDL block at line{node.line}')
    return node
   key,where=tokens[index];index+=1
   if key=='}':
    if not nested:raise ValueError(f'Unexpected close at line{where}')
    return node
   if key in ('{','[',']') or key.startswith('"'):raise ValueError(f'Invalid MDL property name at line{where}')
   if index<len(tokens) and tokens[index][0]=='{':
    index+=1;node.children.append(body(Node(key,where),True));continue
   values=[];depth=0
   while index<len(tokens):
    token,at=tokens[index]
    if token=='\n' and depth==0:
     index+=1;skip()
     if index<len(tokens) and tokens[index][0].startswith('"'):continue
     break
    if token in ('{','}') or token==']' and depth==0:raise ValueError(f'Invalid MDL value at line{at}')
    if token=='[':depth+=1
    elif token==']':depth-=1
    if token!='\n':values.append(token)
    index+=1
   if depth:raise ValueError(f'Unclosed MDL vector at line{where}')
   
   if not values:raise ValueError(f"Missing MDL value for {key} at line{where}")
   node.properties.setdefault(key,[]).append(scalar_text(values))
 return body(Node('root',1),False)

def systems(model):
 """Yield hierarchical source paths and subsystem blocks, with no evaluation."""
 def visit(system,path,block):
  yield path,system,block
  for child in system.nodes('Block'):
   for nested in child.nodes('System'):yield from visit(nested,path+(child.get('Name'),),child)
 for root in model.nodes('Model'):yield from visit(root.one('System'),(root.get('Name'),),None)

def verify_archive(metadata=None):
 """Bind the retained archive and extracted inputs to the pinned Git tree."""
 metadata=Path(metadata or CACHE)
 commit=json.loads((metadata/'commit.json').read_text());tree=json.loads((metadata/'tree.json').read_text())
 if commit['sha']!=PIN or commit['tree']['sha']!=TREE or tree['sha']!=TREE or tree.get('truncated'):raise ValueError('TCSI source pin/tree differs')
 # Reconstruct every tree object, including the root, from its ordered entries.
 entries=tree['tree'];parents={'':TREE,**{e['path']:e['sha'] for e in entries if e['type']=='tree'}}
 if len({e['path'] for e in entries})!=len(entries):raise ValueError('Duplicate TCSI Git tree entry')
 for parent,expected in parents.items():
  rows=[e for e in entries if ('' if Path(e['path']).parent==Path('.') else Path(e['path']).parent.as_posix())==parent]
  rows.sort(key=lambda e:(Path(e['path']).name+('/' if e['type']=='tree' else '')).encode())
  raw=b''.join(e['mode'].lstrip('0').encode()+b' '+Path(e['path']).name.encode()+b'\0'+bytes.fromhex(e['sha']) for e in rows)
  if hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=expected:raise ValueError('TCSI Git tree hash differs')
 row=next(e for e in entries if e['path']=='TCSISimTestbed.zip');archive=metadata/'TCSISimTestbed.zip';data=archive.read_bytes()
 if row['sha']!=ARCHIVE_BLOB or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=ARCHIVE_BLOB:raise ValueError('TCSI archive differs from pinned blob')
 files={}
 with ZipFile(archive) as z:
  for name in ('Engine.mdl','EngineData.m','RunEngine.m'):
   content=z.read(name);local=metadata/'source'/name
   if content!=local.read_bytes():raise ValueError('Extracted TCSI source differs: '+name)
   files[name]=hashlib.sha256(content).hexdigest()
 return dict(commit=PIN,tree=TREE,archive_blob=ARCHIVE_BLOB,archive_sha256=hashlib.sha256(data).hexdigest(),files=files)

def load(metadata=None):
 metadata=Path(metadata or CACHE);provenance=verify_archive(metadata);body=(metadata/'source/Engine.mdl').read_text()
 return parse(body),provenance

if __name__=='__main__':
 model,provenance=load();rows=[]
 for path,system,block in systems(model):
  blocks=system.nodes('Block');rows.append(dict(path='/'.join(path),line=system.line,blocks=len(blocks),types=sorted({b.get('BlockType') for b in blocks})))
 print(json.dumps(dict(scope=__doc__,provenance=provenance,systems=rows),indent=2))
