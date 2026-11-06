#!/usr/bin/env python3
"""Both real controller cores drive independent copies of one external research plant.

No RPM trace, shared sensor trace, commanded-fuel shortcut or shared scheduler.
Not a calibrated engine comparison. See docs/engine-development.md for limits.
"""
import argparse
import copy
import json
import math
from pathlib import Path
from engine_runtime import EngineRuntime
from engine_research_plant import ResearchPlant
from speeduino_runtime import SpeeduinoRuntime
from sequential_metrics import sequential_metrics
from engine_geometry import EngineGeometry, CHANNEL_EXTENT, channel_kind

ROOT=Path(__file__).resolve().parents[1]
CAM_SCENARIOS=('cam_dropout','cam_extra','cam_wrong_phase','cam_missing_start')
SCENARIOS=('warm_start','throttle_step','load_step','trigger_dropout','sensor_short','stall_restart','overrev')
IDLE_SCENARIOS=('idle_load_step','idle_throttle_blip','idle_cold_start')
TRANSIENT_SCENARIOS=('transient_tip','transient_reverse','transient_noise','transient_load')


def benchmark_tune():
    tune=json.loads((ROOT/'config/engine/defaults.json').read_text())
    tune['settings'].update(afterstart_pct=0,ego_enabled=False,dfco_enabled=False,
                            crank_advance_deg=5,max_dwell_ms=3.5)
    tune['curves']['warmup_pct']=[100]*6;tune['curves']['crank_pct']=[100]*6
    tune['curves']['deadtime_ms']=[.9]*5;tune['curves']['dwell_ms']=[2.8]*5
    tune['maps']['ve']['cells']=[85]*256;tune['maps']['spark']['cells']=[10]*256
    tune['maps']['lambda']['cells']=[1]*256
    return tune


class OurController:
    def __init__(self,tune=None,target_dispatcher=False):
        tune=tune or benchmark_tune()
        from target_runtime import TargetRuntime
        boost=tune.get('boost_control',{}).get('pressure_enabled',False)
        self.target_dispatcher=target_dispatcher or tune['settings']['idle_enabled'] or boost
        self.runtime=(TargetRuntime if self.target_dispatcher else EngineRuntime)(tune);self.runtime.wheel()
        self.channels=CHANNEL_EXTENT
        self.worker_us=1000 if self.target_dispatcher else None
        self.status={};self.high=[False]*self.channels;self.stops=[]

    def sample(self,sample,us):
        self.status=self.runtime.step(sample,us,use_decoder=True)
        if self.status['faults'] or self.status['state']=='stopped':
            self.runtime.cut();self.high=[False]*self.channels;return True
        return False

    def advance(self,us):
        edges=[]
        while min(self.runtime.next_event_us(),self.worker_us if self.worker_us is not None else 2**64-1)<=us:
            if self.worker_us is not None and self.worker_us<self.runtime.next_event_us():
                self.runtime.progress(self.worker_us);self.worker_us+=1000;continue
            when=self.runtime.next_event_us();ch,high,advance,dwell=self.runtime.pop_event()
            if ch==-1:continue
            if ch is None:
                self.runtime.cut();self.high=[False]*self.channels
                edges.append((when,None,False,None,None));continue
            self.high[ch]=high;edges.append((when,ch,high,advance,dwell))
        return edges

    def cam(self,us):
        state=self.runtime.cam(us)
        if state in (2,3):
            if state==3:self.stops.append(dict(time_us=us,reason=self.runtime.timing_reason()))
            self.runtime.cut();self.high=[False]*self.channels;return True
        return False

    def trigger(self,us):
        state=self.runtime.trigger(us)
        if state in (2,3):
            if state==3:self.stops.append(dict(time_us=us,reason=self.runtime.timing_reason()))
            self.runtime.cut();self.high=[False]*self.channels;return True
        return False

    def close(self):self.runtime.close()


