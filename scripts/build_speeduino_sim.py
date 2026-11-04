#!/usr/bin/env python3
"""Build a deterministic native adapter around pinned, non-UNIT_TEST Speeduino.

The external checkout is read only. Only the native timer resolution changes in
the cached source copy; the wall-clock timer implementation is replaced by our
single-threaded HAL. This is a native source execution, not AVR emulation.
"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PIN = '9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'


def build(source: Path,timer_bits=32) -> Path:
    if timer_bits not in (16,32):raise ValueError("Native timer width must be16or32")
    cache=ROOT/('.cache/engine/speeduino-sim' if timer_bits==32 else '.cache/engine/speeduino-sim16');cache.mkdir(parents=True,exist_ok=True)
    with (cache/'build.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return build_locked(source,timer_bits)


def build_locked(source: Path,timer_bits=32) -> Path:
    source = source.resolve()
    sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if sha != PIN:
        raise RuntimeError('Speeduino SHA mismatch; audit a new pin explicitly')
    # Refuse edited tracked sources rather than silently testing a different ECU.
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD', '--', 'speeduino', 'lib'], check=True)
    cache = ROOT / ('.cache/engine/speeduino-sim' if timer_bits==32 else '.cache/engine/speeduino-sim16')
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', PIN, 'speeduino', 'lib/ArduinoFake'])
    archive_hash = hashlib.sha256(archive).hexdigest()
    copy = cache / ('source-'+archive_hash[:16]+'-idle-aux-v1')
    copy.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as packed:
        members = {p.name for p in packed.getmembers() if p.isfile()}
        existing = {str(p.relative_to(copy)) for p in copy.rglob('*') if p.is_file()}
        if existing-members:
            raise RuntimeError('Unexpected files in generated reference source cache: '+str(sorted(existing-members)))
        packed.extractall(copy, filter='data')
    timer = copy / 'lib/ArduinoFake/SoftwareTimer.h'
    original_timer = timer.read_bytes()
    if original_timer.count(b'TIMER_RESOLUTION = 100UL') != 1:
        raise RuntimeError('Native HAL has changed')
    generated_timer=original_timer.replace(b'TIMER_RESOLUTION = 100UL', b'TIMER_RESOLUTION = 4UL')
    if timer_bits==16:
        if generated_timer.count(b'using counter_t = uint32_t;')!=1:raise RuntimeError('Native timer type changed')
        generated_timer=generated_timer.replace(b'using counter_t = uint32_t;',b'using counter_t = uint16_t;')
    timer.write_bytes(generated_timer)
    native_board=copy/'speeduino/board_native.cpp';original_board=native_board.read_bytes()
    old=b'uint8_t getPwmTimerResolution(void)\n{\n  return 2;\n}'
    aux_tick=16 if timer_bits==16 else 4
    if original_board.count(old)!=1:raise RuntimeError('Native PWM conversion HAL changed')
    native_board.write_bytes(original_board.replace(old,old.replace(b'return 2;',('return '+str(aux_tick)+';').encode())))
    deps = source / '.pio/libdeps/native_code_coverage'
    upstream_build = source / '.pio/build/native_code_coverage'
    if not deps.is_dir():
        raise RuntimeError('First run the pinned upstream native PlatformIO tests')
    includes = [copy / 'speeduino', copy / 'lib/ArduinoFake', deps / 'SimpleArduinoFake/src',
                deps / 'SimpleArduinoFake/src/arduino', deps / 'ArduinoNativeFake/src']
    includes += [p for lib in sorted(deps.iterdir()) if lib.is_dir()
                 for p in [lib, lib/'src', lib/'include'] if p.is_dir()]
    flags = ['-std=c++14', '-O2', '-fshort-enums', '-fexceptions', '-DUSE_LIBDIVIDE',
             '-DECU_SIM_TIMER_BITS='+str(timer_bits),'-DECU_SIM_IDLE_TICK_US='+str(aux_tick),'-DNATIVE_BOARD', '-DEXTERNAL_BOARD_H="board_native.h"', '-DARDUINO=101',
             '-DUSBCON', '-DINJ_CHANNELS=8', '-DIGN_CHANNELS=8']
    flags += ['-I'+str(p) for p in includes]
    native_header=ROOT/'tools/speeduino_sim_native.hpp'
    flags += ['-include',str(native_header)]
    sources = sorted(copy/p for p in members if p.startswith('speeduino/') and p.endswith('.cpp'))
    sources += [copy/'speeduino/speeduino.ino', copy/'lib/ArduinoFake/FakeMega.cpp',
                ROOT/'tools/speeduino_sim_hal.cpp', ROOT/'tools/speeduino_sim.cpp']
    objects = []
    source_hashes = {}
    commands = []
    libraries = sorted(p for p in upstream_build.rglob('*.a')
                       if p.name not in ('libArduinoFake.a', 'libUnity.a'))
    if not libraries:raise RuntimeError('Missing upstream native dependency archives')
    dependency_hashes = {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(deps.rglob('*')) if p.is_file() and p.suffix in ('.h','.hpp','.tpp','.inc')}
    dependency_hashes.update({str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in libraries})
    compiler = shutil.which('c++')
    compiler_version = subprocess.check_output([compiler,'--version'],text=True)
    headers = {p:hashlib.sha256((copy/p).read_bytes()).hexdigest()
               for p in sorted(members) if Path(p).suffix in ('.h','.hpp','.tpp','.inc')}
    native_header_sha=hashlib.sha256(native_header.read_bytes()).hexdigest()
    common_hash = hashlib.sha256(json.dumps([flags,headers,dependency_hashes,compiler,compiler_version,native_header_sha],sort_keys=True).encode()).hexdigest()
    source_hashes['tools/speeduino_sim_native.hpp']=native_header_sha
    for src in sources:
        key = str(src.relative_to(copy)) if src.is_relative_to(copy) else str(src.relative_to(ROOT))
        obj = cache/'obj'/(key.replace('/', '_')+'.o')
        obj.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        source_hashes[key] = digest
        # Header changes invalidate all objects through the common fingerprint.
        fingerprint = hashlib.sha256((digest+common_hash).encode()).hexdigest()
        stamp = obj.with_suffix('.sha256')
        if not obj.exists() or not stamp.exists() or stamp.read_text() != fingerprint:
            commands.append((['c++', *flags, '-x', 'c++', '-c', str(src), '-o', str(obj)], stamp, fingerprint))
        objects.append(obj)
    def compile_one(job):
        command, stamp, fingerprint = job
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        stamp.write_text(fingerprint)
    print(f'Compiling {len(commands)} of {len(objects)} production/adapter translation units', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(compile_one, commands))
    executable = cache/'speeduino-sim'
    if executable.exists() and (cache/'build-manifest.json').exists():
        previous=cache/'history'/hashlib.sha256(executable.read_bytes()).hexdigest();previous.mkdir(parents=True,exist_ok=True)
        for p in (executable,cache/'build-manifest.json'):
            if not (previous/p.name).exists():shutil.copy2(p,previous/p.name)
    temporary=cache/'speeduino-sim.new'
    subprocess.run(['c++', *map(str, objects), '-Wl,--start-group', *map(str, libraries),
                    '-Wl,--end-group', '-lgcov', '-pthread', '-o', str(temporary)], check=True)
    os.replace(temporary,executable)
    manifest = {'speeduino_sha': sha, 'unit_test': False,
                'execution': 'production setup, loop, decoder and schedulers in native process',
                'hal_changes': ['SoftwareTimer.h TIMER_RESOLUTION 100us to 4us',
                                f'native idleTimer auxiliary clock and getPwmTimerResolution aligned at {aux_tick}us; engine timers remain4us',
                                'override Uno digitalPinToInterrupt macro with Arduino Mega mapping for native GPIO callbacks',
                                'replace wall-clock timer implementation with deterministic single-thread HAL',
                                'drive production oneMSInterval every 1000 virtual microseconds']+(['SoftwareTimer.h counter_t uint32 to uint16, modulo tick, equality compare'] if timer_bits==16 else []),
                'limits': ['not AVR emulation', ('Mega-like uint16 timer counters/equality only; no CPU/register/vector emulation' if timer_bits==16 else 'native uint32 timer counters'),
                           'zero CPU execution cost; explicit main-loop cadence', 'virtual GPIO only',
                           'benchmark tooth command injects primary decoder callback directly; diagnostic input command dispatches native attached callbacks by configured edge; physical wiring untested',
                           'timer callbacks before coincident tooth callback, then production loop',
                           'fast PORT outputs observed after each4us timer tick and loop call'],
                'idle_tick_us':aux_tick,'idle_initial_compare':'unseeded default; explicit benchmark idleconfig may seed counter+1 once and reports registers; not AVR power-on emulation',
                'native_board_original_sha256':hashlib.sha256(original_board).hexdigest(),
                'timer_counter_bits':timer_bits,'timer_compare':('equality, modulo65536' if timer_bits==16 else 'upstream-native >=,32bit'),'archive_sha256':archive_hash,'source_hashes': source_hashes,
                'header_hashes':headers,'dependency_hashes':dependency_hashes,
                'compiler':compiler,'compiler_version':compiler_version,'compile_flags':flags,
                'binary_sha256':hashlib.sha256(executable.read_bytes()).hexdigest()}
    (cache/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return executable


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT.parent/'speeduino')
    parser.add_argument('--timer-bits',type=int,choices=(16,32),default=32)
    args=parser.parse_args();print(build(args.source,args.timer_bits))
