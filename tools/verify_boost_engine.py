"""Audit consumed output edges, coherent snapshots and native-run provenance.

Passing this audit establishes the listed research-run invariants only. It does
not accept an ECU feature, an engine calibration, a controller match or hardware.
"""
import argparse
import json
import math
from pathlib import Path
from boost_engine_provenance import digest
from engine_geometry import EngineGeometry,CHANNEL_EXTENT


def recompute_balances(ledger):
    """Independent algebraic conservation checks from recorded inventories."""
    g=ledger['turbo_gas']
    def number(data,key):
        value=data[key]
        assert type(value)in(int,float)and math.isfinite(value),('Finite physical inventory',key)
        return value
    l=lambda key:number(ledger,key)
    gas=lambda key:number(g,key)
    residuals=dict(
        fuel_residual_mg=l('fuel_in_mg')-l('burned_mg')-l('unburned_mg')-l('stored_mg'),
        chemical_residual_j=l('burned_chemical_j')-l('combustion_shaft_j')-l('heat_j')-l('pending_work_j'),
        shaft_residual_j=l('starter_j')+l('combustion_shaft_j')-l('friction_j')-l('load_j')-l('kinetic_j'),
        heat_partition_residual_j=l('heat_j')-l('wall_heat_j')-l('exhaust_heat_delivered_j')-l('pending_exhaust_heat_j'),
        exhaust_fuel_transport_residual_kg=(l('burned_mg')+l('unburned_mg'))/1e6-l('pending_exhaust_fuel_kg')-gas('fuel_mass'),
        coupled_mass_residual_kg=gas('inventory_mass_kg')-gas('initial_mass_kg')+l('stored_mg')/1e6+l('pending_exhaust_fuel_kg')-l('fuel_in_mg')/1e6-gas('boundary_mass'),
        coupled_energy_residual_j=l('starter_j')+l('burned_chemical_j')+gas('boundary_h')-l('friction_j')-l('external_load_j')-l('wall_heat_j')-gas('cooler_heat')-gas('bearing')-l('kinetic_j')-(gas('inventory_energy_j')-gas('initial_energy_j'))-l('pending_work_j')-l('pending_exhaust_heat_j')-l('pending_pumping_exchange_j'))
    for key,value in residuals.items():
        assert abs(value-number(ledger,key))<1e-7,('Reported/recomputed physical residual',key,value,ledger[key])
    mass=gas('inventory_mass_kg')-gas('initial_mass_kg')-gas('boundary_mass')-gas('fuel_mass')
    energy=gas('inventory_energy_j')-gas('initial_energy_j')-gas('boundary_h')-gas('heat')-gas('pumping')+gas('cooler_heat')+gas('bearing')
    assert abs(mass-gas('mass_residual_kg'))<1e-12 and abs(mass)<1e-9,'Gas mass balance'
    assert abs(energy-gas('energy_residual_j'))<1e-7 and abs(energy)<.02,'Gas energy balance'
    assert abs(l('load_j')-l('pumping_work_j')-l('external_load_j'))<1e-7,'External/pumping load partition'
    assert abs(l('pumping_work_j')-gas('pumping')-l('pending_pumping_exchange_j'))<1e-7,'Pending pumping exchange'
    return residuals


