import datetime, hashlib, json, pathlib, re, struct, subprocess
ROOT = pathlib.Path('/home/mark/persospace/esp32-ecu')
OUT = ROOT / '.cache/engine/semi-architecture-final-review'
PROBES = OUT / 'policy-correction-probes'
HIST = OUT / 'final-addendum.json'
EXPECTED_HIST = 'a8aa6a1f6bffa6b7bcd59dba1a4a69be3bf88517f3ecc7d20e90f170212329c0'
PREFIX = '/home/mark/.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-'
def sha(b): return hashlib.sha256(b).hexdigest()
def rel(p): return str(p.relative_to(ROOT))
def sections(blob):
    e=struct.unpack_from('<16sHHIIIIIHHHHHH',blob,0)
    assert e[0][:5] == b'\x7fELF\x01'
    rows=[struct.unpack_from('<IIIIIIIIII',blob,e[6]+i*e[11]) for i in range(e[12])]
    names=blob[rows[e[13]][4]:rows[e[13]][4]+rows[e[13]][5]]
    return [(names[s[0]:].split(b'\0',1)[0].decode(),s) for s in rows]
def mapped_string(blob,value):
    matches=[]
    needle=value.encode()+b'\0'
    for name,s in sections(blob):
        if s[2]&2 and s[1]!=8:
            data=blob[s[4]:s[4]+s[5]]; at=data.find(needle)
            if at>=0: matches.append({'section':name,'address':hex(s[3]+at),'file_offset':s[4]+at})
    return matches
before=HIST.read_bytes(); assert sha(before)==EXPECTED_HIST
old=json.loads(before)
sources=['firmware/platformio.ini','firmware/main/engine_target.cpp','firmware/main/app.cpp','firmware/include/ecu/pins.hpp','firmware/include/ecu/idle_hardware.hpp']
source_hashes={p:sha((ROOT/p).read_bytes()) for p in sources}
assert source_hashes['firmware/main/engine_target.cpp']==old['unchanged_core_sha256']['firmware/main/engine_target.cpp']
core_checks={p:sha((ROOT/p).read_bytes())==h for p,h in old['unchanged_core_sha256'].items()}
assert all(core_checks.values())
images={}
for env in ['compact_n16r8_web','compact_a3_web','compact_a3_timing_bench']:
    elf=ROOT/'firmware/.pio/build'/env/'firmware.elf'; blob=elf.read_bytes()
    assert sha(blob)==old['final_images'][env]['elf_sha256']
    nm=subprocess.check_output([PREFIX+'nm','-n','-S','-C',str(elf)],text=True)
    relevant=[l for l in nm.splitlines() if 'engine_target' in l and any(x in l for x in ['::output_pins','::on_alarm(','::OutputIO::supervise(', 'engine_target::snapshot()'])]
    (PROBES/(env+'-symbols.txt')).write_text('\n'.join(relevant)+'\n')
    alarm=next(l for l in relevant if '::on_alarm(' in l)
    start,size,_,_=alarm.split(maxsplit=3)
    dis=subprocess.check_output([PREFIX+'objdump','-d','-C','--start-address=0x'+start,'--stop-address=0x'+format(int(start,16)+int(size,16),'x'),str(elf)],text=True)
    dispath=PROBES/(env+'-on-alarm.txt');dispath.write_text(dis)
    strings={s:mapped_string(blob,s) for s in ['DUMMY LOADS ONLY','COMPILE-TIME INHIBITED','hardware_timer_virtual_outputs','hardware_timer_dummy_loads']}
    cfg_path=elf.parent/'compile_commands.json';cfg=json.loads(cfg_path.read_text())
    command=next(x['command'] for x in cfg if x['file'].endswith('/engine_target.cpp'))
    bench=env=='compact_a3_timing_bench'
    assert bool(strings['DUMMY LOADS ONLY'])==bench
    assert bool(strings['COMPILE-TIME INHIBITED'])!=bench
    assert bool(strings['hardware_timer_virtual_outputs'])!=bench
    pins=next((l for l in relevant if '::output_pins' in l),None)
    entry={'elf':rel(elf),'elf_sha256':sha(blob),'engine_dummy_policy':bench,
      'physical_engine_write_path_compiled':bench,'mapped_policy_strings':strings,
      'on_alarm_symbol_address':'0x'+start,'on_alarm_symbol_size_bytes':int(size,16),
      'on_alarm_GPIO_literal_references':sum('<GPIO>' in l for l in dis.splitlines()),
      'snapshot_symbol_retained':any('engine_target::snapshot()' in l for l in relevant),
      'CMake_engine_target_command_contains_ECU_ENGINE_DUMMY_LOADS':('ECU_ENGINE_DUMMY_LOADS' in command),
      'CMake_command_sha256':sha(command.encode()),'symbol_artifact':rel(PROBES/(env+'-symbols.txt')),
      'disassembly_artifact':rel(dispath),'disassembly_sha256':sha(dis.encode())}
    if bench:
        assert pins and entry['on_alarm_GPIO_literal_references']>0
        addr=int(pins.split()[0],16)
        for name,s in sections(blob):
            if s[3]<=addr and addr+32<=s[3]+s[5]:
                compiled=list(struct.unpack_from('<8I',blob,s[4]+addr-s[3]));break
        assert compiled==[4,5,6,7,15,16,17,18]
        entry['compiled_output_pins']={'address':hex(addr),'section':name,'gpio_numbers':compiled}
        for needle in ['40379059:','40379062:','4037906e:','4037907d:','4037908c:','403790a9:','403790e8:']:
            assert needle in dis
        entry['write_path_evidence']={
          'armed_required_branch':'0x40379059','failed_rejection_branch':'0x40379062',
          'SAFE_N_GPIO40_check':'0x4037906e tests GPIO.in1 bit8',
          'interlock_GPIO48_check':'0x4037907d tests GPIO.in1 bit16',
          'ARM_GPIO47_set':'0x4037908c writes 0x8000 to GPIO+20 (out1_w1ts)',
          'channel_high':'0x403790a9 writes selected channel mask to GPIO+8 (out_w1ts)',
          'channel_low':'0x403790e8 writes selected channel mask to GPIO+12 (out_w1tc)',
          'gate_loss_all_low':'0x40376562..0x40376672 checks armed, then GPIO40/48, latches failed and clears ARM, all eight channels, pump/fan'}
        assert not entry['snapshot_symbol_retained']
    else:
        assert not pins and entry['on_alarm_GPIO_literal_references']==0
    images[env]=entry
