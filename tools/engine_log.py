"""Text MSL export for recorded SIL traces; no invented physical measurements."""
import math
FIELDS=[('Time','s','time'),('RPM','RPM','plant_rpm'),('MAP','kPa','map_kpa'),('TPS','%','tps'),('Lambda','','lambda_measured'),('PulseWidth','ms','pulse_ms'),('Advance','deg','advance_deg'),('Dwell','ms','dwell_ms'),('VE','%','ve_pct'),('LambdaTarget','','target_lambda'),('EGO','','ego'),('Faults','bitfield','faults'),('Sync','','synced'),('CrankSync','','crank_synced'),('PhaseSync','','phase_synced'),('PhaseRequired','','phase_required'),('PhaseLosses','count','phase_losses'),('CamRejected','count','cam_rejected'),('CamError','deg','cam_error_deg')]
IDLE_FIELDS=[('IdleTarget','RPM','target_rpm'),('IdleDuty','%','duty_pct'),('IdleFeedforward','%','feedforward_pct'),('IdleP','%','p_term'),('IdleI','%','i_term'),('IdleD','%','d_term'),('IdleFlags','bitfield','flags'),('IdleState','code','state_code'),('IdleReason','code','reason_code'),('IdleAlgorithm','code','algorithm_code'),('IdlePidUpdates','count','pid_updates')]
PWM_FIELDS=[('IdlePwmActive','bool','active'),('IdlePwmHigh','bool','virtual_high'),('IdlePwmPeriod','us','period_us'),('IdlePwmHighTime','us','high_us'),('IdlePwmSequence','count','sequence'),('IdlePwmPendingSequence','count','pending_sequence'),('IdlePwmTuneRevision','count','tune_revision'),('IdlePwmSensorRevision','count','sensor_revision'),('IdlePwmLateness','us','max_lateness_us'),('IdlePwmRecoveries','count','recoveries')]
VALVE_FIELDS=[('ValveCurrent','A','current_a'),('ValveOpening','%','opening_pct'),('ValveEnergized','s','energized_s'),('ValveElectricalResidual','J','electrical_residual_j')]
PWM_CAUSES=('none','disabled','configuration','engine_fault','command_expired','late_interrupt','invalid_command','clock_reversed','output_fault')
def value_text(value):
 if isinstance(value,bool):return str(int(value))
 if isinstance(value,float) and math.isfinite(value):return format(value,'.9g')
 if type(value) is int:return str(value)
 if isinstance(value,str) and value.isascii() and value.isdigit() and 0<=int(value)<=18446744073709551615:return str(int(value))
 return 'NaN'
def export_msl(rows,scenario):
 labels=[(name,unit) for name,unit,_ in FIELDS+IDLE_FIELDS]+[('IdleAvailable','bool')]+[(name,unit) for name,unit,_ in PWM_FIELDS]+[('IdlePwmAvailable','bool'),('IdlePwmFault','code')]+[(name,unit) for name,unit,_ in VALVE_FIELDS]+[('ValveModelAvailable','bool')]
 out=['"ESP32ECU SIL 003"','"UNVALIDATED REDUCED-ORDER SIMULATION / '+scenario+' / physical outputs inhibited; proposed controller terms, virtual dispatcher state and synthetic valve estimates are separate; electrical ledger only"','\t'.join(x[0] for x in labels),'\t'.join(x[1] for x in labels)]
 for row in rows:
  values=[row.get(key,0) for _,_,key in FIELDS]
  idle=row.get('engine_sample',{}).get('idle',{});known=idle.get('available') is True
  values += [idle.get(key) if known else None for _,_,key in IDLE_FIELDS]+[known]
  pwm=row.get('idle_pwm',{});values += [pwm.get(key) for _,_,key in PWM_FIELDS]+[bool(pwm),PWM_CAUSES.index(pwm['fault']) if pwm.get('fault') in PWM_CAUSES else None]
  valve=row.get('idle_valve',{});values += [valve.get(key) for _,_,key in VALVE_FIELDS]+[bool(valve)]
  out.append('\t'.join(value_text(value) for value in values))
 return '\n'.join(out)+'\n'
