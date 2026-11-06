#!/usr/bin/env python3
"""Audit pinned ESP32-S3 ISR code/literal placement, including reachable helpers.

Usage: python scripts/audit_target_isr.py firmware.elf output-directory [--require-boost]
This does not measure latency or prove physical safety. Driver callback
registration and runtime internal-heap allocation also require source review.
"""
from pathlib import Path
import struct,subprocess,re,json,hashlib,sys

def assertion_metadata(mapping,start):
 """Classify pointer values passed straight to the reviewed SDK assertion path.

 Loading an address from an IRAM literal is not a flash dereference. Reject
 branches, dereferences, register overwrites and unrelated calls in between.
 """
 first=mapping.get(start)
 if not first:return False
 match=re.match(r'l32r\s+(a[0-9]+),',first['instruction'])
 if not match or match[1] not in ('a10','a12','a13'):return False
 destination=match[1];pc=start
 for _ in range(12):
  x=mapping.get(pc)
  if not x:return False
  instruction=x['instruction']
  if instruction.startswith('call'):
   return bool(re.fullmatch(r'call8\s+[0-9a-f]+ <__assert_func>',instruction))
  setup=re.fullmatch(r'(l32r|movi(?:\.n)?)\s+(a[0-9]+),.*',instruction)
  if instruction not in ('or\ta1, a1, a1','nop','nop.n'):
   if not setup or setup[2] not in ('a10','a11','a12','a13'):return False
   if pc!=start and setup[2]==destination:return False
  pc+=len(x['bytes'])//2
 return False

def self_test():
 load=('0101a1','l32r\ta10, 40374400 <literal> (3c000100 <file>)')
 call=('000825','call8\t40380000 <__assert_func>')
 cases={'argument_only':([load,('201110','or\ta1, a1, a1'),call],True),
        'dereference':([load,('000a82','l8ui\ta8, a10, 0'),call],False),
        'overwrite':([load,('0a0c','movi.n\ta10, 0'),call],False),
        'branch':([load,('001a16','beqz\ta10, 40380000 <else>'),call],False),
        'unrelated_call':([load,('000825','call8\t40380000 <strlen>')],False),
        'wrong_register':([('010181','l32r\ta8, 40374400 <literal> (3c000100 <file>)'),call],False)}
 for name,(code,expected) in cases.items():
  pc=0x40370000;mapping={}
  for raw,instruction in code:
   mapping[pc]=dict(pc=pc,bytes=raw,instruction=instruction);pc+=len(raw)//2
  if assertion_metadata(mapping,0x40370000)!=expected:raise RuntimeError('Classifier fixture failed: '+name)
 print('Assertion metadata classifier: 1 positive and 5 adversarial fixtures passed')

if sys.argv[1:]==['--self-test']:self_test();raise SystemExit(0)
if len(sys.argv) not in (3,4) or len(sys.argv)==4 and sys.argv[3]!='--require-boost':raise SystemExit(__doc__)
require_boost=len(sys.argv)==4
elf=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
objdump=str(Path.home()/'.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-objdump')
nm=str(Path.home()/'.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-nm')
b=elf.read_bytes()
if b[:5]!=b'\x7fELF\x01' or b[5]!=1:raise RuntimeError('Expected little-endian ELF32')
shoff=struct.unpack_from('<I',b,32)[0];shentsize,shnum,shstr=struct.unpack_from('<HHH',b,46)
sh=[struct.unpack_from('<IIIIIIIIII',b,shoff+i*shentsize) for i in range(shnum)]
strs=b[sh[shstr][4]:sh[shstr][4]+sh[shstr][5]]
sections={strs[h[0]:].split(b'\0',1)[0].decode():h for h in sh}
syms=subprocess.check_output([nm,'-S','-n','-C',str(elf)],text=True)
functions={};names={}
for l in syms.splitlines():
 m=re.match(r'^([0-9a-f]+) ([0-9a-f]+) ([a-zA-Z]) (.*)$',l)
 if m and m[3] in 'tT':functions[int(m[1],16)]={'size':int(m[2],16),'name':m[4]}
 else:
  m0=re.match(r'^([0-9a-f]+) ([tT]) (.*)$',l)
  if m0:functions.setdefault(int(m0[1],16),{'size':0,'name':m0[3]})
 names[l.split()[-1] if l else '']=l
