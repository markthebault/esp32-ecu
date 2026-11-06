"""Publish the reviewed expanded boost fixture, including failed refinement.

This historical packet is a source overlay on BASELINE. Every output directory
must be new. The packager audits saved inputs; it never runs an ECU or engine.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from verify_boost_engine import verify


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache/engine'
BASELINE = '64d5f46fb322a90e32bbe97026000407610626d2'
PIN = '9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
BASE_SHA = '046389d754c996c34cb7e7171b1e42088f5ae6c0615133a3c5e74743f9f6d52c'
SAFE = {'.json', '.jsonl', '.py', '.cpp', '.hpp', '.h', '.c', '.m',
        '.mdl', '.d', '.log', '.txt', '.md', '.gz', '.inc', '.so', '.zip'}
SOURCES = (
    'scripts/build_speeduino_profiles_turbo.py',
    'tools/speeduino_profiles_turbo_sim.cpp',
    'tools/speeduino_profiles_turbo_runtime.py',
    'tools/test_speeduino_profiles_turbo.py',
    'tools/run_boost_engine.py',
    'tools/boost_engine_provenance.py',
    'tools/verify_boost_engine.py',
    'tools/analyse_boost_runs.py',
    'tools/diagnose_boost_sensitivity.py',
    'tools/package_expanded_boost_reference.py',
    'docs/engine-expanded-boost-reference.md',
    'docs/engine-turbo-profiles.md',
    'docs/engine-feature-coverage.md',
)
ORDINARY = (
    'ours-eight-open', 'reference-eight-open', 'reference-one-batch',
    'ours-eight-open-500', 'reference-eight-open-500', 'ours-eight-rail',
    'reference-eight-rail', 'reference-eight-open-125',
    'reference-eight-rail-zero-cap',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main(output):
    output = output.resolve()
    if output.exists():
        raise RuntimeError('Choose a new output directory')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                               text=True).strip() != BASELINE:
        raise RuntimeError('This packet overlays its explicit historical baseline')
    groups = {name: {} for name in ('sources', 'validation', 'runs')}

    def add(group, path, name):
        path, name = Path(path), str(name)
        assert path.is_file() and not path.is_symlink(), path
        assert not Path(name).is_absolute() and '..' not in Path(name).parts, name
        assert name not in groups[group], name
        groups[group][name] = path

    def tree(group, base, prefix):
        for path in sorted(base.rglob('*')):
            if path.is_file() and not path.is_symlink() and path.suffix in SAFE:
                add(group, path, Path(prefix) / path.relative_to(base))

    identities = {name: dict(bytes=(ROOT/name).stat().st_size,
                             sha256=sha(ROOT/name)) for name in SOURCES}
    for name in SOURCES:
        add('sources', ROOT/name, name)

    build = CACHE/'expanded-boost-build-003'
    compiled = read(build/'build-manifest.json')
    assert compiled['scope'] == 'production_sixteen_engine_outputs_and_raw_adc_boost_PWM'
    assert compiled['speeduino_sha'] == PIN and compiled['unit_test'] is False
    assert compiled['original_objects_reused'] == 108
    assert compiled['base_binary_sha256'] == compiled['numerical_relink_sha256'] == BASE_SHA
    assert sha(build/'speeduino-profiles-turbo') == compiled['binary_sha256']
    assert sha(build/'numerical-reference-relink') == BASE_SHA
    for key in ('locked_original_input_hashes', 'object_hashes', 'library_hashes',
                'generated_sources'):
        for name, expected in compiled[key].items():
            assert sha(name) == expected, name
    for name, expected in compiled['fixture_sources'].items():
        assert sha(ROOT/name) == sha(build/'sources'/name) == expected, name
    tree('validation', build/'sources', 'build/sources')
    tree('validation', build/'generated', 'build/generated')
    add('validation', build/'build-manifest.json', 'build/build-manifest.json')
    for index in (1, 2, 3):
        add('validation', build/f'command-{index}.log', f'build/command-{index}.log')

    native = CACHE/'expanded-boost-native-001'
    tests = read(native/'summary.json')
    assert tests['passed'] and tests['source_unchanged'] and tests['tests'] == 8
    assert tests['cases'] == 96 and tests['failures'] == tests['errors'] == 0
    assert tests['binary_sha256'] == compiled['binary_sha256']
    for name, expected in tests['source_sha256'].items():
        assert sha(ROOT/name) == expected, name
    tree('validation', native, 'native')
    add('validation', native.with_suffix('.log'), 'native.log')

    reviews = {}
    for label in ('expanded-boost-review-001', 'expanded-boost-coupling-review-001',
                  'expanded-boost-evidence-review-001'):
        base = CACHE/label
        assessment, whitelist = read(base/'assessment.json'), read(base/'whitelist.json')
        assert assessment['project_baseline'] == BASELINE
        assert assessment['status'].startswith('passed_scoped_')
        assert assessment['reviewer_processes_terminal'] is True
        for item in whitelist['files']:
            path = base/item['path']
            assert path.resolve().is_relative_to(base.resolve()), path
            assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], path
            add('validation', path, Path('independent')/label/item['path'])
        assert len(whitelist['files']) == whitelist['file_count']
        assert sum(item['bytes'] for item in whitelist['files']) == whitelist['total_bytes']
        add('validation', base/'whitelist.json', Path('independent')/label/'whitelist.json')
        reviews[label] = dict(assessment_sha256=sha(base/'assessment.json'),
                             whitelist_sha256=sha(base/'whitelist.json'),
                             status=assessment['status'], scope=assessment['scope'])

    accepted = read(CACHE/'expanded-boost-review-001/assessment.json')
    assert accepted['open_findings_in_accepted_scope'] == 0
    assert accepted['accepted_binary_sha256'] == compiled['binary_sha256']
    assert accepted['accepted_build_manifest_sha256'] == sha(build/'build-manifest.json')
    coupling = read(CACHE/'expanded-boost-coupling-review-001/assessment.json')
    assert coupling['open_audit_findings'] == 0
    assert coupling['accepted_verifier_sha256'] == sha(ROOT/'tools/verify_boost_engine.py')
    closure = read(CACHE/'expanded-boost-coupling-review-001/closure-tamper-results.json')
    assert len(closure['probes']) == 13 and all(row['rejected'] for row in closure['probes'])
    delta = read(CACHE/'expanded-boost-evidence-review-001/assessment.json')
    assert delta['open_source_or_audit_findings'] == 0
    assert delta['native_fixture_sha256'] == compiled['binary_sha256']
    for name, expected in delta['review_sources'].items():
        assert sha(ROOT/name) == expected, name
    for name, expected in delta['source_continuity']['prior_reviews_preserved'].items():
        assert sha(ROOT/name) == expected, name
    assert delta['source_continuity']['bound_inputs_unchanged'] is True

    analysis = CACHE/'expanded-boost-analysis-003'
    report = read(analysis/'comparison.json')
    assert report['analysis_source_sha256'] == sha(ROOT/'tools/analyse_boost_runs.py')
    assert delta['analysis_replay']['exact_report_bytes'] is True
    assert delta['analysis_replay']['refinement'] == report['refinement']
    assert len(report['records']) == 9 and len(report['refinement']) == 3
    assert [(row['controller'], row['coarse_us'], row['fine_us'],
             row['within_declared_two_percent']) for row in report['refinement']] == [
                 ('ours', 500, 250, True), ('speeduino', 500, 250, False),
                 ('speeduino', 250, 125, False)]
    tree('validation', analysis, 'analysis')
    rail = delta['rail_interpretation_correction']
    assert rail['verified_evidence']['raw_output_histories_byte_identical'] is True
    pair = CACHE/'expanded-boost-pair-001'
    assert sha(pair/'reference-eight-rail/edges.jsonl') == sha(pair/'reference-eight-rail-zero-cap/edges.jsonl')
    for row in rail['verified_evidence']['cases'].values():
        assert row['raw_adc_values'] == [1023] and row['production_map_values'] == [47]
        assert row['production_boost_cut_values'] == [0]

    folders = {name: pair/name for name in ORDINARY}
    folders['independent-reference-seven-open'] = CACHE/'expanded-boost-coupling-review-001/reference-seven-open'
    for step in (250, 500):
        folder = CACHE/f'expanded-boost-diagnose-001/step{step}'
        observed = read(folder/'diagnostic.json')
        assert observed['complete'] and observed['exact_ordinary_dispatcher_prefix'] is True
        assert observed['source_physics_changed'] is False
        assert observed['observer_sha256'] == sha(ROOT/'tools/diagnose_boost_sensitivity.py')
        folders[f'diagnostic-step{step}'] = folder
    cases = {}
    for name, folder in folders.items():
        result = verify(folder, current_inputs=True)
        assert result['audit_passed'] and result['post_halt_audited']
        assert result['loaded_layout_attested']
        cases[name] = result
        tree('runs', folder, name)

    manifest = dict(status='reviewed_expanded_reference_checkpoint_goal_active',
                    baseline_commit=BASELINE, goal_complete=False,
                    engine_outputs_inhibited=True, physical_operation_verified=False,
                    fitted_injector_commands=4, fitted_coil_commands=4,
                    source_identities=identities, speeduino_pin=PIN,
                    native_binary_sha256=compiled['binary_sha256'],
                    native_tests=dict(groups=8, saved_cases=96, passed=True),
                    reviews=reviews, cases=cases, refinement=report['refinement'],
                    reference_convergence_accepted=False,
                    rail_interpretation=rail['accepted_interpretation'],
                    archives={}, limits=[
                        'Uncalibrated empirical combustion/source gas graph; zero native CPU/IRQ cost',
                        'Both reference refinement checks fail the unchanged two-percent gate',
                        'Passive observer localizes differences but does not isolate a production bug',
                        'ADC1023 is rejected/held by the reference; sensor paths differ',
                        'Native engine-only halt does not disable production boost',
                        'Low-throttle PWM does not establish positive-boost or closed-loop tracking',
                        'PCB remains four injectors/four coils; complete feature parity and online tuning remain open',
                        'No physical, target/HIL, electrical, vehicle, EMI/surge, thermal, splash, RF or printed-fit qualification'])
    output.mkdir(parents=True, exist_ok=False)
    for group, files in groups.items():
        payloads = {name: dict(bytes=path.stat().st_size, sha256=sha(path))
                    for name, path in sorted(files.items())}
        archive = output/(group+'.zip')
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as stream:
            for name, path in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                stream.writestr(info, path.read_bytes(), compresslevel=9)
        with zipfile.ZipFile(archive) as stream:
            assert stream.testzip() is None and set(stream.namelist()) == set(files)
            for name, path in files.items():
                assert sha(path) == payloads[name]['sha256'] == hashlib.sha256(stream.read(name)).hexdigest()
        manifest['archives'][group] = dict(file=archive.name, bytes=archive.stat().st_size,
                                           sha256=sha(archive), payloads=payloads)

    # The public packets include the attested project shared libraries and all
    # model inputs needed for packet-only auditing. No reference executable,
    # object files, coverage data or proprietary application files are included.
    with tempfile.TemporaryDirectory(prefix='expanded-boost-packet-audit-', dir=CACHE) as temp:
        with zipfile.ZipFile(output/'runs.zip') as stream:
            stream.extractall(temp)
        for name in folders:
            assert verify(Path(temp)/name, current_inputs=False) == cases[name], name
    manifest['packet_only_audits_passed'] = len(cases)
    for name, identity in identities.items():
        assert sha(ROOT/name) == identity['sha256'], name
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    (output/'README.md').write_text(README)
    print(json.dumps(dict(output=str(output), cases=len(cases),
                          reference_convergence_accepted=False,
                          archives={key: dict(bytes=value['bytes'], files=len(value['payloads']))
                                    for key, value in manifest['archives'].items()})))


README = '''# Expanded production boost reference checkpoint

The separate native Speeduino fixture now exposes sixteen real engine-output ports plus production boost PWM, raw ADC inputs and crank/cam callbacks. Independent review passed the fixture, adapter, provenance and audit scope. The full ECU goal remains active. Normal engine outputs remain inhibited and the fitted PCB still has four injector/four coil commands.

- `sources.zip`: thirteen-file source overlay on commit `64d5f46`, with reproduction and limits.
- `validation.zip`: build/generated-adapter identities, eight native test groups with 96 saved cases, unchanged independent review histories, 13 final tamper-rejection controls, finite-step analysis and the separate delta assessment.
- `runs.zip`: nine ordinary project/reference cases, the independent seven-cylinder case and two passive observer diagnostics. Each includes source/model snapshots; project shared libraries are retained so all twelve cases can be audited after extraction. Reference executables, object/coverage files and proprietary applications are excluded.

**The reference comparison is not accepted as converged.** Both reference step-refinement checks fail the unchanged 2% gate. The observer reproduces ordinary event/trace/capture prefixes and finds different cylinder/mixture outcomes near partial-to-full sync, without isolating a production bug. Native prescribed-shaft partition invariance is a separate, narrower result.

The delta assessment supersedes the earlier coupling review's unsupported protection-cap explanation. In both reference cap settings, raw ADC1023 is rejected and production MAP holds at47kPa with boost_cut0; their complete edge histories are identical. These runs do not compare a common recognized overpressure condition. The original assessments remain byte-for-byte unchanged.

Audits recompute before/after-halt mass, energy, fuel and heat balances, replay all sparse output edges and bound capture timestamps. A passing invariant audit does not establish controller equivalence, model calibration, pressure tracking or physical operation. Reference halt stops engine schedulers only; native boost status is reported separately from the simulation-ending valve cut.

For commands and assumptions see `docs/engine-expanded-boost-reference.md` in the source overlay. Coupled reference sensitivity, turbo/map matching, remaining engine features, protected PCB expansion, supported online tuning and target/physical qualification are unfinished. No physical engine, vehicle, electrical, EMI/surge, thermal, splash, RF or printed-fit qualification is claimed.
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
