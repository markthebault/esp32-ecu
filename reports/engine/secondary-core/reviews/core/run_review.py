#!/usr/bin/env python3
"""Rebuild independent probes against the frozen reviewed source snapshot."""
import hashlib,json,subprocess
from pathlib import Path
D=Path(__file__).resolve().parent
F=D/'final-sources'
O=D/'final-execution'
O.mkdir(exist_ok=True)
flags=['-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,command):
 p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (O/(name+'.log')).write_text(p.stdout)
 if p.returncode:raise RuntimeError(name+': '+p.stdout)
 return {'command':command,'returncode':p.returncode,'output':p.stdout,'output_sha256':sha(O/(name+'.log'))}
results={}
results['cJSON_compile']=run('cJSON-compile',['cc',*flags[1:],'-c',str(F/'external/cJSON/cJSON.c'),'-o',str(O/'cJSON.o')])
for name,source,extra in [('core','probe.cpp',[str(O/'cJSON.o')]),('allocation','allocation_probe.cpp',['-Wl,--wrap=malloc','-Wl,--wrap=free']),('binding','binding_probe.cpp',[])]:
 cmd=['c++',*flags,'-I'+str(F/'firmware/include'),'-I'+str(F/'external/cJSON'),str(F/'review-probes'/source),*extra,'-o',str(O/name)]
 results[name+'_compile']=run(name+'-compile',cmd)
 args=sorted((F/'config/engine').glob('*.json')) if name=='core' else []
 results[name]=run(name,[str(O/name),*map(str,args)])
 results[name]['binary_sha256']=sha(O/name)
results['legacy_compile']=run('legacy-compile',['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(F/'firmware/include'),str(F/'review-probes/legacy_probe.cpp'),'-o',str(O/'legacy')])
raw=subprocess.check_output([str(O/'legacy')]);(O/'legacy.csv').write_bytes(raw)
results['legacy']={'rows':raw.count(b'\n'),'sha256':sha(O/'legacy.csv'),'binary_sha256':sha(O/'legacy'),'exact_head_match':raw==(D/'frozen-legacy.csv').read_bytes()}
assert results['legacy']['exact_head_match']
results['source_snapshots']={str(p.relative_to(F)):sha(p) for p in sorted(F.rglob('*')) if p.is_file()}
(O/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({name:results[name]['output'].strip() for name in ['core','allocation','binding']},indent=2))
print(json.dumps({'legacy':results['legacy'],'frozen_files':len(results['source_snapshots'])},indent=2))
