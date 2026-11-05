"""Declared conservative extensions around the attested TCSI component graphs.

The raw source remains available as a reference. This component adapter is not
yet a complete engine plant or calibrated turbo. Original coefficient mismatch,
zero-speed singularities and model-domain extensions are exposed explicitly.
"""
import math
from tcsi_graph import Model

def positive(*values):
 if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):raise ValueError('Positive finite gas inputs required')

class TurboComponents:
 def __init__(self,profile='conservative',model=None):
  if profile not in ('source','conservative'):raise ValueError('Unknown turbo component profile')
  self.profile=profile;self.model=model or Model(parameter_inputs={'toggle_vol':0})
  def graph(name):
   paths=[p for p in self.model.systems if p[-1]==name]
   if len(paths)!=1:raise ValueError('Ambiguous source component '+name)
   return self.model.graph(paths[0])
  self.compressor_graph=graph('Compressor');self.turbine_graph=graph('Turbine1');self.wastegate_graph=graph('Wastegate')
  self.air_restriction=graph('Throttle  Compressible\nRestriction')
  self.engine_graph=graph('Engine flow')
  parameters=self.model.parameters
  self.gases={}
  for medium in ('air','exh'):
   r=parameters['TC_ENGINE.gasProp.'+medium+'.R'];gamma=parameters['TC_ENGINE.gasProp.'+medium+'.kappa'];cv=r/(gamma-1)
   self.gases[medium]=dict(r=r,gamma=gamma,cv=cv,cp=cv+r,declared_rounded_cp=parameters['TC_ENGINE.gasProp.'+medium+'.cp'])
  comp_cp=graph('Compressor\nTorque').env['c_p'];turb_cp=graph('Turbine\nTorque').env['c_p']
  self.parameters=dict(inertia_kg_m2=parameters['TC_ENGINE.turbo.inertia_tc'],bearing_nm_s=parameters['TC_ENGINE.turbo.damp_tc'],
   source_minimum_rad_s=parameters['TC_ENGINE.turbo.omega_min'],source_maximum_rad_s=parameters['TC_ENGINE.turbo.omega_max'],
   finite_stall_reference_rad_s=parameters['TC_ENGINE.turbo.omega_min'],source_initial_rad_s=parameters['TC_ENGINE.turbo.omega_init'],
   source_compressor_torque_cp=comp_cp,source_turbine_torque_cp=turb_cp,
   turbine_dp_linear_pa=300.,
   # Explicit stationary/windmilling extension: forward restriction only
   # when compressor downstream is below inlet pressure. No bypass boost.
   passive_compressor_area_m2=1e-4)
  if comp_cp!=1100 or turb_cp!=1200:raise ValueError('Source coefficient interpretation changed')
  self.provenance=dict(profile=profile,source=self.model.provenance,gases=self.gases,parameters=self.parameters,
   differences=[] if profile=='source' else ['Shaft powers use Cp=gamma*R/(gamma-1), replacing1100/1200 torque coefficients',
    'Below2000rad/s turbine torque is bounded by source gas-power potential/2000; actual gas power and temperature drop use omega*torque',
    'Below300Pa turbine pressure drop, flow is linearized against the unchanged300Pa source-map boundary',
    'Compressor at zero speed has zero map flow/work; under-pressure forward flow uses an explicit passive restriction extension',
    'No source turbo speed floor, initial speed, prescribed exhaust heat or complete engine dynamics is imposed by this component adapter'])
 def speed(self,omega):
  if type(omega) not in (int,float) or not math.isfinite(omega) or not 0<=omega<=self.parameters['source_maximum_rad_s']:raise ValueError('Turbo speed outside declared0..24000rad/s')
  if self.profile=='source' and omega<self.parameters['source_minimum_rad_s']:raise ValueError('Raw source outside its2000rad/s lower domain')
 def compressor(self,p_in,t_in,omega,p_out):
  positive(p_in,t_in,p_out);self.speed(omega)
  if omega:
   raw=self.compressor_graph.run((p_in,t_in,omega,t_in,p_out));map_flow,temp,raw_torque=raw[1],raw[2],raw[3]
  else:map_flow,temp,raw_torque=0.,t_in,None
  flow=map_flow;passive=0.
  if self.profile=='conservative' and p_in>p_out:
   passive=self.air_restriction.run((p_in,t_in,self.parameters['passive_compressor_area_m2'],t_in,p_out))[1]
   flow=max(flow,passive)
  cp=self.gases['air']['cp'];gas_power=flow*cp*(temp-t_in)
  shaft_power=raw_torque*omega if self.profile=='source' else gas_power
  torque=shaft_power/omega if omega else 0.
  return dict(mass_kg_s=flow,temperature_k=temp,torque_nm=torque,shaft_w=shaft_power,gas_w=gas_power,
   power_residual_w=shaft_power-gas_power,source_map_mass_kg_s=map_flow,source_torque_nm=raw_torque,
   passive_candidate_kg_s=passive,low_speed_extension=omega<self.parameters['source_minimum_rad_s'])
 def turbine(self,p_up,t_up,omega,p_down):
  positive(p_up,t_up,p_down);self.speed(omega)
  # Temperature/flow are well defined at zero speed; the unmodified torque
  # block is singular. Preserve that distinction rather than clamping speed.
  raw=self.turbine_graph.run((omega,p_down,p_up,t_up),output_ports={2,3})
  flow,temp=raw[3],raw[2];cp=self.gases['exh']['cp'];linear=False
  delta=p_up-p_down;limit=self.parameters['turbine_dp_linear_pa']
  if self.profile=='conservative' and 0<delta<limit:
   anchor=self.turbine_graph.run((omega,p_down,p_down+limit,t_up),output_ports={3})[3]
   flow=anchor*delta/limit;linear=True
  potential=flow*cp*(t_up-temp)
  if self.profile=='source':
   torque=self.turbine_graph.run((omega,p_down,p_up,t_up),output_ports={1})[1];power=torque*omega
  else:
   torque=potential/max(omega,self.parameters['finite_stall_reference_rad_s']);power=torque*omega
   temp=t_up-power/(flow*cp) if flow else t_up
  gas_power=flow*cp*(t_up-temp)
  return dict(mass_kg_s=flow,temperature_k=temp,torque_nm=torque,shaft_w=power,gas_w=gas_power,
   power_residual_w=power-gas_power,source_gas_power_potential_w=potential,low_speed_extension=omega<self.parameters['source_minimum_rad_s'],linear_pressure_extension=linear)
 def wastegate(self,p_up,t_up,opening,p_down,t_down):
  positive(p_up,t_up,p_down,t_down)
  if type(opening) not in (int,float) or not math.isfinite(opening) or not 0<=opening<=1:raise ValueError('Wastegate opening must be0..1')
  p=self.model.parameters;area=opening*p['TC_ENGINE.wastegate.Amax']*p['TC_ENGINE.wastegate.Cd']
  raw=self.wastegate_graph.run((p_up,t_up,area,t_down,p_down))
  return dict(mass_kg_s=raw[1],temperature_k=raw[2],effective_area_m2=area)
 def engine_flow(self,p_im,t_im,omega_engine,p_em,time_s):
  positive(p_im,t_im,p_em)
  if not math.isfinite(omega_engine) or omega_engine<0:raise ValueError('Nonnegative engine speed required')
  return self.engine_graph.run((p_im,t_im,omega_engine,p_em),time_s=time_s)[1]
