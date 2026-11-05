"""Main-engine boost integration, strict migrations and inhibited execution."""
import copy,csv,io,json,struct,tempfile,unittest
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from target_runtime import TargetRuntime
from engine_protocol import DEFAULT,pages,decode_pages,Session
from engine_msq import export_msq,import_msq,tag
from engine_observability import EngineRecorder
from boost_config import SCALAR_OFFSETS,TABLE_OFFSETS

def tune():
 t=copy.deepcopy(DEFAULT);t['engine']['injector_cc_min']=600;t['settings']['dfco_enabled']=False
 t['boost_control'].update(pressure_enabled=True,mode='open_loop');t['boost_control']['open_duty']['cells']=[40]*64
 return t

def sample(map_kpa=150,**extra):return dict(rpm=2000,map_kpa=map_kpa,tps_pct=50,synced=True,phase_synced=True,**extra)

def stage(session,t):
 body=pages(t)[1]
 for offset in range(0,len(body),256):
  chunk=body[offset:offset+256]
  assert session.command(b'M'+struct.pack('<BBHH',0,1,offset,len(chunk))+chunk)==b'\0'

class BoostTests(unittest.TestCase):
 def test_all_strategies_pressure_cut_recovery_and_coherent_map(self):
  for strategy in ('batch_wasted_4cyl','semi_sequential_4cyl','sequential_4cyl'):
   t=tune();t['strategy']=strategy;r=EngineRuntime(t);rec=EngineRecorder()
   try:
    out=r.step(sample(),0,use_decoder=False);self.assertEqual(out['faults'],0);self.assertGreater(out['pulse_ms'],0);self.assertEqual(out['boost_control']['duty_pct'],0)
    for now in range(5000,405000,5000):out=r.step(sample(),now,use_decoder=False)
    data=r.data();self.assertEqual(data['schema_version'],2);self.assertEqual(data['inputs']['map_kpa'],150);self.assertEqual(data['boost_control']['duty_pct'],40)
    self.assertTrue(rec.bridge.data_validate(json.dumps(data).encode()))
    out=r.step(sample(230),405000,use_decoder=False);self.assertTrue(out['faults']&512);self.assertTrue(out['fuel_cut'] and out['spark_cut']);self.assertEqual(out['boost_control']['duty_pct'],0)
    for now in range(410000,660000,5000):self.assertTrue(r.step(sample(200),now,use_decoder=False)['faults']&512)
    self.assertEqual(r.step(sample(200),660000,use_decoder=False)['faults'],0)
    out=r.step(sample(450,sensors_valid=False),665000,use_decoder=False);self.assertTrue(out['faults']&512);self.assertTrue(out['faults']&4)
    self.assertEqual(out['load_model']['reason'],'known_map_above_configured_pressure_limit')
   finally:r.close();rec.close()

 def test_all_retained_json_migrates_neutral_without_changing_source(self):
  for source in sorted((R/'config/engine').glob('defaults-v*.json')):
   body=source.read_bytes();old=json.loads(body);r=EngineRuntime(old)
   try:
    self.assertEqual(source.read_bytes(),body);self.assertEqual(r.tune['schema_version'],10)
    self.assertFalse(r.tune['boost_control']['pressure_enabled']);self.assertEqual(r.tune['boost_control']['mode'],'off')
    self.assertEqual(r.tune['maps'],old['maps']);self.assertEqual(r.tune['revision'],old['revision'])
   finally:r.close()

 def test_strict_schema_and_pressure_configuration(self):
  for change in (lambda t:t.pop('boost_control'),lambda t:t['boost_control'].update(mode='closed_loop',pressure_enabled=False),lambda t:t['boost_control'].update(cut_kpa=310),lambda t:t['boost_control']['target']['cells'].__setitem__(3,215),lambda t:t['boost_control']['open_duty']['rpm'].__setitem__(3,1500)):
   t=copy.deepcopy(DEFAULT);change(t)
   with self.assertRaises(ValueError):EngineRuntime(t)
  t=json.loads((R/'config/engine/defaults-v9.json').read_text());t['boost_control']=copy.deepcopy(DEFAULT['boost_control'])
  with self.assertRaises(ValueError):EngineRuntime(t)

 def test_binary_msq_and_historical_prefix(self):
  import engine_protocol_v10 as previous
  self.assertEqual(pages(DEFAULT)[1][:8192],previous.pages(DEFAULT)[1])
  t=tune();t['boost_control']['open_duty']['cells']=[(i*7)%91 for i in range(64)];t['boost_control']['target']['cells']=[140+(i%9)*.25 for i in range(64)]
  t['boost_control']['feedforward']['cells']=[(i*11)%93 for i in range(64)];t['maps']['ve']['load'][-1]=250
  r=EngineRuntime(t)
  try:
   binary=pages(r.tune);self.assertEqual(len(binary[1]),12288);decoded=decode_pages(binary,r.tune)
   self.assertEqual(pages(decoded),binary);self.assertEqual(import_msq(export_msq(r.tune)),r.tune)
   with self.assertRaises(ValueError):previous.pages(r.tune)
   # An old layout import gets a neutral new feature, even if its caller has a boosted tune.
   migrated=previous.decode_pages(previous.pages(DEFAULT),r.tune);self.assertFalse(migrated['boost_control']['pressure_enabled'])
   bad=copy.deepcopy(binary);bad[1][8280]=1
   with self.assertRaises(ValueError):decode_pages(bad,r.tune)
  finally:r.close()

 def test_whole_page_burn_is_atomic_and_rejects_stale_writer(self):
  with tempfile.TemporaryDirectory() as directory:
   store=EngineStore(Path(directory)/'engine.json');a=Session(store);b=Session(store)
   try:
    desired=tune();stage(a,desired)
    self.assertFalse(store.path.exists());self.assertEqual(store.tune['boost_control']['mode'],'off')
    # Reject a bad float in a disabled or enabled feature before any file write.
    self.assertEqual(a.command(b'M'+struct.pack('<BBHH',0,1,SCALAR_OFFSETS['frequency_hz'],4)+struct.pack('<f',51)),b'\0')
    self.assertEqual(a.command(b'b\0\1'),b'\x84');self.assertFalse(store.path.exists())
    stage(b,DEFAULT);stage(a,desired);self.assertEqual(a.command(b'b\0\1'),b'\x04');self.assertEqual(store.tune['revision'],2);saved=store.path.read_bytes()
    self.assertTrue(store.tune['boost_control']['pressure_enabled']);self.assertEqual(store.tune['boost_control']['open_duty']['cells'][17],40)
    self.assertEqual(b.command(b'b\0\1'),b'\x84');self.assertEqual(store.path.read_bytes(),saved)
    reloaded=EngineStore(store.path);self.assertTrue(reloaded.storage_ok);self.assertEqual(reloaded.tune,store.tune)
   finally:a.close();b.close()

 def test_old_msq_cannot_inherit_an_active_boost_configuration(self):
  import xml.etree.ElementTree as ET
  root=ET.fromstring(export_msq(tune()));root.find(tag('versionInfo')).set('signature','ESP32ECU DEV 010 INHIBITED')
  for page in root.findall(tag('page')):
   page.set('size','8192')
   for constant in list(page):
    if constant.get('name','').startswith('boost_'):page.remove(constant)
  imported=import_msq(ET.tostring(root));self.assertFalse(imported['boost_control']['pressure_enabled']);self.assertEqual(imported['boost_control']['mode'],'off')

 def test_pid_saturation_logs_preserve_demand_and_u64_counts(self):
  t=tune();t['boost_control'].update(mode='closed_loop',kp=10,cut_kpa=250)
  for pressure,demand in ((100,500),(220,-700)):
   r=EngineRuntime(t);rec=EngineRecorder()
   try:
    out=r.step(sample(pressure),0,use_decoder=False);self.assertEqual(out['faults'],0);data=r.data()
    self.assertEqual(data['boost_control']['demand_pct'],demand);data['boost_control']['pid_updates']=str(2**53+123)
    self.assertTrue(rec.bridge.data_validate(json.dumps(data).encode()));self.assertEqual(rec.command(dict(action='start',period_ms=20,duration_s=1),0),200);self.assertTrue(rec.append(data,0));rec.command(dict(action='stop',log_id=1),1000)
    rows=list(csv.reader(io.StringIO(rec.msl(1)),delimiter='\t'));self.assertEqual([len(row) for row in rows[2:]],[245,245,245]);row=dict(zip(rows[2],rows[4]));self.assertEqual(float(row['BoostDemand']),demand);self.assertEqual(row['BoostPidUpdates'],str(2**53+123));self.assertIn('ENGINE LOG 008',rows[0][0])
   finally:r.close();rec.close()

 def test_target_dispatcher_executes_valve_edges_and_cuts_immediately(self):
  t=tune();t['boost_control']['slew_pct_s']=2000;r=TargetRuntime(t);edges=[]
  def drain(until):
   while r.next_event_us()<=until:
    when=r.next_event_us();event=r.pop_event()
    if event and event[0]==9:edges.append((when,event[1]))
  try:
   for now in range(0,82000,1000):
    drain(now);r.step(sample(),now,use_decoder=False);drain(now)
   self.assertEqual([x[0] for x in edges if x[1]],[1000,41000,81000]);self.assertTrue(r.boost_status()['virtual_high']);self.assertFalse(r.boost_status()['physical_policy_enabled']);self.assertFalse(r.boost_status()['physical_command_high'])
   out=r.step(sample(230),81500,use_decoder=False);drain(81500);self.assertTrue(out['faults']&512);self.assertEqual(edges[-1],(81500,False));self.assertFalse(r.boost_status()['active'])
  finally:r.close()

 def test_producer_timeout_cannot_be_rescued_by_a_fresh_running_command(self):
  r=TargetRuntime(tune())
  try:
   r.step(sample(),0,use_decoder=False);r.step(sample(),1000,use_decoder=False);self.assertTrue(r.boost_status()['active']);r.progress(6001);self.assertFalse(r.boost_status()['active']);self.assertFalse(r.boost_status()['virtual_high'])
   r.step(sample(),7000,use_decoder=False);self.assertFalse(r.boost_status()['active']);self.assertEqual(r.timing_reason(),'producer_timeout')
  finally:r.close()

 def test_historical_screen_formats_suppress_unrepresentable_pressure_profiles(self):
  r=EngineRuntime(tune());rec=EngineRecorder();key=bytes(range(16));nonce=bytes(range(16,32))
  try:
   r.step(sample(),0,use_decoder=False);data=r.data()
   for schema in (1,2,3,4):
    with self.assertRaises(ValueError):rec.frame(data,key,nonce,1,1,schema=schema)
   with self.assertRaises(ValueError):rec.frame_pair(data,key,nonce,1,1)
  finally:r.close();rec.close()

if __name__=='__main__':unittest.main()
