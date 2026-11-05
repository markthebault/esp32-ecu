"""Illustrative three-way bleed solenoid and pressure-operated wastegate.

Only executed binary drive edges energize the independent RL/mechanical model.
No controller duty/target is accepted. Parameters describe an uncalibrated
research hypothesis, not a purchased valve, hose or engine installation.
"""
import math
from idle_valve_plant import IdleValve

class BleedCoil(IdleValve):
 PARAMETERS=dict(resistance_ohm=36.,inductance_h=.03,diode_v=.7,mechanical_tau_s=.025,
                 opening_current_a=.08,full_open_current_a=.32)

class BoostValve:
 MODES=('normal','disconnected','inverted_drive','stuck_gate_closed','stuck_gate_open','hose_leak','stuck_solenoid_bleed','stuck_solenoid_pressure')
 PARAMETERS=dict(fill_tau_s=.04,vent_tau_s=.025,gate_tau_s=.04,spring_crack_kpa=30.,spring_travel_kpa=35.,hose_leak_per_s=100.)
 def __init__(self,mode='normal',ambient_kpa=100.):
  if mode not in self.MODES:raise ValueError('Unknown boost actuator failure mode')
  if type(ambient_kpa) not in (int,float) or not math.isfinite(ambient_kpa) or not 50<=ambient_kpa<=110:raise ValueError('Ambient pressure outside50..110kPa')
  self.mode=mode;self.ambient_kpa=ambient_kpa;self.actuator_kpa=ambient_kpa;self.gate=0.;self.time=0.
  self.coil=BleedCoil(mode if mode in ('disconnected','inverted_drive') else 'normal')
 def edge(self,high):self.coil.edge(high)
 def cut(self):self.coil.cut()
 def step(self,dt,battery,charge_kpa):
  if type(charge_kpa) not in (int,float) or not math.isfinite(charge_kpa) or not 10<=charge_kpa<=500:raise ValueError('Charge pressure outside10..500kPa')
  bleed=self.coil.step(dt,battery)/100
  if self.mode=='stuck_solenoid_bleed':bleed=1.
  elif self.mode=='stuck_solenoid_pressure':bleed=0.
  p=self.PARAMETERS;fill=(1-bleed)/p['fill_tau_s'];vent=bleed/p['vent_tau_s']+(p['hose_leak_per_s'] if self.mode=='hose_leak' else 0.)
  target=(fill*charge_kpa+vent*self.ambient_kpa)/(fill+vent)
  self.actuator_kpa+=(target-self.actuator_kpa)*(-math.expm1(-dt*(fill+vent)))
  equilibrium=min(1.,max(0.,(self.actuator_kpa-self.ambient_kpa-p['spring_crack_kpa'])/p['spring_travel_kpa']))
  self.gate+=(equilibrium-self.gate)*(-math.expm1(-dt/p['gate_tau_s']));self.time+=dt
  return self.opening
 @property
 def opening(self):return 0. if self.mode=='stuck_gate_closed' else 1. if self.mode=='stuck_gate_open' else self.gate
 def snapshot(self):
  return dict(mode=self.mode,time_s=self.time,actuator_kpa=self.actuator_kpa,ambient_kpa=self.ambient_kpa,
   wastegate_opening=self.opening,coil=self.coil.snapshot(),parameters=self.PARAMETERS,
   qualification='Uncalibrated pulse-driven solenoid/hose/spring hypothesis; no physical actuator verification')
