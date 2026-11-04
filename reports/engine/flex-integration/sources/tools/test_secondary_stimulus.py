"""Actual acquisition model: completion causality, fault delivery and core use."""
import copy,unittest
from compare_engine_controllers import benchmark_tune
from engine_runtime import EngineRuntime
from secondary_stimulus import ContactProgram,SecondaryMonitor,NEVER

def tune():
 t=benchmark_tune();t['transient_enrichment']['mode']='off'
 for kind in('fuel','spark'):t['secondary_tables'][kind].update(mode='input',debounce_ms=20)
 return t

class SecondaryStimulusTests(unittest.TestCase):
 def monitor(self,spec=None):
  m=SecondaryMonitor(tune(),spec);self.addCleanup(m.close);return m
 def cycle(self,m,begin):
  end=m.begin(begin)
  while m.next_event()!=NEVER:m.progress(m.next_event())
  s,values,completed=m.observe(end);m.consumed(s,completed,end);return end,s,values,completed
 def test_samples_exist_only_after_delayed_guard_completion(self):
  m=self.monitor({'initial':[True,False]})
  for now in range(0,20000,5000):self.cycle(m,now)
  end=m.begin(20000);self.assertEqual(end,21800)
  self.assertFalse(m.runtime.snapshot()['raw_known'])
  with self.assertRaises(ValueError):m.observe(20000)
  m.progress(20400);self.assertFalse(m.runtime.snapshot()['raw_known'])
  m.progress(21200);self.assertFalse(m.runtime.snapshot()['raw_known'])
  m.progress(21800);s,values,_=m.observe(end)
  self.assertTrue(s['ready']);self.assertEqual(s['observed_us'],'20000');self.assertEqual(s['read_completed_us'],'21800')
  self.assertTrue(values['table_switches'][0]['level']);self.assertFalse(values['table_switches'][1]['level']);self.assertEqual(s['samples'][0]['source_code'],2)
  end,held,_,_=self.cycle(m,25000);self.assertEqual(end,25300);self.assertEqual(held['observed_us'],'20000')
 def test_cannot_skip_device_stage_or_issue_a_second_operation(self):
  m=self.monitor();m.begin(0)
  with self.assertRaises(ValueError):m.begin(1)
  with self.assertRaises(ValueError):m.progress(401)
 def test_gpio_is_sampled_at_declared_mid_read_point(self):
  m=self.monitor({'initial':[False,False],'edges':[{'at_us':21199,'channel':0,'level':True},{'at_us':21201,'channel':0,'level':False}]})
  for now in range(0,25000,5000):_,s,_,_=self.cycle(m,now)
  self.assertTrue(s['samples'][0]['level']);self.assertEqual(m.program.levels(21800),[False,False])
 def test_actual_core_requires_fresh_observations_spanning_debounce(self):
  m=self.monitor({'initial':[True,False]});r=EngineRuntime(tune());self.addCleanup(r.close);qualified=[]
  for begin in range(0,50000,5000):
   end=m.begin(begin)
   while m.next_event()!=NEVER:m.progress(m.next_event())
   s,values,completed=m.observe(end);o=r.step(dict(rpm=1200,synced=True,**values),end,use_decoder=False);m.consumed(s,completed,end)
   if o['secondary_tables']['fuel']['input_qualified']:qualified.append(end)
  self.assertTrue(qualified);self.assertEqual(min(qualified),41800)
 def test_cranking_qualifies_guarded_spark_input_without_switching_angle(self):
  t=tune();t['secondary_tables']['fuel']['mode']='off';t['secondary_tables']['spark']['map']['cells']=[12]*256
  m=SecondaryMonitor(t,{'initial':[True,True]});self.addCleanup(m.close);r=EngineRuntime(t);self.addCleanup(r.close)
  outputs=[]
  for begin in range(0,80000,5000):
   end=m.begin(begin)
   while m.next_event()!=NEVER:m.progress(m.next_event())
   s,values,completed=m.observe(end);crank=end<50000
   o=r.step(dict(rpm=220 if crank else 600,synced=True,**values),end,use_decoder=False);m.consumed(s,completed,end);outputs.append((end,o))
   self.assertEqual(o['faults'],0)
   d=o['secondary_tables']['spark']
   if crank:
    self.assertEqual(o['advance_deg'],t['settings']['crank_advance_deg']);self.assertFalse(d['active']);self.assertEqual(d['reason'],'cranking_spark_bypass')
   else:self.assertEqual(o['advance_deg'],12);self.assertTrue(d['input_qualified']);self.assertTrue(d['active'])
  self.assertTrue(any(o['secondary_tables']['spark']['input_qualified']for end,o in outputs if end<50000))
 def test_fault_survives_recovery_while_core_observation_is_busy(self):
  spec={'initial':[True,True],'faults':[{'begin_us':50000,'end_us':70000,'kind':'nack'},{'begin_us':45000,'end_us':250000,'kind':'control_busy'}]};m=self.monitor(spec)
  pending=[];consumed=[]
  for begin in range(0,300000,5000):
   end,s,_,complete=self.cycle(m,begin)
   if s['fault_pending']:pending.append((end,s,complete))
   if m.history[-1]['fault_acknowledged']:consumed.append(end)
  self.assertTrue(m.applied_faults);self.assertTrue(pending)
  self.assertTrue(any(int(s['reads'])>3 and not s['ready']and not complete for _,s,complete in pending))
  self.assertEqual(min(consumed),250300)
  first_good=next(h for h in m.history if h['control_attempt_us']>min(consumed)and h['acquisition']['ready']);self.assertGreater(int(first_good['acquisition']['observed_us']),min(consumed))
 def test_low_challenge_mid_read_reset_is_not_a_healthy_sample(self):
  m=self.monitor({'faults':[{'begin_us':30000,'end_us':40000,'kind':'reset_before_guard'}]})
  for begin in range(0,35000,5000):_,s,_,_=self.cycle(m,begin)
  self.assertEqual(s['fault'],'configuration_mismatch');self.assertFalse(s['ready']);self.assertTrue(any(x['kind']=='reset_before_guard'for x in m.applied_faults))
 def test_program_rejects_ambiguous_or_forged_stimuli(self):
  for spec in ([],False,{'initial':[0,False]},{'edges':[{'at_us':0,'channel':True,'level':True}]},{'edges':[{'at_us':10,'channel':0,'level':True},{'at_us':10,'channel':0,'level':False}]},{'faults':[{'begin_us':0,'end_us':1,'kind':'unknown'}]},{'target_protected':True}):
   with self.subTest(spec=spec),self.assertRaises(ValueError):ContactProgram(spec)
  m=self.monitor();op=m.runtime.next(3,0)
  for token in('18446744073709551617','01','-1'):
   with self.assertRaises(ValueError):m.runtime.complete(dict(op,token=token),0,[0x28],0,400)
  self.assertTrue(m.runtime.complete(op,0,[0x28],0,400))

if __name__=='__main__':unittest.main()
