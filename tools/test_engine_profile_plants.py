"""Coupled1..8 cylinder actuation/geometry/causality tests; no physical engine.

uv run --with 'fmpy==0.3.26' python tools/test_engine_profile_plants.py --output DIR
"""
import argparse,copy,gzip,hashlib,json,math,unittest
from pathlib import Path
from engine_geometry import EngineGeometry,INJECTOR_CHANNELS,COIL_CHANNELS
from engine_sil import Simulation,Plant
from engine_research_plant import AirPath,ResearchPlant
from compare_engine_controllers import run,benchmark_tune
from engine_log import export_msl

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=None
RESULTS={}

def profile(count,strategy='sequential'):
 t=benchmark_tune();t['engine']['cylinders']=count;t['engine']['displacement_cc']=500*count
 t['strategy']=strategy;t['timing']['firing_order']=[1]+list(range(count,1,-1))+[0]*(8-count)
 return t

def record(name,result):
 RESULTS[name]=result['summary']
 if OUTPUT is not None:(OUTPUT/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(result,separators=(',',':'),allow_nan=False).encode(),mtime=0))

class ProfilePlantTests(unittest.TestCase):
 def test_declared_geometry_and_sparse_outputs_are_real_actuators(self):
  for n in range(1,9):
   g=EngineGeometry.from_tune(profile(n));p=Plant(geometry=g)
   self.assertEqual(len(p.injector_on),n);self.assertEqual(len(p.coil_on),n)
   self.assertEqual(sorted((v-g.tooth1_tdc_deg)%720 for v in g.compression_tdc_deg),[720*i/n for i in range(n)])
   for i,ch in enumerate(g.injector_channels):p.edge(ch,True,0)
   p.integrate(0,.004,starter=False)
   for ch in g.injector_channels:p.edge(ch,False,.004)
   for ch in g.coil_channels:p.edge(ch,True,.004);p.edge(ch,False,.0068,requested_dwell_us=2800)
   self.assertEqual(p.cylinder_sparks,[1]*n);self.assertTrue(all(v>0 for v in p.cylinder_fuel_mg));self.assertAlmostEqual(sum(p.cylinder_fuel_mg),p.fuel_mg)
   for invalid in (8,9,-1,18,False,1.5):
    with self.assertRaises(ValueError):p.edge(invalid,True,.01)
 def test_quick_plant_executes_all24_count_and_strategy_profiles(self):
  for n in range(1,9):
   for mode in ('batch_wasted','semi_sequential','sequential'):
    with self.subTest(cylinders=n,strategy=mode):
     r=Simulation(profile(n,mode),duration_s=4).run();s=r['summary'];record(f'quick-{n}-{mode}',r)
     self.assertTrue(s['sync_acquired']);self.assertEqual(s['final_faults'],0);self.assertEqual(s['rejected_plans'],0);self.assertEqual(s['final_outputs_high'],0)
     self.assertGreater(s['final_rpm'],500);self.assertTrue(all(v>0 for v in s['cylinder_fuel_mg']));self.assertTrue(all(v>0 for v in s['cylinder_sparks']));self.assertTrue(all(v>0 for v in s['cylinder_work_j']))
     self.assertLessEqual(s['max_injector_high_us'],15000);self.assertLessEqual(s['max_dwell_high_us'],3500)
     actual={e[1] for e in r['edges']};g=EngineGeometry.from_tune(profile(n,mode));self.assertEqual(actual,set(g.injector_channels+g.coil_channels))
     if mode=='sequential':self.assertLess(s['max_spark_720_error_deg'],1)
 def test_external_airflow_uses_initialized_geometry_and_per_cylinder_volume(self):
  for n in (1,3,4,7,8):
   g=EngineGeometry.from_tune(profile(n));a=AirPath(geometry=g)
   try:
    self.assertEqual(a.parameters['cylinders'],n);self.assertAlmostEqual(a.parameters['displacement_m3'],500*n*1e-6)
    previous=0
    for k in range(100):previous=a.step(k*.00025,.00025,100,0)['accumulated_outlet_kg']
    self.assertGreater(previous,0)
   finally:a.close()
  legacy=AirPath();current=AirPath(geometry=EngineGeometry())
  try:
   for k in range(1000):
    left=legacy.step(k*.00025,.00025,100,12);right=current.step(k*.00025,.00025,100,12)
    for name in left:self.assertAlmostEqual(left[name],right[name],delta=max(1e-9,abs(left[name])*1e-8),msg=name)
  finally:legacy.close();current.close()
 def test_native_canonicalization_precedes_geometry_for_valid_historical_inputs(self):
  t=profile(4);floating=copy.deepcopy(t);floating['engine']['cylinders']=4.0
  a=run('ours','warm_start',1,250,tune=t);b=run('ours','warm_start',1,250,tune=floating)
  self.assertEqual(a,b)
  old=json.loads((ROOT/'config/engine/defaults-v2.json').read_text());old['schema_version']=1;old.pop('timing')
  from engine_runtime import EngineRuntime
  runtime=EngineRuntime(old)
  try:canonical=copy.deepcopy(runtime.tune)
  finally:runtime.close()
  self.assertEqual(run('ours','warm_start',1,250,tune=old),run('ours','warm_start',1,250,tune=canonical))
 def test_supplied_air_geometry_is_inferred_and_explicit_mismatches_reject(self):
  g=EngineGeometry.from_tune(profile(8));air=AirPath(geometry=g)
  try:
   p=ResearchPlant(air_path=air);self.assertEqual(p.geometry,g);self.assertEqual(len(p.air_charge_mg),8)
   with self.assertRaises(ValueError):ResearchPlant(air_path=air,geometry=EngineGeometry())
  finally:air.close()
  from boost_research_plant import BoostResearchPlant
  with self.assertRaises(ValueError):BoostResearchPlant(geometry=g)
 def test_external_plant_all24_profiles_drive_free_shaft_and_close_ledgers(self):
  for n in range(1,9):
   for mode in ('batch_wasted','semi_sequential','sequential'):
    with self.subTest(cylinders=n,strategy=mode):
     r=run('ours','warm_start',4,250,tune=profile(n,mode),target_dispatcher=True);s=r['summary'];record(f'mvem-{n}-{mode}',r)
     self.assertGreater(s['final_rpm'],500);self.assertEqual(s['final_outputs_high'],0);self.assertFalse(s['physical_outputs_enabled']);self.assertFalse(s['protection_stops'])
     self.assertTrue(all(v>0 for v in s['cylinder_fuel_mg']));self.assertTrue(all(v>0 for v in s['cylinder_burned_mg']));self.assertTrue(all(v>0 for v in s['cylinder_shaft_j']))
     self.assertAlmostEqual(sum(s['cylinder_fuel_mg']),s['ledger']['fuel_in_mg'],delta=1e-7)
     for key,limit in (('fuel_residual_mg',1e-7),('chemical_residual_j',1e-5),('shaft_residual_j',1e-5),('air_residual_kg',1e-8),('air_energy_residual_j',.02)):
      self.assertLess(abs(s['ledger'][key]),limit,(n,mode,key,s['ledger']))
 def test_physical_geometry_is_held_fixed_under_wrong_order_and_offset(self):
  t=profile(8);g=EngineGeometry.from_tune(t);base=run('ours','warm_start',4,250,tune=t,target_dispatcher=True,plant_geometry=g);record('fixed-eight-correct',base)
  wrong=copy.deepcopy(t);wrong['timing']['firing_order']=[1,2,3,4,5,6,7,8]
  order=run('ours','warm_start',4,250,tune=wrong,target_dispatcher=True,plant_geometry=g);record('fixed-eight-wrong-order',order)
  self.assertEqual(base['summary']['plant_geometry'],order['summary']['plant_geometry']);self.assertGreater(order['summary']['max_spark_error_deg'],80)
  self.assertLess(order['summary']['ledger']['combustion_shaft_j'],base['summary']['ledger']['combustion_shaft_j']*.7)
  wrong=copy.deepcopy(t);wrong['settings']['tooth1_btdc_deg']=120
  offset=run('ours','warm_start',4,250,tune=wrong,target_dispatcher=True,plant_geometry=g);record('fixed-eight-wrong-reference',offset)
  self.assertEqual(base['summary']['plant_geometry'],offset['summary']['plant_geometry'])
  # This30-degree reference error exceeds the configured20-degree cam window.
  # No phase lock or spark is the required response, so zero recorded timing
  # error must not be mistaken for a successful timing measurement.
  self.assertIsNone(offset['summary']['first_sync_s']);self.assertEqual(offset['summary']['sparks'],0);self.assertEqual(offset['summary']['ledger']['combustion_shaft_j'],0)
 def test_extended_outputs_are_cut_on_sensor_fault_and_trigger_dropout(self):
  for scenario in ('sensor_short','trigger_dropout'):
   r=Simulation(profile(8),scenario,6).run();record('fault-eight-'+scenario,r)
   self.assertEqual(r['summary']['final_outputs_high'],0)
   self.assertTrue(any(v['fuel_cut'] for v in r['trace'] if 4.2<v['time']<4.6))
   self.assertTrue(any(e[1]==17 for e in r['edges']))
 def test_direct_log_contains_all8_proposals_and_full_masks(self):
  r=Simulation(profile(8),duration_s=3).run();lines=export_msl(r['trace'],'warm_start','sequential').splitlines()
  self.assertEqual(lines[0],'"ESP32ECU SIL 009"');names=lines[2].split('\t');units=lines[3].split('\t');self.assertEqual(len(names),245);self.assertEqual(len(names),len(units));self.assertEqual(len(set(names)),245)
  rows=[dict(zip(names,row.split('\t'))) for row in lines[4:]]
  for actual,source in zip(rows,r['trace']):
   s=source['engine_sample'];self.assertEqual(int(actual['CylinderCount']),8);self.assertEqual(int(actual['VirtualMask']),s['worker_observation']['virtual_high_mask'])
   for i in range(8):
    expected=s['cylinders']['proposals'][i]['pulse_ms'];text=actual[f'C{i+1}PW'];self.assertTrue(text=='NaN' if expected is None else math.isclose(float(text),expected,rel_tol=1e-8,abs_tol=1e-7))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args,rest=parser.parse_known_args()
 if args.output is not None:OUTPUT=args.output.resolve();OUTPUT.mkdir(parents=True,exist_ok=False)
 suite=unittest.main(argv=[__file__,*rest],exit=False,verbosity=2)
 if OUTPUT is not None:
  sources=['tools/test_engine_profile_plants.py','tools/engine_geometry.py','tools/engine_sil.py','tools/engine_research_plant.py','tools/compare_engine_controllers.py','tools/engine_log.py','simulation/modelica/EngineProfileAirPath.mo','simulation/modelica/EngineAirPath.mo','scripts/build_engine_airpath.py']
  manifests={name:json.loads((ROOT/path).read_text()) for name,path in (('profile_airpath','.cache/engine/modelica-mvem/airpath-profiles/manifest.json'),('legacy_airpath','.cache/engine/modelica-mvem/airpath/manifest.json'))}
  (OUTPUT/'summary.json').write_text(json.dumps(dict(passed=suite.result.wasSuccessful(),tests=suite.result.testsRun,failures=len(suite.result.failures),errors=len(suite.result.errors),results=RESULTS,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},plant_manifests=manifests,scope='Uncalibrated synthetic engines driven by executed native project controller/dispatcher edges; expanded Speeduino comparison remains open; no physical qualification'),indent=2)+'\n')
 raise SystemExit(not suite.result.wasSuccessful())
