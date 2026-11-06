"""Run declared, separate free-engine experiments for both real controllers.

Every native reference gets its own executable directory and coverage prefix.
Acceptance here means only successful completion of the listed run invariants;
feature parity, calibrated dynamics and physical qualification remain separate.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from verify_boost_engine import verify
from boost_engine_provenance import digest

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    'critical': [
        dict(name='charged-map-rail', mode='open_loop', scenario='charged_map_rail'),
        dict(name='gas-overboost', mode='open_loop', cut_kpa=140, target=130,reference_protection_rpm=0),
    ],
    'nominal': [
        dict(name='off', mode='off'),
        dict(name='open-zero', mode='open_loop', duty=0),
        dict(name='open-40', mode='open_loop'),
        dict(name='closed-150', mode='closed_loop'),
    ],
    'refinement': [
        dict(name='open-40-250', mode='open_loop', step_us=250),
        dict(name='open-40-125', mode='open_loop', step_us=125),
        dict(name='closed-150-250', mode='closed_loop', step_us=250),
    ],
    'fault': [
        dict(name='throttle-blip', mode='open_loop', scenario='throttle_blip'),
        dict(name='trigger-dropout', mode='open_loop', scenario='trigger_dropout'),
        dict(name='map-high-rail', mode='open_loop', scenario='map_high_rail'),
        dict(name='disconnected', mode='open_loop', actuator='disconnected'),
        dict(name='gate-stuck-open', mode='open_loop', actuator='stuck_gate_open'),
    ],
}


def run(output, reference, suite, jobs):
    if suite not in (*SPECS, 'all') or type(jobs) is not int or not 1 <= jobs <= 4:
        raise ValueError('Choose a declared suite and1..4 workers')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    reference = Path(reference).resolve()
    reference_manifest = reference.with_name('build-manifest.json')
    reference_sha = digest(reference)
    manifest_sha = digest(reference_manifest)
    specs = [item for group, items in SPECS.items() if suite in (group, 'all') for item in items]
    cases = []
    for spec in specs:
        for controller in ('ours', 'speeduino'):
            case = dict(duration=8, step_us=500, duty=40, target=150,cut_kpa=220,reference_protection_rpm=6500,
                        scenario='nominal', actuator='normal', **{'controller': controller})
            case.update(spec)
            case['name'] += '-' + controller
            cases.append(case)
    plan = dict(cases=cases, suite=suite, workers=jobs,
                runner_sha256=digest(ROOT / 'tools/run_boost_engine.py'),
                matrix_driver_sha256=digest(Path(__file__)),
                reference_sha256=reference_sha, reference_manifest_sha256=manifest_sha,
                physical_execution=False)
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')

    def execute(case):
        directory = output / case['name']
        directory.mkdir()
        # No shared gcov files between concurrent native instances.
        local_reference = directory / 'reference' / reference.name
        if case['controller'] == 'speeduino':
            local_reference.parent.mkdir()
            shutil.copy2(reference, local_reference)
            shutil.copy2(reference_manifest, local_reference.with_name(reference_manifest.name))
            if digest(local_reference) != reference_sha or digest(local_reference.with_name(reference_manifest.name)) != manifest_sha:
                raise RuntimeError('Reference changed while preparing a case')
        args = [sys.executable, '-B', str(ROOT / 'tools/run_boost_engine.py'),
                '--output', str(directory / 'run'), '--duration', str(case['duration']),
                '--step-us', str(case['step_us']), '--mode', case['mode'],
                '--controller', case['controller'], '--reference', str(local_reference),
                '--throttle-pct', '60', '--load-nm', '70', '--scenario', case['scenario'],
                '--actuator', case['actuator'], '--duty-pct', str(case['duty']),
                '--target-kpa', str(case['target']),'--cut-kpa',str(case['cut_kpa']),'--reference-protection-rpm',str(case['reference_protection_rpm'])]
        (directory / 'command.json').write_text(json.dumps(args, indent=2) + '\n')
        start = time.monotonic()
        with (directory / 'command.log').open('xb') as log:
            completed = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=False)
        record = dict(name=case['name'], exit_code=completed.returncode, wall_s=time.monotonic()-start)
        if completed.returncode == 0:
            try:
                record['audit'] = verify(directory / 'run', current_inputs=True)
            except Exception as error:
                record['audit_error'] = dict(type=type(error).__name__, message=str(error))
        (directory / 'audit.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
        return record

    records = []
    with ThreadPoolExecutor(max_workers=jobs) as workers:
        active = {workers.submit(execute, case): case['name'] for case in cases}
        while active:
            done, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            for future in done:
                name = active.pop(future)
                try:
                    record = future.result()
                except Exception as error:
                    record = dict(name=name, error=dict(type=type(error).__name__, message=str(error)))
                records.append(record)
                print(json.dumps(record), flush=True)
            progress = dict(completed=len(records), total=len(cases), pending=len(active), records=records)
            temporary = output / 'progress.pending'
            temporary.write_text(json.dumps(progress, indent=2) + '\n')
            temporary.replace(output / 'progress.json')
    sources = []
    for case in cases:
        file = output / case['name'] / 'run/result.json'
        if file.exists():
            sources.append(json.loads(file.read_text())['source_hashes'])
    same_sources = bool(sources) and all(item == sources[0] for item in sources)
    stable_driver = digest(ROOT / 'tools/run_boost_engine.py') == plan['runner_sha256'] and digest(Path(__file__)) == plan['matrix_driver_sha256']
    accepted = same_sources and stable_driver and len(records) == len(cases) and all(item.get('exit_code') == 0 and item.get('audit', {}).get('audit_passed') is True for item in records)
    result = dict(run_invariants_passed=accepted, same_executing_sources=same_sources,
                  stable_driver=stable_driver, records=records, physical_execution=False,
                  qualification=__doc__.strip())
    (output / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return accepted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--suite', choices=(*SPECS, 'all'), default='nominal')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    sys.exit(0 if run(args.output, args.reference, args.suite, args.jobs) else 1)
