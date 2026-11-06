import gzip,hashlib,json,os,pathlib,shutil,struct,subprocess,sys
root=pathlib.Path('/home/mark/persospace/esp32-ecu')
own=root/'.cache/engine/shared-led-review'
build=root/sys.argv[1] if len(sys.argv)>1 else root/'.cache/engine/shared-led-build-001'
out=own/(build.name+'-audit');out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((build/'summary.json').read_text());before=json.loads((build/'sources-before.json').read_text());after=json.loads((build/'sources-after.json').read_text())
checks=0
def check(value,label):
 global checks
 checks+=1
 if not value:raise AssertionError(label)
declared_generation='--declared-generation' in sys.argv
source_differences=[p for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)]
check(meta['exit_code']==0,'build success')
if declared_generation:
 check(source_differences==['firmware/main/web_assets.hpp'] and meta['source_inputs_unchanged'] is False,'honest generation-only difference')
 check(sha(build/'web_assets.before.hpp')==before['firmware/main/web_assets.hpp'],'before generation copy')
 check(sha(build/'web_assets.current.hpp')==after['firmware/main/web_assets.hpp']==meta['generated_assets_sha256'],'compiled generated header')
else:
 check(before==after,'source receipts');check(meta['source_inputs_unchanged'],'source declaration')
cache_before=json.loads((build/'default-cache-before.json').read_text());cache_after=json.loads((build/'default-cache-after.json').read_text())
check(cache_before==cache_after,'cache receipts');check(meta['default_cache_unchanged'],'cache declaration')
from importlib.machinery import SourceFileLoader
wrapper=SourceFileLoader('owned_wrapper',str(own/'freeze-002/scripts/build_firmware_preserved.py')).load_module()
check(wrapper.tree(build/'retained-default-cache')==cache_before,'retained cache equals receipt')
for a in meta['artifacts']:check(sha(build/a['path'])==a['sha256'],'artifact '+a['path'])
nm=pathlib.Path('/home/mark/.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-nm')
records={}
html=(root/'web/index.html').read_bytes()
def compiled_ui(elf,symbol=None):
 body=elf.read_bytes();check(body[:6]==b'\x7fELF\x01\x01','ELF32 little endian')
 offset=struct.unpack_from('<I',body,32)[0];step,count,strings_index=struct.unpack_from('<HHH',body,46)
 sections=[struct.unpack_from('<IIIIIIIIII',body,offset+n*step)for n in range(count)]
 st=sections[strings_index];strings=body[st[4]:st[4]+st[5]]
 for section in sections:
  name=strings[section[0]:].split(b'\0',1)[0]
  if name==b'.flash.rodata':
   if symbol is not None:
    check(section[3]<=symbol<section[3]+section[5],'index symbol inside flash rodata')
    pos=section[4]+symbol-section[3];return body[pos:pos+len(html)+1]==html+b'\0'
   return (html+b'\0')in body[section[4]:section[4]+section[5]]
 return False
for name in meta['environments']:
 src=build/'build'/name/'firmware.elf';p=out/(name+'.elf');shutil.copy2(src,p)
 command=[str(nm),'-C',str(p)];r=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0','PYTHONDONTWRITEBYTECODE':'1'})
 check(r.returncode==0,'nm');(out/(name+'.nm')).write_text(r.stdout)
 symbol=[int(line.split()[0],16)for line in r.stdout.splitlines() if line.endswith(' ecu::web::assets::index')]
 ui=compiled_ui(p,symbol[0]if symbol else None)
 if 'embedded_UI' in meta:check(ui==(name!='compact_a3_timing_bench'),'current UI bytes in actual flash section')
 wanted=('rmt_new_tx_channel','rmt_transmit','led_channel','led_encoder','ecu::board_status::request','ecu::switch_service::(anonymous namespace)::led_acquisition')
 matches=[line for line in r.stdout.splitlines() if any(w in line for w in wanted)]
 if name.endswith('flex_dev'):
  check(not any(w in r.stdout for w in wanted[:4]),'no legacy RMT in flex build')
  check('led_acquisition' in r.stdout,'shared LED linked')
 elif name in ['compact_n16r8_web','compact_a3_web']:
  check(all(w in r.stdout for w in wanted[:4]),'legacy RMT preserved')
  check('led_acquisition' not in r.stdout,'shared LED not in legacy')
 records[name]={'elf_sha256':sha(p),'command':command,'symbols':matches,'current_UI_in_flash_rodata':ui}
for a in meta.get('elf_archives',[]):
 archive=build/a['path'];body=gzip.decompress(archive.read_bytes())
 check(sha(archive)==a['sha256'] and hashlib.sha256(body).hexdigest()==a['elf_sha256'],'archive hashes')
 check(body==(out/(a['environment']+'.elf')).read_bytes(),'lossless archived actual ELF')
for a in meta.get('generated_sdkconfigs',[]):
 if a['original_present']:check(sha(build/a['retained'])==a['original_sha256'],'original SDK config copy')
 if a.get('after_copy'):check(sha(build/a['after_copy'])==a['after_sha256'],'after SDK config copy')
current={p:sha(root/p)==h for p,h in before.items() if (root/p).is_file()}
compiled_current={p:sha(root/p)==h for p,h in after.items() if (root/p).is_file()}
report={'passed':True,'checks':checks,'build_summary_sha256':sha(build/'summary.json'),'source_receipts_equal':before==after,'declared_generation_only':declared_generation,'source_differences':source_differences,'retained_current_default_cache_verified':True,'retention_excludes_previously_deleted_caches':True,'source_hash_mismatches_now':[p for p,v in current.items() if not v],'compiled_input_mismatches_now':[p for p,v in compiled_current.items() if not v],'environments':records,'tool_sha256':sha(nm),'scope':'Read-only metadata/hash checks and nm/ELF section reads on owned target ELF copies; no ELF/device/PlatformIO execution. Retention refers to cache present after previously disclosed deletion. Declared generation exception does not relabel the original source-unchanged flag. Web UI checks compare full bytes at actual assets::index symbol in flash rodata.'}
(out/'review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'checks':checks,'source_mismatches':report['source_hash_mismatches_now']}))
