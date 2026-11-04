#!/usr/bin/env python3
"""Inspect actual ELF policy/data and image size, without inferring runtime fit.

CMake compile_commands omits some PlatformIO SCons defines. Its absence of a
macro is not policy evidence. This audit uses linked code/data plus source.
"""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PREFIX=str(Path.home()/'.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def sections(blob):
 e=struct.unpack_from('<16sHHIIIIIHHHHHH',blob);assert e[0][:5]==b'\x7fELF\x01'
 rows=[struct.unpack_from('<IIIIIIIIII',blob,e[6]+i*e[11]) for i in range(e[12])];s=rows[e[13]];names=blob[s[4]:s[4]+s[5]]
 return [(names[s[0]:].split(b'\0',1)[0].decode(),s) for s in rows]
def audit(environment,output):
 output.mkdir(parents=True,exist_ok=True);build=BUILD_ROOT/environment;elf=build/'firmware.elf';image=build/'firmware.bin';blob=elf.read_bytes();mapped=sections(blob)
 nm=subprocess.check_output([PREFIX+'nm','-n','-S','-C',str(elf)],text=True);relevant=[l for l in nm.splitlines() if 'engine_target' in l and any(k in l for k in ('::on_alarm(','::output_pins','engine_target::snapshot()'))]
 alarm=next(l for l in relevant if '::on_alarm(' in l);address,size,*_=alarm.split(maxsplit=3);start=int(address,16);end=start+int(size,16)
 dis=subprocess.check_output([PREFIX+'objdump','-d','-C','--start-address='+hex(start),'--stop-address='+hex(end),str(elf)],text=True)
 (output/'on-alarm.txt').write_text(dis);(output/'symbols.txt').write_text('\n'.join(relevant)+'\n')
 strings={}
 for text in ('DUMMY LOADS ONLY','COMPILE-TIME INHIBITED','hardware_timer_virtual_outputs','hardware_timer_dummy_loads'):
  strings[text]=[dict(section=name,address=hex(s[3]+offset)) for name,s in mapped if s[2]&2 and s[1]!=8 for offset in [blob[s[4]:s[4]+s[5]].find(text.encode()+b'\0')] if offset>=0]
 bench=environment=='compact_a3_timing_bench';pins=next((l for l in relevant if '::output_pins' in l),None);gpio_refs=dis.count('<GPIO>');compiled_pins=None
 assert bool(strings['DUMMY LOADS ONLY'])==bench and bool(strings['COMPILE-TIME INHIBITED'])!=bench
 assert bool(strings['hardware_timer_virtual_outputs'])!=bench
 if bench:
  assert pins and gpio_refs>0;pin_address=int(pins.split()[0],16)
  name,s=next((name,s) for name,s in mapped if s[1]!=8 and s[3]<=pin_address and pin_address+32<=s[3]+s[5]);compiled_pins=list(struct.unpack_from('<8I',blob,s[4]+pin_address-s[3]));assert compiled_pins==[4,5,6,7,15,16,17,18]
 else:assert not pins and gpio_refs==0
 assert image.stat().st_size<=2097152
 sources=('firmware/platformio.ini','firmware/main/engine_target.cpp','firmware/main/app.cpp','firmware/include/ecu/pins.hpp','firmware/include/ecu/idle_hardware.hpp')
 report=dict(environment=environment,passed=True,elf_sha256=digest(elf),binary_sha256=digest(image),app_image_bytes=image.stat().st_size,factory_partition_bytes=2097152,
             policy='gated_engine_dummy_loads_only' if bench else 'engine_scheduler_physical_writes_compile_time_inhibited',mapped_policy_strings=strings,
             on_alarm_address=hex(start),on_alarm_size=int(size,16),on_alarm_GPIO_literal_references=gpio_refs,compiled_engine_output_pins=compiled_pins,
             source_sha256={p:digest(ROOT/p) for p in sources},allocated_sections={name:s[5] for name,s in mapped if s[2]&2},
             qualification='Linked binary/data/static image checks only. Pin initialization and fail-safe low writes are separate from scheduler actuation. No physical flashing, USB, runtime heap/stack, interrupt latency, electrical, thermal or engine qualification. CMake macro absence is not used as evidence.')
 (output/'audit.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',choices=('compact_n16r8_web','compact_a3_web','compact_a3_timing_bench'));p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(audit(a.environment,a.output),indent=2))
