import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path.cwd();OUT=ROOT/'.cache/engine/flex-radio-parent/audits';OUT.mkdir(exist_ok=False)
BUILD=ROOT/'.cache/engine/flex-radio-build-001/build'
ENVIRONMENTS=('compact_n16r8_flex_dev','compact_n16r8_web','compact_a3_web','compact_a3_timing_bench')
def load(name,old,new):
 source=ROOT/'scripts'/name;original=source.read_text();assert original.count(old)==1
 adapted=original.replace(old,new);destination=OUT/name;destination.write_text(adapted)
 spec=importlib.util.spec_from_file_location(name[:-3]+'_owned',destination);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.ROOT=ROOT;module.R=ROOT;module.BUILD_ROOT=BUILD
 return module,dict(source='scripts/'+name,original_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),adapter_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),old=old,new=new,occurrences=1)
policy,p=load('audit_engine_build.py',"build=ROOT/'firmware/.pio/build'/environment","build=BUILD_ROOT/environment")
usb,u=load('audit_tuning_build.py',"build=root/'.pio/build'/environment","build=BUILD_ROOT/environment")
(OUT/'adapters.json').write_text(json.dumps(dict(passed=True,scope='Only build directory substituted, original auditing logic unchanged; ROOT/R explicitly point to live frozen project',build_root=str(BUILD),adapters=[p,u]),indent=2)+'\n')
for environment in ENVIRONMENTS:
 output=OUT/environment;output.mkdir()
 with (output/'isr.log').open('xb') as log:subprocess.run([sys.executable,'-B',str(ROOT/'scripts/audit_target_isr.py'),str(BUILD/environment/'firmware.elf'),str(output/'isr')],stdout=log,stderr=subprocess.STDOUT,check=True)
 policy.audit(environment,output/'policy')
 if environment!='compact_a3_timing_bench':(output/'usb.json').write_text(json.dumps(usb.audit(environment),indent=2)+'\n')
print('Four ISR/policy and three USB static audits passed; no device execution')
