import hashlib,importlib.util,json,os,pathlib,subprocess
own=pathlib.Path(__file__).resolve().parent
frozen=own/'freeze-005/scripts/build_firmware_preserved.py';spec=importlib.util.spec_from_file_location('frozen_wrapper',frozen);wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
env={**os.environ,'GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0','PYTHONDONTWRITEBYTECODE':'1'}
checks=0;records=[]
def check(v,label):
 global checks
 checks+=1
 if not v:raise AssertionError(label)
model=own/'build-config-model-004'
for mode in ('positive','config_mutation'):
 p=model/('wrapper-'+mode)/'.cache/run/summary.json';x=json.loads(p.read_text())
 check(x['source_inputs_unchanged'] is True and x['generation_only_declared_output'] is True,'compile input interval stable')
 check(x['declared_generation_changes']==['firmware/main/web_assets.hpp'],'only declared stale header regenerated')
 check(json.loads((p.parent/'sources-before.json').read_text())==json.loads((p.parent/'sources-after.json').read_text()),'before/after compiler receipts')
root=model/'wrapper-config_mutation';script=root/'scripts/embed_web.py';script.write_text(script.read_text()+'(r/"firmware/main/mock.cpp").write_text("OWNED UNDECLARED GENERATION MUTATION")\n')
output=root/'.cache/illegal-generation';cmd=['python3','-B',str(root/'scripts/build_firmware_preserved.py'),'--output',str(output),'--environment','owned_fake'];p=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True);records.append({'command':cmd,'returncode':p.returncode,'stderr':p.stderr})
check(p.returncode!=0 and 'undeclared project source' in p.stderr and not(output/'build').exists(),'undeclared generator source write rejected before fake PIO')
root=model/'wrapper-missing_default';generated=root/'firmware/main/web_assets.hpp';generated.rename(generated.with_name('real-generated.hpp'));generated.symlink_to('real-generated.hpp')
output=root/'.cache/asset-symlink';cmd=['python3','-B',str(root/'scripts/build_firmware_preserved.py'),'--output',str(output),'--environment','owned_fake'];p=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True);records.append({'command':cmd,'returncode':p.returncode,'stderr':p.stderr})
check(p.returncode!=0 and 'generated-asset symlink' in p.stderr and generated.is_symlink() and not(output/'build').exists(),'historical generated symlink rejected before fake PIO')
html=(own/'freeze-005/web/index.html').read_bytes();elves=own/'shared-led-build-003-audit'
for name in ('compact_n16r8_flex_dev','compact_n16r8_web','compact_a3_web'):
 elf=elves/(name+'.elf');check(wrapper.embedded_index(elf,html),'actual owned compiled UI positive');check(not wrapper.embedded_index(elf,html+b'bad'),'wrong HTML negative')
elf=elves/'compact_a3_timing_bench.elf';check(not wrapper.embedded_index(elf,html),'nonweb ELF negative')
source=elves/'compact_n16r8_flex_dev.elf';body=source.read_bytes();check(body.count(b'.flash.rodata\0')==1,'one named rodata section')
negative=own/'other-rodata-negative.elf';negative.write_bytes(body.replace(b'.flash.rodata\0',b'.other.rodata\0'));check(html+b'\0' in negative.read_bytes() and not wrapper.embedded_index(negative,html),'matching bytes outside named flash rodata rejected')
report={'passed':True,'checks':checks,'wrapper_source_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'commands':records,'scope':'Owned fake-PIO generation contracts and read-only owned ELF checker controls; no target ELF execution, actual PlatformIO build, service, device or hardware action.'}
(own/'wrapper-generation-001.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'checks':checks}))