def verify(folder, current_inputs=False):
    folder = Path(folder)
    result = json.loads((folder / 'result.json').read_text())
    profile=json.loads((folder/'tune.json').read_text())
    declared=result.get('plant_geometry')
    geometry=EngineGeometry(declared['cylinders'],tuple(declared['firing_order']),declared['displacement_cc'],declared['tooth1_tdc_deg'],declared['cam_edge_deg'])if declared else EngineGeometry(4,(1,3,4,2),1800)
    count=geometry.cylinders;extent=len(result['before_halt']['high'])
    allowed=set(geometry.injector_channels+geometry.coil_channels+(9,))
    assert 10<=extent<=CHANNEL_EXTENT and max(allowed)<extent,'Declared command extent'
    if declared:
        assert geometry.summary()==declared,'Physical geometry summary'
        assert profile['engine']['cylinders']==count and profile['engine']['displacement_cc']==geometry.displacement_cc,'Tune/physical size'
        assert profile['timing']['firing_order']==[*geometry.firing_order,*([0]*(8-count))],'Tune/physical order'
        air=result['plant_air_parameters']
        assert air['cylinders']==count and air['graph_displacement_m3']==geometry.displacement_m3,'Actual graph pumping geometry'
    manifest_path = folder / 'provenance/manifest.json'
    assert digest(manifest_path) == result['provenance_manifest_sha256'], 'Provenance manifest digest'
    manifest = json.loads(manifest_path.read_text())
    assert digest(folder/'tune.json') == manifest['requested_tune_sha256'], 'Requested tune identity'
    assert manifest['source_hashes'] == result['source_hashes'], 'Source inventory'
    for name, expected in manifest['source_hashes'].items():
        assert digest(folder / 'provenance/sources' / name) == expected, name
    layout=manifest.get('loaded_engine_profile_layout')
    if layout is not None:
        assert layout==json.loads((folder/'provenance/sources/config/engine-profile.json').read_text()),'Loaded layout snapshot'
        assert tuple(layout['injector_channels'][:count])==geometry.injector_channels and tuple(layout['coil_channels'][:count])==geometry.coil_channels,'Loaded physical channel map'
    if count!=4 or result.get('expanded_reference'):assert layout is not None,'Expanded run requires loaded-layout attestation'
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
        reference=json.loads((folder/'provenance/reference-build-manifest.json').read_text())
        assert reference['unit_test']is False and reference['binary_sha256']==runtime['binary_sha256'],'Production executable attestation'
        for name,expected in reference['fixture_sources'].items():
            assert manifest['source_hashes'].get(name)==expected,'Reference fixture source inventory: '+name
            assert digest(folder/'provenance/sources'/name)==expected,'Reference fixture source snapshot: '+name
        assert result['reference_profile']['binary_sha256'] == runtime['binary_sha256']
        assert runtime['source_pin'] == '9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20'
        generated=runtime.get('generated_inputs',{})
        assert set(generated)==set(reference.get('generated_sources',{})),'Generated adapter inventory'
        for name,item in generated.items():
            path=folder/'provenance'/item['snapshot']
            assert path.resolve().is_relative_to((folder/'provenance').resolve()),'Generated snapshot path'
            assert item['sha256']==reference['generated_sources'][name]==digest(path),'Generated adapter snapshot identity'
        if result.get('expanded_reference'):
            assert result['reference_profile']['physical_geometry']==declared,'Reference/plant geometry'
            assert result['reference_profile']['representable_ignition_geometry']or result['reference_geometry_diagnostic'],'Unannounced fallback mismatch'
    edges = [json.loads(line) for line in (folder / 'edges.jsonl').read_text().splitlines()]
    traces = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
    stop = round(result['duration_s'] * 1e6)
    high = [False] * extent
    last = -1
    boost = 0
    for index, edge in enumerate(edges, 1):
        stamp, channel, value = edge['time_us'], edge['ch'], edge['high']
        assert edge['sequence'] == index, ('Edge sequence', index)
        assert type(stamp) is int and last <= stamp <= stop, ('Edge clock', index)
        assert type(channel) is int and channel in allowed, ('Edge channel', index)
        assert type(value) is bool and high[channel] != value, ('Distinct edge', index)
        assert edge['cause'] in ('dispatcher', 'fixture_halt', 'cut:simulation_end', 'cut:control', 'cut:trigger', 'cut:deadline','cut:cam')
        if edge['cause'] in ('fixture_halt', 'cut:simulation_end'):
            assert stamp == stop and not value, ('Synthetic termination', index)
        high[channel] = value
        last = stamp
        boost += channel == 9 and edge['cause'] == 'dispatcher'
    assert len(edges) == result['edges'] and boost == result['boost_edges'] and not any(high)
    high = [False] * extent
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
    after=result.get('after_halt')
    if declared or result.get('expanded_reference'):assert after is not None,'Declared current run requires post-halt physical inventory'
    if after is not None:
        consume(after['edges_consumed'],stop)
        assert consumed==len(edges)and high==after['high']and not any(high),'Post-terminal command replay'
        assert after['injector_on']==[None]*count and after['coil_on']==[None]*count and after['boost_command_high']is False,'Post-terminal model outputs'
        assert after['ledger']['boost_valve']['coil']['gpio_high']is False,'Post-terminal modeled boost command'
        if not own and result.get('expanded_reference'):
            observed=after.get('reference_boost_status');assert observed is not None and observed['time_us']==stop,'Independent reference boost halt observation'
            assert observed==before['dispatcher'],'Engine-only halt changed or misreported native boost state'
            # The fixture stops engine schedulers only. Native boost may stay
            # active while the external simulation-ending cut lowers the model.
    scenario=result['stimulus']['scenario']
    if scenario=='charged_map_rail':
        start=result['stimulus']['charged_fault_start_us']
        assert type(start) is int and start>=6000000, 'Charged fault reached'
        assert result['stimulus']['charged_channels_at_start'], 'Charged channel witness'
        if own:
            actual=[row for row in before['cut_discharges'] if abs(row['time_s']-start/1e6)<1e-9]
            assert actual and any(row['energy_j']>.002 for row in actual), 'Real pre-terminal charged-coil cut'
    if profile['boost_control']['cut_kpa']==140:
        progress=json.loads((folder/'progress.json').read_text())
        assert progress['maximum_map_kpa']>140, 'Actual research gas exceeded lowered threshold'
        if own:assert int(before['control']['boost_control']['overboost_events'])>0, 'Own overboost observed'
        else:assert any(row['control']['boost_control']['boost_cut'] for row in traces), 'Production overboost observed'
    for inventory in (ledger,after['ledger'])if after is not None else(ledger,):
      recomputed=recompute_balances(inventory)
      for key, tolerance in (('fuel_residual_mg', 1e-6), ('chemical_residual_j', 1e-5),
                           ('shaft_residual_j', 1e-5), ('coupled_mass_residual_kg', 1e-9),
                           ('coupled_energy_residual_j', .02), ('heat_partition_residual_j', 1e-5),
                           ('exhaust_fuel_transport_residual_kg', 1e-10)):
        assert abs(recomputed[key]) < tolerance, (key, recomputed[key], tolerance)
    for boundary in (before,after)if after is not None else(before,):
        if declared:
            for key,total,tolerance in (('cylinder_fuel_mg','fuel_in_mg',1e-6),('cylinder_burned_mg','burned_mg',1e-6),('cylinder_shaft_j','combustion_shaft_j',1e-5)):
                values=boundary[key]
                assert len(values)==count and all(type(v)in(int,float)and math.isfinite(v)and v>=0 for v in values),'Per-cylinder physical inventories'
                assert abs(sum(values)-boundary['ledger'][total])<tolerance,('Per-cylinder/total inventory',key)
    captures=[json.loads(line)for line in (folder/'trigger-stimuli.jsonl').read_text().splitlines()]
    last_capture=-1;last_tooth=last_cam=None;cranks=missed=cams=0
    for row in captures:
        stamp=row['time_us'];kind=row.get('kind','crank')
        assert type(stamp)is int and 0<=stamp<=stop and stamp>=last_capture,'Ordered bounded capture clock'
        assert type(row['delivered'])is bool and kind in ('crank','cam'),'Declared capture kind/value'
        if kind=='crank':
            angle=row['tooth_angle_deg'];slot=row['slot']
            assert type(angle)is int and angle>0 and angle%6==0 and type(slot)is int and 0<=slot<58 and slot==(angle//6)%60,'Physical60-2 crank capture'
            assert last_tooth is None or angle>last_tooth,'Ordered physical crank angles'
            last_tooth=angle;cranks+=row['delivered'];missed+=not row['delivered']
        else:
            angle=row['cam_angle_deg']
            assert type(angle)in(int,float)and math.isfinite(angle)and angle>=geometry.cam_edge_deg and (angle-geometry.cam_edge_deg)%720==0,'Physical cam phase'
            assert last_cam is None or angle>last_cam,'Ordered physical cam angles'
            last_cam=angle;cams+=row['delivered']
        last_capture=stamp
    assert cranks==result['trigger_edges']and missed==result['suppressed_teeth']and cams==result.get('cam_edges',0),'Capture counts'
    return dict(controller=result['controller'], audit_passed=True, snapshots=len(traces),
                edges=len(edges), dispatcher_boost_edges=boost, source_files=len(result['source_hashes']),
                final_rpm=before['rpm'], final_map_kpa=before['map_kpa'],
                cylinders=count,strategy=result.get('strategy','batch_wasted'),loaded_layout_attested=layout is not None,
                generated_adapter_snapshots=len(manifest.get('reference_runtime',{}).get('generated_inputs',{})),post_halt_audited=after is not None,
                reference_geometry_diagnostic=result.get('reference_geometry_diagnostic',False),
                coupled_energy_residual_j=ledger['coupled_energy_residual_j'],
                post_halt_coupled_energy_residual_j=after['ledger']['coupled_energy_residual_j']if after is not None else None,
                qualification='Consumed-edge/provenance/ledger invariants only; no comparison or physical acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--current-inputs', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.folder, args.current_inputs), indent=2, allow_nan=False))
