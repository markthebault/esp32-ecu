#!/usr/bin/env python3
"""Run a declared matrix of full-controller external-plant regressions."""
import hashlib
import json
import math
from pathlib import Path
import time
from compare_engine_controllers import ROOT,SCENARIOS,benchmark_tune,run


def validate():
    start=time.monotonic();rows=[];convergence=[];failures=[]
    output=ROOT/'.cache/engine/comparison';output.mkdir(parents=True,exist_ok=True)
    for controller in ('ours','speeduino','speeduino_per_tooth'):
        for scenario in SCENARIOS:
            duration=12 if scenario=='stall_restart' else 10
            print('Running',controller,scenario,'250us',flush=True)
            result=run(controller,scenario,duration,250);s=result['summary']
            (output/f'{controller}-{scenario}-250.json').write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
            rows.append(s)
            errors=[]
            for key,tolerance in [('fuel_residual_mg',1e-6),('chemical_residual_j',1e-4),
                                  ('shaft_residual_j',1e-4),('air_residual_kg',1e-7),('air_energy_residual_j',.05)]:
                if abs(s['ledger'][key])>tolerance:errors.append(f'{key} exceeds{tolerance}')
            if s['final_outputs_high'] or s['max_trigger_quantization_deg']>.05:errors.append('termination or trigger quantization')
            if controller=='ours' and (s['max_injector_high_us']>15000 or s['max_dwell_high_us']>3500):errors.append('project pulse bound')
            if scenario in ('warm_start','stall_restart') and not 650<s['mean_final_second_rpm']<1500:
                errors.append('expected sustained/recovered idle absent')
            if scenario=='trigger_dropout' and s['mean_final_second_rpm']>40:errors.append('expected long-gap coast-to-stop absent')
            if scenario=='overrev' and not s['hard_cut_samples']:errors.append('hard rev cut was not exercised')
            if scenario=='sensor_short' and controller=='ours' and not s['project_fault_mask_seen']&4:errors.append('project did not detect the MAP rail fault')
            if scenario=='throttle_step' and s['mean_final_second_rpm']<1500:errors.append('throttle did not raise free RPM')
            if errors:failures.append(dict(controller=controller,scenario=scenario,errors=errors))
            print('Result',round(s['final_rpm'],1),'rpm;',len(errors),'regression failures',flush=True)
        for scenario in ('warm_start','throttle_step'):
            print('Convergence',controller,scenario,'125us',flush=True)
            fine=run(controller,scenario,10,125)
            (output/f'{controller}-{scenario}-125.json').write_text(json.dumps(fine,separators=(',',':'),allow_nan=False)+'\n')
            coarse=next(row for row in rows if row['controller']==controller and row['scenario']==scenario)
            metrics={key:abs(coarse[key]-fine['summary'][key])/max(1,abs(fine['summary'][key])) for key in ('mean_final_second_rpm',)}
            for key in ('fuel_in_mg','combustion_shaft_j'):
                metrics[key]=abs(coarse['ledger'][key]-fine['summary']['ledger'][key])/max(1,abs(fine['summary']['ledger'][key]))
            passed=max(metrics.values())<.03
            convergence.append(dict(controller=controller,scenario=scenario,steps_us=[250,125],relative_differences=metrics,tolerance=.03,passed=passed))
            if not passed:failures.append(dict(controller=controller,scenario=scenario,errors=['coupling step convergence']))
    source_paths=['tools/compare_engine_controllers.py','tools/engine_research_plant.py','tools/speeduino_runtime.py',
                  'tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','simulation/modelica/EngineAirPath.mo',
                  'tools/validate_engine_comparison.py','config/engine/defaults.json',
                  'tools/engine_runtime.py','tools/engine_bridge.cpp','firmware/main/config_json.hpp',
                  'tools/test_research_plant.py','tools/test_speeduino_runtime.py',
                  'scripts/build_engine_airpath.py','scripts/build_speeduino_sim.py','scripts/verify_modelica_sources.py']
    source_paths+=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'firmware/include/ecu').glob('*.hpp'))
    manifests={key:json.loads((ROOT/path).read_text()) for key,path in [('airpath','.cache/engine/modelica-mvem/airpath/manifest.json'),
                                                                 ('speeduino','.cache/engine/speeduino-sim/build-manifest.json')]}
    report=dict(scope='Shared project engine core/decoder/scheduler and production Speeduino loop execute against identical independent copies of an uncalibrated research plant; virtual GPIO only',
                controller_cases=len(rows),convergence_cases=len(convergence),passed=not failures,failures=failures,
                source_hashes={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in source_paths},
                benchmark_tune=benchmark_tune(),
                speeduino_profile=dict(reqFuel_point1ms=107,ve_pct=85,advance_deg=10,crank_advance_deg=5,
                                       cranking_rpm=450,deadtime_ms=.9,dwell_ms=2.8,trigger='60-2 tooth1 -90deg',
                                       enrichments='100% WUE/crank, ASE0, EGO/DFCO off',
                                       rev_limit='protection BOTH and FIXED hard mode enabled/read back; hard6500, soft6200-relative10deg, soft timeout25.5s; project uses ramp/hysteresis',
                                       sensor_cadence='upstream production polling with ADC quantization; stopped defaults retained'),
                runtime_seconds=time.monotonic()-start,
                limitations=['native Speeduino uint32 4us timers, not AVR timer emulation',
                             'zero CPU cost; timers before coincident teeth; project1ms control/native250us loop plus tooth calls',
                             'callback injection does not validate wiring or trigger edge dispatch',
                             'MSL/MVEM intake research components; local empirical and uncalibrated combustion/coil/fuel/shaft parameters',
                             'fixed exhaust pressure, simplified valve events and no calibrated cold/knock/emissions behavior',
                             'overrev includes explicit70Nm motoring dynamometer from6.0..6.25s; its work is booked as negative load work',
                             'native spark errors use last sampled demand; project uses event-latched demand',
                             'termination low is explicit halt/cut, not evidence of natural stall shutdown'],
                build_provenance={name:{'manifest_sha256':hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
                                       'content':{k:v for k,v in manifests[name].items() if k not in ('source_hashes','header_hashes','dependency_hashes','compile_flags')}}
                                  for name,path in [('airpath','.cache/engine/modelica-mvem/airpath/manifest.json'),('speeduino','.cache/engine/speeduino-sim/build-manifest.json')]},
                rows=rows,convergence=convergence)
    destination=ROOT/'reports/engine/full-controller-comparison.json';destination.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('Full comparison:',len(rows),'controller cases,',len(convergence),'convergence cases, failures',len(failures),flush=True)
    return report


if __name__=='__main__':
    report=validate()
    if not report['passed']:raise SystemExit(1)
