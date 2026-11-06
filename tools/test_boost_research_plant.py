"""Complete plant exchanges, input atomicity and real gas-temperature sampling."""
import copy,unittest
from boost_research_plant import BoostResearchPlant

class CompletePlantTests(unittest.TestCase):
 def test_global_cut_and_individual_falls_have_identical_charged_coil_physics(self):
  # Authored identical component fixtures reproduce the independent3000us
  # counterexample. Free-engine fault runs separately establish reachability.
  plants=[]
  for _ in range(2):
   plant=BoostResearchPlant();self.addCleanup(plant.close);plant.rpm=1000;plant.angle=62
   plant.charge_mg[0]=10;plant.air_charge_mg[0]=147;plant.edge(4,True,0)
   for n in range(12):plant.integrate(n*.00025,.00025)
   plants.append(plant)
  cut,fall=plants;cut.cut();fall.edge(4,False,.003)
  self.assertEqual(cut.sparks,1);self.assertEqual(cut.burned_chemical_j,440)
  self.assertEqual(len(cut.cut_discharges),1);self.assertAlmostEqual(cut.cut_discharges[0]['dwell_us'],3000)
  cut.cut();self.assertEqual(cut.sparks,1)
  for n in range(20):
   for plant in plants:plant.integrate(.003+n*.00025,.00025)
  self.assertEqual(cut.air.state,fall.air.state);self.assertEqual(cut.rpm,fall.rpm)
  self.assertEqual(cut.heat_pulses,fall.heat_pulses);self.assertEqual(cut.combustions,fall.combustions)
  a=cut.ledger();b=fall.ledger();a.pop('global_cut_discharges');b.pop('global_cut_discharges');self.assertEqual(a,b)
 def test_stuck_open_gate_starts_without_a_rotor_floor(self):
  for dt in (.0005,.00025,.000125,.0000625):
   plant=BoostResearchPlant(actuator_mode='stuck_gate_open');self.addCleanup(plant.close)
   for n in range(round(.01/dt)):plant.integrate(n*dt,dt,starter=True)
   self.assertGreater(plant.rpm,0);self.assertGreaterEqual(plant.air.state[12],0)
   self.assertLess(plant.air.state[12],.01)
   self.assertEqual(plant.ledger()['burned_chemical_j'],0)
   self.assertLess(abs(plant.ledger()['coupled_energy_residual_j']),1e-8)
 def test_starter_without_fuel_has_no_combustion_heat(self):
  plant=BoostResearchPlant();self.addCleanup(plant.close)
  for n in range(40):plant.integrate(n*.00025,.00025,starter=True)
  ledger=plant.ledger();self.assertGreater(plant.rpm,0);self.assertEqual(ledger['burned_chemical_j'],0);self.assertEqual(ledger['exhaust_heat_delivered_j'],0)
  self.assertLess(abs(ledger['coupled_energy_residual_j']),1e-6);self.assertLess(abs(ledger['coupled_mass_residual_kg']),1e-12)
  self.assertAlmostEqual(plant.sample(.01)['iat_c'],plant.air_state['temperature_k']-273.15,13)
 def test_wrong_time_or_step_cannot_partially_advance_actuator(self):
  plant=BoostResearchPlant();self.addCleanup(plant.close);plant.edge(9,True,0);before=copy.deepcopy(plant.ledger());state=list(plant.air.state)
  for args in ((0,.002),(1,.00025),(0,-.1)):
   with self.assertRaises(ValueError):plant.integrate(*args,starter=True)
   self.assertEqual(plant.ledger(),before);self.assertEqual(plant.air.state,state);self.assertEqual(plant.air.time,0)
  plant.integrate(0,.00025,starter=True);self.assertGreater(plant.boost_valve.coil.current,0)
 def test_rk_candidate_failure_preserves_all_pending_exchanges(self):
  plant=BoostResearchPlant();self.addCleanup(plant.close);plant.edge(9,True,0)
  # Explicit inventory fixture for rollback testing, not combustion evidence.
  plant.heat_j=plant.heat_seen=1/plant.EXHAUST_HEAT_FRACTION;plant.wall_heat_j=plant.heat_j-1
  plant.heat_pulses=[dict(start=0,end=1,rate=1,remaining=1)];plant.pending_fuel_kg=1e-6;plant.pending_pumping_j=.01
  before=copy.deepcopy(plant.ledger());state=list(plant.air.state);original=plant.air.rates;calls=0
  def failure(*args):
   nonlocal calls
   calls+=1
   if calls==3:raise ValueError('Injected RK-stage failure')
   return original(*args)
  plant.air.rates=failure
  with self.assertRaisesRegex(ValueError,'Injected RK-stage'):plant.integrate(0,.00025,starter=True)
  self.assertEqual(plant.ledger(),before);self.assertEqual(plant.air.state,state);self.assertEqual(plant.air.time,0)
  del plant.air.__dict__['rates'];plant.integrate(0,.00025,starter=True);self.assertEqual(plant.air.time,.00025)

if __name__=='__main__':unittest.main(verbosity=2)
