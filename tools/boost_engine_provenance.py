"""Bind coupled turbo experiments to executing sources and native binaries.

The own target bridge is rebuilt separately with the loader's exact flags and
must match the actual mapped shared object byte for byte. Neither the normal
build cache nor an already loaded library is replaced. This attests a native
experiment, not ESP32 execution, physical timing or calibrated plant behavior.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RunProvenance:
    def __init__(self, output):
        self.output = Path(output) / 'provenance'
        self.output.mkdir(exist_ok=False)
        self.files = {}
        self.mapped_bridge = None
        names = {
            'tools/run_boost_engine.py', 'tools/boost_engine_provenance.py',
            'tools/target_runtime.py', 'tools/target_timing_bridge.cpp',
            'tools/engine_runtime.py', 'tools/speeduino_runtime.py',
            'tools/speeduino_turbo_runtime.py', 'tools/speeduino_turbo_sim.cpp',
            'tools/speeduino_sim.cpp', 'tools/speeduino_sim_hal.cpp',
            'tools/speeduino_sim_native.hpp', 'firmware/main/config_json.hpp',
            'config/engine/defaults.json', 'scripts/build_speeduino_turbo.py',
            'scripts/build_speeduino_flex.py', 'config/engine-profile.json',
        }
        # These imported constants determine physical cylinder/channel
        # associations. Bind both their actual loaded value and their data
        # source, so an old module cannot masquerade as the current file.
        from profile_config import LAYOUT
        from engine_geometry import INJECTOR_CHANNELS,COIL_CHANNELS,CHANNEL_EXTENT
        layout_path=ROOT/'config/engine-profile.json'
        self.track(layout_path)
        layout=json.loads(layout_path.read_text())
        if (layout!=LAYOUT or tuple(layout['injector_channels'])!=INJECTOR_CHANNELS or
                tuple(layout['coil_channels'])!=COIL_CHANNELS or
                CHANNEL_EXTENT!=max(INJECTOR_CHANNELS+COIL_CHANNELS)+1):
            raise RuntimeError('Loaded engine profile layout differs from its attested data')
        self.track(layout_path)
        # Includes imported plant/adaptor modules and imported helper modules,
        # rather than maintaining another incomplete hand-written import list.
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT / 'tools') and path.suffix == '.py':
                    names.add(str(path.relative_to(ROOT)))
        names.update(str(p.relative_to(ROOT)) for p in (ROOT / 'firmware/include').rglob('*') if p.is_file())
        self.source_hashes = {name: self.track(ROOT / name) for name in sorted(names)}
        for name in names:
            self.copy(ROOT / name, self.output / 'sources' / name)
        from tcsi_mdl import CACHE
        self.model_inputs = {}
        for path in sorted(CACHE.rglob('*')):
            if path.is_file():
                name = str(path.relative_to(CACHE))
                self.model_inputs[name] = self.track(path)
                self.copy(path, self.output / 'model-inputs' / name)
        self.record = dict(schema=1, source_hashes=self.source_hashes,loaded_engine_profile_layout=layout,
                           model_inputs=self.model_inputs, physical_execution=False,
                           python=dict(version=sys.version, executable=str(Path(sys.executable).resolve()),
                                       sha256=self.track(Path(sys.executable).resolve())),
                           platform=platform.platform())

    @staticmethod
    def copy(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(source.read_bytes())

    def track(self, path):
        path = Path(path).resolve()
        value = digest(path)
        previous = self.files.setdefault(str(path), value)
        if value != previous:
            raise RuntimeError('Experiment input changed: ' + str(path))
        return value

    def command(self, args, name):
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False, timeout=180)
        (self.output / name).write_bytes(result.stdout)
        if result.returncode:
            raise RuntimeError('Native attestation command failed; see ' + str(self.output / name))
        return result.stdout.decode(errors='replace')

    def bind_own(self, runtime):
        cjson = Path.home() / '.platformio/packages/framework-espidf/components/json/cJSON'
        for name in ('cJSON.c', 'cJSON.h'):
            self.track(cjson / name)
            self.copy(cjson / name, self.output / 'external/cJSON' / name)
        compiler = {}
        for name in ('cc', 'c++'):
            path = Path(shutil.which(name)).resolve()
            compiler[name] = dict(path=str(path), sha256=self.track(path),
                                  version=self.command([name, '--version'], name.replace('+', 'p') + '-version.txt'))
        obj = self.output / 'cJSON.o'
        rebuilt = self.output / 'libtarget_engine.so'
        commands = [
            ['cc', '-O2', '-fPIC', '-MD', '-MF', str(self.output / 'cJSON.d'),
             '-c', str(cjson / 'cJSON.c'), '-o', str(obj)],
            ['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
             '-MD', '-MF', str(self.output / 'target.d'), '-I' + str(cjson),
             '-I' + str(ROOT / 'firmware/main'), '-I' + str(ROOT / 'firmware/include'),
             str(ROOT / 'tools/target_timing_bridge.cpp'), str(obj), '-o', str(rebuilt)],
        ]
        for index, command in enumerate(commands):
            self.command(command, f'build-{index}.log')
        dependencies = {}
        for name in ('cJSON.d', 'target.d'):
            content = (self.output / name).read_text().replace('\\\n', ' ')
            for path in shlex.split(content.split(':', 1)[1]):
                dependencies[str(Path(path).resolve())] = self.track(path)
        library = Path(runtime.bridge._name).resolve()
        actual = self.track(library)
        if actual != self.track(rebuilt):
            raise RuntimeError('Loaded own bridge differs from fresh dependency-bound rebuild')
        self.mapped_bridge = runtime.bridge
        mapped = self.mapping(runtime.bridge, library)
        # Retain dynamic-library identities as well as the compiler and all
        # compiler-discovered headers, including system headers.
        linked = self.command(['ldd', str(rebuilt)], 'dynamic-libraries.txt')
        dynamic = {}
        for line in linked.splitlines():
            for word in line.split():
                if word.startswith('/') and Path(word).is_file():
                    dynamic[str(Path(word).resolve())] = self.track(word)
        self.record['own_runtime'] = dict(
            loaded_library=str(library), binary_sha256=actual,
            freshly_rebuilt_sha256=digest(rebuilt), mapped_file=mapped,
            compiler=compiler, commands=commands, dependencies=dependencies,
            dynamic_libraries=dynamic,
            build_environment={name: os.environ.get(name) for name in
                               ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH',
                                'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD')},
            qualification='Exact native shared object match; no target CPU/peripheral timing claim')

    @staticmethod
    def mapping(bridge, library):
        address = ctypes.cast(bridge.engine_create, ctypes.c_void_p).value
        for line in Path('/proc/self/maps').read_text().splitlines():
            fields = line.split(maxsplit=5)
            start, end = [int(v, 16) for v in fields[0].split('-')]
            if start <= address < end:
                if len(fields) != 6 or fields[5].endswith(' (deleted)') or Path(fields[5]).resolve() != library:
                    raise RuntimeError('Own controller function is not in the declared mapped file')
                status = library.stat()
                major, minor = [int(v, 16) for v in fields[3].split(':')]
                if int(fields[4]) != status.st_ino or (major, minor) != (os.major(status.st_dev), os.minor(status.st_dev)):
                    raise RuntimeError('Own mapped library identity changed')
                return dict(path=str(library), device=fields[3], inode=status.st_ino,
                            symbol='engine_create', mapping_permissions=fields[1])
        raise RuntimeError('Cannot identify actual mapped own controller')

    def bind_reference(self, executable):
        executable = Path(executable).resolve()
        manifest = executable.with_name('build-manifest.json')
        reference = json.loads(manifest.read_text())
        binary_hash = self.track(executable)
        if binary_hash != reference['binary_sha256']:
            raise RuntimeError('Reference executable differs from its manifest')
        for name, expected in reference['locked_original_input_hashes'].items():
            if self.track(name) != expected:
                raise RuntimeError('Changed original production build input: ' + name)
        for name, expected in reference['fixture_sources'].items():
            if self.track(ROOT / name) != expected:
                raise RuntimeError('Changed reference fixture source: ' + name)
            if name not in self.source_hashes:
                self.source_hashes[name] = expected
                self.copy(ROOT / name, self.output / 'sources' / name)
        generated = {}
        for name, expected in reference.get('generated_sources', {}).items():
            if self.track(name) != expected:
                raise RuntimeError('Changed generated reference adapter: ' + name)
            snapshot = Path('reference-generated') / Path(name).name
            self.copy(Path(name), self.output / snapshot)
            generated[name] = dict(sha256=expected, snapshot=str(snapshot))
        self.copy(manifest, self.output / 'reference-build-manifest.json')
        self.record['reference_runtime'] = dict(executable=str(executable), binary_sha256=binary_hash,
                                               manifest_sha256=self.track(manifest),
                                               source_pin=reference['speeduino_sha'],generated_inputs=generated)

    def verify(self):
        for name, expected in self.files.items():
            if digest(name) != expected:
                raise RuntimeError('Experiment input changed: ' + name)
        if self.mapped_bridge is not None:
            self.mapping(self.mapped_bridge, Path(self.record['own_runtime']['loaded_library']))

    def save(self):
        self.verify()
        self.record['stable_input_hashes'] = self.files
        with (self.output / 'manifest.json').open('x') as stream:
            stream.write(json.dumps(self.record, indent=2, allow_nan=False) + '\n')
        return digest(self.output / 'manifest.json')
