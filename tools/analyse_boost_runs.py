"""Summarize actual coupled-engine traces, edge duty and refinement differences.

The report records different controllers and policies, not an equivalence claim.
Fault input overrides are kept distinct from the physical research-plant MAP.
"""
import argparse
import json
from pathlib import Path
from statistics import mean
from boost_engine_provenance import digest
from verify_boost_engine import verify


def drive_duty(edges, begin, end):
    high = False
    cursor = begin
    total = 0
    for row in edges:
        if row['ch'] != 9:
            continue
        stamp = row['time_us']
        if stamp < begin:
            high = row['high']
            continue
        if stamp > end:
            break
        total += (stamp-cursor)*high
        cursor = stamp
        high = row['high']
    total += (end-cursor)*high
    return 100*total/(end-begin)


def summarize(folder):
    result = json.loads((folder / 'result.json').read_text())
    audit = verify(folder)
    traces = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
    edges = [json.loads(line) for line in (folder / 'edges.jsonl').read_text().splitlines()]
    triggers = [json.loads(line) for line in (folder / 'trigger-stimuli.jsonl').read_text().splitlines()]
    assert sum(row['delivered'] for row in triggers) == result['trigger_edges']
    assert sum(not row['delivered'] for row in triggers) == result['suppressed_teeth']
    last = -1
    for row in triggers:
        assert last <= row['time_us'] <= round(result['duration_s']*1e6)
        assert row['slot'] < 58 and row['tooth_angle_deg'] % 6 == 0 and type(row['delivered']) is bool
        last = row['time_us']
    recent = [row for row in traces if row['time_us'] >= (result['duration_s']-1)*1e6]
    progress = json.loads((folder / 'progress.json').read_text())
    ledger = result['before_halt']['ledger']
    profile = json.loads((folder / 'tune.json').read_text())
    own = result['controller'] == 'ours'
    first_fault=next((row['time_us'] for row in traces if
        (row['control'].get('faults',0) if own else row['control']['boost_control']['boost_cut'])),None)
    interval=next((result['stimulus'].get(name) for name in
                   ('map_sensor_override_s','crank_capture_dropout_s','throttle_blip_s')
                   if result['stimulus'].get(name) is not None),None)
    fault_window=[round(value*1e6) for value in interval] if interval else None
    if fault_window is None and profile['boost_control']['cut_kpa']==140 and first_fault is not None:
        fault_window=[first_fault,round(result['duration_s']*1e6)]
    record = dict(
        path=str(folder.resolve()), controller=result['controller'], mode=result['mode'],
        scenario=result['stimulus']['scenario'], actuator=result['actuator'], step_us=result['step_us'],
        duration_s=result['duration_s'], requested_duty_pct=profile['boost_control']['open_duty']['cells'][0],
        requested_target_kpa=profile['boost_control']['target']['cells'][0],
        cut_kpa=profile['boost_control']['cut_kpa'],
        audit=audit, maximum_rpm=progress['maximum_crank_rpm'],
        maximum_physical_map_kpa=progress['maximum_map_kpa'], maximum_turbo_rad_s=progress['maximum_turbo_rad_s'],
        final_rpm=result['before_halt']['rpm'], final_map_kpa=result['before_halt']['map_kpa'],
        final_turbo_rad_s=result['before_halt']['turbo_rad_s'],
        last_second_mean_rpm=mean(row['plant_rpm'] for row in recent),
        last_second_mean_map_kpa=mean(row['gas']['map_kpa'] for row in recent),
        last_second_mean_turbo_rad_s=mean(row['gas']['turbo_rad_s'] for row in recent),
        last_second_executed_gpio_duty_pct=drive_duty(edges, round((result['duration_s']-1)*1e6), round(result['duration_s']*1e6)),
        fuel_in_mg=ledger['fuel_in_mg'], burned_chemical_j=ledger['burned_chemical_j'],
        coil_source_j=ledger['boost_valve']['coil']['source_j'],
        maximum_coil_current_a=ledger['boost_valve']['coil']['max_current_a'],
        observed_project_fault_mask=result['observed_project_fault_mask'],
        final_control=result['before_halt']['control'],
        suppressed_teeth=result['suppressed_teeth'],
        maximum_sensor_input_map_kpa=max(row['sensor_input']['map_kpa'] for row in traces),
        declared_fault_window_us=fault_window,
        fault_window_engine_rises=sum(row['high'] and row['ch'] < 8 and fault_window[0]+20000 <= row['time_us'] < fault_window[1] for row in edges) if fault_window else None,
        fault_window_boost_gpio_duty_pct=drive_duty(edges,fault_window[0]+20000,fault_window[1]) if fault_window else None,
        first_fault_snapshot_us=first_fault,
        source_hashes=result['source_hashes'],
        raw_sha256={name:digest(folder / name) for name in
                    ('result.json','progress.json','trace.jsonl','edges.jsonl','trigger-stimuli.jsonl','provenance/manifest.json')})
    return record


def compare_refinement(records):
    groups = {}
    for record in records:
        key = tuple(record[name] for name in ('controller','mode','scenario','actuator','requested_duty_pct','requested_target_kpa','duration_s','cut_kpa'))
        group = groups.setdefault(key, {})
        if record['step_us'] in group:
            raise ValueError('Duplicate experiment profile/step in comparison')
        group[record['step_us']] = record
    output = []
    keys = ('last_second_mean_rpm','last_second_mean_map_kpa','last_second_mean_turbo_rad_s','fuel_in_mg')
    for key, group in groups.items():
        for coarse, fine in ((500,250),(250,125)):
            if coarse not in group or fine not in group:
                continue
            a, b = group[coarse], group[fine]
            relative = {name:abs(a[name]-b[name])/max(abs(b[name]),1) for name in keys}
            output.append(dict(controller=key[0],mode=key[1],scenario=key[2],actuator=key[3],
                               coarse_us=coarse,fine_us=fine,relative_difference=relative,
                               within_declared_two_percent=all(value < .02 for value in relative.values()),
                               qualification='Finite profile check, not uniform order or calibration'))
    return output


def run(folders, output):
    output.mkdir(parents=True, exist_ok=False)
    records = [summarize(folder) for folder in folders]
    assert all(record['source_hashes'] == records[0]['source_hashes'] for record in records), 'Mixed executing project sources'
    report = dict(records=records,refinement=compare_refinement(records),
                  analysis_source_sha256=digest(Path(__file__)),physical_execution=False,
                  qualification=__doc__.strip())
    (output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folders', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.folders, args.output)
    print(json.dumps(dict(runs=len(report['records']),refinement=report['refinement']),indent=2))
