"""External MVEM air path with an explicitly empirical pulse-driven combustion model.

This is a research benchmark, not a calibrated engine or tuning oracle. Upstream
supplies manifold thermodynamics/pumping only. This file owns fuel transport,
spark sensitivity, starter/load/friction and free-shaft dynamics with ledgers.
"""
import hashlib
import json
import math
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class AirPath:
    def __init__(self,ambient_kpa=100):
        if type(ambient_kpa) not in (int,float) or not math.isfinite(ambient_kpa) or not 50<=ambient_kpa<=110:raise ValueError('Research ambient pressure outside50..110kPa absolute')
        from fmpy import extract, read_model_description
        from fmpy.fmi2 import FMU2Slave
        base=ROOT/'.cache/engine/modelica-mvem/airpath'
        fmu=base/'EngineAirPath.fmu'
        manifest=json.loads((base/'manifest.json').read_text())
        if hashlib.sha256(fmu.read_bytes()).hexdigest()!=manifest['fmu_sha256']:
            raise RuntimeError('Research FMU hash differs from build manifest')
        if hashlib.sha256((ROOT/'simulation/modelica/EngineAirPath.mo').read_bytes()).hexdigest()!=manifest['adapter_sha256']:
            raise RuntimeError('Rebuild research FMU after Modelica adapter changes')
        description=read_model_description(str(fmu))
        self.vr={v.name:v.valueReference for v in description.modelVariables}
        self.temp=tempfile.TemporaryDirectory(prefix='ecu-airpath-',dir=base)
        extract(str(fmu),unzipdir=self.temp.name)
        self.model=FMU2Slave(guid=description.guid,unzipDirectory=self.temp.name,
                            modelIdentifier=description.coSimulation.modelIdentifier,instanceName='ecu_airpath')
        try:
            self.model.instantiate()
            self.model.setupExperiment(startTime=0,tolerance=1e-8)
            if ambient_kpa!=100:self.model.setReal([self.vr['ambient_pa']],[ambient_kpa*1000])
            self.model.setReal([self.vr[k] for k in ('shaft_rad_s','throttle_pct','idle_pct')],[0,0,0])
            self.model.enterInitializationMode();self.model.exitInitializationMode()
            self.time=0.;self.initial=self.read()
        except Exception:
            self.model.freeInstance();self.temp.cleanup();raise

    def read(self):
        keys=('map_kpa','temperature_k','cylinder_air_kg_s','inlet_air_kg_s',
              'inventory_kg','inventory_j','accumulated_inlet_kg','accumulated_outlet_kg',
              'accumulated_inlet_j','accumulated_outlet_j')
        values=self.model.getReal([self.vr[k] for k in keys])
        if not all(math.isfinite(v) for v in values):raise RuntimeError('Non-finite MVEM air state')
        return dict(zip(keys,values))

    def step(self,t,dt,omega,tps,idle=0):
        if abs(t-self.time)>1e-8 or dt<0:raise RuntimeError('Air-path coupling clock mismatch')
        if dt==0:return self.read()
        self.model.setReal([self.vr[k] for k in ('shaft_rad_s','throttle_pct','idle_pct')],[omega,tps,idle])
        self.model.doStep(currentCommunicationPoint=t,communicationStepSize=dt)
        self.time=t+dt
        return self.read()

    def close(self):
        if self.model:
            try:self.model.terminate()
            finally:self.model.freeInstance();self.model=None;self.temp.cleanup()


