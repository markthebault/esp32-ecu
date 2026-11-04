"""Independent air actuator causal check, fixed shaft, zero throttle, no ECU."""
import json
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from engine_research_plant import AirPath

rows=[]
for rpm in (600,900,1200):
 for idle in (0,25,50,100):
  model=AirPath()
  try:
   for n in range(4000):state=model.step(n*.00025,.00025,rpm*math.pi/30,0,idle)
   mass=state['inventory_kg']-model.initial['inventory_kg']-state['accumulated_inlet_kg']+state['accumulated_outlet_kg']
   energy=state['inventory_j']-model.initial['inventory_j']-state['accumulated_inlet_j']+state['accumulated_outlet_j']
   rows.append(dict(rpm=rpm,idle_pct=idle,map_kpa=state['map_kpa'],cylinder_air_kg_s=state['cylinder_air_kg_s'],air_residual_kg=mass,air_energy_residual_j=energy))
  finally:model.close()
(Path(__file__).parent/'airpath-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
