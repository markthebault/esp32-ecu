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

ROOT=Path(__file__).resolve().parents[1]
CAM_SCENARIOS=('cam_dropout','cam_extra','cam_wrong_phase','cam_missing_start')
SCENARIOS=('warm_start','throttle_step','load_step','trigger_dropout','sensor_short','stall_restart','overrev')


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
    def __init__(self,tune=None):
        self.runtime=EngineRuntime(tune or benchmark_tune());self.runtime.wheel()
        self.status={};self.high=[False]*8;self.stops=[]

    def sample(self,sample,us):
        self.status=self.runtime.step(sample,us,use_decoder=True)
        if self.status['faults'] or self.status['state']=='stopped':
            self.runtime.cut();self.high=[False]*8;return True
        return False

    def advance(self,us):
        edges=[]
        while self.runtime.next_event_us()<=us:
            when=self.runtime.next_event_us();ch,high,advance,dwell=self.runtime.pop_event()
            if ch is None:
                self.runtime.cut();self.high=[False]*8
                edges.append((when,None,False,None,None));continue
            self.high[ch]=high;edges.append((when,ch,high,advance,dwell))
        return edges

    def cam(self,us):
        state=self.runtime.cam(us)
        if state in (2,3):
            if state==3:self.stops.append(dict(time_us=us,reason=self.runtime.timing_reason()))
            self.runtime.cut();self.high=[False]*8;return True
        return False

    def trigger(self,us):
        state=self.runtime.trigger(us)
        if state in (2,3):
            if state==3:self.stops.append(dict(time_us=us,reason=self.runtime.timing_reason()))
            self.runtime.cut();self.high=[False]*8;return True
        return False

    def close(self):self.runtime.close()