report={
 'reviewed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'scope':'Narrow static source/final-ELF physical-policy evidence correction; no production edits, firmware rebuild, flashing or hardware execution.',
 'verdict':'CORRECTED_EVIDENCE: separate timing-bench image has the engine dummy-load physical write policy compiled in; both web images remain inhibited.',
 'historical_report':{'path':rel(HIST),'sha256_before':EXPECTED_HIST,'preserved_byte_for_byte':True},
 'supersedes':[{'json_pointer':'/final_images/compact_a3_timing_bench/engine_dummy_policy','historical_value':False,'correct_value':True}],
 'cause':'The CMake compile_commands.json engine_target command omits the PlatformIO SCons build_flags in all three environments. Missing ECU_ENGINE_DUMMY_LOADS there is not evidence of the compiled macro value. The old false inference is withdrawn.',
 'authoritative_evidence':'Final allocated ELF policy strings, retained internal-DRAM output_pins, emitted gated GPIO set/clear instructions, source gates, and the declared PlatformIO environment. A missing bench snapshot mode string is not an inhibition proof: engine_target::snapshot() is not retained in that ELF.',
 'final_images':images,
 'source_sha256':source_hashes,
 'previously_bound_core_sources_unchanged':core_checks,
 'source_contract':{
   'bench_environment':'firmware/platformio.ini compact_a3_timing_bench explicitly sets -DECU_ENGINE_DUMMY_LOADS=1; no ECU_IDLE_DUMMY_LOADS override is configured.',
   'engine_target':'OutputIO::write requires armed, !failed, SAFE_N and interlock for every rising write; all_low clears ARM/all eight engine channels/pump/fan. supervise requires boot interlock, healthy producer and current power/interlock, and latches failures. on_alarm independently trips/cuts on gate loss.',
   'selected_compile_gate':'firmware/main/app.cpp rejects ECU_SELECTED_N16R8 together with ECU_ENGINE_DUMMY_LOADS.',
   'idle':'ECU_IDLE_DUMMY_LOADS remains separately default0 in idle_hardware.hpp; the bench engine policy does not by itself enable channel8 accessory writes.'},
 'qualification':'Compiled physical capability in the separate dummy-load image is not physical activation or qualification. No image was flashed and no driver loading, jitter, gate latency, polarity, board fit or stack high-water was measured. Existing hardware holds remain.',
 'commands':['python3 .cache/engine/semi-architecture-final-review/policy-correction-probes/check.py',PREFIX+'nm -n -S -C <final ELF>',PREFIX+'objdump -d -C --start-address=<on_alarm> --stop-address=<on_alarm+size> <final ELF>'],
}
assert HIST.read_bytes()==before
out=OUT/'policy-correction.json';out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'report':rel(out),'sha256':sha(out.read_bytes()),'historical_report_unchanged':sha(HIST.read_bytes())==EXPECTED_HIST,'engine_dummy_policy':{k:v['engine_dummy_policy'] for k,v in images.items()},'all_previously_bound_core_hashes_match':all(core_checks.values())},indent=2))
