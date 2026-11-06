"""Executed-edge solenoid, pneumatic failure and electrical-ledger checks."""
import unittest
from boost_valve_plant import BoostValve

def drive(valve,duty,seconds=2,charge=180):
 # Independent ideal20Hz edge source for component checks only. Full-engine
 # integration must supply its own actual controller/dispatcher edges.
 step=.00025;high=valve.coil.high
 for n in range(round(seconds/step)):
  desired=(n%200)<round(duty*200)
  if desired!=high:valve.edge(desired);high=desired
  valve.step(step,14,charge)
 return valve.snapshot()

class ValveTests(unittest.TestCase):
 def test_spring_pressure_and_direction(self):
  states=[drive(BoostValve(),v) for v in (0,.3,.6,1)]
  self.assertGreater(states[0]['wastegate_opening'],.99)
  self.assertLess(states[-1]['wastegate_opening'],.001)
  self.assertTrue(all(states[n]['actuator_kpa']>=states[n+1]['actuator_kpa'] for n in range(3)))
  self.assertEqual(drive(BoostValve(),0,charge=120)['wastegate_opening'],0)
 def test_electrical_energy_and_remaining_pressure_after_cut(self):
  valve=BoostValve();state=drive(valve,.6)
  self.assertLess(abs(state['coil']['electrical_residual_j']),1e-9);self.assertGreater(state['coil']['edges'],50)
  valve.edge(True)
  for _ in range(20):valve.step(.00025,14,180)
  valve.cut();current=valve.coil.current
  self.assertLess(valve.opening,.1)
  for _ in range(2000):valve.step(.00025,14,180)
  state=valve.snapshot();self.assertGreater(current,0);self.assertEqual(valve.coil.current,0);self.assertGreater(state['wastegate_opening'],.99)
  self.assertLess(abs(state['coil']['electrical_residual_j']),1e-9)
 def test_faults_have_distinct_physical_effects(self):
  disconnected=drive(BoostValve('disconnected'),1);leak=drive(BoostValve('hose_leak'),0)
  self.assertGreater(disconnected['wastegate_opening'],.99);self.assertEqual(disconnected['coil']['current_a'],0)
  self.assertLess(leak['wastegate_opening'],.001)
  self.assertEqual(drive(BoostValve('stuck_gate_open'),1)['wastegate_opening'],1)
  self.assertEqual(drive(BoostValve('stuck_gate_closed'),0)['wastegate_opening'],0)
  self.assertLess(drive(BoostValve('inverted_drive'),0)['wastegate_opening'],.001)
 def test_no_duty_api_or_malformed_drive(self):
  valve=BoostValve()
  with self.assertRaises(ValueError):valve.edge(False)
  with self.assertRaises(ValueError):valve.edge(1)
  for pressure in (0,float('nan'),501):
   with self.assertRaises(ValueError):valve.step(.001,14,pressure)

if __name__=='__main__':unittest.main(verbosity=2)
