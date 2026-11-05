"""Audit consumed output edges, coherent snapshots and native-run provenance.

Passing this audit establishes the listed research-run invariants only. It does
not accept an ECU feature, an engine calibration, a controller match or hardware.
"""
import argparse
import json
from pathlib import Path
from boost_engine_provenance import digest


def verify(folder, current_inputs=False):
    folder = Path(folder)
    result = json.loads((folder / 'result.json').read_text())
    manifest_path = folder / 'provenance/manifest.json'
    assert digest(manifest_path) == result['provenance_manifest_sha256'], 'Provenance manifest digest'
    manifest = json.loads(manifest_path.read_text())
    assert digest(folder/'tune.json') == manifest['requested_tune_sha256'], 'Requested tune identity'
    assert manifest['source_hashes'] == result['source_hashes'], 'Source inventory'
    for name, expected in manifest['source_hashes'].items():
        assert digest(folder / 'provenance/sources' / name) == expected, name
    for name, expected in manifest['model_inputs'].items():
        assert digest(folder / 'provenance/model-inputs' / name) == expected, name
    if current_inputs:
        for name, expected in manifest['stable_input_hashes'].items():
            assert digest(name) == expected, name
    own = result['controller'] == 'ours'
    assert result['controller'] in ('ours', 'speeduino') and result['completed'] is True
    assert result['physical_execution'] is False and manifest['physical_execution'] is False
    assert result['production_speeduino_executed'] is (not own)
    if own:
        runtime = manifest['own_runtime']
        assert runtime['binary_sha256'] == runtime['freshly_rebuilt_sha256']
        assert digest(folder / 'provenance/libtarget_engine.so') == runtime['binary_sha256']
    else:
        runtime = manifest['reference_runtime']
        assert digest(folder / 'provenance/reference-build-manifest.json') == runtime['manifest_sha256']
        assert result['reference_profile']['binary_sha256'] == runtime['binary_sha256']
        assert runtime['source_pin'] == '9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
    edges = [json.loads(line) for line in (folder / 'edges.jsonl').read_text().splitlines()]
    traces = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
    stop = round(result['duration_s'] * 1e6)
    high = [False] * 10
    last = -1
    boost = 0
    for index, edge in enumerate(edges, 1):
        stamp, channel, value = edge['time_us'], edge['ch'], edge['high']
        assert edge['sequence'] == index, ('Edge sequence', index)
        assert type(stamp) is int and last <= stamp <= stop, ('Edge clock', index)
        assert type(channel) is int and 0 <= channel < 10 and channel != 8, ('Edge channel', index)
        assert type(value) is bool and high[channel] != value, ('Distinct edge', index)
        assert edge['cause'] in ('dispatcher', 'fixture_halt', 'cut:simulation_end', 'cut:control', 'cut:trigger', 'cut:deadline')
        if edge['cause'] in ('fixture_halt', 'cut:simulation_end'):
            assert stamp == stop and not value, ('Synthetic termination', index)
        high[channel] = value
        last = stamp
        boost += channel == 9 and edge['cause'] == 'dispatcher'
    assert len(edges) == result['edges'] and boost == result['boost_edges'] and not any(high)
    high = [False] * 10
    consumed = boost_all = boost_dispatcher = 0
    previous_trace = -1

    def consume(count, stamp):
        nonlocal consumed, boost_all, boost_dispatcher
        assert type(count) is int and consumed <= count <= len(edges)
        while consumed < count:
            edge = edges[consumed]
            assert edge['time_us'] <= stamp, ('Future consumed edge', stamp, consumed)
            high[edge['ch']] = edge['high']
            boost_all += edge['ch'] == 9
            boost_dispatcher += edge['ch'] == 9 and edge['cause'] == 'dispatcher'
            consumed += 1

    def snapshot(row, stamp):
        coil = row['valve']['coil']
        assert coil['gpio_high'] == high[9], ('Valve GPIO', stamp, consumed)
        assert coil['edges'] == boost_all, ('Valve edge count', stamp, consumed)
        assert abs(row['valve']['time_s'] - stamp / 1e6) < 1e-8, ('Actuator clock', stamp)
        assert abs(coil['electrical_residual_j']) < 1e-8, ('Coil energy ledger', stamp)
        dispatcher = row['dispatcher']
        assert bool(dispatcher['virtual_high'] if own else dispatcher['pin_high']) == high[9], ('Dispatcher GPIO', stamp, consumed)
        if own:
            assert dispatcher['physical_policy_enabled'] is False and dispatcher['physical_command_high'] is False

    for row in traces:
        stamp = row['time_us']
        assert type(stamp) is int and previous_trace < stamp < stop
        consume(row['edges_consumed'], stamp)
        assert row['boost_dispatcher_edges_consumed'] == boost_dispatcher
        # A snapshot is taken after every current-time command/tooth edge has
        # been drained. Timestamp equality alone is no longer ambiguous.
        assert consumed == len(edges) or edges[consumed]['time_us'] > stamp, ('Undrained same-time edge', stamp, consumed)
        snapshot(row, stamp)
        previous_trace = stamp
    before = result['before_halt']
    consume(before['edges_consumed'], stop)
    assert high == before['high'], 'Pre-terminal pin state'
    snapshot(dict(valve=before['ledger']['boost_valve'], dispatcher=before['dispatcher']), stop)
    assert all(edge['time_us'] == stop and edge['cause'] in ('fixture_halt', 'cut:simulation_end') for edge in edges[consumed:])
    ledger = before['ledger']
    scenario=result['stimulus']['scenario']
    if scenario=='charged_map_rail':
        start=result['stimulus']['charged_fault_start_us']
        assert type(start) is int and start>=6000000, 'Charged fault reached'
        assert result['stimulus']['charged_channels_at_start'], 'Charged channel witness'
        if own:
            actual=[row for row in before['cut_discharges'] if abs(row['time_s']-start/1e6)<1e-9]
            assert actual and any(row['energy_j']>.002 for row in actual), 'Real pre-terminal charged-coil cut'
    profile=json.loads((folder/'tune.json').read_text())
    if profile['boost_control']['cut_kpa']==140:
        progress=json.loads((folder/'progress.json').read_text())
        assert progress['maximum_map_kpa']>140, 'Actual research gas exceeded lowered threshold'
        if own:assert int(before['control']['boost_control']['overboost_events'])>0, 'Own overboost observed'
        else:assert any(row['control']['boost_control']['boost_cut'] for row in traces), 'Production overboost observed'
    for key, tolerance in (('fuel_residual_mg', 1e-6), ('chemical_residual_j', 1e-5),
                           ('shaft_residual_j', 1e-5), ('coupled_mass_residual_kg', 1e-9),
                           ('coupled_energy_residual_j', .02), ('heat_partition_residual_j', 1e-5),
                           ('exhaust_fuel_transport_residual_kg', 1e-10)):
        assert abs(ledger[key]) < tolerance, (key, ledger[key], tolerance)
    return dict(controller=result['controller'], audit_passed=True, snapshots=len(traces),
                edges=len(edges), dispatcher_boost_edges=boost, source_files=len(result['source_hashes']),
                final_rpm=before['rpm'], final_map_kpa=before['map_kpa'],
                coupled_energy_residual_j=ledger['coupled_energy_residual_j'],
                qualification='Consumed-edge/provenance/ledger invariants only; no comparison or physical acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--current-inputs', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.folder, args.current_inputs), indent=2, allow_nan=False))