addresses=sorted(functions)
for i,a in enumerate(addresses[:-1]):
 if not functions[a]['size']:functions[a]['size']=addresses[i+1]-a
roots=[a for a,f in functions.items() if f['name'].startswith('ecu::engine_target::') and any('::'+name+'(' in f['name'] for name in ('on_capture','on_alarm','on_trigger_capture','on_flex_capture')) or f['name'] in ('gptimer_default_isr','mcpwm_capture_default_isr')]
instructions={};audit=[];queue=list(roots);seen=set();external=[];indirect=[];bad_lit=[];bad_loaded=[];dumps=[]
def section_for(a):
 for n,h in sections.items():
  if h[3]<=a<h[3]+h[5] and h[3]:return n
 return 'ROM' if 0x40000000<=a<0x40080000 else 'UNKNOWN'
def parse_disassembly(text):
 result=[]
 for l in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$',l)
  if m and not m[3].startswith('.') :result.append({'pc':int(m[1],16),'bytes':m[2],'instruction':m[3]})
 return result

def disasm(a,f):
 # GNU linear Xtensa disassembly can lose alignment at jump-over padding;
 # walk the actual branch/fall-through graph and restart at every missing PC.
 text=subprocess.check_output([objdump,'-d','-C',f'--start-address={a}',f'--stop-address={a+f["size"]}',str(elf)],text=True)
 cache={x['pc']:x for x in parse_disassembly(text)}
 work=[a];visited=set();result=[]
 while work:
  pc=work.pop()
  if pc in visited or pc<a or pc>=a+f['size']:continue
  if pc not in cache:
   text=subprocess.check_output([objdump,'-d','-C',f'--start-address={pc}',f'--stop-address={min(a+f["size"],pc+256)}',str(elf)],text=True)
   cache.update({x['pc']:x for x in parse_disassembly(text)})
  if pc not in cache:raise RuntimeError(f'No instruction at {pc:x}')
  x=cache[pc];visited.add(pc);result.append(x);op=x['instruction'].split()[0]
  if op.startswith(('ret','rfe','rfde','rfw')) or op in ('jx','break','break.n','ill','ill.n'):continue
  if op=='j' or op.startswith('b') and not op.startswith('break') or op.startswith('loop'):
   m=re.search(r'([0-9a-f]+) <',x['instruction'])
   if m:work.append(int(m[1],16))
   elif op=='j':raise RuntimeError(f'Unresolved jump {x}')
   if op=='j':continue
  work.append(pc+len(x['bytes'])//2)
 return sorted(result,key=lambda x:x['pc'])

while queue:
 a=queue.pop()
 if a in seen:continue
 seen.add(a)
 if a not in functions:
  external.append({'address':hex(a),'section':section_for(a)});continue
 f=functions[a];ins=disasm(a,f);instructions[a]=ins;calls=[]
 for i,x in enumerate(ins):
  l=x['instruction'];m=re.match(r'call[04812]*\s+([0-9a-f]+)',l)
  if m:
   target=int(m[1],16);calls.append({'pc':hex(x['pc']),'target':hex(target),'section':section_for(target),'name':functions.get(target,{}).get('name')});queue.append(target)
  if l.startswith('callx'):
   reg=l.split()[-1];resolved=None
   for prev in reversed(ins[max(0,i-8):i]):
    if re.match('l32r\\s+'+reg+',',prev['instruction']):
     z=re.search(r'\(([0-9a-f]+)',prev['instruction'])
     if z:resolved=int(z[1],16)
     break
   indirect.append({'caller':f['name'],'pc':hex(x['pc']),'instruction':l,'resolved':hex(resolved) if resolved is not None else None,'resolved_section':section_for(resolved) if resolved is not None else None})
  m=re.match(r'l32r\s+[^,]+, ([0-9a-f]+)',l)
  if m and section_for(int(m[1],16))!='.iram0.text':bad_lit.append({'caller':f['name'],'pc':hex(x['pc']),'instruction':l,'literal_section':section_for(int(m[1],16))})
  z=re.search(r'\(([0-9a-f]+)',l)
  if m and z and section_for(int(z[1],16)) in ('.flash.text','.flash.rodata'):bad_loaded.append({'caller':f['name'],'pc':hex(x['pc']),'instruction':l,'loaded_section':section_for(int(z[1],16))})
 audit.append({'address':hex(a),'name':f['name'],'section':section_for(a),'size':f['size'],'calls':calls})
 dumps.append(f"{a:08x} <{f['name']}>:\n"+'\n'.join(f"{x['pc']:08x}: {x['bytes']} {x['instruction']}" for x in ins))
sdk_assertions={'vPortExitCritical','xPortEnterCriticalTimeout','xQueueGenericSendFromISR',
 'xTaskRemoveFromEventList','prvIsYieldRequiredSMP','esp_crosscore_int_send',
 'prvNotifyQueueSetContainer','xTaskPriorityDisinherit'}
by_name={functions[a]['name']:{x['pc']:x for x in ins} for a,ins in instructions.items()}
metadata=[];unclassified=[]
for load in bad_loaded:
 destination=metadata if load['caller'] in sdk_assertions and assertion_metadata(by_name[load['caller']],int(load['pc'],16)) else unclassified
 destination.append(load)
sdk_assert=Path.home()/'.platformio/packages/framework-espidf/components/newlib/src/assert.c'
assert_sha=hashlib.sha256(sdk_assert.read_bytes()).hexdigest()
reviewed_assert_sha='42d25f58eae3d2b315d6e3badc291cd1423a08fcf97e16fe2eee944ad8a2397d'
report={'elf_sha256':hashlib.sha256(b).hexdigest(),'roots':[hex(x) for x in roots],'functions':audit,'external':external,'indirect_calls':indirect,'literals_outside_iram':bad_lit,'loads_of_flash_pointers':bad_loaded,
 'assertion_argument_only':metadata,'unclassified_flash_pointers':unclassified,'sdk_assert_source_sha256':assert_sha,
 'assertion_path_review':'Reviewed pinned SDK checks cache state before dereferencing file/func/expr and substitutes internal strings/stack text. Full fatal panic restores cache before flash code; no physical fail-low on SDK assertion is established.'}
(out/'closure.json').write_text(json.dumps(report,indent=2)+'\n');(out/'closure-disassembly.txt').write_text('\n\n'.join(dumps)+'\n')
print(json.dumps({'elf_sha256':report['elf_sha256'],'functions':len(audit),'external':external,
 'indirect_calls':len(indirect),'literals_outside_iram':bad_lit,
 'assertion_argument_only':len(metadata),'unclassified_flash_pointers':unclassified},indent=2))

failures=[]
if len(roots) not in (4,5,6):failures.append('Expected two timing callbacks, optional diagnostic/flex callbacks and both registered driver ISR roots')
floating=[]
for address,ins in instructions.items():
 for x in ins:
  op=x['instruction'].split()[0]
  if op.endswith(('.s','.d')) or op in ('rfr','wfr','lsi','lsiu','ssi','ssiu'):
   floating.append(dict(caller=functions[address]['name'],pc=hex(x['pc']),instruction=x['instruction']))
if floating:failures.append('Floating-point instruction in ISR closure')
for required in ('::on_capture(','::on_alarm(','gptimer_default_isr','mcpwm_capture_default_isr'):
 if not any(required in functions[a]['name'] for a in roots):failures.append('Missing required ISR root: '+required)
for function in audit:
 if function['section'] not in ('.iram0.text','ROM'):failures.append('Reachable code outside IRAM/ROM: '+function['name'])
for function in external:
 if function['section']!='ROM':failures.append('Unresolved external target outside ROM: '+function['address'])
for call in indirect:
 if call['resolved'] is not None:
  if call['resolved_section'] not in ('.iram0.text','ROM'):failures.append('Indirect call outside IRAM/ROM')
 elif call['caller'] not in ('gptimer_default_isr','mcpwm_capture_default_isr'):
  failures.append('Unresolved indirect call requires review: '+call['caller'])
if bad_lit:failures.append('Literal fetch outside IRAM')
if unclassified:failures.append('Unclassified flash pointer requires source/control-flow review')
if metadata and assert_sha!=reviewed_assert_sha:failures.append('SDK assertion source differs from independently reviewed implementation')
data=[]
for line in syms.splitlines():
 m=re.match(r'^([0-9a-f]+) ([0-9a-f]+) ([bBdDrR]) (.*)$',line)
 if m and m[4] in ('ecu::engine_target::(anonymous namespace)::executor',
                    'ecu::engine_target::(anonymous namespace)::capture_clock',
                    'ecu::engine_target::(anonymous namespace)::flex_port',
                    'ecu::engine_target::(anonymous namespace)::flex_command_ticket',
                    'ecu::engine_target::(anonymous namespace)::flex_command_live',
                    'ecu::engine_target::(anonymous namespace)::flex_channel_owned',
                    'ecu::engine_target::(anonymous namespace)::idle_executor',
                    'ecu::engine_target::(anonymous namespace)::boost_executor',
                    'ecu::engine_target::(anonymous namespace)::boost_output',
                    'ecu::engine_target::(anonymous namespace)::idle_output',
                    'ecu::engine_target::(anonymous namespace)::trigger_capture',
                    'ecu::engine_target::(anonymous namespace)::trigger_clock',
                    'ecu::engine_target::(anonymous namespace)::cam_context',
                    'ecu::engine_target::(anonymous namespace)::output',
                    'ecu::engine_target::(anonymous namespace)::output_pins',
                    'ecu::engine_target::(anonymous namespace)::lock',
                    'ecu::engine_target::(anonymous namespace)::external_epoch',
                    'ecu::engine_target::(anonymous namespace)::installed_alarm',
                    'ecu::engine_target::(anonymous namespace)::measured',
                    'ecu::engine_target::(anonymous namespace)::configuration_hold',
                    'ecu::engine_target::(anonymous namespace)::commands',
                    'ecu::engine_target::(anonymous namespace)::captures',
                    'ecu::engine_target::(anonymous namespace)::timer'):
  address=int(m[1],16);section=section_for(address)
  data.append(dict(name=m[4],address=hex(address),section=section))
  if not section.startswith('.dram'):failures.append('ISR state outside internal DRAM: '+m[4])
required_state={'executor','capture_clock','output','lock','external_epoch','installed_alarm','measured','configuration_hold','commands','captures','timer','cam_context','idle_executor','idle_output'}
if require_boost:required_state|={'boost_executor'}
if any('::on_trigger_capture(' in functions[a]['name'] for a in roots):required_state|={'trigger_capture','trigger_clock'}
if any('::on_flex_capture(' in functions[a]['name'] for a in roots):required_state|={'flex_port','flex_command_ticket','flex_command_live','flex_channel_owned'}
present={row['name'].split('::')[-1] for row in data}
for missing in sorted(required_state-present):failures.append('Required ISR state symbol not found: '+missing)
if 'flex_port' in present and not any('::on_flex_capture(' in functions[a]['name'] for a in roots):failures.append('Flex state present without registered callback root')
report.update(boost_state_required=require_boost,passed_static_placement=not failures,failures=failures,data_symbols=data,floating_point_instructions=floating,
 qualification='Static placement assistance only; assertion-only metadata is separately classified, not hidden. Driver callback targets matched to source registration. Heap allocation, indirect data accesses and physical timing require separate review/evidence.')
(out/'closure.json').write_text(json.dumps(report,indent=2)+'\n')
print('Static placement checks:', 'PASS' if not failures else 'FAIL',failures)
if failures:raise SystemExit(1)
