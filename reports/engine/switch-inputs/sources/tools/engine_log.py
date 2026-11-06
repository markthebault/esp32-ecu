"""Text MSL export for recorded SIL traces; no invented physical measurements."""
import math
from secondary_config import KINDS,VALUE_NAMES as SEC_VALUES,log_fields
FIELDS=[('Time','s','time'),('RPM','RPM','plant_rpm'),('MAP','kPa','map_kpa'),('TPS','%','tps'),('Lambda','','lambda_measured'),('PulseWidth','ms','pulse_ms'),('Advance','deg','advance_deg'),('Dwell','ms','dwell_ms'),('VE','%','ve_pct'),('LambdaTarget','','target_lambda'),('EGO','','ego'),('Faults','bitfield','faults'),('Sync','','synced'),('CrankSync','','crank_synced'),('PhaseSync','','phase_synced'),('PhaseRequired','','phase_required'),('PhaseLosses','count','phase_losses'),('CamRejected','count','cam_rejected'),('CamError','deg','cam_error_deg')]
IDLE_FIELDS=[('IdleTarget','RPM','target_rpm'),('IdleDuty','%','duty_pct'),('IdleFeedforward','%','feedforward_pct'),('IdleP','%','p_term'),('IdleI','%','i_term'),('IdleD','%','d_term'),('IdleFlags','bitfield','flags'),('IdleState','code','state_code'),('IdleReason','code','reason_code'),('IdleAlgorithm','code','algorithm_code'),('IdlePidUpdates','count','pid_updates')]
PWM_FIELDS=[('IdlePwmActive','bool','active'),('IdlePwmHigh','bool','virtual_high'),('IdlePwmPeriod','us','period_us'),('IdlePwmHighTime','us','high_us'),('IdlePwmSequence','count','sequence'),('IdlePwmPendingSequence','count','pending_sequence'),('IdlePwmTuneRevision','count','tune_revision'),('IdlePwmSensorRevision','count','sensor_revision'),('IdlePwmLateness','us','max_lateness_us'),('IdlePwmRecoveries','count','recoveries')]
VALVE_FIELDS=[('ValveCurrent','A','current_a'),('ValveOpening','%','opening_pct'),('ValveEnergized','s','energized_s'),('ValveElectricalResidual','J','electrical_residual_j')]
AE_FIELDS=[('AeTpsDot','%/s','tps_dot_pct_s'),('AeMapDot','kPa/s','map_dot_kpa_s'),('AeWindowMs','ms','window_ms'),('AeTriggerDot','source_units/s','trigger_dot'),('AeCorrectionPct','%','correction_pct'),('AeUnclampedPct','%','unclamped_pct'),('AeRemainingAtSampleMs','ms','remaining_ms'),('AeAddedFuelMg','mg','added_fuel_mg'),('AeFlags','bitfield','flags'),('AeMode','code','mode_code'),('AeApply','code','apply_code'),('AePhase','code','phase_code'),('AeReason','code','reason_code')]
LOAD_FIELDS=[('LoadFuel','source_units','fuel_load'),('LoadSpark','source_units','spark_load'),('LoadLambda','source_units','lambda_load'),('LoadTrim','source_units','trim_load'),('LoadPressureFactor','ratio','pressure_factor'),('LoadBaro','kPa','baro_kpa'),('LoadEmap','kPa','emap_kpa'),('LoadAux','kPa','aux_kpa'),('LoadAfrFactor','ratio','afr_factor'),('LoadFlags','bitfield','flags'),('LoadFuelSource','code','fuel_source_code'),('LoadSparkSource','code','spark_source_code'),('LoadLambdaSource','code','lambda_source_code'),('LoadTrimSource','code','trim_source_code'),('LoadPressure','code','pressure_code'),('LoadAuxRole','code','aux_role_code'),('LoadBaroSource','code','baro_source_code'),('LoadAfr','code','afr_code'),('LoadReason','code','reason_code'),('LoadAfrState','code','afr_state_code')]
PWM_CAUSES=('none','disabled','configuration','engine_fault','command_expired','late_interrupt','invalid_command','clock_reversed','output_fault')
def value_text(value):
 if isinstance(value,bool):return str(int(value))
 if isinstance(value,float) and math.isfinite(value):return format(value,'.9g')
 if type(value) is int:return str(value)
 if isinstance(value,str) and value.isascii() and value.isdigit() and 0<=int(value)<=18446744073709551615:return str(int(value))
 return 'NaN'
def export_msl(rows,scenario,strategy=None):
 if strategy is not None and strategy not in ('batch_wasted_4cyl','sequential_4cyl','semi_sequential_4cyl'):raise ValueError('Unknown log strategy')
 labels=[(name,unit) for name,unit,_ in FIELDS+IDLE_FIELDS]+[('IdleAvailable','bool')]+[(name,unit) for name,unit,_ in PWM_FIELDS]+[('IdlePwmAvailable','bool'),('IdlePwmFault','code')]+[(name,unit) for name,unit,_ in VALVE_FIELDS]+[('ValveModelAvailable','bool')]+[(name,unit) for name,unit,_ in AE_FIELDS]+[('AeAvailable','bool')]
 labels += [(name,unit) for name,unit,_ in LOAD_FIELDS]+[('LoadAvailable','bool')]
 labels += [(name,unit) for kind in KINDS for name,unit,_ in log_fields(kind)]
 out=['"ESP32ECU SIL 006"','"UNVALIDATED REDUCED-ORDER SIMULATION / '+scenario+(' / '+strategy if strategy else '')+' / physical outputs inhibited; proposals/virtual state/synthetic estimates are separate; Load*=fuel model; Sec*=source-tagged secondary values/selection/input diagnostics; check availability/validity; electrical ledger only"','\t'.join(x[0] for x in labels),'\t'.join(x[1] for x in labels)]
 for row in rows:
  values=[row.get(key,0) for _,_,key in FIELDS]
  idle=row.get('engine_sample',{}).get('idle',{});known=idle.get('available') is True
  values += [idle.get(key) if known else None for _,_,key in IDLE_FIELDS]+[known]
  pwm=row.get('idle_pwm',{});values += [pwm.get(key) for _,_,key in PWM_FIELDS]+[bool(pwm),PWM_CAUSES.index(pwm['fault']) if pwm.get('fault') in PWM_CAUSES else None]
  valve=row.get('idle_valve',{});values += [valve.get(key) for _,_,key in VALVE_FIELDS]+[bool(valve)]
  ae=row.get('transient_enrichment',{});available=ae.get('available') is True;values += [ae.get(key) if available else None for _,_,key in AE_FIELDS]+[available]
  model=row.get('load_model',row.get('engine_sample',{}).get('load_model',{}));known=model.get('available') is True
  values += [model.get(key) if known else None for _,_,key in LOAD_FIELDS]+[known]
  second=row.get('secondary_tables',row.get('engine_sample',{}).get('secondary_tables',{}))
  for kind in KINDS:
   observation=second.get(kind,{})
   if not observation.get('available'):observation=dict(available=False,active_high=True,flags=1024)
   for _,_,key in log_fields(kind):
    value=observation.get(key)
    if key in SEC_VALUES:value=value if observation.get('available') else None
    elif key=='input_observed_us':value=value if observation.get('mode_code')==4 and observation.get('input_source_code') else None
    elif key!='flags':value=value if value is not None else False if key in ('available','evaluated','active','clamped','pending','input_qualified','input_level','pending_level','input_valid','input_raw','valid') else 0
    values.append(value)
  out.append('\t'.join(value_text(value) for value in values))
 return '\n'.join(out)+'\n'
