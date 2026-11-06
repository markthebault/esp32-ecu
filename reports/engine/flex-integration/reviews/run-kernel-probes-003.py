from pathlib import Path
import subprocess,os,json,hashlib
O=Path(__file__).resolve().parent;F=O/'kernel-freeze-003';C=O/'cjson-owned';env={**os.environ,'GCOV_PREFIX':str(O/'gcov'),'GCOV_PREFIX_STRIP':'0'};rows=[]
for name,src,extra,args in [
 ('parent-engine-flex-003',F/'firmware/tests/engine_flex_test.cpp',[],[]),
 ('kernel-malformed-003',O/'kernel-malformed-001.cpp',[],[]),
 ('high-gap-003',O/'high-gap-002.cpp',[],[]),
 ('context-probe-003',O/'context-probe-003.cpp',[],[]),
 ('kernel-json-003',O/'kernel-json-003.cpp',['-I'+str(C),str(C/'cJSON.o')],[str(O/'json-fixtures-003')]),
 ('off-candidate-003',O/'off-baseline-001.cpp',['-DREVIEW_NEW'],[])]:
 exe=O/name;cmd=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(F/'firmware/include'),str(src),*extra,'-o',str(exe)];b=subprocess.run(cmd,env=env,capture_output=True,text=True);(O/(name+'-build.log')).write_text(b.stdout+b.stderr);assert b.returncode==0,b.stderr
 run=subprocess.run([str(exe),*args],env=env,capture_output=True,timeout=30);(O/(name+'.log')).write_bytes(run.stdout+run.stderr);row={'name':name,'command':cmd,'run':[str(exe),*args],'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(run.stdout).hexdigest(),'returncode':run.returncode,'stderr':run.stderr.decode()}
 if name.startswith('off-'):
  row['bit_exact_baseline']=run.stdout==(O/'off-baseline-001.output').read_bytes();row['rows']=run.stdout.count(b'\n');assert row['bit_exact_baseline'];(O/'off-candidate-003.output').write_bytes(run.stdout)
 else:row['stdout']=run.stdout.decode()
 rows.append(row);print(json.dumps(row if not name.startswith('off-') else {k:v for k,v in row.items() if k not in ['command','run']},indent=2),flush=True);assert run.returncode==0 and not run.stderr
(O/'kernel-probe-results-003.json').write_text(json.dumps({'freeze_manifest_sha256':hashlib.sha256((F/'manifest.json').read_bytes()).hexdigest(),'runs':rows,'GCOV_PREFIX':env['GCOV_PREFIX'],'GCOV_PREFIX_STRIP':'0'},indent=2)+'\n')
