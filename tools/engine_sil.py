"""Deterministic reduced-order SI-engine regression plant, NOT calibrated engine physics.
Independent intake/VE/dead-time/torque parameters, real shared C++ ECU + trigger
code, virtual injector edges and ignition edges. No predetermined RPM trace.
The model is for software/fault regressions, not tuning/emissions predictions.
"""
import copy, json, math, random
from engine_runtime import EngineRuntime

SCENARIOS=('warm_start','cold_start','throttle_step','load_step','trigger_dropout','sensor_short','overrev','stall_restart','load_stall_restart')
class Plant:
 def __init__(self,cold=False,seed=1):
  rng=random.Random(seed);self.injector_flow_cc_min=300*rng.uniform(.98,1.02);self.rotor_inertia=.18*rng.uniform(.97,1.03)
  self.rpm=0.;self.angle=0.;self.map_kpa=99.;self.tps=2.;self.clt=0. if cold else 85.;self.iat=25.;self.battery=13.8
  self.fuel_rate=0.;self.air_rate=0.;self.lambda_sensor=1.;self.last_spark=-1e9;self.advance=15.;self.started=False
  self.injector_on=[None]*4;self.fuel_mg=0.;self.sparks=0;self.spk_errors=[]
  self.coil_on=[None]*4;self.coil_requests=[0]*4;self.dwell_events=[];self.spark_errors=[];self.charge_mg=[0.]*4;self.wall_mg=[0.]*4;self.combustions=[];self.exhaust_lambda=1.;self.burned_work_j=0.
 def edge(self,ch,high,time_s,commanded_advance=0,latest_demand=0,requested_dwell_us=0):
  if ch<4:self.injector_on[ch]=time_s if high else None
  elif high:
   self.coil_on[ch-4]=time_s;self.coil_requests[ch-4]=requested_dwell_us
  else:
   started=self.coil_on[ch-4]
   if started is None:raise RuntimeError('Coil fall without a preceding charge event')
   dwell=max(0,time_s-started);self.coil_on[ch-4]=None
   # Illustrative independent RL/current-limited coil proxy, not a real coil calibration.
   current=min(6.,max(0,self.battery-1.5)/.7*(1-math.exp(-.7*dwell/.003)))
   energy=.5*.003*current*current
   self.dwell_events.append(dict(time_s=time_s,channel=ch,dwell_us=dwell*1e6,requested_us=self.coil_requests[ch-4],energy_j=energy))
   self.sparks+=1
   tdc_mod=(90,270,270,90)[ch-4];actual=(tdc_mod-self.angle%360+180)%360-180
   error=(actual-commanded_advance+180)%360-180
   phase_advance=((90,630,270,450)[ch-4]-self.angle%720+360)%720-360
   phase_error=(phase_advance-commanded_advance+360)%720-360
   self.spark_errors.append(dict(time_s=time_s,channel=ch,requested_deg=commanded_advance,actual_deg=actual,error_deg=error,phase_error_deg=phase_error,shaft_angle_deg=self.angle,latest_demand_deg=latest_demand,demand_error_deg=(actual-latest_demand+180)%360-180,rpm=self.rpm))
   cyl=ch-4;tdc=(90,630,270,450)[cyl];advance=(tdc-self.angle%720+360)%720-360
   if abs(advance)>90:return # wasted spark on exhaust stroke
   self.advance=advance;self.spk_errors.append(advance)
   fuel=self.charge_mg[cyl];self.charge_mg[cyl]=0.
   ve=.76+.10*math.exp(-((self.rpm-3500)/2500)**2)+.02*(self.map_kpa/100)
   air=self.map_kpa*1000*.0005*ve/(287.05*(self.iat+273.15))*1e6
   lam=air/(14.7*fuel) if fuel>.001 else 3.
   self.exhaust_lambda=max(.2,min(3.,lam))
   if not .55<lam<1.65:return
   optimum=12+min(20,self.rpm/250)-5*(self.map_kpa/100)
   efficiency=.27*math.exp(-((advance-optimum)/30)**2)*max(0,1-1.3*(lam-.95)**2)*(.75 if self.clt<30 else 1)
   work=fuel*44*efficiency*min(1,energy/.04);duration=max(.005,30/max(self.rpm,80))
   self.combustions.append((time_s,time_s+duration,work/duration));self.burned_work_j+=work
 def cut(self):self.injector_on=[None]*4;self.coil_on=[None]*4
 def sample(self,t):return dict(map_kpa=self.map_kpa,tps_pct=self.tps,clt_c=self.clt,iat_c=self.iat,**{'lambda':min(1.5,max(.65,self.lambda_sensor))},battery_v=self.battery,sensor_v=5,sensors_valid=True,lambda_ready=t>3)
 def integrate(self,t,dt,starter=False,load=5,idle_pct=0):
  # Compressible quasi-steady throttle orifice and ideal-gas manifold filling.
  r=287.05;temp=self.iat+273.15;ambient=100000.;ratio=min(.999999,max(.01,self.map_kpa*1000/ambient));gamma=1.4
  area=17e-6+6e-4*self.tps/100+2e-5*idle_pct/100
  if ratio<(2/(gamma+1))**(gamma/(gamma-1)):flow=.72*area*ambient*math.sqrt(gamma/(r*temp))*(2/(gamma+1))**((gamma+1)/(2*(gamma-1)))
  else:flow=.72*area*ambient*math.sqrt(2*gamma/(r*temp*(gamma-1))*(ratio**(2/gamma)-ratio**((gamma+1)/gamma)))
  actual_ve=.76+.10*math.exp(-((self.rpm-3500)/2500)**2)+.02*(self.map_kpa/100)
  out=self.map_kpa*1000/(r*temp)*.002*self.rpm/120*actual_ve
  self.map_kpa=max(10,min(100,self.map_kpa+r*temp/.003*(flow-out)*dt/1000))
  # Fuel comes only from the scheduled electrical high intervals, after the
  # plant's own battery dead time, not directly from ECU pulse-width numbers.
  dead_ms=.96*(14/max(self.battery,7))**1.5
  if dt<=0:return self.exhaust_lambda
  flow_mg_s=self.injector_flow_cc_min*.745/60*1000
  for cyl,start in enumerate(self.injector_on):
   if start is not None:
    effective=max(0,t+dt-max(t,start+dead_ms/1000));fuel=flow_mg_s*effective
    film_fraction=.45 if self.clt<30 else .05
    self.wall_mg[cyl]+=fuel*film_fraction;self.charge_mg[cyl]+=fuel*(1-film_fraction);self.fuel_mg+=fuel
  tau=1.5 if self.clt<30 else .05
  for cyl in range(4):
   evaporated=self.wall_mg[cyl]*(1-math.exp(-dt/tau));self.wall_mg[cyl]-=evaporated;self.charge_mg[cyl]+=evaporated
  self.lambda_sensor+=(self.exhaust_lambda-self.lambda_sensor)*min(1,dt/.12)
  self.combustions=[c for c in self.combustions if c[1]>t]
  power=sum(c[2]*max(0,min(t+dt,c[1])-max(t,c[0]))/dt for c in self.combustions)
  omega=self.rpm*math.pi/30
  torque=power/max(omega,20)
  starter_torque=55*max(0,1-self.rpm/350) if starter else 0
  friction=12+.006*self.rpm
  acc=(torque+starter_torque-friction-load)/self.rotor_inertia
  next_omega=max(0,omega+acc*dt)
  self.angle+=(omega+next_omega)*.5*dt*180/math.pi
  self.rpm=next_omega*30/math.pi
  return self.exhaust_lambda

