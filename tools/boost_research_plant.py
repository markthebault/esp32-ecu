"""Pulse-driven combustion/free crank coupled to conservative turbo gas states.

This composition is a research model. It supplies no physical tune or engine
qualification. Heat/fuel transport and the one-step pumping-work exchange are
explicit pending inventories; complete controller comparisons are separate.
"""
import copy,math
from engine_research_plant import ResearchPlant
from turbo_gas_path import TurboGasPath
from boost_valve_plant import BoostValve

class BoostResearchPlant(ResearchPlant):
 EXHAUST_HEAT_FRACTION=.55
 FUEL_TRANSPORT_TAU_S=.02
 def __init__(self,actuator_mode='normal',ambient_kpa=100.,initial_turbo_rad_s=0.,**kwargs):
  air=TurboGasPath(ambient_kpa=ambient_kpa,initial_turbo_rad_s=initial_turbo_rad_s)
  super().__init__(ambient_kpa=ambient_kpa,air_path=air,**kwargs)
  self.boost_valve=BoostValve(actuator_mode,ambient_kpa);self.heat_pulses=[];self.heat_seen=0.;self.wall_heat_j=0.
  self.fuel_seen_mg=0.;self.pending_fuel_kg=0.;self.pending_pumping_j=0.;self.pumping_work_j=0.
  self.heat_delivered_j=0.;self.maximum_exchange_delay_s=0.;self.iat=self.air_state['temperature_k']-273.15
  self.cut_discharges=[]
 def schedule_heat(self,t,duration):
  delta=self.heat_j-self.heat_seen
  if delta<-1e-8:raise RuntimeError('Engine heat ledger regressed')
  if delta>0:
   exhaust=delta*self.EXHAUST_HEAT_FRACTION;self.wall_heat_j+=delta-exhaust
   self.heat_pulses.append(dict(start=t,end=t+duration,rate=exhaust/duration,remaining=exhaust))
  self.heat_seen=self.heat_j
 def edge(self,ch,high,t,commanded_advance=10,latest_demand=10,requested_dwell_us=2800):
  if ch==9:self.boost_valve.edge(high);return
  before=len(self.combustions)
  super().edge(ch,high,t,commanded_advance,latest_demand,requested_dwell_us)
  if len(self.combustions)>before:
   pulse=self.combustions[-1];self.schedule_heat(t,pulse['end']-pulse['start'])
 def cut(self):
  # A global GPIO-low command has the same electrical meaning as individual
  # falling edges. In particular, an already charged smart-coil command can
  # discharge even though the controller has just requested an ignition cut.
  # This models command removal, not a separate ideal coil-power quench.
  for ch in range(8):
   active=self.injector_on if ch<4 else self.coil_on
   if active[ch%4] is not None:
    chemical=self.burned_chemical_j
    self.edge(ch,False,self.air.time)
    if ch>=4:self.cut_discharges.append(dict(self.dwell_events[-1],channel=ch,chemical_delta_j=self.burned_chemical_j-chemical))
  super().cut();self.boost_valve.cut()
 def integrate(self,t,dt,starter=False,load=5,idle_pct=0):
  if type(dt) not in (int,float) or not math.isfinite(dt) or not 0<=dt<=.001 or not math.isfinite(t) or abs(t-self.air.time)>1e-8 or type(starter) is not bool or not math.isfinite(load) or not math.isfinite(idle_pct) or not 0<=idle_pct<=100:raise ValueError('Invalid complete-plant integration request')
  if not dt:return
  # Candidate ownership is deliberately narrow: graph definitions and
  # append-only spark diagnostic history are read-only during integration.
  # All changed physical states/exchange inventories have private copies.
  candidate=copy.copy(self);candidate.air=copy.copy(self.air);candidate.air.state=list(self.air.state)
  candidate.boost_valve=copy.copy(self.boost_valve);candidate.boost_valve.coil=copy.copy(self.boost_valve.coil)
  if self.idle_valve is not None:candidate.idle_valve=copy.copy(self.idle_valve)
  for name in ('injector_on','coil_on','charge_mg','port_mg','wall_mg','air_charge_mg','cylinder_fuel_mg','cylinder_burned_mg','cylinder_scheduled_work_j','cylinder_shaft_j'):
   setattr(candidate,name,list(getattr(self,name)))
  candidate.combustions=[dict(p) for p in self.combustions];candidate.heat_pulses=[dict(p) for p in self.heat_pulses]
  candidate._integrate_candidate(t,dt,starter,load,idle_pct)
  self.__dict__=candidate.__dict__
 def _integrate_candidate(self,t,dt,starter,load,idle_pct):
  state=self.air.read();gate=self.boost_valve.step(dt,self.battery,state['charge_kpa'])
  delivered=0.
  for pulse in self.heat_pulses:
   amount=(pulse['remaining'] if t+dt>=pulse['end'] else min(pulse['remaining'],pulse['rate']*max(0,min(t+dt,pulse['end'])-max(t,pulse['start']))))
   pulse['remaining']-=amount;delivered+=amount
  self.heat_pulses=[p for p in self.heat_pulses if p['remaining']>1e-12]
  retired=self.burned_mg+self.unburned_mg
  if retired<self.fuel_seen_mg-1e-9:raise RuntimeError('Retired fuel ledger regressed')
  self.pending_fuel_kg+=(retired-self.fuel_seen_mg)/1e6;self.fuel_seen_mg=retired
  fuel=self.pending_fuel_kg*(-math.expm1(-dt/self.FUEL_TRANSPORT_TAU_S));self.pending_fuel_kg-=fuel
  self.air.sources(gate,delivered/dt,fuel/dt,self.pending_pumping_j/dt);self.pending_pumping_j=0.;self.heat_delivered_j+=delivered
  displacement=self.air.components.model.parameters['TC_ENGINE.geometry.V_d']
  pumping_torque=(state['exhaust_kpa']-state['map_kpa'])*1000*displacement/(4*math.pi)
  angle=self.angle
  super().integrate(t,dt,starter,load+pumping_torque,idle_pct)
  pumping=pumping_torque*(self.angle-angle)*math.pi/180
  self.pumping_work_j+=pumping;self.pending_pumping_j=pumping
  # The existing crank closure can dissipate additional scheduled work at
  # low speed. Release that newly known heat from the next boundary, with
  # its short coupling delay retained in the pending energy inventory.
  self.schedule_heat(t+dt,dt);self.maximum_exchange_delay_s=max(self.maximum_exchange_delay_s,dt)
  self.iat=self.air_state['temperature_k']-273.15
 def ledger(self):
  result=super().ledger();gas=self.air.ledger();pending_heat=sum(p['remaining'] for p in self.heat_pulses)
  retired=(self.burned_mg+self.unburned_mg)/1e6;not_queued=(self.burned_mg+self.unburned_mg-self.fuel_seen_mg)/1e6
  pending_fuel=self.pending_fuel_kg+not_queued;external_load=self.load_j-self.pumping_work_j
  result.update(turbo_gas=gas,boost_valve=self.boost_valve.snapshot(),
   pending_exhaust_heat_j=pending_heat,wall_heat_j=self.wall_heat_j,exhaust_heat_delivered_j=self.heat_delivered_j,
   pending_exhaust_fuel_kg=pending_fuel,pumping_work_j=self.pumping_work_j,pending_pumping_exchange_j=self.pending_pumping_j,
   external_load_j=external_load,maximum_pumping_exchange_delay_s=self.maximum_exchange_delay_s,
   heat_partition_residual_j=self.heat_j-self.wall_heat_j-self.heat_delivered_j-pending_heat,
   exhaust_fuel_transport_residual_kg=retired-pending_fuel-gas['fuel_mass'],
   coupled_mass_residual_kg=gas['inventory_mass_kg']-gas['initial_mass_kg']+result['stored_mg']/1e6+pending_fuel-self.fuel_mg/1e6-gas['boundary_mass'],
   coupled_energy_residual_j=self.starter_j+self.burned_chemical_j+gas['boundary_h']-self.friction_j-external_load-self.wall_heat_j-gas['cooler_heat']-gas['bearing']-result['kinetic_j']-(gas['inventory_energy_j']-gas['initial_energy_j'])-result['pending_work_j']-pending_heat-self.pending_pumping_j,
   global_cut_discharges=len(self.cut_discharges),
   plant_qualification='Uncalibrated pulse-driven turbo research composition; physical valve/engine behavior unverified')
  return result
