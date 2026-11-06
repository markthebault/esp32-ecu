#!/usr/bin/env python3
"""Freeze expanded-kernel timing, four-cylinder equivalence and reference geometry.

This is an internal-core checkpoint, not public1..8 ECU or engine-plant acceptance.
The supplied kernel binary must come from the completed sanitized firmware suite.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'cdbd534a25a3e5594292f9bc65ae6d91a1897b8a'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output, kernel_binary, reference_dir):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    kernel_binary, reference_dir = kernel_binary.resolve(), reference_dir.resolve()
    suite = json.loads((kernel_binary.parent.parent / 'suite-result.json').read_text())
    assert suite['exit_code'] == 0 and suite['sources_unchanged']
    suite_hashes = json.loads((kernel_binary.parent.parent / 'suite-source-hashes.json').read_text())
    assert all(digest(ROOT / name) == value for name, value in suite_hashes.items())
    manifest = json.loads((reference_dir / 'build-manifest.json').read_text())
    reference = reference_dir / 'speeduino-cylinder-geometry'
    assert manifest['scope'] == 'production_setup_cylinder_geometry_only' and not manifest['unit_test']
    assert digest(reference) == manifest['binary_sha256']
    assert all(digest(Path(name)) == value for name, value in manifest['locked_original_input_hashes'].items())
    assert all(digest(ROOT / name) == value for name, value in manifest['fixture_sources'].items())
    commands = []

    def execute(args, filename):
        commands.append(list(map(str, args)))
        with (output / filename).open('xb') as stream:
            subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)

    execute([str(kernel_binary), '--jsonl'], 'motored-cases.jsonl')
    cases = [json.loads(line) for line in (output / 'motored-cases.jsonl').read_text().splitlines()]
    assert cases[-1]['kind'] == 'summary' and cases[-1]['passed'] and cases[-1]['motored_cases'] == 1296
    assert len(cases) == 1297 and all(row['passed'] for row in cases)
    before = output / 'before'
    before.mkdir()
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASELINE, '--',
                                     'firmware/include/ecu', 'tools/secondary_legacy_probe.cpp'], cwd=ROOT, text=True).splitlines()
    for name in names:
        path = before / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(['git', 'show', BASELINE + ':' + name], cwd=ROOT))
    probe = 'tools/secondary_legacy_probe.cpp'
    assert (before / probe).read_bytes() == (ROOT / probe).read_bytes()
    compiler = shutil.which(os.environ.get('CXX', 'g++'))
    assert compiler
    for label, include, source in [('before', before / 'firmware/include', before / probe),
                                    ('current', ROOT / 'firmware/include', ROOT / probe)]:
        binary = output / ('legacy-' + label)
        execute([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(include),
                 str(source), '-o', str(binary)], 'legacy-' + label + '-build.log')
        execute([str(binary)], 'legacy-' + label + '.txt')
    previous, current = output / 'legacy-before.txt', output / 'legacy-current.txt'
    assert previous.read_bytes() == current.read_bytes()
    legacy_rows = len(current.read_text().splitlines())
    assert legacy_rows == 7776
    observations, differences = [], []
    for count in range(1, 9):
        for mode in ('sequential', 'wasted_cop', 'semi'):
            args = [str(reference), str(count), mode]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True, timeout=30)
            profile = json.loads(result.stdout)
            assert profile['cylinders'] == count and profile['rpm'] == 0
            assert profile['scope'] == 'production_setup_geometry_only_no_GPIO_or_engine_evidence'
            observations.append(dict(count=count, requested_mode=mode, command=args, stdout=result.stdout,
                                     stderr=result.stderr, exit_code=result.returncode, profile=profile))
            if mode == 'sequential':
                assert profile['spark_mode'] == profile['requested_spark_mode']
                assert profile['effective_injection_layout'] == profile['requested_injection_layout']
                assert profile['ignition_outputs'] == count == profile['primary_injector_outputs']
                ideal = [720 * rank / count for rank in range(count)]
                for kind in ('fuel', 'spark'):
                    actual = profile[kind + '_schedule_degrees'][:count]
                    if any(abs(a - b) > 1e-9 for a, b in zip(actual, ideal)):
                        differences.append(dict(cylinders=count, channel_kind=kind, ideal_even_fire_deg=ideal,
                                                production_schedule_deg=actual))
    (output / 'reference-observations.json').write_text(json.dumps(observations, indent=2) + '\n')
    shutil.copyfile(reference_dir / 'build-manifest.json', output / 'reference-build-manifest.json')
    for filename in ('suite-result.json', 'suite-source-hashes.json', 'firmware-tests.log'):
        shutil.copyfile(kernel_binary.parent.parent / filename, output / filename)
    paths = [*sorted((ROOT / 'firmware/include/ecu').glob('*.hpp')), ROOT / probe,
             ROOT / 'firmware/tests/engine_profiles_test.cpp', ROOT / 'tools/run_engine_profiles.py',
             ROOT / 'scripts/test_firmware.sh', ROOT / 'scripts/generate_tuning_wire.py',
             ROOT / 'tools/engine_protocol.py', ROOT / 'tools/test_engine_profile_boundaries.py',
             ROOT / 'tools/speeduino_cylinder_geometry.cpp', ROOT / 'scripts/build_speeduino_cylinder_geometry.py']
    sources = {str(path.relative_to(ROOT)): digest(path) for path in paths}
    for name in sources:
        path = output / 'current-source' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    summary = dict(kernel_cases_passed=1296, cylinder_counts=list(range(1, 9)), legacy_samples_identical=legacy_rows,
                   legacy_before_commit=BASELINE, legacy_f64_rows_sha256=digest(current),
                   max_spark_phase_error_deg=max(row['max_spark_error_deg'] for row in cases[:-1]),
                   max_injector_phase_error_deg=max(row['max_injector_error_deg'] for row in cases[:-1]),
                   reference_profiles_observed=len(observations), production_geometry_differences=differences,
                   reference_sha=manifest['speeduino_sha'], source_hashes=sources, commands=commands,
                   kernel_binary_sha256=digest(kernel_binary), compiler=compiler,
                   public_cylinder_support=[4], expanded_public_integration_complete=False,
                   generalized_engine_plant_verified=False, physical_operation_verified=False,
                   goal_complete=False, scope='Internal1..8 even-fire four-stroke controller/scheduler foundation. '
                   'Motored timing and production setup geometry, not coupled engine/physical ECU acceptance. '
                   'Current public UI/tune/USB/radio/target/PCB remain four-cylinder.')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kernel-binary', type=Path, required=True)
    parser.add_argument('--reference-dir', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output, args.kernel_binary, args.reference_dir)
    print(json.dumps({key: result[key] for key in ('kernel_cases_passed', 'legacy_samples_identical',
                                                  'reference_profiles_observed', 'public_cylinder_support')}))
