"""Actual production setup/loop secondary profiles and independent raw inputs."""
import copy,unittest
from compare_engine_controllers import benchmark_tune
from speeduino_runtime import SpeeduinoRuntime
from test_speeduino_runtime import constant_speed

def profile(mode='input',source='map'):
 t=benchmark_tune();t['transient_enrichment']['mode']='off'
 for kind in('fuel','spark'):
  r=t['secondary_tables'][kind];r.update(mode=mode,source=source,axis={'map':'map_kpa','tps':'tps_pct','imap_emap':'imap_emap_pct'}[source],cells='multiplier'if mode=='multiply'else'adder'if mode=='add'else'absolute',condition='tps_pct',threshold=10)
  r['map']['load']=[10+6*i for i in range(16)]if source=='map'else[0,2,4,6,8,10,12,16,20,24,30,40,50,65,80,100]if source=='tps'else[20*i for i in range(16)]
  r['map']['cells']=[150 if mode=='multiply'else 5 if kind=='fuel'and mode=='add'else 2 if mode=='add'else 100 if kind=='fuel'else 18]*256
 if source=='imap_emap':t['load_model']['aux_role']='emap'
 return t

class SecondaryReferenceTests(unittest.TestCase):
 def runtime(self,bits=32,channels=(0,1),sequential=False):
  r=SpeeduinoRuntime(timer_bits=bits,secondary_channels=channels,sequential=sequential);self.addCleanup(r.close);return r
 def configure(self,r,t):r.configure_load(t);return r.configure_secondary(t)
 def sensors(self,r,tps=12.5):r.pressures(125,100);r.sensors(dict(map_kpa=60,tps_pct=tps,clt_c=85,iat_c=25,battery_v=14,**{'lambda':1}))
 def test_all_modes_sources_have_exact_readbacks_and_native_selection(self):
  for bits in(32,16):
   for mode in('off','multiply','add','conditional','input'):
    for source in('map','tps','imap_emap'):
     with self.subTest(bits=bits,mode=mode,source=source):
      r=self.runtime(bits);t=profile(mode,source);p=self.configure(r,t);self.assertEqual(p['raw_profile'][-8:],[14,15,14,15,0,0,0,0]);self.sensors(r);r.contacts([True,True]);constant_speed(r,1000,300000);d=r.secondary_status()
      self.assertEqual(d['rpm'],1000);self.assertEqual(d['fuel_active'],int(mode!='off'));self.assertEqual(d['spark_active'],int(mode!='off'))
      self.assertEqual(d['combined_ve'],{'off':85,'multiply':128,'add':90,'conditional':100,'input':100}[mode]);self.assertEqual(d['combined_advance'],{'off':10,'multiply':15,'add':12,'conditional':18,'input':18}[mode])
      expected={'map':d['map_kpa'],'tps':d['tps_raw_half_pct']*2,'imap_emap':int(d['map_kpa']*100/d['emap_kpa'])if d['emap_kpa']else-1}[source]
      self.assertEqual(d['secondary_fuel_load'],expected);self.assertEqual(d['secondary_spark_load'],expected);r.close()
 def test_independent_shared_and_polarity_mapped_inputs(self):
  for channels in((0,1),(1,0),(0,0),(1,1)):
   r=self.runtime(channels=channels);t=profile();t['secondary_tables']['fuel']['input_channel']=channels[0];t['secondary_tables']['spark'].update(input_channel=channels[1],active_high=False);self.configure(r,t);self.sensors(r);constant_speed(r,1000,300000)
   for levels in((False,False),(True,False),(False,True),(True,True)):
    before=r.secondary_status();r.contacts(list(levels));held=r.secondary_status();self.assertEqual(held['loop_count'],before['loop_count']);self.assertEqual(held['fuel_active'],before['fuel_active'])
    r.advance(r.now+250);d=r.secondary_status();self.assertEqual(d['fuel_active'],int(levels[channels[0]]));self.assertEqual(d['spark_active'],int(not levels[channels[1]]))
   r.close()
 def test_preparation_failure_does_not_change_native_profile_and_retry_succeeds(self):
  r=self.runtime();initial=r._secondary_readback();base=profile();r.configure_load(base)
  bads=[]
  for kind,key,value in[('spark','mode','unknown'),('fuel','active_high',1),('fuel','input_channel',True),('fuel','threshold',True),('fuel','axis','tps_pct')]:
   t=copy.deepcopy(base);t['secondary_tables'][kind][key]=value;bads.append(t)
  t=profile('multiply');t['secondary_tables']['spark']['map']['cells'][0]=216;bads.append(t)
  t=copy.deepcopy(base);t['secondary_tables']['fuel']['map']['load'][1]=10.01;bads.append(t)
  t=profile('conditional');t['secondary_tables']['fuel']['condition']='ethanol_pct';bads.append(t)
  for t in bads:
   with self.assertRaises(ValueError):r.configure_secondary(t)
   self.assertIsNone(r.secondary_profile);self.assertEqual(r._secondary_readback(),initial);self.assertEqual(r.now,0)
  r.configure_secondary(base)
  with self.assertRaises(ValueError):r.configure_secondary(base)
 def test_fixture_cannot_run_until_both_tables_are_configured(self):
  r=self.runtime()
  with self.assertRaises(ValueError):r.advance(1)
  for channels in((True,0),(2,0),[],(0,),None):
   if channels is None:continue
   with self.assertRaises(ValueError):SpeeduinoRuntime(secondary_channels=channels)

if __name__=='__main__':unittest.main()
