"""Schema10/own011 boost layout, with every older offset retained."""
MODES=('off','open_loop','closed_loop')
ACTIVATIONS=('barometric','fixed')
SCALARS=('maximum_map_kpa','cut_kpa','cut_hysteresis_kpa','recovery_ms','frequency_hz','control_period_ms','min_pct','max_pct','minimum_rpm','minimum_tps_pct','activation_kpa','activation_hysteresis_kpa','inactive_pct','kp','ki','kd','integral_limit_pct','derivative_filter_s','slew_pct_s')
TABLES=('open_duty','target','feedforward')
OFFSET=8192
SCALAR_OFFSETS={name:8204+4*n for n,name in enumerate(SCALARS)}
TABLE_OFFSETS={name:8320+320*n for n,name in enumerate(TABLES)}
USED_END=9280;PAGE_BYTES=12288;LIVE_OFFSET=832;LIVE_BYTES=1152
UNITS=dict(maximum_map_kpa='kPa absolute',cut_kpa='kPa absolute',cut_hysteresis_kpa='kPa',recovery_ms='ms',frequency_hz='Hz',control_period_ms='ms',min_pct='%',max_pct='%',minimum_rpm='RPM',minimum_tps_pct='%',activation_kpa='kPa absolute',activation_hysteresis_kpa='kPa',inactive_pct='%',kp='%/kPa',ki='%/(kPa*s)',kd='%*s/kPa',integral_limit_pct='%',derivative_filter_s='s',slew_pct_s='%/s')
LIMITS=dict(maximum_map_kpa=(110,400),cut_kpa=(100,400),cut_hysteresis_kpa=(1,50),recovery_ms=(0,5000),frequency_hz=(10,50),control_period_ms=(20,250),min_pct=(0,99),max_pct=(1,100),minimum_rpm=(500,4000),minimum_tps_pct=(0,100),activation_kpa=(50,400),activation_hysteresis_kpa=(1,20),inactive_pct=(0,100),kp=(0,10),ki=(0,10),kd=(0,10),integral_limit_pct=(0,100),derivative_filter_s=(0,2),slew_pct_s=(1,2000))
LABELS=dict(maximum_map_kpa='Confirmed MAP range ceiling',cut_kpa='Overboost cut',cut_hysteresis_kpa='Pressure recovery hysteresis',recovery_ms='Pressure recovery observation time',frequency_hz='Valve PWM frequency',control_period_ms='PID update interval',min_pct='Active minimum duty',max_pct='Maximum duty',minimum_rpm='Minimum running speed',minimum_tps_pct='Minimum throttle',activation_kpa='Fixed activation pressure',activation_hysteresis_kpa='Activation hysteresis',inactive_pct='Direct duty below activation',kp='Proportional gain',ki='Integral gain',kd='Derivative gain',integral_limit_pct='Integral limit',derivative_filter_s='Derivative filter time',slew_pct_s='Active duty slew limit')
RPM=[500,1000,1500,2000,3000,4000,6000,8000]
TPS=[0,5,10,20,40,60,80,100]
DEFAULT=dict(pressure_enabled=False,mode='off',activation='barometric',maximum_map_kpa=300,cut_kpa=220,cut_hysteresis_kpa=10,recovery_ms=250,frequency_hz=25,control_period_ms=100,min_pct=0,max_pct=90,minimum_rpm=800,minimum_tps_pct=5,activation_kpa=120,activation_hysteresis_kpa=2,inactive_pct=0,kp=.5,ki=.1,kd=0,integral_limit_pct=40,derivative_filter_s=.1,slew_pct_s=100,open_duty=dict(rpm=RPM.copy(),axis=TPS.copy(),cells=[0]*64),target=dict(rpm=RPM.copy(),axis=TPS.copy(),cells=[150]*64),feedforward=dict(rpm=RPM.copy(),axis=[50,75,100,125,150,200,250,300],cells=[0]*64))
VALUES=('duty_pct','demand_pct','target_kpa','feedforward_pct','error_kpa','p_term','i_term','d_term')
REASONS=('disabled','ready','invalid_configuration','control_clock','stale_input','map_unavailable','throttle_gate','baro_unavailable','stopped_or_below_rpm','cranking','engine_fault','overrun','below_activation','target_not_above_ambient','overboost','overboost_recovery','pressure_protection_only')

def constant(name):return 'boost_'+name

def log_fields():
 return [(name,unit,key) for name,unit,key in zip(('BoostDuty','BoostDemand','BoostTarget','BoostFeedforward','BoostError','BoostP','BoostI','BoostD'),('%','%','kPa','%','kPa','%','%','%'),VALUES)]+[(name,unit,key) for name,unit,key in (('BoostFlags','bitfield','flags'),('BoostReason','code','reason_code'),('BoostMode','code','mode_code'),('BoostAvailable','bool','available'),('BoostPressureEnabled','bool','pressure_enabled'),('BoostInhibitEngine','bool','inhibit_engine'),('BoostPidUpdates','count','pid_updates'),('BoostOverboostEvents','count','overboost_events'))]
