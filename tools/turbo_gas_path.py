"""Conservative, source-backed six-volume turbo air/exhaust coupling.

TCSI scalar graphs supply maps, restrictions, engine pumping and nonisothermal
volume derivatives. Composition, zero-speed behavior and external pulse-derived
heat are explicit local extensions. This is an uncalibrated research plant.
"""
import math
from tcsi_graph import Graph
from turbo_components import TurboComponents

class TurboGasPath:
 INTEGRATION='RK4 on mass/internal-energy increments; exact integrating factor for linear rotor bearing drag; no speed floor'
 VOLUMES=(('filter','Air fil ter\nControl\nVolume','air'),('charge','Compressor\nControl\nVolume','air'),
  ('cooler','Intercooler\nControl Volume','air'),('intake','Intake Manifold\nControl Volume','air'),
  ('exhaust','Exhaust\nManifold\nControl Volume','exh'),('tail','Turbine\nControl\nVolume','exh'))
 COUNTERS=('boundary_mass','fuel_mass','boundary_h','heat','pumping','cooler_heat','bearing',
  'compressor_work','turbine_work','source_power_defect','intake_in_mass','intake_out_mass','intake_in_h','intake_out_h')
 def __init__(self,ambient_kpa=100.,ambient_k=298.15,initial_turbo_rad_s=0.,profile='conservative'):
  if not 50<=ambient_kpa<=110 or not 250<=ambient_k<=330:raise ValueError('Ambient outside research domain')
  self.components=TurboComponents(profile);self.components.speed(initial_turbo_rad_s);self.ambient_pa=ambient_kpa*1000;self.ambient_k=ambient_k
  self.graphs={};self.index={};self.medium={};self.state=[];self.time=0.
  model=self.components.model
  for n,(name,suffix,medium) in enumerate(self.VOLUMES):
   graph=model.graph(next(p for p in model.systems if p[-1]==suffix));self.graphs[name]=graph;self.index[name]=n;self.medium[name]=medium
   if graph.integrators!={'Receiver\nMass','Receiver\nTemperature'}:raise ValueError('Source volume states changed')
   r=graph.env['R'];volume=graph.env['V'];self.state.extend((self.ambient_pa*volume/r/ambient_k,ambient_k))
  self.state.append(initial_turbo_rad_s);self.state.extend([0.]*len(self.COUNTERS));self.offset={k:13+n for n,k in enumerate(self.COUNTERS)}
  template=model.graph(next(p for p in model.systems if p[-1]=='Intercooler Flow'))
  self.restrictions={}
  for name,prefix in (('filter','airFilter'),('cooler','interCooler'),('tail','exhaustSystem')):
   env=dict(template.env,H=model.parameters['TC_ENGINE.'+prefix+'.H'],p_lin=model.parameters['TC_ENGINE.'+prefix+'.p_lin'])
   self.restrictions[name]=Graph(model,template.system,None,env,template.path+('composition_'+name,))
  self.gate_opening=0.;self.heat_w=0.;self.fuel_kg_s=0.;self.pumping_w=0.
  self.latest={};self.initial=self.read();self.initial_total_mass=self.total_mass(self.state);self.initial_energy=self.total_energy(self.state)
 def gas(self,name):return self.components.gases[self.medium[name]]
 def thermo(self,state,name):
  n=2*self.index[name];mass,temp=state[n:n+2];r=self.graphs[name].env['R'];volume=self.graphs[name].env['V']
  pressure=mass*r*temp/volume
  if not all(math.isfinite(v) for v in (mass,temp,pressure)) or mass<=0 or not 150<temp<2000 or not 3000<pressure<650000:raise ValueError('Gas state outside explicit research domain: '+name)
  return mass,temp,pressure
 def total_mass(self,state):return sum(state[2*n] for n in range(6))
 def total_energy(self,state):
  # One common sensible-enthalpy reference h(Tref)=0 permits the declared
  # air/exhaust property change across the engine without invented heat.
  # u=h-RT, hence u=Cv*T-Cp*Tref. Source volume derivatives are unchanged.
  gas=sum(state[2*n]*(self.gas(name)['cv']*state[2*n+1]-self.gas(name)['cp']*self.ambient_k) for n,(name,_,_) in enumerate(self.VOLUMES))
  return gas+.5*self.components.parameters['inertia_kg_m2']*state[12]**2
 def sources(self,gate_opening,heat_w=0.,fuel_kg_s=0.,pumping_w=0.):
  if any(type(v) not in (int,float) or not math.isfinite(v) for v in (gate_opening,heat_w,fuel_kg_s,pumping_w)) or not 0<=gate_opening<=1 or heat_w<0 or fuel_kg_s<0:raise ValueError('Invalid explicit turbo coupling sources')
  self.gate_opening=gate_opening;self.heat_w=heat_w;self.fuel_kg_s=fuel_kg_s;self.pumping_w=pumping_w
 def rates(self,time,state,omega_engine,tps,idle):
  thermo={name:self.thermo(state,name) for name,_,_ in self.VOLUMES};omega=state[12];self.components.speed(omega)
  temperature=lambda name:thermo[name][1]
  pressure=lambda name:thermo[name][2]
  cp_air=self.components.gases['air']['cp'];cp_ex=self.components.gases['exh']['cp'];ambient=self.ambient_k
  def restriction(name,p_up,t_up,t_down,p_down):return self.restrictions[name].run((p_up,t_up,t_down,p_down))
  af=restriction('filter',self.ambient_pa,ambient,temperature('filter'),pressure('filter'))
  compressor=self.components.compressor(pressure('filter'),temperature('filter'),omega,pressure('charge'));qc=compressor['mass_kg_s']
  ic=restriction('cooler',pressure('charge'),temperature('charge'),temperature('cooler'),pressure('cooler'));qi=ic[1]
  efficiency=self.components.model.parameters['TC_ENGINE.interCooler.epsilon']
  cooler_source=temperature('charge') if qi>=0 else temperature('cooler');cooler_out=ambient+(cooler_source-ambient)*(1-efficiency)
  cooling=abs(qi)*cp_air*(cooler_source-cooler_out)
  area=.72*(17e-6+6e-4*tps/100+2e-5*idle/100) # Retained independent benchmark throttle geometry.
  throttle=self.components.air_restriction.run((pressure('cooler'),temperature('cooler'),area,temperature('intake'),pressure('intake')))
  qt=throttle[1];engine=self.components.engine_flow(pressure('intake'),temperature('intake'),omega_engine,pressure('exhaust'),time)
  if engine<0:raise ValueError('Reverse cylinder pumping outside research domain')
  turbine=self.components.turbine(pressure('exhaust'),temperature('exhaust'),omega,pressure('tail'));q_turb=turbine['mass_kg_s']
  gate=self.components.wastegate(pressure('exhaust'),temperature('exhaust'),self.gate_opening,pressure('tail'),temperature('tail'));qg=gate['mass_kg_s'];outflow=q_turb+qg
  tail=restriction('tail',pressure('tail'),temperature('tail'),ambient,self.ambient_pa)
  fuel=self.fuel_kg_s;incoming=engine+fuel
  engine_temp=ambient+engine*cp_air*(temperature('intake')-ambient)/(incoming*cp_ex) if incoming else ambient
  gate_face=temperature('exhaust') if qg>=0 else temperature('tail')
  gate_correction=qg*cp_ex*(gate_face-temperature('exhaust'))
  flows={
   'filter':(af[1],ambient if af[1]>=0 else temperature('filter'),0.,temperature('filter'),qc),
   'charge':(qc,compressor['temperature_k'],0.,temperature('charge') if qi>=0 else cooler_out,qi),
   'cooler':(qi,cooler_out if qi>=0 else temperature('cooler'),0.,temperature('cooler') if qt>=0 else temperature('intake'),qt),
   'intake':(qt,temperature('cooler') if qt>=0 else temperature('intake'),0.,temperature('intake'),engine),
   'exhaust':(incoming,engine_temp,self.heat_w+self.pumping_w-gate_correction,temperature('exhaust'),outflow),
   'tail':(outflow,temperature('exhaust'),q_turb*cp_ex*(turbine['temperature_k']-temperature('exhaust'))+gate_correction,
           temperature('tail') if tail[1]>=0 else ambient,tail[1])}
  derivative=[]
  for name,_,_ in self.VOLUMES:
   mass,temp,_=thermo[name];_,d=self.graphs[name].run(flows[name],{'Receiver\nMass':mass,'Receiver\nTemperature':temp},True)
   derivative.extend((d['Receiver\nMass'],d['Receiver\nTemperature']))
  p=self.components.parameters;friction=p['bearing_nm_s']*omega
  derivative.append((turbine['torque_nm']-compressor['torque_nm']-friction)/p['inertia_kg_m2'])
  boundary_h=af[1]*cp_air*((ambient if af[1]>=0 else temperature('filter'))-ambient)-tail[1]*cp_ex*((temperature('tail') if tail[1]>=0 else ambient)-ambient)
  counter=dict(boundary_mass=af[1]-tail[1],fuel_mass=fuel,boundary_h=boundary_h,heat=self.heat_w,pumping=self.pumping_w,
   cooler_heat=cooling,bearing=friction*omega,compressor_work=compressor['shaft_w'],turbine_work=turbine['shaft_w'],
   source_power_defect=turbine['power_residual_w']-compressor['power_residual_w'],intake_in_mass=qt,intake_out_mass=engine,
   intake_in_h=qt*cp_air*(temperature('cooler') if qt>=0 else temperature('intake')),intake_out_h=engine*cp_air*temperature('intake'))
  derivative.extend(counter[k] for k in self.COUNTERS)
  observation=dict(thermo=thermo,compressor=compressor,turbine=turbine,wastegate=gate,engine_mass_kg_s=engine,throttle_mass_kg_s=qt,
   cooler_heat_w=cooling,bearing_w=counter['bearing'],boundary_h_w=boundary_h,source_power_defect_w=counter['source_power_defect'])
  return derivative,observation
 def read(self):
  mass,temp,map_pa=self.thermo(self.state,'intake');cp=self.gas('intake')['cp'];cv=self.gas('intake')['cv'];offset=self.offset
  return dict(map_kpa=map_pa/1000,temperature_k=temp,cylinder_air_kg_s=self.latest.get('engine_mass_kg_s',0.),
   inlet_air_kg_s=self.latest.get('throttle_mass_kg_s',0.),inventory_kg=mass,inventory_j=mass*cv*temp,
   accumulated_inlet_kg=self.state[offset['intake_in_mass']],accumulated_outlet_kg=self.state[offset['intake_out_mass']],
   accumulated_inlet_j=self.state[offset['intake_in_h']],accumulated_outlet_j=self.state[offset['intake_out_h']],
   charge_kpa=self.thermo(self.state,'charge')[2]/1000,exhaust_kpa=self.thermo(self.state,'exhaust')[2]/1000,
   turbo_rad_s=self.state[12],turbo_rpm=self.state[12]*30/math.pi,source=self.components.provenance,integration=self.INTEGRATION)
 def step(self,t,dt,omega,tps,idle=0.):
  if abs(t-self.time)>1e-8 or type(dt) not in (int,float) or not math.isfinite(dt) or not 0<=dt<=.001 or not math.isfinite(omega) or not 0<=omega<=1100 or not 0<=tps<=100 or not 0<=idle<=100:raise ValueError('Invalid turbo coupling time or inputs')
  if not dt:return self.read()
  state=self.state;working=list(state);properties=[]
  for n,(name,_,_) in enumerate(self.VOLUMES):
   gas=self.gas(name);mass,temp=state[2*n:2*n+2];cv=gas['cv'];specific=cv*temp-gas['cp']*self.ambient_k
   properties.append((mass,temp,cv,specific));working[2*n+1]=0.
  inertia=self.components.parameters['inertia_kg_m2'];decay=self.components.parameters['bearing_nm_s']/inertia
  def physical(vector,elapsed):
   result=list(vector)
   for n,(initial_mass,initial_temp,cv,specific) in enumerate(properties):
    mass=vector[2*n]
    if mass<=0:raise ValueError('Nonpositive candidate gas inventory')
    # delta(U)=u0*delta(m)+m*Cv*delta(T). Increments avoid a
    # subtract/divide roundoff perturbation of an exact resting state.
    result[2*n+1]=initial_temp+(vector[2*n+1]-specific*(mass-initial_mass))/(mass*cv)
   result[12]=vector[12]*math.exp(-decay*elapsed)
   return result
  def stage(elapsed,vector):
   actual=physical(vector,elapsed);derivative,observation=self.rates(t+elapsed,actual,omega,tps,idle)
   for n,(_,_,cv,_) in enumerate(properties):
    mass,temp=actual[2*n:2*n+2];gas=self.gas(self.VOLUMES[n][0])
    derivative[2*n+1]=(cv*temp-gas['cp']*self.ambient_k)*derivative[2*n]+mass*cv*derivative[2*n+1]
   # Integrate z=exp(a*t)*omega. Removing linear bearing drag here
   # avoids a negative intermediate RK stage when torque starts at zero,
   # becomes positive, then returns to zero within one step. Drive torque
   # is read directly to avoid subtract/add cancellation of tiny drag.
   derivative[12]=math.exp(decay*elapsed)*(observation['turbine']['torque_nm']-observation['compressor']['torque_nm'])/inertia
   return derivative
  k1=stage(0.,working)
  k2=stage(dt/2,[x+dt*v/2 for x,v in zip(working,k1)])
  k3=stage(dt/2,[x+dt*v/2 for x,v in zip(working,k2)])
  k4=stage(dt,[x+dt*v for x,v in zip(working,k3)])
  candidate=physical([x+dt*(a+2*b+2*c+d)/6 for x,a,b,c,d in zip(working,k1,k2,k3,k4)],dt)
  _,latest=self.rates(t+dt,candidate,omega,tps,idle) # Reject invalid candidate before publishing.
  self.state=candidate;self.latest=latest;self.time=t+dt;return self.read()
 def ledger(self):
  counter={k:self.state[v] for k,v in self.offset.items()};mass=self.total_mass(self.state);energy=self.total_energy(self.state)
  return dict(**counter,inventory_mass_kg=mass,initial_mass_kg=self.initial_total_mass,
   mass_residual_kg=mass-self.initial_total_mass-counter['boundary_mass']-counter['fuel_mass'],
   inventory_energy_j=energy,initial_energy_j=self.initial_energy,
   energy_residual_j=energy-self.initial_energy-counter['boundary_h']-counter['heat']-counter['pumping']+counter['cooler_heat']+counter['bearing'],
   rotor_kinetic_j=.5*self.components.parameters['inertia_kg_m2']*self.state[12]**2,
   integration=self.INTEGRATION,qualification='Declared source-backed gas/shaft research composition; no calibrated engine or physical qualification')
 def close(self):pass
