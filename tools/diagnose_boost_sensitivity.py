"""Read-only physical-event instrumentation of the ordinary turbo composition.

Delegates every physics/controller operation unchanged. The observer logs new
combustion records after actual coil falls; it does not supply status or fuel.
Used to investigate finite-step sensitivity, not to tune the plant to a result.
"""
import argparse,copy,hashlib,json
from pathlib import Path
import run_boost_engine as runner
from boost_research_plant import BoostResearchPlant
from engine_geometry import EngineGeometry

CAPTURED=[]


class ObservedPlant(BoostResearchPlant):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.observations=[];CAPTURED.append(self)
 def edge(self,*args,**kwargs):
  before=len(self.cylinder_combustions)
  super().edge(*args,**kwargs)
  for row in self.cylinder_combustions[before:]:
   self.observations.append(dict(event=copy.deepcopy(row),shaft_rpm=self.rpm,shaft_angle_deg=self.angle,
    map_kpa=self.map_kpa,modeled_IAT_c=self.iat,
    source='Actual composition combustion record after unchanged physical edge execution'))


def run(output,reference,step=250,duration=1.65,compare_prefix=None):
 if CAPTURED:raise RuntimeError('Use one fresh observer process per run')
 original=runner.BoostResearchPlant;runner.BoostResearchPlant=ObservedPlant
 try:
  runner.run(output,duration=duration,step_us=step,mode='open_loop',controller='speeduino',reference=reference,
   throttle_pct=20,load_nm=5,geometry=EngineGeometry(8,(1,8,7,6,5,4,3,2),4000),strategy='sequential')
 finally:runner.BoostResearchPlant=original
 if len(CAPTURED)!=1:raise RuntimeError('Expected exactly one observed physical composition')
 with(output/'combustion-observations.jsonl').open('x')as stream:
  for row in CAPTURED[0].observations:stream.write(json.dumps(row,allow_nan=False)+'\n')
 identical=None
 if compare_prefix is not None:
  horizon=round(duration*1e6)
  def rows(folder):return[json.loads(line)for line in(folder/'edges.jsonl').read_text().splitlines()]
  baseline=[r for r in rows(compare_prefix)if r['time_us']<=horizon and r['cause']=='dispatcher']
  observed=[r for r in rows(output)if r['cause']=='dispatcher']
  identical=observed==baseline
  if not identical:raise RuntimeError('Diagnostic observer changed the ordinary actual-output prefix')
 data=dict(complete=True,observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  step_us=step,duration_s=duration,events=len(CAPTURED[0].observations),
  exact_ordinary_dispatcher_prefix=identical,source_physics_changed=False,
  scope='Instrumented actual physical events; uncalibrated research model, no convergence or controller qualification claim')
 with(output/'diagnostic.json').open('x')as stream:stream.write(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--reference',type=Path,required=True);p.add_argument('--step-us',type=int,default=250)
 p.add_argument('--duration',type=float,default=1.65);p.add_argument('--compare-prefix',type=Path)
 a=p.parse_args();run(a.output,a.reference,a.step_us,a.duration,a.compare_prefix)
