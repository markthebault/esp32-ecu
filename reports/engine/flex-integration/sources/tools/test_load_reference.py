"""Pinned production-reference load profiles and external ambient causality."""
import copy,json,math,unittest
from pathlib import Path
from compare_engine_controllers import benchmark_tune
from speeduino_runtime import SpeeduinoRuntime,ROOT
from engine_research_plant import ResearchPlant

def profile(fuel,spark,pressure,afr):
 t=benchmark_tune();c=t['load_model'];sources=('map','tps','imap_emap');axes=('map_kpa','tps_pct','imap_emap_pct')
 c.update(fuel_source=sources[fuel],spark_source=sources[spark],pressure=pressure,afr=afr,ve_axis=axes[fuel],spark_axis=axes[spark],lambda_axis=axes[fuel],trim_axis=axes[fuel],aux_role='emap' if 2 in (fuel,spark) else 'postcat_monitor',fixed_baro_kpa=80)
 for name,code in (('ve',fuel),('spark',spark),('lambda',fuel)):
  if code==1:t['maps'][name]['load']=[0,1,2,3,4,5,7,10,15,20,30,40,55,70,85,100]
 if fuel==1:
  for m in t['cylinder_trims']['fuel_maps']:m['load']=[0,20,40,60,80,100]
 return t

@unittest.skipUnless(all((ROOT/p).exists() for p in ('.cache/engine/speeduino-sim/build-manifest.json','.cache/engine/speeduino-sim16/build-manifest.json')),'Build both pinned production references before these probes')
class LoadReferenceTests(unittest.TestCase):
 def test54_production_source_pressure_profiles_read_back_and_sample(self):
  for bits in (32,16):
   for fuel in range(3):
    for spark in range(3):
     for n,pressure in enumerate(('none','map_100kpa','map_baro')):
      r=SpeeduinoRuntime(timer_bits=bits)
      try:
       t=profile(fuel,spark,pressure,('off','target','measured')[n]);p=r.configure_load(t)
       self.assertEqual(len(p['raw_profile']),18);r.pressures(125,80)
       r.sensors(dict(map_kpa=60,tps_pct=12.5,clt_c=85,iat_c=25,battery_v=14,**{'lambda':1.1}));r.advance(1000);d=r.load_status()
       expected=(d['map_kpa'],d['tps_raw_half_pct']*2,int(d['map_kpa']*100/d['emap_kpa']) if d['emap_kpa'] else None)
       self.assertEqual(d['fuel_load'],expected[fuel]);self.assertEqual(d['spark_load'],expected[spark]);self.assertEqual(d['baro_kpa'],80)
       self.assertEqual(d['ve_pct'],85);self.assertEqual(r.advance(1250),[])
      finally:r.close()
 def test_bad_table_preparation_does_not_mutate_reference_then_valid_retry_works(self):
  r=SpeeduinoRuntime()
  try:
   bad=benchmark_tune();bad['maps']['ve']['load'][1]=bad['maps']['ve']['load'][0]+.01
   with self.assertRaises(ValueError):r.configure_load(bad)
   self.assertIsNone(r.load_profile);self.assertEqual(r.now,0);r.configure_load(benchmark_tune())
   with self.assertRaises(ValueError):r.configure_load(benchmark_tune())
  finally:r.close()
 def test_reference_lambda_follows_fuel_and_rejects_independent_active_source(self):
  r=SpeeduinoRuntime()
  try:
   t=benchmark_tune();t['load_model'].update(lambda_source='tps',lambda_axis='tps_pct');t['maps']['lambda']['load']=[i*100/15 for i in range(16)]
   with self.assertRaises(ValueError):r.configure_load(t)
   r.configure_load(benchmark_tune())
  finally:r.close()
 def test_virtual_emap_endpoint_headroom_produces_fresh_production_observations(self):
  for bits in (32,16):
   r=SpeeduinoRuntime(timer_bits=bits)
   try:
    r.configure_load(profile(2,2,'map_100kpa','target'))
    for n,pressure in enumerate((20,100,125,500,125)):
     r.pressures(pressure,100);r.advance((n+1)*1000);d=r.load_status()
     self.assertEqual(d['emap_kpa'],pressure);self.assertEqual(d['fuel_load'],int(d['map_kpa']*100/pressure))
   finally:r.close()

class AmbientPlantTests(unittest.TestCase):
 def test80kpa_changes_physical_inventory_and_conserves_motored_air_and_energy(self):
  plants=[]
  try:
   for ambient in (100,80):
    p=ResearchPlant(ambient_kpa=ambient);plants.append(p);self.assertEqual(p.air_state['map_kpa'],ambient)
    for i in range(4000):p.integrate(i*.00025,.00025,starter=True)
    ledger=p.ledger();self.assertLess(abs(ledger['air_residual_kg']),1e-8);self.assertLess(abs(ledger['air_energy_residual_j']),.05);self.assertEqual(ledger['fuel_in_mg'],0)
   self.assertAlmostEqual(plants[1].air.initial['inventory_kg']/plants[0].air.initial['inventory_kg'],.8)
   self.assertLess(plants[1].air_state['cylinder_air_kg_s'],plants[0].air_state['cylinder_air_kg_s'])
  finally:
   for p in plants:p.close()

if __name__=='__main__':unittest.main(verbosity=2)