class Simulation:
 def __init__(self,tune,scenario='warm_start',duration_s=10,seed=1):
  if scenario not in SCENARIOS:raise ValueError('Unknown engine scenario')
  if isinstance(duration_s,bool) or not isinstance(duration_s,(int,float)) or not 1<=duration_s<=30:raise ValueError('Duration must be 1-30 virtual seconds')
  if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<=4294967295:raise ValueError('Seed must be a uint32 integer')
  self.tune=copy.deepcopy(tune);self.scenario=scenario;self.duration=duration_s;self.seed=seed
 def run(self):
  runtime=EngineRuntime(self.tune);runtime.wheel();plant=Plant(self.scenario=='cold_start',self.seed)
  states=[False]*8;trace=[];edge_trace=[];trigger_trace=[];cam_trace=[];timing_stops=[];failure_recorded=False;fault_or=0;sync_seen=False;late=0;max_high=[0]*8;rise=[0]*8
  def cut_outputs(time_us,cause):
   nonlocal states
   for ch,high in enumerate(states):
    if high:
     max_high[ch]=max(max_high[ch],max(0,time_us-rise[ch]))
     edge_trace.append([time_us,ch,False,'cut:'+cause])
   runtime.cut();plant.cut();states=[False]*8
  sequential=self.tune['strategy']=='sequential_4cyl';cam_angle=540.
  dt=.00025;t=0.;next_sample=0.;tooth_index=1;proposals=0;sample={};result={};latest_lambda=1.
  try:
   while t<self.duration-1e-10:
    # Deliberately independent plant stimulus; no forced desired RPM.
    if self.scenario in ('throttle_step','overrev') and t>=3:plant.tps=12 if self.scenario=='throttle_step' else 65
    else:plant.tps=0
    load=35 if (self.scenario=='load_step' and t>=4) or (self.scenario=='load_stall_restart' and 4<=t<6) else 5
    starter=t<2.5 or (self.scenario in ('stall_restart','load_stall_restart') and 8<t<10)
    dropout=(self.scenario=='trigger_dropout' and 4<t<4.7) or (self.scenario=='stall_restart' and 4<t<8)
    if t+1e-9>=next_sample:
     sample=plant.sample(t)
     if self.scenario=='sensor_short' and 4<t<5:sample['map_kpa']=0
     result=runtime.step(sample,round(t*1e6),use_decoder=True);failure_recorded=failure_recorded and bool(result['faults']&128);fault_or|=result['faults'];sync_seen|=result['synced'];next_sample+=.001
     if result['faults'] or result['state']=='stopped':
      cut_outputs(round(t*1e6),'control_inhibit')
     if int(round(t*1000))%20==0:
      trace.append(dict(time=round(t,4),plant_rpm=plant.rpm,map_kpa=plant.map_kpa,tps=plant.tps,lambda_measured=plant.lambda_sensor,actual_lambda=latest_lambda,fuel_mg=plant.fuel_mg,engine_sample=runtime.data(),**result))
    # Trigger crossings are timestamped inside the integration step. Integrate
    # to queued output edges first, then provide every actual 60-2 tooth.
    until_tooth=(tooth_index*6-plant.angle)/(plant.rpm*6) if plant.rpm>1e-6 else dt
    until_cam=(cam_angle-plant.angle)/(plant.rpm*6) if sequential and plant.rpm>1e-6 else dt
    end=min(self.duration,t+max(1e-7,min(dt,until_tooth,until_cam)),next_sample)
    # Trigger and timer timestamps share integer microseconds. Drain all
    # deadlines at the rounded crossing before delivering a tooth at that
    # same timestamp; fractional integration endpoints can differ by <0.5us.
    while runtime.next_event_us()<=round(end*1e6):
     us=runtime.next_event_us();ch,high,commanded_advance,requested_dwell_us=runtime.pop_event();
     if ch is None:cut_outputs(us,'control_deadline');continue
     event_t=max(t,min(end,us/1e6))
     latest_lambda=plant.integrate(t,event_t-t,starter,load,result.get('idle_pct',0));t=event_t
     if high==states[ch]:raise RuntimeError(f'Duplicate virtual channel edge at {us} us: channel={ch} high={high} state={states[ch]} time={t} status={result}')
     if high:rise[ch]=us
     elif states[ch]:max_high[ch]=max(max_high[ch],us-rise[ch])
     states[ch]=high;plant.edge(ch,high,t,commanded_advance,result.get('advance_deg',0),requested_dwell_us)
     edge_trace.append([us,ch,high,'scheduled'])
    before=plant.angle;old_t=t;latest_lambda=plant.integrate(t,end-t,starter,load,result.get('idle_pct',0));t=end
    while tooth_index*6<=plant.angle:
     target=tooth_index*6;tooth=tooth_index%60;tooth_index+=1
     if tooth>=58 or dropout:continue
     frac=(target-before)/(plant.angle-before) if plant.angle>before else 1
     edge_us=round((old_t+max(0,min(1,frac))*(t-old_t))*1e6)
     trigger_result=runtime.trigger(edge_us);trigger_trace.append([edge_us,tooth,trigger_result])
     if trigger_result in (2,3):
      cut_outputs(round(t*1e6),'trigger_inhibit')
      if trigger_result==3:
       late+=1
       if not failure_recorded:timing_stops.append(dict(time_us=edge_us,reason=runtime.timing_reason(),plant_rpm=plant.rpm));failure_recorded=True
     if trigger_result==1:proposals+=1
    while sequential and cam_angle<=plant.angle:
     cam_angle+=720
     cam_us=round(t*1e6);cam_result=runtime.cam(cam_us);cam_trace.append([cam_us,cam_result])
     if cam_result in (2,3):cut_outputs(cam_us,'cam_inhibit')
   before_stop=sum(states);cut_outputs(round(t*1e6),'simulation_end')
   errors=sorted(abs(e['error_deg']) for e in plant.spark_errors);warm_errors=[abs(e['error_deg']) for e in plant.spark_errors if e['time_s']>=3]
   summary=dict(strategy=self.tune['strategy'],wrong_stroke_sparks=sum(abs(e['phase_error_deg'])>180 for e in plant.spark_errors) if sequential else None,max_spark_720_error_deg=max((abs(e['phase_error_deg']) for e in plant.spark_errors),default=0) if sequential else None,scenario=self.scenario,duration_s=self.duration,seed=self.seed,model='unvalidated reduced-order SI plant v1',ecu='native production engine.hpp + MissingTooth decoder',physical_outputs_enabled=False,plant_parameters=dict(injector_flow_cc_min=plant.injector_flow_cc_min,rotor_inertia_kg_m2=plant.rotor_inertia),sync_acquired=sync_seen,max_rpm=max((p['plant_rpm'] for p in trace),default=0),final_rpm=plant.rpm,fuel_mg=plant.fuel_mg,sparks=plant.sparks,planned_revolutions=proposals,rejected_plans=late,max_injector_high_us=max(max_high[:4]),max_dwell_high_us=max(max_high[4:]),min_completed_dwell_us=min((d['dwell_us'] for d in plant.dwell_events),default=0),max_dwell_shortfall_us=max((d['requested_us']-d['dwell_us'] for d in plant.dwell_events),default=0),max_spark_error_deg=max(errors,default=0),max_spark_error_to_latest_demand_deg=max((abs(e['demand_error_deg']) for e in plant.spark_errors),default=0),p95_spark_error_deg=errors[int(.95*(len(errors)-1))] if errors else 0,max_spark_error_after_3s_deg=max(warm_errors,default=0),fault_mask_seen=fault_or,final_state=result.get('state'),final_faults=result.get('faults'),outputs_high_before_stop=before_stop,executor_stopped=True,final_outputs_high=sum(states),timing_recoveries=result.get('timing_recoveries',0),timing_protection_stops=result.get('timing_stops',0))
   return dict(summary=summary,trace=trace,edges=edge_trace,trigger_edges=trigger_trace,cam_edges=cam_trace,timing_stops=timing_stops,spark_timing=plant.spark_errors,dwell_events=plant.dwell_events,final=result)
  finally:runtime.close()
