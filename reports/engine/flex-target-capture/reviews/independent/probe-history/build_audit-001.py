from pathlib import Path
import gzip,hashlib,json,os,shutil,stat,struct,subprocess
root=Path('/home/mark/persospace/esp32-ecu');own=root/'.cache/engine/flex-owner-review';build=root/'.cache/engine/flex-capture-build-003';out=own/'build-003-audit';out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();meta=json.loads((build/'summary.json').read_text());checks=0;records={}
def check(v,label):
 global checks
 checks+=1
 if not v:raise AssertionError(label)
def read(p):return json.loads(p.read_text())
before=read(build/'sources-before.json');after=read(build/'sources-after.json');check(meta['exit_code']==0 and meta['source_inputs_unchanged']is True and meta['default_cache_unchanged']is True,'four-env successful attestation');check(before==after,'source input receipts');check(read(build/'default-cache-before.json')==read(build/'default-cache-after.json'),'default cache receipts');check(all(sha(root/p)==h for p,h in after.items()),'current source receipts')
for a in meta['artifacts']:check(sha(build/a['path'])==a['sha256'],'actual build artifact')
nm=Path('/home/mark/.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-nm');env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0'}
html=(own/'freeze-004/web/index.html').read_bytes();js=(own/'freeze-004/web/flex_fuel.js').read_bytes()
for name in meta['environments']:
 p=out/(name+'.elf');shutil.copy2(build/'build'/name/'firmware.elf',p);c=[str(nm),'-S','-n','-C',str(p)];r=subprocess.run(c,env=env,capture_output=True,text=True);check(not r.returncode,'nm');(out/(name+'.nm')).write_text(r.stdout)
 b=p.read_bytes();check(b[:6]==b'\x7fELF\x01\x01','ELF32');off=struct.unpack_from('<I',b,32)[0];step,count,strings_index=struct.unpack_from('<HHH',b,46);headers=[struct.unpack_from('<IIIIIIIIII',b,off+n*step)for n in range(count)];h=headers[strings_index];strings=b[h[4]:h[4]+h[5]];sections={strings[h[0]:].split(b'\0',1)[0]:h for h in headers};s=sections[b'.flash.rodata']
 def exact_symbol(symbol,body):
  match=[line for line in r.stdout.splitlines() if line.endswith(' '+symbol)]
  if not match:return False
  address=int(match[0].split()[0],16);pos=s[4]+address-s[3];return s[3]<=address<s[3]+s[5] and b[pos:pos+len(body)+1]==body+b'\0'
 web=name!='compact_a3_timing_bench';check(exact_symbol('ecu::web::assets::index',html)==web,'exact compiled index symbol');check(exact_symbol('ecu::web::assets::flex_js',js)==web,'exact compiled flex-JS symbol')
 if name=='compact_n16r8_flex_dev':
  check('on_flex_capture('in r.stdout and 'flex_port' in r.stdout,'actual callback/port linked');check(not any(x in r.stdout for x in ['rmt_new_tx_channel','rmt_transmit','led_channel','led_encoder']),'legacy RMT excluded')
 elif web:check('on_flex_capture('not in r.stdout and all(x in r.stdout for x in ['rmt_new_tx_channel','rmt_transmit']),'legacy capture omitted/RMT retained')
 audit=root/'.cache/engine/flex-capture-audits-001'/name;policy=read(audit/'policy.json')if(audit/'policy.json').exists()else read(audit/'audit.json');check(policy['passed']is True and policy['elf_sha256']==sha(p),'policy actual ELF binding')
 check(policy['policy']==('gated_engine_dummy_loads_only'if not web else'engine_scheduler_physical_writes_compile_time_inhibited'),'physical scheduler policy');check(all(before.get(k)==v for k,v in policy['source_sha256'].items()),'policy source binding')
 closure=read(audit/'isr/closure.json')if(audit/'isr/closure.json').exists()else read(audit/'closure.json');check(closure['passed_static_placement']is True and not closure['failures'] and closure['elf_sha256']==sha(p),'parent ISR closure actual ELF binding')
 records[name]={'elf_sha256':sha(p),'exact_UI_at_symbols':web,'nm_command':c,'policy_sha256':sha(audit/'policy.json')if(audit/'policy.json').exists()else sha(audit/'audit.json'),'parent_ISR_root_count':len(closure['roots'])}
for a in meta.get('elf_archives',[]):
 p=build/a['path'];body=gzip.decompress(p.read_bytes());check(sha(p)==a['sha256']and hashlib.sha256(body).hexdigest()==a['elf_sha256'],'archive digests');check(body==(out/(a['environment']+'.elf')).read_bytes(),'lossless current ELF archive')
report={'passed':True,'checks':checks,'build_summary_sha256':sha(build/'summary.json'),'all_sources_and_artifacts_match':True,'new_default_cache_retention_is_not_recovery_of_prior_lost_caches':True,'environments':records,'tool_sha256':sha(nm),'scope':'Read-only actual final firmware ELF copies, sections/symbols, receipts and existing policy/placement bindings. No firmware ELF execution or physical qualification.'};(out/'review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'checks':checks}))
