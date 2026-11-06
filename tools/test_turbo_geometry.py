"""Declared1..8-cylinder turbo geometry, sparse actuation and atomic boundaries."""
import argparse,copy,hashlib,json,math,unittest
from pathlib import Path
from engine_geometry import EngineGeometry
from turbo_components import TurboComponents
from turbo_gas_path import TurboGasPath
from boost_research_plant import BoostResearchPlant
from tcsi_graph import Model

ROOT=Path(__file__).resolve().parents[1]
VOLUMES=dict(filter=.010,charge=.005,cooler=.005,intake=.0018,exhaust=.0025,tail=.020)

def geometry(n,total=None):return EngineGeometry(n,(1,*range(n,1,-1)),500*n if total is None else total)


class TurboGeometryTests(unittest.TestCase):
 def test_total_flow_depends_on_displacement_while_count_only_partitions_cylinders(self):
  reference=TurboComponents(geometry=geometry(4,2000)).engine_flow(100000,298.15,100,110000,0)
  for n in range(1,9):
   fixed=TurboComponents(geometry=geometry(n,2000));scaled=TurboComponents(geometry=geometry(n))
   self.assertEqual(fixed.geometry_binding['cylinders'],n)
   self.assertEqual(fixed.engine_graph.env['V_d'],.002)
   self.assertEqual(fixed.engine_flow(100000,298.15,100,110000,0),reference)
   self.assertAlmostEqual(scaled.engine_flow(100000,298.15,100,110000,0),reference*n/4,delta=1e-14)
 def test_geometry_is_private_and_preserves_shared_source_and_graphs(self):
  model=Model(parameter_inputs={'toggle_vol':1});before=copy.deepcopy(model.parameters);provenance=copy.deepcopy(model.provenance)
  old=TurboComponents(model=model);flow=old.engine_flow(100000,298.15,100,110000,0)
  changed=TurboComponents(model=model,geometry=geometry(8))
  self.assertIsNot(changed.model,model);self.assertEqual(model.parameters,before);self.assertEqual(model.provenance,provenance)
  self.assertEqual(old.engine_flow(100000,298.15,100,110000,0),flow)
  self.assertEqual(changed.model.parameters['toggle_vol'],1)
  self.assertEqual(changed.model.parameters['TC_ENGINE.geometry.n_cyl'],8)
  self.assertEqual(changed.model.parameters['V_D'],.004)
 def test_actual_initialized_geometry_and_fixed_volumes_match(self):
  old=BoostResearchPlant();self.addCleanup(old.close)
  self.assertEqual(old.geometry,EngineGeometry(4,(1,3,4,2),1800))
  for n in range(1,9):
   p=BoostResearchPlant(geometry=geometry(n));self.addCleanup(p.close)
   self.assertEqual(p.air.geometry,p.geometry);self.assertEqual(len(p.injector_on),n)
   self.assertEqual(p.air.parameters['fixed_volume_m3'],VOLUMES)
   self.assertEqual(p.air.parameters['graph_displacement_m3'],p.geometry.displacement_m3)
   for k in range(20):p.integrate(k*.00025,.00025,starter=True)
   ledger=p.ledger();self.assertEqual(ledger['burned_chemical_j'],0)
   self.assertLess(abs(ledger['coupled_mass_residual_kg']),1e-12)
   self.assertLess(abs(ledger['coupled_energy_residual_j']),1e-6)
 def test_trapped_air_is_total_four_stroke_cycle_mass_divided_by_count(self):
  for n in range(1,9):
   p=BoostResearchPlant(geometry=geometry(n));self.addCleanup(p.close)
   p.rpm=1000;p.angle=629.99;omega=p.rpm*math.pi/30
   p.integrate(0,.0001)
   event=next(row for row in p.intake_events if row['cylinder']==1)
   self.assertLess(event['time_s'],.0001)
   expected=event['cylinder_air_kg_s']*4*math.pi/event['airflow_sample_omega_rad_s']/n*1e6
   self.assertGreater(expected,0);self.assertAlmostEqual(p.air_charge_mg[0],expected,delta=1e-12)
   frozen=p.air_charge_mg[0];p.tps=80;p.integrate(.0001,.0001)
   self.assertEqual(p.air_charge_mg[0],frozen)
 def test_all_sparse_channels_and_auxiliaries_cut_like_individual_falls(self):
  for n in range(1,9):
   plants=[];g=geometry(n)
   for _ in range(2):
    p=BoostResearchPlant(geometry=g,idle_valve='normal');self.addCleanup(p.close)
    p.rpm=1000;p.angle=62;p.starter_j=.5*p.rotor_inertia*(p.rpm*math.pi/30)**2
    p.charge_mg[0]=10;p.air_charge_mg[0]=147;p.fuel_mg=10;p.cylinder_fuel_mg[0]=10
    for ch in g.injector_channels+g.coil_channels+(8,9):p.edge(ch,True,0)
    for k in range(12):p.integrate(k*.00025,.00025)
    plants.append(p)
   cut,falls=plants;cut.cut()
   for ch in g.injector_channels+g.coil_channels+(8,9):falls.edge(ch,False,falls.air.time)
   self.assertEqual(len(cut.cut_discharges),n);self.assertEqual(cut.injector_on,[None]*n);self.assertEqual(cut.coil_on,[None]*n)
   for k in range(20):
    for p in plants:p.integrate(.003+k*.00025,.00025)
   a=cut.ledger();b=falls.ledger();a.pop('global_cut_discharges');b.pop('global_cut_discharges')
   self.assertEqual(a,b);self.assertEqual(cut.air.state,falls.air.state)
   self.assertLess(abs(a['heat_partition_residual_j']),1e-9);self.assertLess(abs(a['coupled_energy_residual_j']),1e-6)
 def test_accepted_subclock_instants_cannot_leave_a_partial_global_cut(self):
  p=BoostResearchPlant(geometry=geometry(8));self.addCleanup(p.close);p.integrate(0,.00025)
  for ch,offset in ((4,0),(14,5e-9),(17,-5e-9),(9,5e-9)):
   p.edge(ch,True,p.air.time+offset)
  self.assertEqual(p.coil_on[4],p.air.time);self.assertEqual(p.coil_on[7],p.air.time)
  p.cut();self.assertEqual(p.coil_on,[None]*8);self.assertEqual(len(p.cut_discharges),3)
  self.assertFalse(p.boost_valve.coil.high);p.cut();self.assertEqual(len(p.cut_discharges),3)
 def test_invalid_inputs_preserve_physical_state_and_inventory(self):
  p=BoostResearchPlant(geometry=geometry(8));self.addCleanup(p.close);p.edge(17,True,0)
  before=copy.deepcopy(p.ledger());state=list(p.air.state);coils=list(p.coil_on)
  bad_edges=((9.0,True,0),(17,1,0),(True,False,0),(17,False,-.001),(17,False,.001),
             (17,False,float('nan')),(17,False,False))
  for args in bad_edges:
   with self.assertRaises(ValueError):p.edge(*args)
   self.assertEqual(p.ledger(),before);self.assertEqual(p.air.state,state);self.assertEqual(p.coil_on,coils)
  for key,value in (('commanded_advance',float('nan')),('latest_demand',float('inf')),('requested_dwell_us',True)):
   with self.assertRaises(ValueError):p.edge(17,False,0,**{key:value})
   self.assertEqual(p.ledger(),before);self.assertEqual(p.coil_on,coils)
  for args in ((float('nan'),0,0,0),(False,0,0,0),(0,False,0,0),(0,.00025,True,0),(0,.00025,0,float('nan'))):
   with self.assertRaises(ValueError):p.air.step(*args)
   self.assertEqual(p.air.state,state);self.assertEqual(p.air.time,0)
 def test_rk_failure_preserves_eight_cylinder_pending_states(self):
  p=BoostResearchPlant(geometry=geometry(8));self.addCleanup(p.close);p.edge(17,True,0);p.edge(9,True,0)
  before=copy.deepcopy(p.ledger());state=list(p.air.state);coils=list(p.coil_on);original=p.air.rates;calls=0
  def failure(*args):
   nonlocal calls
   calls+=1
   if calls==3:raise ValueError('Deliberate third-stage failure')
   return original(*args)
  p.air.rates=failure
  with self.assertRaisesRegex(ValueError,'Deliberate'):p.integrate(0,.00025,starter=True)
  self.assertEqual(p.ledger(),before);self.assertEqual(p.air.state,state);self.assertEqual(p.coil_on,coils)
  self.assertEqual(p.air.time,0)


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
 args,rest=parser.parse_known_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 names=('tools/test_turbo_geometry.py','tools/turbo_components.py','tools/turbo_gas_path.py','tools/boost_research_plant.py','tools/engine_research_plant.py','tools/shaft_dynamics.py','tools/engine_geometry.py','tools/tcsi_graph.py')
 sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in names}
 result=unittest.main(argv=[__file__,*rest],exit=False,verbosity=2).result
 unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in sources.items())
 (out/'summary.json').write_text(json.dumps(dict(passed=result.wasSuccessful()and unchanged,tests=result.testsRun,
  failures=len(result.failures),errors=len(result.errors),source_unchanged=unchanged,source_sha256=sources,
  scope='Research turbo geometry, conservation, sparse global-low and invalid-input boundaries; no coupled controller, physical engine or target qualification'),indent=2)+'\n')
 raise SystemExit(not(result.wasSuccessful()and unchanged))
