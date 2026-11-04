from pathlib import Path
import copy,gzip,hashlib,json,os,shutil,subprocess,sys,time
own=Path(__file__).resolve().parent
verifier=own/(sys.argv[1]if len(sys.argv)>1 else'verify-001.py')
packet=own/(sys.argv[2]if len(sys.argv)>2 else'packet-001')
run_id=sys.argv[3]if len(sys.argv)>3 else'001'
work=own/('corrupt-'+run_id);shutil.copytree(packet,work)
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0'}
sha=lambda body:hashlib.sha256(body).hexdigest()
results=[]
def read(p):return json.loads((work/p).read_text())
def encoded(x):return(json.dumps(x,indent=2)+'\n').encode()
def case(name,changes,replay=False):
 saved={p:(work/p).read_bytes()for p in changes};manifest=(work/'artifact-manifest.json').read_bytes()
 try:
  for p,v in changes.items():(work/p).write_bytes(v)
  m=read('artifact-manifest.json')
  for row in m['artifacts']:
   p=work/row['path'];row['bytes']=p.stat().st_size;row['sha256']=sha(p.read_bytes())
  (work/'artifact-manifest.json').write_bytes(encoded(m))
  c=['python3','-B',str(verifier),'--report',str(work)]+(['--replay']if replay else[])
  start=time.monotonic();p=subprocess.run(c,env=env,capture_output=True,text=True)
  row={'case':name,'updated_outer_manifest':True,'expected':'reject','rejected':p.returncode!=0,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'command':c,'elapsed_seconds':time.monotonic()-start}
  results.append(row);print(name,'REJECTED'if row['rejected']else'ACCEPTED_UNEXPECTEDLY',flush=True)
 finally:
  for p,body in saved.items():(work/p).write_bytes(body)
  (work/'artifact-manifest.json').write_bytes(manifest)
  (own/('corruptions-'+run_id+'.json')).write_bytes(encoded({'all_rejected':all(x['rejected']for x in results),'results':results,'scope':'Owned packet only, refreshed manifests; no firmware execution. Native fixture case executes only sanitizer-built frozen native tests.'}))
x=read('summary.json');x['target_capture_producer']=True;case('overstated_scope',{'summary.json':encoded(x)})
x=read('reviews/independent/review.json');x['accepted']=False;case('missing_independent_acceptance',{'reviews/independent/review.json':encoded(x)})
x=read('reviews/independent/review.json');x['source_hashes']={};case('empty_review_bindings',{'reviews/independent/review.json':encoded(x)})
x=read('summary.json');del x['source_hashes']['firmware/include/ecu/status_led.hpp'];case('missing_required_execution_binding',{'summary.json':encoded(x)})
x=read('build/sources-before.json');del x['firmware/main/switch_service.cpp'];case('missing_required_compilation_binding',{'build/sources-before.json':encoded(x),'build/sources-after.json':encoded(x)})
x=read('build/sources-before.json');x['firmware/main/switch_service.cpp']='0'*64;case('false_compile_source_binding',{'build/sources-before.json':encoded(x),'build/sources-after.json':encoded(x)})
p='audits/compact_n16r8_flex_dev/audit.json';x=read(p);x['source_sha256']['firmware/main/engine_target.cpp']='0'*64;case('false_policy_source_binding',{p:encoded(x)})
x=read('build/summary.json');row=next(r for r in x['elf_archives']if r['environment']=='compact_n16r8_flex_dev');p='build/'+row['path'];body=gzip.decompress((work/p).read_bytes());html=(work/'sources/web/index.html').read_text().encode();assert body.count(html+b'\0')>=1;changed=html.replace(b'radioIndicatorText',b'xxxxxIndicatorText',1);assert len(changed)==len(html)and changed!=html
body=body.replace(html+b'\0',changed+b'\0');archive=gzip.compress(body,mtime=0);row['sha256']=sha(archive);row['elf_sha256']=sha(body);row['bytes']=len(archive);case('wrong_actual_compiled_UI',{'build/summary.json':encoded(x),p:archive})
p='audits/compact_n16r8_flex_dev/audit.json';x=read(p);x['elf_sha256']='0'*64;case('wrong_policy_ELF_binding',{p:encoded(x)})
p='fixtures/green_ready.json';x=read(p);x['known']=False;case('native_fixture_replay_differs',{p:encoded(x)},True)
