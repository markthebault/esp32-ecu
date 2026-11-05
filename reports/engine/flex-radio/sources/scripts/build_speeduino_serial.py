#!/usr/bin/env python3
"""Build the stopped-engine serial positive control from a verified native build.

The numerical benchmark and external checkout are not rebuilt or modified.
Production objects are reused with their original compiler flags; only the
serial fixture and an explicitly bounded600s clock copy are compiled here.
"""
import argparse,fcntl,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def build(source=None):
 source=Path(source or ROOT.parent/'speeduino').resolve();base=ROOT/'.cache/engine/speeduino-sim';cache=ROOT/'.cache/engine/speeduino-serial-sim';cache.mkdir(parents=True,exist_ok=True)
 if not base.exists():raise RuntimeError('First build scripts/build_speeduino_sim.py')
 with(cache/'build.lock').open('a+b')as lock,(base/'build.lock').open('a+b')as base_lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  fcntl.flock(base_lock,fcntl.LOCK_SH)
  manifest=base/'build-manifest.json'
  if not manifest.exists():raise RuntimeError('First build the pinned32-bit numerical adapter with scripts/build_speeduino_sim.py')
  m=json.loads(manifest.read_text())
  if m['unit_test']or m['speeduino_sha']!=PIN or m['timer_counter_bits']!=32 or digest(base/'speeduino-sim')!=m['binary_sha256']:raise RuntimeError('Numerical reference executable attestation failed')
  if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=PIN:raise RuntimeError('Reference checkout pin changed')
  subprocess.run(['git','-C',str(source),'diff','--exit-code','HEAD','--','speeduino','lib'],check=True)
  copied=base/('source-'+m['archive_sha256'][:16]+'-idle-aux-v1')
  original_source_inputs={}
  for name,sha in m['source_hashes'].items():
   path=ROOT/name if name.startswith('tools/')else copied/name
   if digest(path)!=sha:raise RuntimeError('Reference source changed: '+name)
   original_source_inputs[str(path)]=sha
  for name,sha in m['header_hashes'].items():
   if digest(copied/name)!=sha:raise RuntimeError('Reference header changed: '+name)
   original_source_inputs[str(copied/name)]=sha
  for name,sha in m['dependency_hashes'].items():
   if digest(source/name)!=sha:raise RuntimeError('Reference dependency changed: '+name)
   original_source_inputs[str(source/name)]=sha
  flags=m['compile_flags'];objects=[];original_objects=[]
  excluded={'tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp'}
  for name in m['source_hashes']:
   if name=='tools/speeduino_sim_native.hpp':continue
   obj=base/'obj'/(name.replace('/','_')+'.o')
   if not obj.is_file():raise RuntimeError('Missing attested production object: '+name)
   original_objects.append(obj)
   if name not in excluded:objects.append(obj)
  if len(objects)!=107:raise RuntimeError('Reference production translation-unit set changed')
  libraries=[source/name for name in m['dependency_hashes']if name.endswith('.a')]
  inputs={**original_source_inputs,**{str(p):digest(p)for p in original_objects+libraries+[manifest,base/'speeduino-sim']}}
  # A byte-identical relink binds the cached objects to the already attested
  # executable. Merely hashing arbitrary existing objects would not do that.
  relink=cache/'numerical-reference-relink'
  subprocess.run([m['compiler'],*map(str,original_objects),'-Wl,--start-group',*map(str,libraries),'-Wl,--end-group','-lgcov','-pthread','-o',str(relink)],check=True)
  if digest(relink)!=m['binary_sha256']:raise RuntimeError('Cached objects do not reproduce the attested numerical reference binary')
  old_hal=(ROOT/'tools/speeduino_sim_hal.cpp').read_bytes()
  if old_hal.count(b'60000000')!=1 or old_hal.count(b'exceeds60s bound')!=1:raise RuntimeError('Reference HAL bound changed')
  generated=cache/'serial_clock_hal.cpp';generated.write_bytes(old_hal.replace(b'60000000',b'600000000').replace(b'exceeds60s bound',b'exceeds600s serial-only bound'))
  adapter=ROOT/'tools/speeduino_serial_sim.cpp'
  fixture_inputs={'tools/speeduino_serial_sim.cpp':digest(adapter),'scripts/build_speeduino_serial.py':digest(Path(__file__))}
  for cpp in(adapter,generated):
   obj=cache/(cpp.stem+'.o');subprocess.run([m['compiler'],*flags,'-x','c++','-c',str(cpp),'-o',str(obj)],check=True);objects.append(obj)
  binary=cache/'speeduino-serial-sim'
  if binary.exists()and(cache/'build-manifest.json').exists():
   previous=cache/'history'/digest(binary);previous.mkdir(parents=True,exist_ok=True)
   for p in(binary,cache/'build-manifest.json'):
    if not(previous/p.name).exists():shutil.copy2(p,previous/p.name)
  temporary=cache/'speeduino-serial-sim.new'
  subprocess.run([m['compiler'],*map(str,objects),'-Wl,--start-group',*map(str,libraries),'-Wl,--end-group','-lgcov','-pthread','-o',str(temporary)],check=True);os.replace(temporary,binary)
  if any(digest(Path(name))!=sha for name,sha in inputs.items()):raise RuntimeError('Numerical reference inputs changed during serial build')
  if any(digest(ROOT/name)!=sha for name,sha in fixture_inputs.items()):raise RuntimeError('Serial fixture source changed during build')
  result=dict(scope='stopped_engine_serial_positive_control',speeduino_sha=PIN,unit_test=False,binary_sha256=digest(binary),base_manifest_sha256=digest(manifest),base_binary_sha256=m['binary_sha256'],base_source_hashes=m['source_hashes'],compile_flags=flags,numerical_relink_sha256=digest(relink),locked_original_input_hashes=inputs,
   fixture_sources=fixture_inputs,generated_hal_sha256=digest(generated),original_hal_sha256=hashlib.sha256(old_hal).hexdigest(),object_hashes={str(p):digest(p)for p in objects},library_hashes={str(p):digest(p)for p in libraries},
   io_capacity_bytes=16384,worker_sleep_ms=1,clock_limit_us=600000000,
   limits=['Wall-clock receive deadlines and virtual timer catch-up between loops; not an engine plant or CPU timing model','Only static virtual ADC values and stopped crank; no physical serial or GPIO','Actual pinned protocol quirks retained, including extra I response bytes','The numerical benchmark executable remains unchanged; coverage redirected to this cache'])
  (cache/'build-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
  if digest(base/'speeduino-sim')!=m['binary_sha256']:raise RuntimeError('Numerical benchmark changed during serial build')
  return binary
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path);args=parser.parse_args();print(build(args.source))
