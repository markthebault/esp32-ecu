"""Pinned-source adapter and independent thermodynamic component identities."""
import math,random,unittest
from tcsi_mdl import parse,verify_archive
from tcsi_graph import Model,Unsupported,expression

class SourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.model=Model()
 def graph(self,suffix):
  paths=[p for p in self.model.systems if p[-1]==suffix]
  self.assertEqual(len(paths),1);return self.model.graph(paths[0])
 def test_pinned_source_and_complete_structural_inventory(self):
  source=verify_archive();self.assertEqual(source['commit'],'66a972d6c7206d258deb0c21b4cd6aded8a827e2');self.assertEqual(set(source['files']),{'Engine.mdl','EngineData.m','RunEngine.m'})
  self.assertEqual(len(self.model.systems),63)
 def test_quoted_layout_comments_repeated_cells_and_strict_structure(self):
  tree=parse('Model {\n Name "a\\n"\n "b"\n # ignored {\n Array {\n Cell "1"\n Cell "2"\n }\n}\n')
  self.assertEqual(tree.one('Model').get('Name'),'a\nb');self.assertEqual(tree.one('Model').one('Array').properties['Cell'],['1','2'])
  with self.assertRaises(ValueError):tree.one('Model').one('Array').get('Cell')
  for text in ('Model {\n','}\n','Model {\n Value [1 2\n}\n','Model {\n Value "a" 1\n}\n'):
   with self.assertRaises(ValueError):parse(text)
 def test_expression_allowlist_and_exact_mask_scope(self):
  self.assertEqual(expression('u(2)^u(1)',{},(2,3)),9)
  self.assertEqual(expression('TC_ENGINE.compressor.D*2',self.model.parameters),.12)
  for text in ("__import__('os').system('false')",'open("x")','(lambda:1)()','[x for x in [1]]','u(0)','u(-1)'):
   with self.assertRaises((Unsupported,ValueError)):expression(text,{},(1,2))
  compressor=self.graph('Compressor\nTorque');turbine=self.graph('Turbine\nTorque')
  self.assertEqual(compressor.env['c_p'],1100);self.assertEqual(turbine.env['c_p'],1200)
  self.assertEqual(self.model.defaults['Constant'].get('Value'),'1');self.assertEqual(self.model.defaults['Product'].get('Inputs'),'2')
 def test_source_compressor_fields_and_power_mismatch_are_preserved(self):
  graph=self.graph('Compressor');flow,temp,torque=graph.run((101300,298,20000,350,180000)).values()
  self.assertAlmostEqual(flow,.07524840728545303,14);self.assertAlmostEqual(temp,392.0242162564089,11)
  self.assertAlmostEqual(torque*20000,flow*1100*(temp-298),10)
  gas_cp=self.model.parameters['TC_ENGINE.gasProp.air.cp']
  self.assertAlmostEqual(torque*20000/(flow*gas_cp*(temp-298)),1100/1005.2,13)
  self.assertGreater(abs(torque*20000-flow*gas_cp*(temp-298)),600)
 def test_turbine_units_and_wastegate_parallel_flow(self):
  turbine=self.graph('Turbine1');torque,temp,flow=turbine.run((20000,101300,200000,900)).values()
  self.assertAlmostEqual(flow,.08881722003613202,14);self.assertAlmostEqual(torque*20000,flow*1200*(900-temp),10)
  mix=self.graph('Turbine and\nwastegate');closed=mix.run((101300,298,20000,0,200000,900));opened=mix.run((101300,298,20000,1,200000,900))
  self.assertAlmostEqual(-closed[2],flow,14);self.assertGreater(-opened[2],flow);self.assertGreater(opened[1],closed[1]);self.assertEqual(opened[3],closed[3])
 def test_actual_control_volume_derivatives_close_mass_and_energy(self):
  rng=random.Random(5391);graph=self.graph('Intake Manifold\nControl Volume');r=graph.env['R'];gamma=graph.env['gamma'];volume=graph.env['V'];cv=r/(gamma-1);cp=cv+r
  for _ in range(150):
   mass=rng.uniform(.001,.004);temp=rng.uniform(290,450);up=rng.uniform(0,.1);down=rng.uniform(0,.1);t_up=rng.uniform(290,550);heat=rng.uniform(-200,200)
   states={'Receiver\nMass':mass,'Receiver\nTemperature':temp};out,derivative=graph.run((up,t_up,heat,temp,down),states,True)
   dm=derivative['Receiver\nMass'];dt=derivative['Receiver\nTemperature']
   self.assertEqual(out[1],temp);self.assertAlmostEqual(out[2],mass*r*temp/volume,8);self.assertAlmostEqual(dm,up-down,13)
   self.assertAlmostEqual(cv*(mass*dt+temp*dm),cp*(up*t_up-down*temp)+heat,8)
 def test_runtime_boundaries_and_singular_source_domain_are_explicit(self):
  graph=self.graph('Compressor')
  for values in ((101300,298,20000,350), (101300,298,20000,350,180000,1)):
   with self.assertRaises(Unsupported):graph.run(values)
  with self.assertRaises((ZeroDivisionError,ValueError)):graph.run((101300,298,0,350,180000))
  cv=self.graph('Intake Manifold\nControl Volume')
  with self.assertRaises(Unsupported):cv.run((.01,300,0,300,.01))
  with self.assertRaises(Unsupported):cv.run((.01,300,0,300,.01),{'Receiver\nMass':.002})
 def test_external_fault_program_is_declared_and_time_based(self):
  p=next(p for p in self.model.systems if p[-1]=='Engine flow')
  healthy=Model(parameter_inputs={'toggle_vol':0}).graph(p);faulty=Model(parameter_inputs={'toggle_vol':1}).graph(p)
  values=(150000,310,200,180000)
  self.assertEqual(healthy.run(values,time_s=1),faulty.run(values,time_s=1))
  # The source subtracts0.08 from the masked C/(r_c-1) coefficient, rather
  # than changing the EngineData airMassFlowGain field or adding8percent.
  coefficient=healthy.env['C']/(healthy.env['r_c']-1)
  self.assertAlmostEqual(faulty.run(values,time_s=31)[1],healthy.run(values,time_s=31)[1]*(coefficient-.08)/coefficient,13)
  with self.assertRaises(Unsupported):healthy.run(values)
  for config in ({'toggle_vol':True},{'toggle_vol':2},{'TC_ENGINE.compressor.D':.1},{'unknown':0}):
   with self.assertRaises(Unsupported):Model(parameter_inputs=config)

