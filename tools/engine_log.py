"""Text MSL export for recorded SIL traces; no invented physical measurements."""
import math
FIELDS=[('Time','s','time'),('RPM','RPM','plant_rpm'),('MAP','kPa','map_kpa'),('TPS','%','tps'),('Lambda','','lambda_measured'),('PulseWidth','ms','pulse_ms'),('Advance','deg','advance_deg'),('Dwell','ms','dwell_ms'),('VE','%','ve_pct'),('LambdaTarget','','target_lambda'),('EGO','','ego'),('Faults','bitfield','faults'),('Sync','','synced'),('CrankSync','','crank_synced'),('PhaseSync','','phase_synced'),('PhaseRequired','','phase_required'),('PhaseLosses','count','phase_losses'),('CamRejected','count','cam_rejected'),('CamError','deg','cam_error_deg')]
def export_msl(rows,scenario):
 out=['"ESP32ECU SIL 002"','"UNVALIDATED REDUCED-ORDER SIMULATION / '+scenario+' / physical outputs inhibited"','\t'.join(x[0] for x in FIELDS),'\t'.join(x[1] for x in FIELDS)]
 for row in rows:
  values=[]
  for name,unit,key in FIELDS:
   value=row.get(key,0)
   if isinstance(value,bool):value=int(value)
   values.append(f'{value:.6f}' if isinstance(value,float) and math.isfinite(value) else str(value) if isinstance(value,int) else 'NaN')
  out.append('\t'.join(values))
 return '\n'.join(out)+'\n'
