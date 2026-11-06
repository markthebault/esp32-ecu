#!/usr/bin/env python3
"""Real controller/decoder/PWM paths on independent pulse-driven turbo plants.

Each invocation owns its own plant history. Full comparison acceptance and
calibrated physics remain separate; native execution is not physical hardware.
"""
import argparse,json,math,time
from pathlib import Path
from boost_research_plant import BoostResearchPlant
from boost_valve_plant import BoostValve
from compare_engine_controllers import OurController,benchmark_tune,ROOT
from speeduino_turbo_runtime import SpeeduinoTurboRuntime
from boost_engine_provenance import RunProvenance
from engine_geometry import EngineGeometry,CHANNEL_EXTENT
SCENARIOS=('nominal','throttle_blip','trigger_dropout','map_high_rail','charged_map_rail','cam_dropout')

def tune(mode,duty=40,target=150,cut_kpa=220,geometry=None,strategy='batch_wasted'):
 if strategy not in ('batch_wasted','semi_sequential','sequential'):raise ValueError('Unknown engine strategy')
 if geometry is not None and not isinstance(geometry,EngineGeometry):raise ValueError('Explicit physical EngineGeometry required')
 t=benchmark_tune();t['engine']['displacement_cc']=1800
 t['strategy']=strategy
 if geometry is not None:
  t['engine'].update(cylinders=geometry.cylinders,displacement_cc=geometry.displacement_cc)
  t['timing']['firing_order']=[*geometry.firing_order,*([0]*(8-geometry.cylinders))]
 t['boost_control'].update(pressure_enabled=True,mode=mode)
 t['boost_control'].update(frequency_hz=24,activation='fixed',activation_kpa=120,cut_kpa=cut_kpa)
 t['boost_control']['open_duty']['cells']=[duty]*64;t['boost_control']['feedforward']['cells']=[duty]*64;t['boost_control']['target']['cells']=[target]*64
 return t

