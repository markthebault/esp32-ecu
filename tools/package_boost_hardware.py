#!/usr/bin/env python3
"""Freeze the reviewed inhibited boost hardware checkpoint, without fab release."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.cache/engine'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def safe(name):
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts
    return path.as_posix()


def regular(directory):
    files = sorted(path for path in directory.rglob('*') if path.is_file())
    assert not any(path.is_symlink() for path in files)
    return files


def samples(study, output):
    """Keep exact rows around transitions/peaks; never claim a full raw trace."""
    import numpy as np
    output.mkdir(parents=True, exist_ok=False)
    identity = []
    for directory in sorted(path for path in study.iterdir() if (path/'trace.tsv').exists()):
        source = directory/'trace.tsv'
        a = np.loadtxt(source, skiprows=1)
        t = a[:, 0]
        keep = (t <= 100e-6) | (t >= t[-1]-100e-6)
        keep[::500] = True
        witnesses = []
        for column, threshold in ((2, 4), (6, 1.5), (8, .001), (9, .002), (10, .002), (16, 2.4)):
            state = a[:, column] > threshold
            indices = np.flatnonzero(state[1:] != state[:-1])+1
            indices = np.unique(np.r_[indices, np.argmax(a[:, column]), np.argmin(a[:, column])])
            for index in indices:
                lo = np.searchsorted(t, t[index]-50e-6)
                hi = np.searchsorted(t, t[index]+50e-6, side='right')
                keep[lo:hi] = True
                witnesses.append(dict(column=column, row=int(index), time_s=float(t[index])))
        target = output/(directory.name+'.tsv.gz')
        header = source.open().readline().rstrip('\n')
        with gzip.open(target, 'wt') as stream:
            stream.write(header+'\n')
            np.savetxt(stream, a[keep], fmt='%.17g', delimiter='\t')
        # Selected rows retain parsed float64 values, including their timestamps.
        with gzip.open(target, 'rt') as stream:
            assert np.array_equal(np.loadtxt(stream, skiprows=1), a[keep])
        identity.append(dict(case=directory.name, full_raw_bytes=source.stat().st_size,
            full_raw_sha256=sha(source.read_bytes()), full_gzip_sha256=sha((directory/'trace.tsv.gz').read_bytes()),
            full_rows=len(a), selected_rows=int(keep.sum()), selected_sha256=sha(target.read_bytes()),
            selection='Every500th row, first/last100us, and exact rows within50us of declared threshold transitions and extrema. Full-row metrics audited separately.',
            witnesses=witnesses))
    (output/'selection.json').write_text(json.dumps(identity, indent=2)+'\n')
    return identity


def verify(output, repo=None):
    manifest = read(output/'artifact-manifest.json')
    expected = {row['path']: row for row in manifest['files']}
    assert len(expected) == len(manifest['files'])
    assert not any(path.is_symlink() for path in output.rglob('*'))
    assert {str(path.relative_to(output)) for path in regular(output)} == set(expected)|{'artifact-manifest.json'}
    for name, row in expected.items():
        data = (output/safe(name)).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256'], name
    payloads = 0
    for archive in manifest['archives']:
        rows = {row['path']: row for row in archive['payloads']}
        assert len(rows) == len(archive['payloads'])
        with tarfile.open(output/safe(archive['path']), 'r:gz') as stream:
            members = stream.getmembers()
            assert len(members) == len(rows) and {m.name for m in members} == set(rows)
            for member in members:
                assert member.isfile() and safe(member.name) == member.name
                data = stream.extractfile(member).read(); row = rows[member.name]
                assert len(data) == row['bytes'] and sha(data) == row['sha256'], member.name
        payloads += len(rows)
    summary = read(output/'summary.json')
    assert summary['checks_passed'] and not summary['full_speeduino_parity'] and not summary['physical_qualification'] and not summary['flashed']
    if repo:
        for name, digest in summary['source_hashes'].items():
            assert sha((repo/safe(name)).read_bytes()) == digest, name
    return dict(passed=True, archives=len(manifest['archives']), payloads=payloads, live_sources_checked=bool(repo))


def package(output):
    study = CACHE/'boost-circuit-full-003'
    model = read(study/'results.json')
    review = CACHE/'boost-hardware-review-003'
    assessment = read(review/'assessment.json')
    assert model['validation']['passed'] and model['source_unchanged'] and len(model['results']) == 30
    assert assessment['accepted_for_declared_native_and_conditional_circuit_scope'] and not assessment['open_findings']
    assert assessment['full_stage']['source_results_sha256'] == sha((study/'results.json').read_bytes())
    for name, digest in model['source_sha256'].items():
        assert sha(Path(name).read_bytes()) == digest, name
    output.mkdir(parents=True, exist_ok=False)
    sample_directory = CACHE/('boost-evidence-samples-'+sha(str(output).encode())[:12])
    selections = samples(study, sample_directory)
    archives = []

    def archive(name, items):
        names = set(); rows = []
        with (output/name).open('xb') as raw, gzip.GzipFile(fileobj=raw, filename='', mode='wb', mtime=0, compresslevel=9) as zipped, tarfile.open(fileobj=zipped, mode='w') as stream:
            for label, source in sorted(items):
                label = safe(label)
                assert label not in names and source.is_file() and not source.is_symlink(), label
                names.add(label); data = source.read_bytes()
                info = tarfile.TarInfo(label); info.size = len(data); info.mode = 0o644; info.mtime = 0
                stream.addfile(info, io.BytesIO(data)); rows.append(dict(path=label, bytes=len(data), sha256=sha(data)))
        archives.append(dict(path=name, payloads=rows))

    names = set()
    for directory in ('hardware/a7-boost-interface', 'hardware/boost-isolated', 'hardware/boost-control'):
        names.update(str(path.relative_to(ROOT)) for path in regular(ROOT/directory))
    names.update(('.gitattributes', 'README.md', 'docs/engine-feature-coverage.md', 'docs/engine-boost-development.md', 'docs/engine-boost-hardware.md', 'docs/engine-turbo-benchmark.md',
        'scripts/build_boost_hardware.py', 'scripts/route_boost_hardware.py', 'tools/run_boost_circuit.py', 'tools/run_idle_circuit.py', 'tools/test_boost_circuit.py', 'tools/test_boost_ui.py', 'tools/package_boost_hardware.py',
        'config/interface-guide-development.json', 'config/interface-guide.json', 'web/index.html', 'web/boost_control_logic.js', 'web/boost_control.js', 'web/idle_control_logic.js', 'web/idle_control.js', 'firmware/main/web_assets.hpp'))
    source_hashes = {name: sha((ROOT/name).read_bytes()) for name in sorted(names)}
    archive('sources.tar.gz', [(name, ROOT/name) for name in sorted(names)])

    items = []
    for label, directory, whitelist_name in [('phase1', CACHE/'boost-hardware-review-001', 'phase1-whitelist.json'), ('final', review, 'whitelist.json')]:
        whitelist = read(directory/whitelist_name)
        for row in whitelist['files']:
            path = directory/safe(row['path']); data = path.read_bytes()
            assert len(data) == row['bytes'] and sha(data) == row['sha256'], path
            items.append((label+'/'+row['path'], path))
        if not any(row['path'] == whitelist_name for row in whitelist['files']):
            items.append((label+'/'+whitelist_name, directory/whitelist_name))
    archive('independent-reviews.tar.gz', items)

    items = [('final/'+str(path.relative_to(study)), path) for path in regular(study) if path.name not in ('trace.tsv', 'trace.tsv.gz')]
    items += [('selected/'+path.name, path) for path in regular(sample_directory)]
    for label in ('boost-circuit-full-001', 'boost-circuit-full-002'):
        directory = CACHE/label
        items += [('history/'+label+'/'+str(path.relative_to(directory)), path) for path in regular(directory) if path.name not in ('trace.tsv', 'trace.tsv.gz')]
    archive('circuit-experiments.tar.gz', items)
    # Two complete critical traces remain directly downloadable. Other cases
    # publish identities, complete decks/results and explicit selected windows.
    for case, name in [('engine_edges_2', 'charged-own-full.tsv.gz'), ('engine_edges_3', 'charged-reference-full.tsv.gz')]:
        source = study/case/'trace.tsv.gz'
        assert source.stat().st_size < 50*1024**2
        shutil.copyfile(source, output/name)

    items = []
    for directory in (CACHE/'boost-native-checks-003', CACHE/'boost-native-checks-004', CACHE/'boost-copper-correction-001', CACHE/'boost-manual-route-003', CACHE/'boost-label-correction-001', CACHE/'boost-route-002', CACHE/'boost-hardware-build-011/carrier/copper-pruning', CACHE/'boost-hardware-build-011/accessory/copper-pruning'):
        items += [(str(path.relative_to(CACHE)), path) for path in regular(directory)]
    archive('native-routing-history.tar.gz', items)

    build = CACHE/'boost-hardware-firmware-001'; firmware = read(build/'summary.json')
    assert firmware['exit_code'] == 0 and firmware['default_cache_unchanged'] and firmware['source_inputs_unchanged'] and not firmware['flashed']
    for name, digest in read(build/'sources-before.json').items():
        if name.startswith(('firmware/', 'web/', 'config/')):
            assert sha((ROOT/name).read_bytes()) == digest, ('Application build source drift', name)
    items = []
    for name in ('summary.json', 'build.log', 'sources-before.json', 'sources-after.json', 'default-cache-before.json', 'default-cache-after.json'):
        items.append(('build/'+name, build/name))
    for path in regular(build/'elf-archives'):
        items.append(('elfs/'+path.name, path))
    for env in firmware['environments']:
        directory = CACHE/'boost-hardware-firmware-audits-001'/env
        isr, policy, usb = read(directory/'isr/closure.json'), read(directory/'policy/audit.json'), read(directory/'usb.json')
        assert isr['passed_static_placement'] and isr['boost_state_required'] and policy['passed'] and usb['exclusive_usb']
        assert policy['policy'] == 'engine_scheduler_physical_writes_compile_time_inhibited'
        assert isr['elf_sha256'] == policy['elf_sha256'] == usb['elf_sha256']
        image = build/'build'/env/'firmware.bin'; assert sha(image.read_bytes()) == policy['binary_sha256']
        items.append((env+'/firmware.bin', image))
        items += [('audits/'+env+'/'+str(path.relative_to(directory)), path) for path in regular(directory)]
    ui = CACHE/'boost-hardware-ui-002'; assert read(ui/'ui-tests.json')['passed']
    items += [('browser/'+str(path.relative_to(ui)), path) for path in regular(ui)]
    archive('inhibited-firmware-validation.tar.gz', items)

    figures = output/'figures'; figures.mkdir()
    for name in ('charged-cut-replay.png', 'charged-cut-replay.svg', 'plot.py', 'plot-provenance.json', 'assembly-results.json'):
        shutil.copyfile(CACHE/'boost-views-002'/name, figures/name)
    shutil.copyfile(Path(__file__), output/'verify.py')
    summary = dict(checks_passed=True, full_speeduino_parity=False, physical_qualification=False, flashed=False,
        base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        scope=assessment['scope'], native=assessment['native'], full_stage=assessment['full_stage'],
        phase1=read(CACHE/'boost-hardware-review-001/phase1-final-assessment.json')['independent_results'],
        firmware_environments=firmware['environments'], chrome_checks=len(read(ui/'ui-tests.json')['checks']),
        source_hashes=source_hashes, full_trace_rows=sum(row['full_rows'] for row in selections),
        published_selected_rows=sum(row['selected_rows'] for row in selections),
        waveform_publication='All30 full raw TSV/gzip traces remain in the local cache with independently audited identities. Two charged-fault traces are published complete; other cases include explicit selected windows, all decks/results and full raw hashes. Selection is not full-waveform acceptance.',
        release_holds=assessment['release_holds'])
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    (output/'README.md').write_text('''# Reviewed boost hardware development checkpoint

The separate A7 carrier and BOOST-DRAFT1 accessory have reviewed native CAD and30 conditional full-stage circuit cases, including actual nominal/charged-cut/overboost controller-edge prefixes. Both boards pass independent all-severity ERC/DRC/connectivity/parity checks. Source A6/IAC records remain unchanged. Physical engine outputs remain inhibited and GPIO45 is unallocated.

See [the hardware guide](../../../docs/engine-boost-hardware.md), [summary](summary.json) and [feature ledger](../../../docs/engine-feature-coverage.md). The archive contains exact source/build identities, reviewer-selected evidence, original routing findings, corrected routing and the earlier nominal-only replay tool. Independent review audited2,318,987 final raw rows. Raw controller edges and source snapshots are included with the model experiments.

[Own charged-fault full trace](charged-own-full.tsv.gz) and [reference full trace](charged-reference-full.tsv.gz) retain every original column/row. Other cases publish exact selected diagnostic windows with explicit selection rules and full raw hashes; all complete raw traces remain in the local cache. Quantitative metrics come from the complete independent audit, not the selected plots. The previous replay filter omitted control-cut causes; the corrected runner preserves them and rejects fixture shutdowns.

![Conditional charged-fault electrical replay](figures/charged-cut-replay.png)

The coil, optical threshold/pole, MOSFET/driver/supervisor and sources are conditional models. There is no engine feedback or physical timing/current/temperature guarantee. Combined RUN loading, procured-package bounds, actual minimum pulse, valve/protected branch/independent disconnect, target/HIL, ordinary-iron assembly, enclosure, RF and wider feature/tuning-application acceptance remain open. No manufacturing release is made.

Verify the closed archive inventory and optionally current project sources:

```sh
python3 reports/engine/boost-hardware/verify.py --verify-only --output reports/engine/boost-hardware --repo .
```

This verifies file/payload integrity and declared scope. It does not reproduce the physics, rerun KiCad or qualify hardware. Reproduction commands and assumptions are in the hardware guide.
''')
    manifest = dict(scope='inhibited_boost_native_and_conditional_circuit', files=[dict(path=str(path.relative_to(output)), bytes=path.stat().st_size, sha256=sha(path.read_bytes())) for path in regular(output)], archives=archives)
    (output/'artifact-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(verify(output, ROOT)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--repo', type=Path)
    args = parser.parse_args()
    if args.verify_only:
        print(json.dumps(verify(args.output.resolve(), args.repo.resolve() if args.repo else None)))
    else:
        package(args.output.resolve())
