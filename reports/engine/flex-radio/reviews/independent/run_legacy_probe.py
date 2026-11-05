from pathlib import Path
import hashlib,hmac,json,os,struct,subprocess,sys
own=Path(__file__).resolve().parent;freeze=own/(sys.argv[1]if len(sys.argv)>1 else'freeze-legacy-001');run=sys.argv[2]if len(sys.argv)>2 else'002';name='legacy-wire-'+run
env={**os.environ,'GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0','ASAN_OPTIONS':'detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1','PYTHONDONTWRITEBYTECODE':'1'}
source=own/'legacy_wire_probe.cpp';digest=hashlib.sha256(source.read_bytes()).hexdigest()
command=['c++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-MMD','-MF',str(own/(name+'.d')),'-I'+str(freeze/'firmware/include'),str(source),'-o',str(own/name)]
b=subprocess.run(command,env=env,capture_output=True,text=True)
assert b.returncode==0,b.stderr
r=subprocess.run([str(own/name)],env=env,capture_output=True)
assert r.returncode==0,r.stderr
assert digest==hashlib.sha256(source.read_bytes()).hexdigest()
(own/(name+'.bin')).write_bytes(r.stdout);position=0;vectors=[];key=bytes(range(32))
while position<len(r.stdout):
 schema,index,size,ok,padding=struct.unpack_from('<HHHBB',r.stdout,position);position+=8
 packet=r.stdout[position:position+size];position+=size
 assert ok==1 and padding==0 and size==(232 if schema<3 else 250)
 signed=packet[:-32]+hmac.digest(key,packet[:-32],'sha256')
 vectors.append({'schema':schema,'index':index,'bytes':size,'body_sha256':hashlib.sha256(packet[:-32]).hexdigest(),'signed_sha256':hashlib.sha256(signed).hexdigest()})
assert position==len(r.stdout)and len(vectors)==417
report={'compile_command':command,'compile_returncode':b.returncode,'compile_stderr':b.stderr,'run_returncode':r.returncode,'run_stderr':r.stderr.decode(),'source_sha256':digest,'capture_bytes':len(r.stdout),'capture_sha256':hashlib.sha256(r.stdout).hexdigest(),'vectors':vectors,'legacy_required_flex_gates_checked':4,'environment':{k:env[k]for k in ('GCOV_PREFIX','GCOV_PREFIX_STRIP','ASAN_OPTIONS','UBSAN_OPTIONS','PYTHONDONTWRITEBYTECODE')}}
(own/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'vectors':len(vectors),'bytes':len(r.stdout),'sha256':report['capture_sha256']}))
