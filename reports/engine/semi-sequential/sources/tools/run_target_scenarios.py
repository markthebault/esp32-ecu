#!/usr/bin/env python3
"""Actual target dispatcher + shared ECU core on the external research plant.

Native execution has zero CPU/peripheral latency. Separate adversarial unit
tests cover those faults; target interrupt jitter remains physically unmeasured.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import compare_engine_controllers as benchmark
from target_runtime import TargetRuntime


class TargetController(benchmark.OurController):
    def __init__(self,tune=None):
        super().__init__(tune,target_dispatcher=True)


def audit(result,target):
    """Reconstruct actuator state independently from the complete edge stream."""
    s=result['summary'];errors=[];high={};widths=[0]*8;previous=0;channels=set()
    def require(condition,message):
        if not condition:errors.append(message)
    for us,ch,value,cause in result['edges']:
        require(isinstance(us,int) and previous<=us<=round(s['duration_s']*1e6),'edge time/order')
        previous=us;channels.add(ch)
        if ch not in range(8):errors.append('edge channel');continue
        if value:
            require(ch not in high,'duplicate rise');high[ch]=us
        else:
            require(ch in high,'fall without rise')
            if ch in high:widths[ch]=max(widths[ch],us-high.pop(ch))
    require(not high and not s['final_outputs_high'],'termination left an output high')
    require(channels==set(range(8)),'not all eight virtual channels exercised')
    require(len(result['edges'])==s['edges'],'edge count differs from summary')
    require(max(widths[:4])==s['max_injector_high_us'] and max(widths[4:])==s['max_dwell_high_us'],'pulse summary differs from replay')
    for key,tolerance in [('fuel_residual_mg',1e-6),('chemical_residual_j',1e-4),
                          ('shaft_residual_j',1e-4),('air_residual_kg',1e-7),('air_energy_residual_j',.05)]:
        require(math.isfinite(s['ledger'][key]) and abs(s['ledger'][key])<tolerance,key+' balance')
    require(s['max_trigger_quantization_deg']<.05,'trigger quantization')
    require(s['sparks']>100 and s['ledger']['combustion_shaft_j']>0,'combustion was not exercised')
    scenario=s['scenario'];rpm=s['mean_final_second_rpm']
    if scenario in ('warm_start','stall_restart'):require(650<rpm<1500,'sustained/recovered idle absent')
    if scenario=='throttle_step':require(rpm>1500,'throttle response absent')
    if scenario in ('load_step','trigger_dropout'):require(rpm<40,'expected coast to rest absent')
    if scenario=='overrev':require(s['hard_cut_samples']>0,'hard rev cut not exercised')
    if target:
        require(max(widths[:4])<=15000 and max(widths[4:])<=3500,'target pulse bounds')
        require(s['max_spark_error_deg']<.2,'latched spark-angle error')
        masks={'warm_start':0,'throttle_step':0,'load_step':0,'trigger_dropout':128,
               'sensor_short':4,'stall_restart':128,'overrev':32}
        require(s['project_fault_mask_seen']==masks[scenario],'missing or unexpected target fault')
        final=result['final_ecu'];dropout=scenario in ('trigger_dropout','stall_restart')
        require(final['timing_stops']==int(dropout) and final['timing_recoveries']==int(dropout),'timing stop/recovery count')
        require(final['timing_stop_reason']==('tooth_timeout' if dropout else 'none'),'unexpected timing stop reason')
        require(final['faults']==0,'target fault remained latched at end')
        if dropout:
            require(not s['output_rises_after_dropout'],'new pulse during declared trigger loss')
            require(s['last_output_after_dropout_ms']<=20,'trigger-loss closing edge exceeded command lifetime')
    return dict(passed=not errors,errors=errors,replayed_edges=len(result['edges']),
                replayed_max_high_us=widths,all_virtual_channels_exercised=channels==set(range(8)))


def validate(compare=True,convergence=True,output_dir=None):
    root=Path(__file__).resolve().parents[1];output=Path(output_dir) if output_dir else root/'.cache/engine/target-scenarios';output.mkdir(parents=True,exist_ok=True)
    original=benchmark.OurController;benchmark.OurController=TargetController;rows=[];checks=[];failures=[];start=time.monotonic()
    try:
        for controller in ('ours','speeduino') if compare else ('ours',):
            label='native_esp32_dispatcher' if controller=='ours' else controller
            for scenario in benchmark.SCENARIOS:
                print('Running',label,scenario,'250us',flush=True)
                seconds=12 if scenario=='stall_restart' else 10
                result=benchmark.run(controller,scenario,seconds,250,control_period_us=5000)
                summary=result['summary'];summary['controller']=label;summary['audit']=audit(result,controller=='ours');rows.append(summary)
                if not summary['audit']['passed']:failures.append(dict(controller=label,scenario=scenario,errors=summary['audit']['errors']))
                path=output/(label+'-'+scenario+'-250.json');path.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
                summary['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                print(scenario,round(summary['final_rpm'],1),'RPM; audit',summary['audit']['passed'],flush=True)
            if convergence:
                for scenario in ('warm_start','throttle_step'):
                    print('Convergence',label,scenario,'125us',flush=True)
                    fine=benchmark.run(controller,scenario,10,125,control_period_us=5000)
                    (output/(label+'-'+scenario+'-125.json')).write_text(json.dumps(fine,separators=(',',':'),allow_nan=False)+'\n')
                    coarse=next(row for row in rows if row['controller']==label and row['scenario']==scenario)
                    metrics={'mean_final_second_rpm':abs(coarse['mean_final_second_rpm']-fine['summary']['mean_final_second_rpm'])/max(1,abs(fine['summary']['mean_final_second_rpm']))}
                    for key in ('fuel_in_mg','combustion_shaft_j'):
                        metrics[key]=abs(coarse['ledger'][key]-fine['summary']['ledger'][key])/max(1,abs(fine['summary']['ledger'][key]))
                    passed=max(metrics.values())<.03 and audit(fine,controller=='ours')['passed']
                    checks.append(dict(controller=label,scenario=scenario,steps_us=[250,125],relative_differences=metrics,tolerance=.03,passed=passed))
                    if not passed:failures.append(dict(controller=label,scenario=scenario,errors=['coupling convergence or fine edge audit']))
        paths=['tools/run_target_scenarios.py','tools/target_runtime.py','tools/target_timing_bridge.cpp',
               'tools/compare_engine_controllers.py','tools/engine_research_plant.py','tools/speeduino_runtime.py',
               'tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','simulation/modelica/EngineAirPath.mo','config/engine/defaults.json']
        paths+=sorted(str(p.relative_to(root)) for p in (root/'firmware/include/ecu').glob('*.hpp'))
        report=dict(scope='Shared ESP32 dispatcher/angle scheduler/decoder/controller on external uncalibrated MVEM air path + local empirical combustion/free shaft',
                    control_period_us=5000,producer_period_us=1000,cpu_latency_model='zero; no physical jitter qualification',
                    reference='Actual pinned Speeduino production loop/decoder/schedulers, per-tooth timing disabled; same 5ms sensor injection, production polling retained',
                    benchmark_tune=benchmark.benchmark_tune(),controller_cases=len(rows),convergence_cases=len(checks),
                    passed=not failures,failures=failures,runtime_seconds=time.monotonic()-start,
                    source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},rows=rows,convergence=checks)
        (output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report
    finally:benchmark.OurController=original


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target-only',action='store_true');parser.add_argument('--no-convergence',action='store_true');parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();report=validate(not args.target_only,not args.no_convergence,args.output_dir)
    print('Target/reference comparison:',report['controller_cases'],'cases;',report['convergence_cases'],'convergence checks; passed',report['passed'],flush=True)
    if not report['passed']:raise SystemExit(1)