class ResearchPlant:
    """2L gasoline four cylinder, 1-3-4-2 physical cylinder order.

    One positive shaft direction; no compression ripple, knock, emissions or
    exhaust gas dynamics. Spark timing response and cold behavior are empirical.
    """
    def __init__(self,cold=False,injector_flow_factors=None,optimum_spark_offsets=None,idle_valve=None,ambient_kpa=100):
        from idle_valve_plant import IdleValve
        self.idle_valve=IdleValve(idle_valve) if idle_valve is not None else None
        self.injector_flow_factors=list(injector_flow_factors or [1]*4)
        self.optimum_spark_offsets=list(optimum_spark_offsets or [0]*4)
        if len(self.injector_flow_factors)!=4 or any(not math.isfinite(v) or not .5<=v<=1.5 for v in self.injector_flow_factors):raise ValueError('Four bounded independent injector flow factors required')
        if len(self.optimum_spark_offsets)!=4 or any(not math.isfinite(v) or not -10<=v<=10 for v in self.optimum_spark_offsets):raise ValueError('Four bounded independent spark optimum offsets required')
        self.air=AirPath() if ambient_kpa==100 else AirPath(ambient_kpa);self.air_state=self.air.initial
        self.rpm=0.;self.angle=0.;self.tps=0.;self.clt=0. if cold else 85.
        self.iat=25.;self.battery=14.;self.map_kpa=100. if ambient_kpa==100 else self.air_state['map_kpa'];self.lambda_sensor=1.
        self.exhaust_lambda=1.;self.lambda_valid=False
        self.last_exhaust_t=-math.inf
        self.injector_flow_cc_min=300.;self.rotor_inertia=.18
        self.injector_on=[None]*4;self.coil_on=[None]*4
        self.charge_mg=[0.]*4;self.port_mg=[0.]*4;self.wall_mg=[0.]*4
        self.air_charge_mg=[0.]*4
        self.fuel_mg=0.;self.burned_mg=0.;self.unburned_mg=0.
        self.combustions=[];self.sparks=0;self.dwell_events=[];self.spark_errors=[]
        self.burned_chemical_j=0.;self.combustion_shaft_j=0.;self.heat_j=0.
        self.starter_j=0.;self.friction_j=0.;self.load_j=0.
        self.cylinder_fuel_mg=[0.]*4;self.cylinder_burned_mg=[0.]*4;self.cylinder_scheduled_work_j=[0.]*4;self.cylinder_shaft_j=[0.]*4;self.cylinder_combustions=[]

    def edge(self,ch,high,t,commanded_advance=10,latest_demand=10,requested_dwell_us=2800):
        if ch==8 and self.idle_valve is not None:self.idle_valve.edge(high);return
        if not 0<=ch<8:raise ValueError('Virtual channel outside0..7')
        events=self.injector_on if ch<4 else self.coil_on
        index=ch%4
        if high:
            if events[index] is not None:raise RuntimeError('Duplicate actuator rise')
            events[index]=t;return
        start=events[index]
        if start is None:raise RuntimeError('Actuator fall without rise')
        events[index]=None
        if ch<4:return
        dwell=t-start
        current=min(6.,max(0,self.battery-1.5)/.7*(1-math.exp(-.7*dwell/.003)))
        energy=.5*.003*current*current
        self.dwell_events.append(dict(time_s=t,channel=ch,dwell_us=dwell*1e6,energy_j=energy))
        self.sparks+=1
        tdc=(90,630,270,450)[index]
        advance=(tdc-self.angle%720+360)%720-360
        error=((tdc%360-self.angle%360+180)%360-180-commanded_advance+180)%360-180
        self.spark_errors.append(dict(time_s=t,channel=ch,actual_deg=(tdc%360-self.angle%360+180)%360-180,
                                      requested_deg=commanded_advance,error_deg=error,phase_error_deg=(advance-commanded_advance+360)%720-360,shaft_angle_deg=self.angle,rpm=self.rpm))
        if abs(advance)>90:return  # wasted spark on exhaust stroke
        fuel=self.charge_mg[index];self.charge_mg[index]=0.
        # Charge was frozen at intake closing using upstream pumping. Changing
        # manifold pressure after the valve closes cannot alter trapped air.
        air_mg=self.air_charge_mg[index];self.air_charge_mg[index]=0.
        lam=air_mg/(14.7*fuel) if fuel>1e-9 and air_mg>1e-9 else None
        record=dict(time_s=t,cylinder=index+1,air_mg=air_mg,fuel_mg=fuel,lambda_value=lam,advance_deg=advance,scheduled_work_j=0.)
        self.cylinder_combustions.append(record)
        self.lambda_valid=False
        if lam is not None:self.exhaust_lambda=min(3.,max(.2,lam))
        if lam is None or not .55<lam<1.65 or self.rpm<40 or energy<.002:
            self.unburned_mg+=fuel;return
        self.lambda_valid=True;self.last_exhaust_t=t
        burned=min(fuel,air_mg/14.7);self.burned_mg+=burned;self.unburned_mg+=fuel-burned
        optimum=12+min(20,self.rpm/250)-5*(self.map_kpa/100)+self.optimum_spark_offsets[index]
        efficiency=.27*math.exp(-((advance-optimum)/30)**2)*max(0,1-1.3*(lam-.95)**2)
        efficiency*=min(1,energy/.04)*(.75 if self.clt<30 else 1)
        chemical=burned*44.;work=chemical*efficiency
        self.cylinder_burned_mg[index]+=burned;self.cylinder_scheduled_work_j[index]+=work;record['scheduled_work_j']=work
        self.burned_chemical_j+=chemical;self.heat_j+=chemical-work
        duration=max(.005,30/max(self.rpm,80))
        self.combustions.append(dict(start=t,end=t+duration,rate=work/duration,remaining=work,cylinder=index))

    def cut(self):
        # External removal of electrical drive is an inhibit, no fabricated
        # normal coil discharge/spark is added to the combustion model.
        self.injector_on=[None]*4;self.coil_on=[None]*4
        if self.idle_valve is not None:self.idle_valve.cut()

    def sample(self,t):
        return dict(map_kpa=self.map_kpa,tps_pct=self.tps,clt_c=self.clt,iat_c=self.iat,
                    battery_v=self.battery,sensor_v=5.,sensors_valid=True,
                    lambda_ready=t>3 and self.lambda_valid,**{'lambda':min(1.5,max(.65,self.lambda_sensor))})

    def integrate(self,t,dt,starter=False,load=5,idle_pct=0):
        if dt<=0:return
        if self.idle_valve is not None:
            if idle_pct!=0:raise ValueError('Controller-duty shortcut is forbidden with the executed-edge valve model')
            idle_pct=self.idle_valve.step(dt,self.battery)
        omega=self.rpm*math.pi/30
        self.air_state=self.air.step(t,dt,omega,self.tps,idle_pct)
        self.map_kpa=self.air_state['map_kpa']
        flow=self.injector_flow_cc_min*.745/60*1000
        dead_s=.9e-3  # fixed benchmark actuator; not a real injector calibration
        for cylinder,start in enumerate(self.injector_on):
            if start is not None:
                mass=flow*self.injector_flow_factors[cylinder]*max(0,t+dt-max(t,start+dead_s));self.fuel_mg+=mass;self.cylinder_fuel_mg[cylinder]+=mass
                fraction=.45 if self.clt<30 else .05
                self.wall_mg[cylinder]+=mass*fraction;self.port_mg[cylinder]+=mass*(1-fraction)
        tau=1.5 if self.clt<30 else .05
        for cylinder in range(4):
            evaporated=self.wall_mg[cylinder]*(1-math.exp(-dt/tau))
            self.wall_mg[cylinder]-=evaporated;self.port_mg[cylinder]+=evaporated
        available=0.
        for pulse in self.combustions:
            released=(pulse['remaining'] if t+dt>=pulse['end'] else
                      min(pulse['remaining'],pulse['rate']*max(0,min(t+dt,pulse['end'])-max(t,pulse['start']))))
            pulse['remaining']-=released;available+=released;self.cylinder_shaft_j[pulse['cylinder']]+=released*min(1,omega/20)
        self.combustions=[p for p in self.combustions if p['remaining']>1e-12]
        work=available*min(1,omega/20)
        self.heat_j+=available-work;self.combustion_shaft_j+=work
        starter_torque=55*max(0,1-self.rpm/350) if starter else 0.
        friction=12+.006*self.rpm
        torque=starter_torque-friction-load
        b=torque*dt/self.rotor_inertia
        next_omega=max(0,.5*b+math.sqrt((omega+.5*b)**2+2*work/self.rotor_inertia))
        if work==0 and torque<0 and omega+b<=0:
            rotation=omega*omega/(2*(-torque/self.rotor_inertia))
            next_omega=0.
        else:rotation=(omega+next_omega)*.5*dt
        self.starter_j+=starter_torque*rotation;self.friction_j+=friction*rotation;self.load_j+=load*rotation
        before_angle=self.angle
        self.angle+=rotation*180/math.pi;self.rpm=next_omega*30/math.pi
        # Mean-value intake closing180degrees before firing TDC. Delivered
        # port fuel becomes a cylinder charge here; unfired previous charge
        # exits unburned. Ignition cuts cannot accumulate fuel indefinitely in
        # a closed cylinder and then burn several missed cycles on recovery.
        for cylinder,tdc in enumerate((90,630,270,450)):
            phase=tdc-180
            if math.floor((self.angle-phase)/720)>math.floor((before_angle-phase)/720):
                self.unburned_mg+=self.charge_mg[cylinder]
                self.charge_mg[cylinder]=self.port_mg[cylinder];self.port_mg[cylinder]=0.
                self.air_charge_mg[cylinder]=self.air_state['cylinder_air_kg_s']*math.pi/omega*1e6 if omega>1e-9 else 0.
        self.lambda_sensor+=(self.exhaust_lambda-self.lambda_sensor)*(1-math.exp(-dt/.12))
        self.lambda_valid=(self.lambda_valid and t+dt-self.last_exhaust_t<=.3
                           and self.rpm>40 and self.air_state['cylinder_air_kg_s']>1e-6)
        if not all(math.isfinite(v) for v in (self.rpm,self.angle,self.map_kpa,self.fuel_mg)):
            raise RuntimeError('Non-finite research plant state')

    def ledger(self):
        pending=sum(p['remaining'] for p in self.combustions)
        kinetic=.5*self.rotor_inertia*(self.rpm*math.pi/30)**2
        a=self.air_state;initial=self.air.initial
        return dict(fuel_in_mg=self.fuel_mg,burned_mg=self.burned_mg,unburned_mg=self.unburned_mg,
                    stored_mg=sum(self.charge_mg)+sum(self.wall_mg)+sum(self.port_mg),
                    fuel_residual_mg=self.fuel_mg-self.burned_mg-self.unburned_mg-sum(self.charge_mg)-sum(self.wall_mg)-sum(self.port_mg),
                    burned_chemical_j=self.burned_chemical_j,combustion_shaft_j=self.combustion_shaft_j,
                    heat_j=self.heat_j,pending_work_j=pending,
                    chemical_residual_j=self.burned_chemical_j-self.combustion_shaft_j-self.heat_j-pending,
                    kinetic_j=kinetic,starter_j=self.starter_j,friction_j=self.friction_j,load_j=self.load_j,
                    shaft_residual_j=self.starter_j+self.combustion_shaft_j-self.friction_j-self.load_j-kinetic,
                    air_residual_kg=a['inventory_kg']-initial['inventory_kg']-a['accumulated_inlet_kg']+a['accumulated_outlet_kg'],
                    air_energy_residual_j=a['inventory_j']-initial['inventory_j']-a['accumulated_inlet_j']+a['accumulated_outlet_j'])

    def close(self):self.air.close()
