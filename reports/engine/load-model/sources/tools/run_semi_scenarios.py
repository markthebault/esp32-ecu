#!/usr/bin/env python3
"""Timed semi-sequential source comparison on the independent research plant.

Native execution has zero CPU/IRQ cost. Reference16 is a timer-width model,
not AVR emulation. Neutral profiles and this plant are not engine calibration.
"""
import argparse,hashlib,json,time
from pathlib import Path
import compare_engine_controllers as benchmark
from run_target_scenarios import audit as edge_audit

ROOT=Path(__file__).resolve().parents[1]
PROFILES=(('ours',False,32,'portable'),('ours',True,32,'target'),
          ('speeduino',False,32,'speeduino32'),('speeduino',False,16,'speeduino16'))

def audit(result,ours):
    # Reuse the independent edge/ledger replay, then apply this strategy's
    # explicitly declared protection outcomes. Portable and target runtimes
    # have different tooth-watchdog ownership; don't equate their fault codes.
    report=edge_audit(result,False);errors=report['errors'];edges=result['edges'];s=result['summary']
    def require(ok,message):
        if not ok:errors.append(message)
    for a,b in ((0,3),(1,2)):
        if [(t,v) for t,ch,v,_ in edges if ch==a]!=[(t,v) for t,ch,v,_ in edges if ch==b]:errors.append('paired injector transitions differ')
    if ours and any(row['ecu'].get('phase_required') or row['ecu'].get('phase_synced') for row in result['trace']):errors.append('unexpected cam dependency')
    if ours:
        require(s['max_injector_high_us']<=15000 and s['max_dwell_high_us']<=3500,'project high-time bounds')
        require(s['max_spark_error_deg']<.2,'latched spark-angle error')
        scenario=s['scenario'];target=s['project_runtime']=='target_dispatcher';dropout=scenario in ('trigger_dropout','stall_restart');stall=scenario=='load_step'
        expected_fault=128 if stall or (dropout and target) else 4 if scenario=='sensor_short' else 32 if scenario=='overrev' else 0
        require(s['project_fault_mask_seen']==expected_fault,'missing or unexpected project fault')
        final=result['final_ecu'];stops=int(stall or (dropout and target))
        require(final['timing_stops']==stops and final['timing_recoveries']==stops,'timing stop/recovery count')
        reason=('invalid_angle_plan' if target else 'dwell_limit') if stall else 'tooth_timeout' if dropout and target else 'none'
        require(final['timing_stop_reason']==reason and final['faults']==0,'unexpected final timing/fault state')
        if dropout:
            start,end=s['dropout_raw_gap_us']
            watchdog=s.get('dropout_accepted_crank_watchdog')
            require(watchdog is not None and watchdog['last_accepted_us']==start,'missing actual accepted-crank watchdog')
            if watchdog:
                require(s['last_output_after_dropout_ms']*1000<=watchdog['timeout_us'],'post-loss exposure exceeds actual timeout')
                require(not any(watchdog['deadline_us']<=t<end for t,_,_,_ in edges),'output edge after stale-plan horizon')
                report['actual_crank_watchdog']=watchdog
            report['post_loss_predicted_rises']=s['output_rises_after_dropout']
            report['post_loss_last_edge_ms']=s['last_output_after_dropout_ms']
            report['post_loss_policy']='Previously predicted starts can occur before tooth/command expiry; no instantaneous loss detection is claimed'
    report['passed']=not errors
    report['paired_injector_edges_equal']=not any('paired injector' in e for e in errors)
    # End-angle prediction under changing RPM is measured, not asserted equal
    # to a steady-shaft oracle. Once opened, electrical width remains fixed.
    report['closing_error_scope']='actual plant shaft at scheduled falls; cut falls excluded; finite pulse duration and speed changes remain'
    return report

def validate(output):
    output.mkdir(parents=True,exist_ok=True);rows=[];checks=[];failures=[];started=time.monotonic()
    for who,target,bits,label in PROFILES:
        for step,scenarios in ((250,benchmark.SCENARIOS),(125,('warm_start','throttle_step'))):
            for scenario in scenarios:
                print('Running',label,scenario,step,flush=True)
                result=benchmark.run(who,scenario,12 if scenario=='stall_restart' else 10,step,
                    control_period_us=5000,semi_sequential=True,target_dispatcher=target,reference_timer_bits=bits)
                summary=result['summary'];summary['label']=label;summary['audit']=audit(result,who=='ours')
                path=output/f'{label}-{scenario}-{step}.json'
                path.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
                summary['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                if not summary['audit']['passed']:failures.append(dict(label=label,scenario=scenario,step_us=step,errors=summary['audit']['errors']))
                if step==250:rows.append(summary)
                else:
                    coarse=next(r for r in rows if r['label']==label and r['scenario']==scenario)
                    diff={'mean_final_second_rpm':abs(coarse['mean_final_second_rpm']-summary['mean_final_second_rpm'])/max(1,abs(summary['mean_final_second_rpm']))}
                    for key in ('fuel_in_mg','combustion_shaft_j'):diff[key]=abs(coarse['ledger'][key]-summary['ledger'][key])/max(1,abs(summary['ledger'][key]))
                    check=dict(label=label,scenario=scenario,relative_differences=diff,tolerance=.03,passed=max(diff.values())<.03 and summary['audit']['passed']);checks.append(check)
                    if not check['passed']:failures.append(dict(label=label,scenario=scenario,step_us=step,errors=['step refinement or edge audit']))
                print('Result',round(summary['mean_final_second_rpm'],2),'RPM; closing error',round(summary['max_injection_closing_error_after_3s_deg'],3),'deg;',summary['audit']['errors'],flush=True)
    paths=['tools/run_semi_scenarios.py','tools/compare_engine_controllers.py','tools/run_target_scenarios.py','tools/engine_research_plant.py','tools/engine_runtime.py','tools/engine_bridge.cpp','tools/target_runtime.py','tools/target_timing_bridge.cpp','tools/speeduino_runtime.py','tools/speeduino_sim.cpp','tools/speeduino_sim_hal.cpp','tools/speeduino_sim_native.hpp','scripts/build_speeduino_sim.py','simulation/modelica/EngineAirPath.mo','config/engine/defaults.json']
    paths+=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'firmware/include/ecu').glob('*.hpp'))
    report=dict(scope='Four independent injectors, timed logical pairs, crank-only360deg, wasted COP; fixed physical1-3-4-2 research plant',
        passed=not failures,failures=failures,controller_cases=len(rows),convergence_cases=len(checks),rows=rows,convergence=checks,
        physical_outputs_enabled=False,cpu_latency_model='zero; no physical jitter qualification',control_period_us=5000,producer_period_us=1000,
        reference_commit='9ff5aae44de51fdc00d3fb1c7c2bfc1f0d0b3e20',reference_scope='Unchanged production algorithms; declared timedSemi profile after actual setup;32bit/native and16bit/4us/equality HALs; no AVR CPU emulation',
        reference_profile_readback='injectorprofile: configured/effective layout1/1, timing1, pairing0, nSquirts2, span360, primary schedules2, wastedCOP2',
        calibration_scope='Neutral maps/corrections, uncalibrated external MVEM airpath + empirical fuel/combustion/free shaft; each core drives its own copy by executed actuator edges',
        runtime_seconds=time.monotonic()-started,source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'.cache/engine/semi/matrix');a=p.parse_args()
    result=validate(a.output_dir);print('Passed',result['passed'],'failures',result['failures'],flush=True)
    if not result['passed']:raise SystemExit(1)
