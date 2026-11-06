"""Build a geometry-only entry point using attested production Speeduino objects."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
from build_speeduino_flex import ROOT, PIN, BASE_SHA, digest


def build(output, source=None):
    source = Path(source or ROOT.parent / 'speeduino').resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = ROOT / '.cache/engine/speeduino-sim'
    with (base / 'build.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        manifest = base / 'build-manifest.json'
        model = json.loads(manifest.read_text())
        if (model['unit_test'] or model['speeduino_sha'] != PIN or
                model['timer_counter_bits'] != 32 or model['binary_sha256'] != BASE_SHA or
                digest(base / 'speeduino-sim') != BASE_SHA):
            raise RuntimeError('Production reference attestation failed')
        if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != PIN:
            raise RuntimeError('Reference pin changed')
        subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD', '--', 'speeduino', 'lib'], check=True)
        copied = base / ('source-' + model['archive_sha256'][:16] + '-idle-aux-v1')
        inputs = {}
        for name, expected in model['source_hashes'].items():
            path = ROOT / name if name.startswith('tools/') else copied / name
            if digest(path) != expected:
                raise RuntimeError('Changed numerical source: ' + name)
            inputs[str(path)] = expected
        for key, directory in (('header_hashes', copied), ('dependency_hashes', source)):
            for name, expected in model[key].items():
                path = directory / name
                if digest(path) != expected:
                    raise RuntimeError('Changed reference input: ' + name)
                inputs[str(path)] = expected
        original = [base / 'obj' / (name.replace('/', '_') + '.o')
                    for name in model['source_hashes'] if name != 'tools/speeduino_sim_native.hpp']
        libraries = [source / name for name in model['dependency_hashes'] if name.endswith('.a')]
        if len(original) != 109:
            raise RuntimeError('Original translation-unit set changed')
        for path in original + libraries + [manifest, base / 'speeduino-sim']:
            inputs[str(path)] = digest(path)
        commands = []

        def command(args):
            commands.append(args)
            with (output / f'command-{len(commands)}.log').open('xb') as stream:
                subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, check=True)

        tail = ['-Wl,--start-group', *map(str, libraries), '-Wl,--end-group', '-lgcov', '-pthread']
        relink = output / 'numerical-reference-relink'
        command([model['compiler'], *map(str, original), *tail, '-o', str(relink)])
        if digest(relink) != BASE_SHA:
            raise RuntimeError('Original object relink differs')
        names = ['tools/speeduino_cylinder_geometry.cpp', 'scripts/build_speeduino_cylinder_geometry.py',
                 'tools/speeduino_sim.cpp', 'scripts/build_speeduino_flex.py']
        own = {name: digest(ROOT / name) for name in names}
        for name in names:
            path = output / 'sources' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, path)
        entry = output / 'entry.o'
        command([model['compiler'], *model['compile_flags'], '-x', 'c++', '-c',
                 str(ROOT / 'tools/speeduino_cylinder_geometry.cpp'), '-o', str(entry)])
        objects = [path for path in original if path.name != 'tools_speeduino_sim.cpp.o'] + [entry]
        binary = output / 'speeduino-cylinder-geometry'
        command([model['compiler'], *map(str, objects), *tail, '-o', str(binary)])
        if any(digest(Path(name)) != expected for name, expected in inputs.items()) or any(
                digest(ROOT / name) != expected for name, expected in own.items()):
            raise RuntimeError('Source changed during build')
        result = dict(scope='production_setup_cylinder_geometry_only', speeduino_sha=PIN, unit_test=False,
                      binary_sha256=digest(binary), base_manifest_sha256=digest(manifest),
                      numerical_relink_sha256=digest(relink), locked_original_input_hashes=inputs,
                      fixture_sources=own, original_objects_reused=108, commands=commands,
                      limits=['No prescribed shaft, decoder/timer edge or engine-plant run in this probe',
                              'The legacy v0.4 pin fixture is not a sixteen-output board or GPIO witness',
                              'Effective setup fields, schedule angles and fallback are reported verbatim',
                              'No target, physical engine or electrical qualification'])
        (output / 'build-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
        return binary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    print(build(args.output, args.source))