class ConservativeComponents(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from turbo_components import TurboComponents
  cls.original=TurboComponents('source');cls.current=TurboComponents()
 def test_map_flow_and_temperature_preserved_in_original_speed_domain(self):
  for omega in (2000,4000,10000,20000,24000):
   for pressure in (110000,140000,180000,250000):
    a=self.original.compressor(101300,298,omega,pressure);b=self.current.compressor(101300,298,omega,pressure)
    self.assertEqual(a['mass_kg_s'],b['mass_kg_s']);self.assertEqual(a['temperature_k'],b['temperature_k']);self.assertAlmostEqual(b['power_residual_w'],0,9)
    a=self.original.turbine(pressure,900,omega,101300);b=self.current.turbine(pressure,900,omega,101300)
    self.assertEqual(a['mass_kg_s'],b['mass_kg_s']);self.assertAlmostEqual(a['temperature_k'],b['temperature_k'],11);self.assertAlmostEqual(b['power_residual_w'],0,8)
 def test_zero_speed_has_finite_stall_torque_and_zero_extracted_power(self):
  rotor=self.current.turbine(200000,900,0,101300)
  self.assertTrue(math.isfinite(rotor['torque_nm']));self.assertGreater(rotor['torque_nm'],0);self.assertEqual(rotor['shaft_w'],0);self.assertEqual(rotor['temperature_k'],900)
  self.assertLess(self.current.turbine(200000,900,10,101300)['shaft_w'],self.current.turbine(200000,900,1000,101300)['shaft_w'])
  with self.assertRaises(ValueError):self.original.turbine(200000,900,0,101300)
 def test_passive_stationary_airflow_has_no_compressor_work_or_boost(self):
  c=self.current.compressor(101300,298,0,90000);self.assertGreater(c['mass_kg_s'],0);self.assertEqual(c['shaft_w'],0);self.assertEqual(c['temperature_k'],298)
  c=self.current.compressor(101300,298,0,150000);self.assertEqual(c['mass_kg_s'],0);self.assertEqual(c['shaft_w'],0)
 def test_zero_pressure_ratio_produces_no_turbine_energy(self):
  for omega in (0,1000,2000,20000):
   c=self.current.turbine(101300,298,omega,101300);self.assertEqual(c['mass_kg_s'],0);self.assertEqual(c['shaft_w'],0);self.assertEqual(c['torque_nm'],0)
 def test_declared_hypotheses_and_source_power_residual_are_visible(self):
  self.assertEqual(len(self.current.provenance['differences']),5);self.assertEqual(self.original.provenance['differences'],[])
  self.assertNotEqual(self.original.compressor(101300,298,20000,180000)['power_residual_w'],0)
  self.assertNotEqual(self.original.turbine(200000,900,20000,101300)['power_residual_w'],0)

if __name__=='__main__':unittest.main(verbosity=2)
