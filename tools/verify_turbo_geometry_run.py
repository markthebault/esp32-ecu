"""Audit a source-bound generalized turbo run and optional charged end-cut.

Prefix-only historical runs cannot establish post-halt physical inventories.
This checks native research evidence, never target or physical qualification.
"""
import argparse,hashlib,json,math
from pathlib import Path
from engine_geometry import EngineGeometry

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(value,message):
 if not value:raise RuntimeError(message)

def audit(directory,prefix_only=False,charged_cylinder=None):
 directory=directory.resolve();r=json.loads((directory/'result.json').read_text())
 progress=json.loads((directory/'progress.json').read_text())
 require(r['completed']and progress['complete'],'Run is not complete')
 require(r['controller']=='ours'and not r['physical_execution']and not r['production_speeduino_executed'],'Expected native project research run')
 g=r['plant_geometry'];geometry=EngineGeometry(g['cylinders'],tuple(g['firing_order']),g['displacement_cc'],g['tooth1_tdc_deg'],g['cam_edge_deg'])
 require(geometry.summary()==g,'Physical geometry summary differs')
 tune=json.loads((directory/'tune.json').read_text());n=geometry.cylinders
 require(tune['engine']['cylinders']==n and tune['engine']['displacement_cc']==g['displacement_cc'],'Tune/physical engine size differs')
 require(tune['timing']['firing_order']==[*geometry.firing_order,*([0]*(8-n))],'Tune/physical firing order differs')
 require(tune['strategy']==r['strategy'],'Tune/strategy differs')
 air=r['plant_air_parameters']
 require(air['cylinders']==n and air['graph_displacement_m3']==geometry.displacement_m3,'Actual graph geometry differs')
 require(air['fixed_volume_m3']==dict(filter=.010,charge=.005,cooler=.005,intake=.0018,exhaust=.0025,tail=.020),'Fixed source volumes differ')
 provenance=json.loads((directory/'provenance/manifest.json').read_text())
 require(sha(directory/'provenance/manifest.json')==r['provenance_manifest_sha256'],'Provenance manifest identity differs')
 require(provenance['source_hashes']==r['source_hashes'],'Run/provenance source identities differ')
 for name,expected in r['source_hashes'].items():
  path=directory/'provenance/sources'/name
  require(path.resolve().is_relative_to((directory/'provenance/sources').resolve())and sha(path)==expected,'Source snapshot differs: '+name)
 layout=json.loads((directory/'provenance/sources/config/engine-profile.json').read_text())
 require(provenance.get('loaded_engine_profile_layout')==layout,'Loaded channel layout was not attested')
 require(tuple(layout['injector_channels'][:n])==geometry.injector_channels and tuple(layout['coil_channels'][:n])==geometry.coil_channels,'Recorded physical channel mapping differs')
 native=provenance['own_runtime']
 require(native['binary_sha256']==native['freshly_rebuilt_sha256'],'Mapped native bridge differs from its dependency-bound rebuild')
 edges=[json.loads(line)for line in (directory/'edges.jsonl').read_text().splitlines()]
 require(len(edges)==r['edges'],'Output edge count differs')
 allowed=set(geometry.injector_channels+geometry.coil_channels+(9,));active=set();rise={};last=0;before_state=set();used=set()
 horizon=round(r['duration_s']*1e6);cursor=r['before_halt']['edges_consumed']
 for i,e in enumerate(edges,1):
  stamp,ch,high=e['time_us'],e['ch'],e['high']
  require(e['sequence']==i and type(stamp)is int and last<=stamp<=horizon,'Nonmonotonic output event')
  require(type(ch)is int and ch in allowed and type(high)is bool,'Invalid active output channel/value')
  require((ch in active)!=high,'Duplicate output transition')
  if high:active.add(ch);rise[ch]=stamp
  else:active.remove(ch)
  used.add(ch);last=stamp
  if i==cursor:before_state=set(active)
 require(not active,'Final replay leaves an actuator high')
 require(before_state=={ch for ch,v in enumerate(r['before_halt']['high'])if v},'Before-halt command snapshot differs from edge replay')
 require(set(geometry.injector_channels+geometry.coil_channels)<=used,'A declared engine channel never executed')
 if prefix_only:
  require(charged_cylinder is None,'Prefix-only evidence cannot prove charged post-halt physics')
  ledger=r['before_halt']['ledger'];post=False;discharge=None
 else:
  after=r.get('after_halt');require(after is not None,'Missing distinct post-halt physical snapshot')
  require(not any(after['high'])and after['injector_on']==[None]*n and after['coil_on']==[None]*n and not after['boost_command_high'],'Post-halt actuator command remains high')
  require(after['edges_consumed']==len(edges),'Post-halt edge cursor differs')
  require(len(after['cylinder_burned_mg'])==n and all(v>0 for v in after['cylinder_burned_mg']),'Declared cylinder has no recorded combustion')
  ledger=after['ledger'];post=True;discharge=None
  if charged_cylinder is not None:
   require(type(charged_cylinder)is int and 1<=charged_cylinder<=n,'Invalid charged-cylinder request')
   channel=geometry.coil_channels[charged_cylinder-1]
   require(channel in before_state,'Requested coil was not charged at the actual stop')
   previous=len(r['before_halt']['cut_discharges'])
   matches=[e for e in after['cut_discharges'][previous:]if e['channel']==channel]
   require(len(matches)==1,'Missing actual post-stop charged-coil discharge')
   discharge=matches[0]
   require(discharge['dwell_us']>0 and abs(discharge['dwell_us']-(horizon-rise[channel]))<1e-4,'Charged-cut dwell differs from actual edge history')
 for name,tolerance in (('coupled_mass_residual_kg',1e-8),('coupled_energy_residual_j',.001),('heat_partition_residual_j',1e-5),('exhaust_fuel_transport_residual_kg',1e-10)):
  require(math.isfinite(ledger[name])and abs(ledger[name])<tolerance,'Conservation residual exceeds declared audit bound: '+name)
 require(not r['paired_comparison_accepted'],'This project-only audit cannot approve a paired reference comparison')
 return dict(passed=True,run=str(directory),source_sha256=sha(Path(__file__)),result_sha256=sha(directory/'result.json'),
  cylinders=n,strategy=r['strategy'],mode=r['mode'],duration_s=r['duration_s'],edges=len(edges),boost_edges=r['boost_edges'],
  prefix_only=prefix_only,post_halt_physics_verified=post,charged_cut=discharge,
  final_rpm=r['before_halt']['rpm'],conservation={name:ledger[name]for name in ('coupled_mass_residual_kg','coupled_energy_residual_j','heat_partition_residual_j')},
  current_source_differences=[name for name,expected in r['source_hashes'].items()if not(ROOT/name).is_file()or sha(ROOT/name)!=expected],
  scope='Declared native project turbo run; source/layout, executed edges and conservation audit. No expanded Speeduino, target or physical qualification')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--prefix-only',action='store_true');p.add_argument('--charged-cylinder',type=int)
 a=p.parse_args();result=audit(a.run,a.prefix_only,a.charged_cylinder)
 with a.output.open('x')as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print(json.dumps(result,indent=2,allow_nan=False))