def run(controller='ours',scenario='warm_start',duration=10,step_us=250,tune=None,control_period_us=1000,sequential=False,reference_timer_bits=32,idle_options=None,semi_sequential=False,target_dispatcher=False,transient_options=None,load_options=None,secondary_options=None,plant_geometry=None):
    secondary_tune=None;secondary_program=None;secondary_monitor=None
    if secondary_options is not None:
        from secondary_stimulus import ContactProgram
        secondary_options=copy.deepcopy(secondary_options)
        if set(secondary_options)-{'tune','stimulus'} or 'tune'not in secondary_options:raise ValueError('Secondary comparison requires one explicit complete tune and contact program')
        if control_period_us!=5000:raise ValueError('Synthetic synchronous secondary monitor uses a nominal5ms cycle')
        secondary_tune=secondary_options['tune'];secondary_program=ContactProgram(secondary_options.get('stimulus'))
        wanted=secondary_tune['strategy'];want_seq=wanted in ('sequential','sequential_4cyl');want_semi=wanted in ('semi_sequential','semi_sequential_4cyl')
        if sequential and not want_seq or semi_sequential and not want_semi:raise ValueError('Conflicting secondary/cycle profile')
        sequential=want_seq;semi_sequential=want_semi
        if tune is not None and tune!=secondary_tune:raise ValueError('Conflicting complete secondary tune')
        if load_options is not None and load_options.get('tune')!=secondary_tune:raise ValueError('Load and secondary profiles must share the same declared complete tune')
        load_options=copy.deepcopy(load_options)if load_options is not None else dict(tune=secondary_tune)
        if transient_options is not None and transient_options['config']!=secondary_tune['transient_enrichment']:raise ValueError('Conflicting transient profile')
        transient_options=copy.deepcopy(transient_options)if transient_options is not None else dict(config=secondary_tune['transient_enrichment'])
        if secondary_tune['settings']['idle_enabled']:
            if idle_options is not None and idle_options.get('tune')!=secondary_tune:raise ValueError('Conflicting idle profile')
            idle_options=copy.deepcopy(idle_options)if idle_options is not None else dict(tune=secondary_tune)
        elif idle_options is not None:raise ValueError('Idle options conflict with complete secondary tune')
        if controller=='ours':tune=copy.deepcopy(secondary_tune)
    if sequential and semi_sequential:raise ValueError('Conflicting cycle profiles')
    if target_dispatcher and controller!='ours':raise ValueError('Target dispatcher applies only to the project')
    if tune is not None and not sequential and not semi_sequential:
        sequential=tune['strategy'] in ('sequential','sequential_4cyl');semi_sequential=tune['strategy'] in ('semi_sequential','semi_sequential_4cyl')
    if controller not in ('ours','speeduino','speeduino_per_tooth') or scenario not in (SCENARIOS+(CAM_SCENARIOS if sequential else ())+ (IDLE_SCENARIOS if idle_options is not None else ())+(TRANSIENT_SCENARIOS if transient_options is not None else ())+(('secondary_cycle','secondary_plateau')if secondary_tune is not None else ())):raise ValueError('Unknown benchmark case')
    if step_us not in (100,125,250,500) or not 1<=duration<=30:raise ValueError('Invalid benchmark duration/step')
    if control_period_us not in (1000,5000):raise ValueError('Unsupported control sampling period')
    if tune is not None and controller!='ours':raise ValueError('Custom tune is supported only by the project controller')
    idle=idle_options is not None
    if idle:
        idle_options=dict(idle_options);idle_tune=copy.deepcopy(idle_options.get('tune') or benchmark_tune());idle_tune['settings']['idle_enabled']=True
        if controller=='ours':tune=idle_tune
    if transient_options is not None:
        transient_options=copy.deepcopy(transient_options)
        if controller=='ours':
            tune=copy.deepcopy(tune or benchmark_tune());tune['transient_enrichment']=transient_options['config']
    if load_options is not None:
        load_options=copy.deepcopy(load_options);load_tune=load_options['tune']
        if controller=='ours':tune=copy.deepcopy(load_tune)
    if (sequential or semi_sequential) and controller=='ours':
        tune=copy.deepcopy(tune or benchmark_tune());tune['strategy']=('sequential' if sequential else 'semi_sequential')+('_4cyl' if tune['schema_version']<11 else '')
    if controller=='ours':
        # Geometry must use the same validated/migrated document that the
        # controller consumes. Accepted integral JSON floats and schema1's
        # implicit timing must not reach Python slicing as raw input.
        prepared=EngineRuntime(tune or benchmark_tune())
        try:tune=copy.deepcopy(prepared.tune)
        finally:prepared.close()
    geometry=plant_geometry or (EngineGeometry.from_tune(tune or benchmark_tune()) if controller=='ours' else EngineGeometry())
    if not isinstance(geometry,EngineGeometry):raise ValueError('Expected explicit physical EngineGeometry')
    if controller!='ours' and geometry!=EngineGeometry():raise ValueError('Existing production-reference adapter is a four-cylinder2L fixture; expanded fixture required')
    # Keep the historical default FMU available for exactly matching4-cylinder
    # regressions. Other declared geometry uses the separately attested model.
    plant=ResearchPlant(cold=scenario=='idle_cold_start' or bool(transient_options and transient_options.get('cold')),idle_valve=idle_options.get('valve_mode','normal') if idle else None,geometry=geometry if geometry!=EngineGeometry() else None,**(dict(ambient_kpa=load_options.get('ambient_kpa',100)) if load_options is not None else {}))
    secondary_channels=tuple(secondary_tune['secondary_tables'][k]['input_channel']for k in('fuel','spark'))if secondary_tune is not None else None
    try:ecu=(OurController(tune,target_dispatcher=True) if target_dispatcher else OurController(tune)) if controller=='ours' else SpeeduinoRuntime(per_tooth=controller=='speeduino_per_tooth',sequential=sequential,timer_bits=reference_timer_bits,semi_sequential=semi_sequential,secondary_channels=secondary_channels)
    except Exception:plant.close();raise
    trace=[];edges_all=[];injection_timing=[];accepted_crank=[];trigger_edges=[];cam_edges=[];cam_angles=[geometry.cam_edge_deg+360 if scenario=='cam_wrong_phase' else geometry.cam_edge_deg,geometry.cam_edge_deg+360];now=0;next_sample=0;tooth_index=1
    channels=CHANNEL_EXTENT
    state={};high=[False]*channels;rise=[0]*channels;max_high=[0]*channels;inhibits=[];hard_cut_samples=0;fault_mask=0
    monitor_started=False;monitor_begin_us=0;last_control_us=None;last_contact_levels=None;next_secondary_trace_us=0
    if idle and controller!='ours':
        initial=ecu.configure_idle(idle_tune,seeded=idle_options.get('seeded',True),invert=idle_options.get('invert',False))
        for us,ch,value,_,_ in initial:
            if ch!=8 or us!=0:raise RuntimeError('Unexpected before-start idle transition')
            high[ch]=value;plant.edge(ch,value,0)
    def inhibit(us,cause):
        for ch,value in enumerate(high):
            if value:
                max_high[ch]=max(max_high[ch],us-rise[ch]);edges_all.append([us,ch,False,'cut:'+cause])
        high[:]=[False]*channels;plant.cut();inhibits.append([us,cause])
    def plant_edge(ch,value,us,advance,latest,dwell):
        plant.edge(ch,value,us/1e6,advance,latest,dwell)
        actuator=channel_kind(ch)
        if semi_sequential and actuator and actuator[0]=='injector' and not value:
            # Record the plant's actual shaft angle after integrating up to
            # the executed closing edge. The plant geometry stays independent
            # of the controller's configured order/reference.
            end_angle=tune['timing']['injection_end_deg'] if controller=='ours' and tune else 540 if controller=='ours' else 180
            goal=(geometry.compression_tdc_deg[actuator[1]]+end_angle)%360
            injection_timing.append(dict(time_us=us,channel=ch,shaft_angle_deg=plant.angle,closing_error_deg=math.remainder(plant.angle-goal,360),width_us=us-rise[ch]))
        if actuator and actuator[0]=='coil' and not value:
            if controller=='ours':mode=dict(sync_status=2 if state.get('phase_synced') else 1 if state.get('crank_synced',state.get('synced')) else 0,ignition_cycle_deg=720 if sequential else 360,effective_sequential=sequential and bool(state.get('phase_synced')))
            else:
                mode=ecu.edge_modes.get((us,ch,value),{})
                if sequential and not mode:raise RuntimeError('Missing reference event mode')
            plant.spark_errors[-1].update(mode)
    try:
        if transient_options is not None and controller!='ours':ecu.configure_transient(transient_options['config'],map_sampling=transient_options.get('reference_map_sampling',0))
        if load_options is not None and controller!='ours':ecu.configure_load(load_tune,allow_cylinder_trims=secondary_tune is not None)
        if secondary_tune is not None:
            if controller=='ours':
                from secondary_stimulus import SecondaryMonitor
                secondary_monitor=SecondaryMonitor(secondary_tune,secondary_program)
            else:
                ecu.configure_secondary(secondary_tune)
                if secondary_tune['cylinder_trims']['enabled']:ecu.cylinder_trims(secondary_tune['cylinder_trims'])
        while now<round(duration*1e6):
            t=now/1e6
            if secondary_monitor is not None:
                secondary_monitor.progress(now)
                if now>=next_sample and not monitor_started:
                    monitor_begin_us=now;next_sample=secondary_monitor.begin(now);monitor_started=True
            elif secondary_program is not None:
                levels=secondary_program.levels(now)
                if levels!=last_contact_levels:ecu.contacts(levels);last_contact_levels=levels
            plant.tps=(12 if scenario=='throttle_step' else 100) if t>=3 and scenario in ('throttle_step','overrev') else 0
            if scenario=='secondary_cycle':plant.tps=12 if 3<=t<4 else 0
            if scenario=='secondary_plateau':plant.tps=20 if 3<=t<3.5 or 4.25<=t<5 else 25 if 3.5<=t<4.25 else 0
            if scenario=='idle_throttle_blip':plant.tps=8 if 4<=t<4.5 else 0
            if scenario=='transient_tip':plant.tps=0 if t<3 or t>=4 else (min(12,(t-3)*60) if t<3.6 else max(0,12-(t-3.6)*30))
            if scenario=='transient_reverse':plant.tps=0 if t<3 or t>=3.12 else ((t-3)*200 if t<3.04 else max(0,8-(t-3.04)*100))
            load=35 if scenario=='load_step' and t>=4 else 5
            if scenario=='idle_load_step':load=idle_options.get('step_load_nm',9) if 5<=t<9 else 5
            if scenario=='transient_load':load=9 if 4<=t<5.6 else 5
            # A declared motoring dynamometer forces the shaft across the hard
            # limit even if soft retard would otherwise settle below it. Its
            # supplied work is explicit as negative resisting-load work.
            if scenario=='overrev' and 6<=t<6.25:load=-70
            starter=t<2.5 or (scenario=='stall_restart' and 8<t<10)
            dropout=(scenario=='trigger_dropout' and 4<t<4.7) or (scenario=='stall_restart' and 4<t<8)
            if now>=next_sample:
                switch_snapshot=None;switch_inputs={};control_completed=True
                if secondary_monitor is not None:switch_snapshot,switch_inputs,control_completed=secondary_monitor.observe(now)
                sample=plant.sample(t)
                sample.update(switch_inputs)
                if scenario=='sensor_short' and 4<t<5:sample['map_kpa']=0
                if scenario=='transient_noise' and 3<=t<5:sample['tps_pct']+=.2 if (now//20000)%2 else 0
                if load_options is not None:
                    c=load_tune['load_model'];baro=load_options.get('ambient_kpa',100) if c['baro_source']=='aux' else c['fixed_baro_kpa'];emap=load_options.get('emap_kpa',100)
                    if controller=='ours':sample.update(aux_pressure_kpa=emap if c['aux_role']=='emap' else load_options.get('ambient_kpa',100),aux_pressure_qualified=c['aux_role']!='postcat_monitor')
                    else:ecu.pressures(emap,baro)
                    interval=load_options.get('map_unavailable_window')
                    if interval and interval[0]<=t<interval[1]:
                        sample['map_kpa']=None if controller=='ours' else 0
                        if controller=='ours':sample['map_qualified']=False
                    interval=load_options.get('known_overpressure_window')
                    if interval and interval[0]<=t<interval[1]:sample['map_kpa']=115
                if controller=='ours':
                    if control_completed:
                        if ecu.sample(sample,now):inhibit(now,'control')
                        last_control_us=now
                    state=copy.deepcopy(ecu.status)
                    fault_mask|=state.get('faults',0)
                    if secondary_monitor is not None:
                        secondary_monitor.consumed(switch_snapshot,control_completed,now)
                        secondary_monitor.history[-1]['edge_cursor']=len(edges_all)
                        secondary_monitor.history[-1]['control']=dict(time_us=now,rpm=state.get('rpm'),faults=state.get('faults'),state=state.get('state'),fuel_cut=state.get('fuel_cut'),spark_cut=state.get('spark_cut'),secondary_tables=copy.deepcopy(state.get('secondary_tables')))if control_completed else None
                else:
                    ecu.sensors(sample);state=ecu.status()
                    if transient_options is not None:state['transient_enrichment']=ecu.transient_status()
                    if load_options is not None:state['load_model']=ecu.load_status()
                    if secondary_tune is not None:state['secondary_reference']=ecu.secondary_status();last_control_us=state['secondary_reference']['last_loop_us']
                if idle:
                    state['idle_valve']=plant.idle_valve.snapshot()
                    state['idle_pwm']=ecu.runtime.idle_status() if controller=='ours' else ecu.idle_status()
                if (controller=='ours' and state.get('faults',0)&32) or (controller!='ours' and state.get('rpm',0)>=6450 and state.get('fuel_channels',255)==0 and state.get('ignition_channels',255)==0):
                    hard_cut_samples+=1
                next_sample=(monitor_begin_us if secondary_monitor is not None else now)+control_period_us;monitor_started=False
                trace_due=now>=next_secondary_trace_us if secondary_tune is not None else now%20000<1000
                if trace_due:
                    if secondary_tune is not None:next_secondary_trace_us=(now//20000+1)*20000
                    trace.append(dict(time=t,plant_rpm=plant.rpm,map_kpa=plant.map_kpa,
                                      tps=plant.tps,lambda_measured=plant.lambda_sensor,
                                      lambda_valid=plant.lambda_valid,sensor_map_kpa=sample['map_kpa'],**{'ecu':state},
                                      **(dict(control_observation_completed=control_completed,control_observed_us=last_control_us,control_observation_age_us=now-last_control_us if last_control_us is not None else None,contact_levels=secondary_program.levels(now))if secondary_tune is not None else {})))
            # End very near the next actual shaft-angle crossing. At most one
            # microsecond quantization remains after this adaptive subdivision.
            tooth_wait=(tooth_index*6-plant.angle)/(plant.rpm*6) if plant.rpm>1e-9 else step_us/1e6
            cam_wait=min((a-plant.angle)/(plant.rpm*6) for a in cam_angles) if sequential and plant.rpm>1e-9 else step_us/1e6
            delta=max(1,min(step_us,max(1,math.floor(min(tooth_wait,cam_wait)*1e6))))
            end=min(round(duration*1e6),now+delta,next_sample)
            if secondary_program is not None:end=min(end,secondary_program.next_event(now))
            if secondary_monitor is not None:end=min(end,secondary_monitor.next_event())
            edges=ecu.advance(end)
            cursor=now
            for us,ch,value,advance,dwell in edges:
                if not cursor<=us<=end:raise RuntimeError('Controller edge outside coupling interval')
                plant.integrate(cursor/1e6,(us-cursor)/1e6,starter,load);cursor=us
                if ch is None:inhibit(us,'deadline');continue
                if high[ch]==value:raise RuntimeError('Duplicate controller actuator edge')
                if value:rise[ch]=us
                else:max_high[ch]=max(max_high[ch],us-rise[ch])
                high[ch]=value
                plant_edge(ch,value,us,advance if advance is not None else state.get('advance_deg',10),state.get('advance_deg',10),dwell or 2800)
                edges_all.append([us,ch,value,'scheduled'])
            plant.integrate(cursor/1e6,(end-cursor)/1e6,starter,load);now=end
            while tooth_index*6<=plant.angle:
                tooth=tooth_index%60;target=tooth_index*6;tooth_index+=1
                if tooth>=58 or dropout:continue
                trigger_edges.append([now,tooth,plant.angle-target])
                if controller=='ours':
                    stopped=ecu.trigger(now)
                    if stopped:inhibit(now,'trigger')
                    timeout=ecu.runtime.crank_timeout_us()
                    if not stopped and timeout:accepted_crank.append([now,timeout])
                else:
                    # No virtual time elapses between the final timer callback
                    # and the production trigger/loop calls at this crossing.
                    post=ecu.advance(now,tooth=True)
                    for us,ch,value,advance,dwell in post:
                        if high[ch]==value:raise RuntimeError('Duplicate native post-tooth edge')
                        if value:rise[ch]=us
                        else:max_high[ch]=max(max_high[ch],us-rise[ch])
                        high[ch]=value;plant_edge(ch,value,us,state.get('advance_deg',10),10,2800)
                        edges_all.append([us,ch,value,'scheduled'])
            if sequential:
                for index in range(2):
                    while cam_angles[index]<=plant.angle:
                        target=cam_angles[index];cam_angles[index]+=720
                        emit=(index==0 and scenario!='cam_missing_start' and not(scenario=='cam_dropout' and t>=4)) or (index==1 and scenario=='cam_extra' and 4<t<4.8)
                        if not emit:continue
                        cam_edges.append([now,plant.angle-target,index])
                        if controller=='ours':
                            if ecu.cam(now):inhibit(now,'cam')
                        else:
                            post=ecu.input_edge(now,1,True)+ecu.input_edge(now,1,False)
                            for us,ch,value,advance,dwell in post:
                                if high[ch]==value:raise RuntimeError('Duplicate native post-cam edge')
                                if value:rise[ch]=us
                                else:max_high[ch]=max(max_high[ch],us-rise[ch])
                                high[ch]=value;plant_edge(ch,value,us,state.get('advance_deg',10),10,2800)
                                edges_all.append([us,ch,value,'scheduled'])
        ledger=plant.ledger();final_rpm=plant.rpm
        if controller!='ours':
            state=ecu.status()
            if secondary_tune is not None:state['secondary_reference']=ecu.secondary_status()
        inhibits_before_end=len(inhibits)
        gap_start=gap_end=None;post_loss=[]
        if scenario in ('trigger_dropout','stall_restart'):
            gap_start=max((r[0] for r in trigger_edges if r[0]<4100000),default=4000000)
            gap_end=min((r[0] for r in trigger_edges if r[0]>4100000),default=now)
            post_loss=[r for r in edges_all if gap_start<r[0]<gap_end]
        before_end_high=sum(high)
        if controller!='ours':
            for us,ch,value in ecu.halt():
                if value:raise RuntimeError('Native termination raised an output')
                if not high[ch]:raise RuntimeError('Duplicate native termination fall')
                max_high[ch]=max(max_high[ch],us-rise[ch]);high[ch]=False
                edges_all.append([us,ch,False,'cut:production_halt'])
            if any(high[ch] for ch in geometry.injector_channels+geometry.coil_channels):raise RuntimeError('Native production halt left an engine output high')
        else:ecu.runtime.cut()
        idle_halt_high=bool(high[8]) if idle and controller!='ours' else False
        idle_post_halt=[]
        if idle and controller!='ours':
            # Observe the unmodified production disable path for >2 periods.
            # This diagnostic interval is outside the coupled plant horizon.
            idle_post_halt=ecu._edges(ecu.command('idleclock '+str(now+50000)))
            if any(ch!=8 for _,ch,_,_,_ in idle_post_halt):raise RuntimeError('Engine output restarted after production halt')
        inhibit(now,'simulation_end')
        summary=dict(strategy='sequential' if sequential else 'semi_sequential' if semi_sequential else 'batch_wasted',project_runtime=('target_dispatcher' if getattr(ecu,'target_dispatcher',False) else 'portable_core') if controller=='ours' else None,reference_profile=ecu.profile if controller!='ours' else None,cam_profile=('one rising edge at90deg ATDC C1 compression TDC (deliberately wrong by360)' if scenario=='cam_wrong_phase' else 'one rising edge at450deg ATDC C1 compression TDC') if sequential else None,reference_timer_bits=reference_timer_bits if controller!='ours' else None,controller=controller,scenario=scenario,duration_s=duration,step_us=step_us,
                     control_period_us=control_period_us,
                     plant='MVEMLib air path + local empirical combustion/free shaft, uncalibrated',
                     plant_geometry=geometry.summary(),plant_air_parameters=plant.air.parameters,geometry_source='explicit_fixed_fixture' if plant_geometry else 'declared_tune_geometry_assumed_physical' if controller=='ours' else 'historical_four_cylinder_reference_fixture',
                     cylinder_fuel_mg=plant.cylinder_fuel_mg,cylinder_burned_mg=plant.cylinder_burned_mg,cylinder_scheduled_work_j=plant.cylinder_scheduled_work_j,cylinder_shaft_j=plant.cylinder_shaft_j,
                     physical_outputs_enabled=False,final_rpm=final_rpm,max_rpm=max((r['plant_rpm'] for r in trace),default=0),
                     sparks=plant.sparks,edges=len(edges_all),trigger_edges=len(trigger_edges),
                     max_trigger_quantization_deg=max((r[2] for r in trigger_edges),default=0),
                     max_injector_high_us=max(max_high[ch] for ch in geometry.injector_channels),max_dwell_high_us=max(max_high[ch] for ch in geometry.coil_channels),
                     max_spark_error_deg=max((abs(r['error_deg']) for r in plant.spark_errors),default=0),
                     max_spark_error_after_3s_deg=max((abs(r['error_deg']) for r in plant.spark_errors if r['time_s']>=3),default=0),
                     spark_error_reference='latched dwell-start demand' if controller=='ours' else 'last sampled production demand; not event-latched',
                     hard_cut_samples=hard_cut_samples,
                     project_fault_mask_seen=fault_mask if controller=='ours' else None,
                     first_crank_sync_s=next((r['time'] for r in trace if r['ecu'].get('crank_synced',r['ecu'].get('sync',0)>=1)),None),first_sync_s=next((r['time'] for r in trace if r['ecu'].get('synced',r['ecu'].get('sync',0)==2 if sequential else r['ecu'].get('sync',0)>=1)),None),
                     mean_final_second_rpm=sum(r['plant_rpm'] for r in trace if r['time']>=duration-1)/max(1,sum(r['time']>=duration-1 for r in trace)),
                     dropout_raw_gap_us=[gap_start,gap_end] if gap_start is not None else None,
                     last_output_after_dropout_ms=max((r[0]-gap_start for r in post_loss),default=0)/1000,
                     output_rises_after_dropout=sum(bool(r[2]) for r in post_loss),
                     inhibit_calls=inhibits_before_end,protection_stops=ecu.stops if controller=='ours' else [],
                     outputs_high_before_stop=before_end_high,termination='explicit virtual production halt/cut',
                     final_outputs_high=sum(high),ledger=ledger)
        if sequential:summary.update(sequential_metrics(plant.spark_errors))
        if idle:
            summary.update(idle_valve=plant.idle_valve.snapshot(),idle_profile=ecu.idle_profile if controller!='ours' else dict(tune=idle_tune['idle_control'],settings={k:v for k,v in idle_tune['settings'].items() if k.startswith('idle_')}),
                           idle_high_after_production_halt=idle_halt_high,
                           idle_post_halt_probe=dict(duration_us=50000,edges=idle_post_halt,pwm_restarts_or_stays_high=idle_halt_high or any(row[2] for row in idle_post_halt),basis='timer-only diagnostic after coupled horizon; no plant integration in this separate probe'),
                           idle_electrical_ledger_basis='before explicit external simulation-end cut; NC mechanical/current decay is finite')
        if semi_sequential:summary['max_injection_closing_error_after_3s_deg']=max((abs(row['closing_error_deg']) for row in injection_timing if row['time_us']>=3000000),default=0)
        if transient_options is not None:
            summary['transient_profile']=dict(requested=transient_options,reference=ecu.transient_profile if controller!='ours' else None)
            summary['transient_scope']='Independent fixed plant, executed actuator edges only; empirical wall film, no calibration or physical qualification'
        if load_options is not None:
            summary['load_profile']=dict(requested=load_options,reference=ecu.load_profile if controller!='ours' else None)
            summary['load_scope']='Declared source/pressure/AFR fixture; FMU ambient pressure is a physical parameter, EMAP is an exogenous sensor stimulus with no exhaust dynamics; pulse-driven empirical combustion; no calibration or physical qualification'
        if secondary_tune is not None:
            summary['secondary_profile']=dict(requested=secondary_options,reference=ecu.secondary_profile if controller!='ours'else None)
            summary['secondary_scope']='Actual controller/dispatcher loops on independent plants. Project actual portable acquisition uses a synthetic three-stage MCP model in a nominal5ms blocking monitor: registers0..8 at+400us,GPIO/OLAT at+1200us,guard/publication at+1800us; other I2C operation durations are declared wire-clock-scale assumptions. Reference independently polls raw virtual GPIO without project debounce/validity; source-channel acquisition ages are not provided. Native main-loop opportunities track adaptive plant steps,tooth callbacks and program-event boundaries, with zero CPU/IRQ cost. No physical timing/electrical/engine qualification.'
            summary['secondary_applied_faults']=secondary_monitor.applied_faults if secondary_monitor is not None else []
            summary['secondary_monitor_operations']=int(secondary_monitor.runtime.snapshot()['attempts'])if secondary_monitor is not None else None
            summary['secondary_operation_pending_at_end']=secondary_monitor.pending is not None if secondary_monitor is not None else None
        if controller=='ours' and gap_start is not None:
            last=max((r for r in accepted_crank if r[0]<=gap_start),default=None)
            summary['dropout_accepted_crank_watchdog']=dict(last_accepted_us=last[0],timeout_us=last[1],deadline_us=last[0]+last[1],basis='Native production decoder timeout at last successfully accepted plan; period*(missing+2)*2 clamped20..150ms') if last else None
        return dict(summary=summary,trace=trace,edges=edges_all,injection_timing=injection_timing,triggers=trigger_edges,
                    accepted_crank_watchdogs=accepted_crank,cams=cam_edges,spark_timing=plant.spark_errors,dwell=plant.dwell_events,final_ecu=state,
                    **(dict(combustions=plant.cylinder_combustions) if transient_options is not None or load_options is not None else {}),
                    **(dict(secondary_monitor=secondary_monitor.history if secondary_monitor is not None else None)if secondary_tune is not None else {}))
    finally:
        if secondary_monitor is not None:secondary_monitor.close()
        ecu.close();plant.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller',choices=('ours','speeduino','speeduino_per_tooth'),default='ours')
    parser.add_argument('--scenario',choices=SCENARIOS,default='warm_start')
    parser.add_argument('--duration',type=float,default=10)
    parser.add_argument('--step-us',type=int,default=250)
    cycle=parser.add_mutually_exclusive_group()
    cycle.add_argument('--semi-sequential',action='store_true')
    cycle.add_argument('--sequential',action='store_true')
    parser.add_argument('--target-dispatcher',action='store_true')
    parser.add_argument('--output',type=Path)
    a=parser.parse_args();result=run(a.controller,a.scenario,a.duration,a.step_us,sequential=a.sequential,semi_sequential=a.semi_sequential,target_dispatcher=a.target_dispatcher)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(result['summary'],indent=2,allow_nan=False))
