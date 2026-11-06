from pathlib import Path
import hashlib,json,shlex
own=Path(__file__).resolve().parent;repo=own.parents[2];f=own/'freeze-final-001';m=json.loads((f/'manifest.json').read_text())['source_hashes'];changed=[]
for p,d in m.items():
 assert hashlib.sha256((f/p).read_bytes()).hexdigest()==d
 if hashlib.sha256((repo/p).read_bytes()).hexdigest()!=d:changed.append(p)
roots=[str(f),str(own/'probes')];allowed={str(own/'legacy_wire_probe.cpp')};deps=[];escapes=[]
for d in [own/'legacy-wire-003.d',own/'independent-native-001.d',*(own/'sender-001').glob('*.d')]:
 body=d.read_text().replace('\\\n',' ');allpaths=shlex.split(body.split(':',1)[1]);entries=[]
 for p in allpaths:
  p=Path(p).resolve();entries.append(str(p))
  if str(p)not in allowed and not any(str(p).startswith(root+'/')for root in roots):escapes.append(str(p))
 deps.append({'receipt':str(d.relative_to(own)),'inputs':entries})
assert not escapes,escapes
external=json.loads((f/'external-manifest.json').read_text())
for p,d in external.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==d and hashlib.sha256((f/'external/cJSON'/Path(p).name).read_bytes()).hexdigest()==d
r={'project_originals_changed_after_freeze':changed,'frozen_snapshots_stable':True,'external_originals_snapshots_stable':True,'compiler_non_system_dependency_escapes':escapes,'compiler_dependencies':deps}
(own/'source-dependency-check-001.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'changed':changed,'dependency_receipts':len(deps),'escapes':escapes}))