def run(output,duration=6.,step_us=250,mode='off',actuator='normal',controller='ours',reference=None,throttle_pct=20.,load_nm=35.,scenario='nominal',duty=40,target=150,cut_kpa=220,reference_protection_rpm=6500,geometry=None,strategy='batch_wasted'):
 if type(step_us) is not int or step_us not in (125,250,500) or not 0<duration<=30 or not 0<=throttle_pct<=100 or not math.isfinite(load_nm):raise ValueError('Invalid bounded research interval')
 if controller not in ('ours','speeduino') or controller=='speeduino' and reference is None:raise ValueError('Production comparison needs an attested reference executable')
 if scenario not in SCENARIOS or type(duty) is not int or not 0<=duty<=90 or duty%2 or type(target) is not int or not 50<=target<=210 or target%2:raise ValueError('Unrepresentable comparison stimulus/profile')
 if type(cut_kpa) is not int or not 120<=cut_kpa<=300 or cut_kpa%2 or target>cut_kpa-10:raise ValueError('Invalid common pressure-cut profile')
 if type(reference_protection_rpm) is not int or not 0<=reference_protection_rpm<=6500 or reference_protection_rpm%100:raise ValueError('Invalid declared reference protection RPM')
 if geometry is not None and not isinstance(geometry,EngineGeometry):raise ValueError('Explicit physical EngineGeometry required')
 physical=geometry or EngineGeometry(4,(1,3,4,2),1800)
 if physical.tooth1_tdc_deg!=90 or physical.cam_edge_deg!=540:raise ValueError('Turbo fixture currently requires physical tooth1=90deg andcam=540deg')
 if strategy not in ('batch_wasted','semi_sequential','sequential'):raise ValueError('Unknown engine strategy')
 if scenario=='cam_dropout'and strategy!='sequential':raise ValueError('Cam fault requires sequential strategy')
 if controller=='speeduino'and (physical!=EngineGeometry(4,(1,3,4,2),1800)or strategy!='batch_wasted'):
  raise ValueError('Existing turbo production-reference fixture is4-cylinder1800cc batch; expanded boost reference is required')
 output=output.resolve();output.mkdir(parents=True,exist_ok=False)
 provenance=RunProvenance(output);hashes=provenance.source_hashes
 profile=tune(mode,duty,target,cut_kpa,geometry,strategy);(output/'tune.json').write_text(json.dumps(profile,indent=2)+'\n')
 provenance.record['requested_tune_sha256']=provenance.track(output/'tune.json')
 plant=BoostResearchPlant(actuator_mode=actuator,geometry=geometry)
 ecu=None
 try:
  ecu=OurController(profile,target_dispatcher=True) if controller=='ours' else SpeeduinoTurboRuntime(reference,mode,duty,target,cut_kpa=cut_kpa,protection_rpm=reference_protection_rpm)
  if controller=='ours':provenance.bind_own(ecu.runtime)
  else:provenance.bind_reference(reference)
  provenance_sha256=provenance.save()
 except BaseException:
  if ecu is not None:ecu.close()
  plant.close();raise
 channels=CHANNEL_EXTENT if geometry is not None or strategy!='batch_wasted'else 10
 allowed=set(physical.injector_channels+physical.coil_channels+(9,))
 now=0;next_sample=0;next_trace=0;next_progress=0;tooth=1;cam_angle=physical.cam_edge_deg;cams=0;high=[False]*channels;edges=0;teeth=0;faults=0;state={};status='running';failure=None
 started=time.monotonic();peak_rpm=peak_map=peak_turbo=0.;max_tooth_error=0.;boost_edges=0;suppressed_teeth=0;sample={};charged_start=None;charged_channels=[]
 def progress(status,error=None):
  body=dict(status=status,complete=status=='complete',controller=controller,time_us=now,duration_s=duration,wall_s=time.monotonic()-started,
   error=error,edges=edges,boost_edges=boost_edges,trigger_edges=teeth,maximum_crank_rpm=peak_rpm,maximum_map_kpa=peak_map,maximum_turbo_rad_s=peak_turbo,
   source_hashes=hashes,provenance_manifest_sha256=provenance_sha256,scenario=scenario,charged_fault_start_us=charged_start,suppressed_teeth=suppressed_teeth,actual_RF=False,physical_execution=False,paired_comparison_accepted=False)
  temporary=output/'progress.pending';temporary.write_text(json.dumps(body,indent=2)+'\n');temporary.replace(output/'progress.json')
 def cut(when,cause,stream):
  nonlocal edges
  for ch,value in enumerate(high):
   if value:
    edges+=1;stream.write(json.dumps(dict(sequence=edges,time_us=when,ch=ch,high=False,cause='cut:'+cause))+'\n')
  high[:]=[False]*channels;plant.cut()
 def edge(row,stream,cause='dispatcher'):
  nonlocal edges,boost_edges
  when,ch,value,advance,dwell=row
  if ch is None:cut(when,'deadline',stream);return
  if type(when) is not int or not 0<=when<=round(duration*1e6) or type(ch) is not int or ch not in allowed or type(value) is not bool:raise RuntimeError('Unexpected active dispatcher channel/time/value')
  if high[ch]==value:raise RuntimeError('Duplicate dispatcher transition')
  high[ch]=value;plant.edge(ch,value,when/1e6,advance if advance is not None else state.get('advance_deg',10),state.get('advance_deg',10),dwell or 2800)
  edges+=1;boost_edges+=ch==9 and cause=='dispatcher'
  stream.write(json.dumps(dict(sequence=edges,time_us=when,ch=ch,high=value,cause=cause))+'\n')
 def same_time(rows,stream,cause='dispatcher'):
  for row in rows:
   if row[0]!=now:raise RuntimeError('Same-time output outside current plant boundary')
   edge(row,stream,cause)
 try:
  progress('running')
  with (output/'trace.jsonl').open('x') as trace,(output/'edges.jsonl').open('x') as transitions,(output/'trigger-stimuli.jsonl').open('x') as captures:
   while now<round(duration*1e6):
    t=now/1e6;plant.tps=throttle_pct if t>=3 else 0.;starter=t<2.5;load=load_nm if t>=4 else 5
    if scenario=='throttle_blip' and 6<=t<6.4:plant.tps=0.
    if now>=next_sample:
     sample=plant.sample(t)
     if scenario=='charged_map_rail' and charged_start is None and now>=6000000:
      charged_channels=[physical.coil_channels[index] for index,start in enumerate(plant.coil_on) if start is not None and t-start>=.0015]
      if charged_channels:charged_start=now
     if scenario=='map_high_rail' and 6<=t<6.25:sample['map_kpa']=400.
     if charged_start is not None and charged_start<=now<charged_start+250000:sample['map_kpa']=400.
     if controller=='ours':
      if ecu.sample(sample,now):cut(now,'control',transitions)
      state=ecu.status;faults|=state['faults']
     else:ecu.sensors(sample);state=ecu.status();state['boost_control']=ecu.boost_status()
     # engine_step can queue an immediate PWM rise at this exact timestamp.
     # Consume it before observing either the plant or dispatcher state.
     if controller=='ours':same_time(ecu.advance(now),transitions)
     next_sample=now+5000
    if now>=next_trace:
     trace.write(json.dumps(dict(time_us=now,edges_consumed=edges,boost_dispatcher_edges_consumed=boost_edges,plant_rpm=plant.rpm,sensor_input=sample,input_adc_counts=ecu.raw_adc_counts if controller=='speeduino' else None,gas=plant.air.read(),valve=plant.boost_valve.snapshot(),control=state,dispatcher=ecu.runtime.boost_status() if controller=='ours' else ecu.boost_status()),allow_nan=False)+'\n');next_trace=now+20000
    if now>=next_progress:
     trace.flush();transitions.flush();progress('running');next_progress=now+250000
    waiting=(tooth*6-plant.angle)/(plant.rpm*6) if plant.rpm>1e-9 else step_us/1e6
    if strategy=='sequential'and plant.rpm>1e-9:waiting=min(waiting,(cam_angle-plant.angle)/(plant.rpm*6))
    delta=max(1,min(step_us,max(1,math.floor(waiting*1e6))))
    end=min(round(duration*1e6),now+delta,next_sample,next_trace,next_progress)
    cursor=now
    for row in ecu.advance(end):
     when=row[0]
     if not cursor<=when<=end:raise RuntimeError('Dispatcher event outside plant interval')
     plant.integrate(cursor/1e6,(when-cursor)/1e6,starter,load);cursor=when;edge(row,transitions)
    plant.integrate(cursor/1e6,(end-cursor)/1e6,starter,load);now=end
    while tooth*6<=plant.angle:
     index=tooth%60;target_angle=tooth*6;tooth+=1
     if index>=58:continue
     delivered=not(scenario=='trigger_dropout' and 6<=now/1e6<6.3)
     captures.write(json.dumps(dict(time_us=now,tooth_angle_deg=target_angle,slot=index,delivered=delivered))+'\n')
     max_tooth_error=max(max_tooth_error,plant.angle-target_angle)
     if not delivered:suppressed_teeth+=1;continue
     teeth+=1
     if controller=='ours':
      if ecu.trigger(now):cut(now,'trigger',transitions)
      same_time(ecu.advance(now),transitions)
     else:
      same_time(ecu.advance(now,tooth=True),transitions)
    if strategy=='sequential':
     while cam_angle<=plant.angle:
      delivered=not(scenario=='cam_dropout'and now>=6000000)
      captures.write(json.dumps(dict(kind='cam',time_us=now,cam_angle_deg=cam_angle,delivered=delivered))+'\n');cam_angle+=720
      if delivered:
       cams+=1
       if ecu.cam(now):cut(now,'cam',transitions)
       same_time(ecu.advance(now),transitions)
    peak_rpm=max(peak_rpm,plant.rpm);peak_map=max(peak_map,plant.map_kpa);peak_turbo=max(peak_turbo,plant.air.state[12])
   if scenario=='charged_map_rail' and charged_start is None:raise RuntimeError('Declared charged-coil fault was never reached')
   before_halt=dict(high=high.copy(),edges_consumed=edges,rpm=plant.rpm,map_kpa=plant.map_kpa,turbo_rad_s=plant.air.state[12],ledger=plant.ledger(),cut_discharges=[dict(row) for row in plant.cut_discharges],control=state,dispatcher=ecu.runtime.boost_status() if controller=='ours' else ecu.boost_status(),
    cylinder_fuel_mg=plant.cylinder_fuel_mg.copy(),cylinder_burned_mg=plant.cylinder_burned_mg.copy(),cylinder_shaft_j=plant.cylinder_shaft_j.copy())
   if controller=='ours':ecu.runtime.cut()
   else:same_time(ecu.halt(),transitions,'fixture_halt')
   cut(now,'simulation_end',transitions)
   after_halt=dict(high=high.copy(),edges_consumed=edges,injector_on=plant.injector_on.copy(),coil_on=plant.coil_on.copy(),
    boost_command_high=plant.boost_valve.coil.high,ledger=plant.ledger(),cut_discharges=[dict(row)for row in plant.cut_discharges],
    cylinder_fuel_mg=plant.cylinder_fuel_mg.copy(),cylinder_burned_mg=plant.cylinder_burned_mg.copy(),cylinder_shaft_j=plant.cylinder_shaft_j.copy(),
    basis='Same physical boundary after explicit global command-low, with coil discharge and pending heat/fuel/work retained; no instantaneous magnetic-current quench')
   if any(high)or any(start is not None for start in plant.injector_on+plant.coil_on)or plant.boost_valve.coil.high:
    raise RuntimeError('Simulation halt left an actuator command high')
  provenance.verify()
  result=dict(qualification=__doc__.strip(),controller=controller,mode=mode,actuator=actuator,step_us=step_us,duration_s=duration,
   strategy=strategy,plant_geometry=physical.summary(),plant_air_parameters=plant.air.parameters,cam_edges=cams,
   stimulus=dict(scenario=scenario,throttle_pct_after_3s=throttle_pct,load_nm_after_4s=load_nm,starter_until_s=2.5,throttle_blip_s=[6,6.4] if scenario=='throttle_blip' else None,crank_capture_dropout_s=[6,6.3] if scenario=='trigger_dropout' else None,map_sensor_override_kpa=400 if scenario in ('map_high_rail','charged_map_rail') else None,map_sensor_override_s=[6,6.25] if scenario=='map_high_rail' else ([charged_start/1e6,(charged_start+250000)/1e6] if charged_start is not None else None),charged_fault_start_us=charged_start,charged_channels_at_start=charged_channels,minimum_charged_dwell_us=1500 if scenario=='charged_map_rail' else None,cut_kpa=cut_kpa,reference_protection_rpm=reference_protection_rpm),reference_profile=ecu.profile if controller=='speeduino' else None,
   source_hashes=hashes,provenance_manifest_sha256=provenance_sha256,component_provenance=plant.air.components.provenance,completed=True,
   before_halt=before_halt,after_halt=after_halt,observed_project_fault_mask=faults,maximum_tooth_quantization_deg=max_tooth_error,
   edges=edges,boost_edges=boost_edges,trigger_edges=teeth,suppressed_teeth=suppressed_teeth,production_speeduino_executed=controller=='speeduino',paired_comparison_accepted=False,physical_execution=False)
  (output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');progress('complete');print(json.dumps(dict(output=str(output),complete=True,wall_s=time.monotonic()-started)))
 except BaseException as error:
  progress('failed',dict(type=type(error).__name__,message=str(error)));raise
 finally:ecu.close();plant.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=float,default=6)
 p.add_argument('--step-us',type=int,default=250);p.add_argument('--mode',choices=('off','open_loop','closed_loop'),default='off');p.add_argument('--actuator',choices=BoostValve.MODES,default='normal')
 p.add_argument('--controller',choices=('ours','speeduino'),default='ours');p.add_argument('--reference',type=Path);p.add_argument('--throttle-pct',type=float,default=20);p.add_argument('--load-nm',type=float,default=35)
 p.add_argument('--cylinders',type=int,choices=range(1,9));p.add_argument('--displacement-cc',type=float)
 p.add_argument('--strategy',choices=('batch_wasted','semi_sequential','sequential'),default='batch_wasted')
 p.add_argument('--scenario',choices=SCENARIOS,default='nominal');p.add_argument('--duty-pct',type=int,default=40);p.add_argument('--target-kpa',type=int,default=150)
 p.add_argument('--cut-kpa',type=int,default=220)
 p.add_argument('--reference-protection-rpm',type=int,default=6500)
 a=p.parse_args();count=a.cylinders or 4
 physical=None if a.cylinders is None and a.displacement_cc is None else EngineGeometry(count,(1,*range(count,1,-1)),a.displacement_cc if a.displacement_cc is not None else 500*count)
 run(a.output,a.duration,a.step_us,a.mode,a.actuator,a.controller,a.reference,a.throttle_pct,a.load_nm,a.scenario,a.duty_pct,a.target_kpa,a.cut_kpa,a.reference_protection_rpm,physical,a.strategy)
