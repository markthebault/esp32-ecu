from pathlib import Path
import hashlib,json,os,subprocess,sys
own=Path(__file__).resolve().parent;freeze=own/(sys.argv[1]if len(sys.argv)>1 else'freeze-final-001');run=sys.argv[2]if len(sys.argv)>2 else'001'
env={**os.environ,'GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0','ASAN_OPTIONS':'detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1','PYTHONDONTWRITEBYTECODE':'1'}
name='independent-native-'+run;source=own/'probes/independent_native.cpp';exe=own/name
commands=[['c++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-MMD','-MF',str(exe)+'.d','-I'+str(freeze/'firmware/include'),str(source),'-lcrypto','-o',str(exe)],
 [str(exe)],[sys.executable,'-B',str(own/'probes/independent_receiver.py'),freeze.name,name+'.ndjson']]
receipt={'source_sha256':{str(p.relative_to(own)):hashlib.sha256(p.read_bytes()).hexdigest()for p in (source,own/'probes/independent_receiver.py',Path(__file__))},'freeze':freeze.name,'environment':{k:env[k]for k in ('GCOV_PREFIX','GCOV_PREFIX_STRIP','ASAN_OPTIONS','UBSAN_OPTIONS','PYTHONDONTWRITEBYTECODE')},'commands':[]}
for i,cmd in enumerate(commands):
 p=subprocess.run(cmd,env=env,capture_output=True)
 suffix=('compile','native','receiver')[i];out=own/('independent-'+run+'-'+suffix+'.log');out.write_bytes(p.stdout+p.stderr)
 if i==1:(own/(name+'.ndjson')).write_bytes(p.stdout)
 receipt['commands'].append({'command':cmd,'returncode':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(p.stderr).hexdigest(),'log':str(out.relative_to(own))})
 (own/('independent-'+run+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
 if p.returncode:print(json.dumps(receipt['commands'][-1]));sys.exit(p.returncode)
print(json.dumps({'receipt':'independent-'+run+'.json','commands':len(commands),'passed':True}))
