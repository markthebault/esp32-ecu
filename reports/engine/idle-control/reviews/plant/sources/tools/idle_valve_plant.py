"""Independent illustrative NC solenoid, RL coil and overdamped return spring.

Fixed parameters are not derived from controller calibration and are shared by
both simulated ECUs. This is an uncalibrated actuator hypothesis, not a selected
valve's measured characteristics. Drive comes only from executed GPIO edges.
"""
import math

class IdleValve:
    MODES=('normal','disconnected','stuck_closed','stuck_open','reversed_polarity')
    PARAMETERS=dict(resistance_ohm=8.,inductance_h=.012,diode_v=.7,mechanical_tau_s=.06,
                    opening_current_a=.2,full_open_current_a=1.1)

    def __init__(self,mode='normal'):
        if mode not in self.MODES:raise ValueError('Unknown idle valve failure mode')
        self.mode=mode;self.high=False;self.current=0.;self.position=0.;self.edges=0
        self.source_j=0.;self.copper_j=0.;self.flyback_j=0.;self.disconnect_j=0.
        self.high_s=0.;self.max_current=0.;self.time=0.

    def edge(self,high):
        if type(high) is not bool or high==self.high:raise ValueError('Idle actuator requires distinct boolean GPIO edges')
        self.high=high;self.edges+=1

    def cut(self):
        if self.high:self.edge(False)

    def step(self,dt,battery):
        if not math.isfinite(dt) or not 0<=dt<=.01 or not math.isfinite(battery) or not 0<=battery<=24:raise ValueError('Invalid idle valve integration step')
        if dt==0:return self.opening_pct
        p=self.PARAMETERS;r=p['resistance_ohm'];l=p['inductance_h'];tau=l/r
        energized=self.high if self.mode!='reversed_polarity' else not self.high
        self.high_s+=dt*int(energized);i0=self.current
        if self.mode=='disconnected':
            self.disconnect_j+=.5*l*i0*i0;self.current=0.;i2=0.
        else:
            voltage=battery if energized else -p['diode_v'];a=voltage/r;b=i0-a
            h=dt
            if not energized:h=min(dt,tau*math.log((i0-a)/(-a))) if i0>0 else 0.
            decay=math.exp(-h/tau);one=-math.expm1(-h/tau)
            integral_i=max(0.,a*h+b*tau*one)
            integral_i2=max(0.,a*a*h+2*a*b*tau*one+b*b*tau*.5*(-math.expm1(-2*h/tau)))
            self.current=max(0.,a+b*decay) if h==dt else 0.
            self.copper_j+=r*integral_i2
            if energized:self.source_j+=battery*integral_i
            else:self.flyback_j+=p['diode_v']*integral_i
            i2=integral_i2/dt
        # Mean squared current drives force against a return spring; the
        # mechanical pole remains independent of the ECU's PID and target.
        low=p['opening_current_a']**2;span=p['full_open_current_a']**2-low
        equilibrium=min(1.,max(0.,(i2-low)/span))
        self.position+=(equilibrium-self.position)*(-math.expm1(-dt/p['mechanical_tau_s']))
        self.max_current=max(self.max_current,i0,self.current);self.time+=dt
        return self.opening_pct

    @property
    def opening_pct(self):
        return 0. if self.mode=='stuck_closed' else 100. if self.mode=='stuck_open' else self.position*100

    def snapshot(self):
        stored=.5*self.PARAMETERS['inductance_h']*self.current**2
        return dict(mode=self.mode,gpio_high=self.high,current_a=self.current,opening_pct=self.opening_pct,
                    edges=self.edges,source_j=self.source_j,copper_j=self.copper_j,flyback_j=self.flyback_j,
                    disconnect_j=self.disconnect_j,stored_j=stored,
                    electrical_residual_j=self.source_j-self.copper_j-self.flyback_j-self.disconnect_j-stored,
                    energized_s=self.high_s,max_current_a=self.max_current,parameters=self.PARAMETERS)
