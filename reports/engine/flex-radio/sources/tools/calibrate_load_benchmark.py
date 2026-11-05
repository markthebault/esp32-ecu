#!/usr/bin/env python3
"""Static Alpha-N benchmark map from independent FMU air flow, no ECU feedback.

This calibrates only this declared research plant's steady operating corridor.
Cells below its10kPa domain use a disclosed pressure-floor extension. They are
not engine calibration evidence. Transient film/combustion remains unadjusted.
"""
import argparse,hashlib,json,math,sys
from pathlib import Path
from engine_research_plant import AirPath

ROOT=Path(__file__).resolve().parents[1]
RPM=(100,500,800,1000,1200,1500,1800,2200,2600,3000,3500,4000,4500,5000,6500,8000)
TPS=(0,1,2,3,4,5,7,10,15,20,30,40,55,70,85,100)

def point(rpm,tps):
 p=AirPath();last=p.initial;t=0.;stable_since=None;reason='time_limit';derivative=None;observed_rpm=0
 try:
  while t<20:
   dt=.0002 if last['map_kpa']<15 else .002
   observed_rpm=rpm*min((t+dt)/3,1)
   state=p.step(t,dt,observed_rpm*2*math.pi/60,tps);t+=dt
   derivative=(state['map_kpa']-last['map_kpa'])/dt;last=state
   if state['map_kpa']<10.3:reason='below_qualified_pressure_corridor';break
   if state['temperature_k']<210:reason='outside_qualified_thermal_corridor';break
   if t>3.5 and abs(state['inlet_air_kg_s']-state['cylinder_air_kg_s'])<1e-8 and abs(derivative)<.001:
    if stable_since is None:stable_since=t
    if t-stable_since>.1:reason='steady';break
   else:stable_since=None
  air_mg=last['cylinder_air_kg_s']/(observed_rpm/120*4)*1e6
  reference_air_mg=100000*.0005/(287.05*298.15)*1e6
  coefficient=air_mg/reference_air_mg*100
  if not math.isfinite(coefficient) or not 0<=coefficient<=255:raise RuntimeError('Benchmark coefficient outside supported domain')
  return dict(rpm=rpm,observed_rpm=observed_rpm,tps_pct=tps,time_s=t,status=reason,coefficient_pct=round(coefficient,6),map_kpa=last['map_kpa'],temperature_k=last['temperature_k'],air_kg_s=last['cylinder_air_kg_s'],inlet_air_kg_s=last['inlet_air_kg_s'],map_dot_kpa_s=derivative)
 finally:p.close()

def build(output):
 if output.exists():raise ValueError('Calibration output exists; preserve it and choose a new path')
 output.parent.mkdir(parents=True,exist_ok=True);points=[]
 for tps in TPS:
  for rpm in RPM:points.append(point(rpm,tps))
  print('Calibrated TPS',tps,flush=True)
 rows=dict(rpm=RPM,tps_pct=TPS,cells=[p['coefficient_pct'] for p in points],points=points,
   provenance=dict(method='Independent fixed-shaft steady FMU pumping mass per cylinder per720deg /100kPa25C modeled reference air; no ECU or coupled-run output used',
                   plant_fmu_manifest=json.loads((ROOT/'.cache/engine/modelica-mvem/airpath/manifest.json').read_text()),
                   calibration_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   scope='Fixed100kPa ambient,25C declared research plant; prescribed3s RPM ramp avoids instantaneous shaft steps; empirical fuel transport untouched. Pressure/thermal-domain exits retain their final per-cycle flow as a conservative extension; these corners and time-limit points are unqualified. Not a vehicle tune.'))
 output.write_text(json.dumps(rows,indent=2)+'\n');return rows

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();build(a.output)