def run(controller='ours',scenario='warm_start',duration=10,step_us=250,tune=None,control_period_us=1000,sequential=False,reference_timer_bits=32):
    if controller not in ('ours','speeduino','speeduino_per_tooth') or scenario not in (SCENARIOS+CAM_SCENARIOS if sequential else SCENARIOS):raise ValueError('Unknown benchmark case')
    if step_us not in (100,125,250,500) or not 1<=duration<=30:raise ValueError('Invalid benchmark duration/step')
    if control_period_us not in (1000,5000):raise ValueError('Unsupported control sampling period')
    if tune is not None and controller!='ours':raise ValueError('Custom tune is supported only by the project controller')
    plant=ResearchPlant()
    if sequential and controller=='ours':
        tune=copy.deepcopy(tune or benchmark_tune());tune['strategy']='sequential_4cyl'
    try:ecu=OurController(tune) if controller=='ours' else SpeeduinoRuntime(per_tooth=controller=='speeduino_per_tooth',sequential=sequential,timer_bits=reference_timer_bits)
    except Exception:plant.close();raise
    trace=[];edges_all=[];trigger_edges=[];cam_edges=[];cam_angles=[900. if scenario=='cam_wrong_phase' else 540.,900.];now=0;next_sample=0;tooth_index=1
    state={};high=[False]*8;rise=[0]*8;max_high=[0]*8;inhibits=[];hard_cut_samples=0;fault_mask=0
    def inhibit(us,cause):
        for ch,value in enumerate(high):
            if value:
                max_high[ch]=max(max_high[ch],us-rise[ch]);edges_all.append([us,ch,False,'cut:'+cause])
        high[:]=[False]*8;plant.cut();inhibits.append([us,cause])
    def plant_edge(ch,value,us,advance,latest,dwell):
        plant.edge(ch,value,us/1e6,advance,latest,dwell)
        if ch>=4 and not value:
            if controller=='ours':mode=dict(sync_status=2 if state.get('phase_synced') else 1 if state.get('crank_synced',state.get('synced')) else 0,ignition_cycle_deg=720 if sequential else 360,effective_sequential=sequential and bool(state.get('phase_synced')))
            else:
                mode=ecu.edge_modes.get((us,ch,value),{})
                if sequential and not mode:raise RuntimeError('Missing reference event mode')
            plant.spark_errors[-1].update(mode)
    try:
        while now<round(duration*1e6):
            t=now/1e6
            plant.tps=(12 if scenario=='throttle_step' else 100) if t>=3 and scenario in ('throttle_step','overrev') else 0
            load=35 if scenario=='load_step' and t>=4 else 5
            # A declared motoring dynamometer forces the shaft across the hard
            # limit even if soft retard would otherwise settle below it. Its
            # supplied work is explicit as negative resisting-load work.
            if scenario=='overrev' and 6<=t<6.25:load=-70
            starter=t<2.5 or (scenario=='stall_restart' and 8<t<10)
            dropout=(scenario=='trigger_dropout' and 4<t<4.7) or (scenario=='stall_restart' and 4<t<8)
            if now>=next_sample:
                sample=plant.sample(t)
                if scenario=='sensor_short' and 4<t<5:sample['map_kpa']=0
                if controller=='ours':
                    if ecu.sample(sample,now):inhibit(now,'control')
                    state=copy.deepcopy(ecu.status)
                    fault_mask|=state.get('faults',0)
                else:
                    ecu.sensors(sample);state=ecu.status()
                if (controller=='ours' and state.get('faults',0)&32) or (controller!='ours' and state.get('rpm',0)>=6450 and state.get('fuel_channels',255)==0 and state.get('ignition_channels',255)==0):
                    hard_cut_samples+=1
                next_sample=now+control_period_us
                if now%20000<1000:
                    trace.append(dict(time=t,plant_rpm=plant.rpm,map_kpa=plant.map_kpa,
                                      tps=plant.tps,lambda_measured=plant.lambda_sensor,
                                      lambda_valid=plant.lambda_valid,sensor_map_kpa=sample['map_kpa'],**{'ecu':state}))
            # End very near the next actual shaft-angle crossing. At most one
            # microsecond quantization remains after this adaptive subdivision.
            tooth_wait=(tooth_index*6-plant.angle)/(plant.rpm*6) if plant.rpm>1e-9 else step_us/1e6
            cam_wait=min((a-plant.angle)/(plant.rpm*6) for a in cam_angles) if sequential and plant.rpm>1e-9 else step_us/1e6
            delta=max(1,min(step_us,max(1,math.floor(min(tooth_wait,cam_wait)*1e6))))
            end=min(round(duration*1e6),now+delta,next_sample)
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
                    if ecu.trigger(now):inhibit(now,'trigger')
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
        if controller!='ours':state=ecu.status()
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
            if any(high):raise RuntimeError('Native production halt left an output high')
        else:ecu.runtime.cut()
        inhibit(now,'simulation_end')
        summary=dict(strategy='sequential_4cyl' if sequential else 'batch_wasted_4cyl',cam_profile=('one rising edge at90deg ATDC C1 compression TDC (deliberately wrong by360)' if scenario=='cam_wrong_phase' else 'one rising edge at450deg ATDC C1 compression TDC') if sequential else None,reference_timer_bits=reference_timer_bits if controller!='ours' else None,raw_exhaust_stroke_discharges=sum(abs(r['phase_error_deg'])>180 for r in plant.spark_errors) if sequential else None,wasted_fallback_discharges=sum(r.get('ignition_cycle_deg')==360 for r in plant.spark_errors) if sequential else None,unsynced_720_discharges=sum(r.get('ignition_cycle_deg')==720 and r.get('sync_status')!=2 for r in plant.spark_errors) if sequential else None,wrong_stroke_sparks=sum(abs(r['phase_error_deg'])>180 for r in plant.spark_errors if r.get('effective_sequential')) if sequential else None,max_spark_720_error_deg=max((abs(r['phase_error_deg']) for r in plant.spark_errors if r.get('effective_sequential') and r['rpm']>=50),default=0) if sequential else None,controller=controller,scenario=scenario,duration_s=duration,step_us=step_us,
                     control_period_us=control_period_us,
                     plant='MVEMLib air path + local empirical combustion/free shaft, uncalibrated',
                     physical_outputs_enabled=False,final_rpm=final_rpm,max_rpm=max((r['plant_rpm'] for r in trace),default=0),
                     sparks=plant.sparks,edges=len(edges_all),trigger_edges=len(trigger_edges),
                     max_trigger_quantization_deg=max((r[2] for r in trigger_edges),default=0),
                     max_injector_high_us=max(max_high[:4]),max_dwell_high_us=max(max_high[4:]),
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
        return dict(summary=summary,trace=trace,edges=edges_all,triggers=trigger_edges,
                    cams=cam_edges,spark_timing=plant.spark_errors,dwell=plant.dwell_events,final_ecu=state)
    finally:
        ecu.close();plant.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller',choices=('ours','speeduino','speeduino_per_tooth'),default='ours')
    parser.add_argument('--scenario',choices=SCENARIOS,default='warm_start')
    parser.add_argument('--duration',type=float,default=10)
    parser.add_argument('--step-us',type=int,default=250)
    parser.add_argument('--output',type=Path)
    a=parser.parse_args();result=run(a.controller,a.scenario,a.duration,a.step_us)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(result['summary'],indent=2,allow_nan=False))
