"""Conservation/convergence of the component composition, without an ECU."""
import unittest
from turbo_gas_path import TurboGasPath

def component_run(step=.00025,profile='conservative',initial_speed=0,heat=2000,engine=30,duration=.025):
 plant=TurboGasPath(profile=profile,initial_turbo_rad_s=initial_speed);plant.sources(.3,heat_w=heat)
 for n in range(round(duration/step)):plant.step(n*step,step,engine,10)
 return plant.read(),plant.ledger()

class GasPathTests(unittest.TestCase):
 def test_no_external_energy_has_no_invented_hot_exhaust_or_rotation(self):
  state,ledger=component_run(heat=0,engine=0)
  self.assertEqual(state['turbo_rad_s'],0);self.assertAlmostEqual(state['map_kpa'],100,11)
  self.assertAlmostEqual(state['exhaust_kpa'],100,11);self.assertEqual(ledger['energy_residual_j'],0)
 def test_communication_step_refinement_closes_balances(self):
  rows=[component_run(step) for step in (.0005,.00025,.000125)]
  for state,ledger in rows:
   self.assertGreater(state['turbo_rad_s'],0);self.assertLess(abs(ledger['mass_residual_kg']),1e-12)
   self.assertLess(abs(ledger['energy_residual_j']),1e-8)
  # Internal-energy coordinates can reach the floating-point accumulation
  # floor. A refinement ratio below that floor has no useful meaning.
  self.assertLess(abs(rows[-1][1]['energy_residual_j']),max(abs(rows[0][1]['energy_residual_j'])/8,1e-9))
  self.assertLess(abs(rows[-1][0]['map_kpa']-rows[-2][0]['map_kpa']),.001)
 def test_raw_coefficient_defect_is_detected_in_system_ledger(self):
  corrected=component_run(initial_speed=20000,heat=0,engine=0,duration=.01)
  raw=component_run(profile='source',initial_speed=20000,heat=0,engine=0,duration=.01)
  self.assertGreater(abs(raw[1]['source_power_defect']),.001)
  self.assertGreater(abs(raw[1]['energy_residual_j']),100*max(abs(corrected[1]['energy_residual_j']),1e-9))
  self.assertAlmostEqual(raw[1]['energy_residual_j'],raw[1]['source_power_defect'],3)
 def test_initial_rotor_energy_and_zero_inflow_coast_are_accounted(self):
  plant=TurboGasPath(initial_turbo_rad_s=3000);self.assertEqual(plant.ledger()['rotor_kinetic_j'],135)
  for n in range(100):plant.step(n*.00025,.00025,0,0)
  ledger=plant.ledger();self.assertLess(ledger['rotor_kinetic_j'],135);self.assertGreater(ledger['bearing'],0)
  self.assertEqual(ledger['heat'],0);self.assertLess(abs(ledger['energy_residual_j']),.001)
 def test_invalid_step_does_not_publish_candidate(self):
  plant=TurboGasPath();before=list(plant.state)
  for args in ((1,.00025,0,0),(0,.01,0,0),(0,.00025,-1,0),(0,.00025,0,101)):
   with self.assertRaises(ValueError):plant.step(*args)
   self.assertEqual(plant.state,before);self.assertEqual(plant.time,0)

if __name__=='__main__':unittest.main(verbosity=2)
