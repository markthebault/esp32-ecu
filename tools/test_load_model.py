"""Load-model boundaries through real native control, storage, tuning and logs."""
import copy,csv,io,json,math,struct,tempfile,unittest
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from engine_msq import export_msq,import_msq
from engine_protocol import Session,pages,decode_pages,envelope,LIVE_BYTES
from engine_observability import EngineRecorder,encoded
from engine_log import export_msl
from load_config import ENUM_OFFSETS,SCALAR_OFFSETS,USED_END

def tune():return json.loads((R/'config/engine/defaults.json').read_text())
def alpha():
 t=tune();c=t['load_model'];c.update(fuel_source='tps',spark_source='tps',pressure='none')
 for name in ('ve_axis','spark_axis','lambda_axis','trim_axis'):c[name]='tps_pct'
 for m in list(t['maps'].values())+t['cylinder_trims']['fuel_maps']:m['load']=[100*i/(len(m['load'])-1) for i in range(len(m['load']))]
 return t
def request(command,offset=0,body=None,count=4):return command+struct.pack('<BBHH',0,1,offset,len(body) if body is not None else count)+(body or b'')
def stage(s,t):
 body=pages(t)[1]
 for i in range(0,len(body),256):assert s.command(request(b'M',i,body[i:i+256]))==b'\0'

class LoadModelTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
 def runtime(self,t=None):
  r=EngineRuntime(t);self.addCleanup(r.close);return r
 def recorder(self):
  r=EngineRecorder();self.addCleanup(r.close);return r
 def sample(self,t=None,**inputs):
  r=self.runtime(t);r.step(dict(rpm=1200,map_kpa=45,tps_pct=10,synced=True,**inputs),1000000,use_decoder=False);return r.data()
 def test_json_and_msq_legacy_bounds_and_migration_preserve_f32_semantics(self):
  for schema in range(1,7):
   path=R/'config/engine'/('defaults-v1.json' if schema==1 else f'defaults-v{schema}.json')
   if not path.exists():continue
   old=json.loads(path.read_text());r=self.runtime(old)
   self.assertEqual(r.tune['schema_version'],9);self.assertEqual(r.tune['load_model'],tune()['load_model'])
   for value,allowed in ((0,False),(19.9999999,True),(120.000001,True),(120.001,False)):
    bad=copy.deepcopy(old);bad['maps']['ve']['cells'][0]=value
    if allowed:self.runtime(bad)
    else:
     with self.assertRaises(ValueError):self.runtime(bad)
  for path in (R/'tuning/examples').glob('*.msq'):
   if any(identity in path.read_bytes() for identity in (b'ESP32ECU DEV 008 INHIBITED',b'ESP32ECU DEV 009 INHIBITED')):continue
   result=import_msq(path.read_bytes());self.assertEqual(result['schema_version'],9);self.assertEqual(result['load_model'],tune()['load_model'])
 def test_independent_source_and_unit_metadata_reject_without_reinterpreting(self):
  t=tune();t['load_model']['fuel_source']='tps'
  with self.assertRaises(ValueError):self.runtime(t)
  t=alpha();t['maps']['ve']['cells']=[0]*256;self.assertEqual(pages(import_msq(export_msq(t))),pages(self.runtime(t).tune))
 def test_real_native_optional_map_stays_unknown_and_bad_j16_unqualifies(self):
  r=self.runtime(alpha());o=r.step(dict(rpm=1200,map_kpa=None,map_qualified=False,tps_pct=10,synced=True),1000000,use_decoder=False)
  d=r.data();self.assertEqual(o['faults'],0);self.assertIsNone(d['inputs']['map_kpa']);self.assertFalse(d['input_valid_mask']&2)
  self.assertEqual(d['load_model']['fuel_load'],10);self.assertFalse(d['load_model']['flags']&256)
  t=tune();t['load_model'].update(pressure='map_baro',aux_role='baro',baro_source='aux');r=self.runtime(t)
  r.step(dict(rpm=1200,synced=True,aux_pressure_kpa=100,aux_pressure_qualified=False),1000000,use_decoder=False)
  d=r.data();self.assertFalse(d['flags']&16384);self.assertEqual(d['load_model']['reason'],'required_baro_unavailable')
 def test_whole_page_load_transition_requires_consistent_axes_and_persists(self):
  store=EngineStore(Path(self.directory.name)/'tune.json');self.addCleanup(lambda:store.runtime.close());self.addCleanup(store.data_recorder.close);s=Session(store);self.addCleanup(s.close)
  s.command(request(b'M',ENUM_OFFSETS['fuel_source'],struct.pack('<I',1)))
  self.assertEqual(s.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['load_model'],tune()['load_model'])
  stage(s,alpha());self.assertEqual(s.command(b'b\0\1'),b'\4');self.assertEqual(store.tune['revision'],2)
  self.assertEqual(store.tune['load_model']['fuel_source'],'tps');self.assertEqual(s.diagnostics()['origin_revision'],1)
  self.assertEqual(json.loads(store.path.read_text()),store.tune)
  self.assertEqual(pages(decode_pages({1:s.buffers[1]},dict(store.tune,revision=1)))[1],s.buffers[1])
 def test_reserved_tail_and_enum_failure_preserve_previous_publication(self):
  store=EngineStore(Path(self.directory.name)/'tune.json');self.addCleanup(lambda:store.runtime.close());self.addCleanup(store.data_recorder.close);s=Session(store);self.addCleanup(s.close)
  before=s.buffers[1]
  for offset in (5116,USED_END,5375):
   self.assertEqual(s.command(request(b'M',offset,b'\1')),b'\x84');self.assertEqual(s.buffers[1],before)
  for value in (3,4294967295):
   s.command(request(b'M',ENUM_OFFSETS['fuel_source'],struct.pack('<I',value)))
   self.assertEqual(s.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['revision'],1)
  stage(s,tune());s.command(request(b'M',SCALAR_OFFSETS['fixed_baro_kpa'],struct.pack('<f',float('nan'))))
  self.assertEqual(s.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['revision'],1)
 def test_single_atomic_live_read_640_bytes_framed_647(self):
  store=EngineStore(Path(self.directory.name)/'tune.json');self.addCleanup(lambda:store.runtime.close());self.addCleanup(store.data_recorder.close);s=Session(store);self.addCleanup(s.close)
  self.assertEqual(LIVE_BYTES,832);request=b'r'+struct.pack('<BBHH',0,0x30,0,832)
  response=s.command(request);self.assertEqual(len(response),833);self.assertEqual(len(envelope(response)),839)
  data=response[1:];self.assertEqual(struct.unpack_from('<I',data,356)[0],0);self.assertEqual(data[392:416],bytes(24))
 def test_model_json_fixture_rejects_null_mismatch_unknown_and_overflow(self):
  data=self.sample();rec=self.recorder();self.assertTrue(rec.bridge.data_validate(encoded(data)))
  for field,value in [('load_model',None),('load_model',{}),('load_model',[]),('load_model',{'available':False})]:
   bad=copy.deepcopy(data);bad[field]=value;self.assertFalse(rec.bridge.data_validate(encoded(bad)))
  for key,value in [('fuel_source_code',3),('fuel_source','tps'),('reason_code',9),('reason','invalid'),('afr_state_code',255),('afr_factor',None),('spark_load',3.5e38),('fuel_load','45'),('unexpected',0)]:
   bad=copy.deepcopy(data);bad['load_model'][key]=value;self.assertFalse(rec.bridge.data_validate(encoded(bad)),key)
  del data['load_model'];self.assertTrue(rec.bridge.data_validate(encoded(data)))
 def test_native_log_126_fields_and_sil_log_83_preserve_source_and_unknown(self):
  r=self.runtime(alpha());r.step(dict(rpm=1200,map_kpa=None,map_qualified=False,tps_pct=10,synced=True),1000000,use_decoder=False);d=r.data()
  rec=self.recorder();self.assertEqual(rec.command(dict(action='start',period_ms=20,duration_s=2),1000000),200);self.assertTrue(rec.append(d,1000000));rec.command(dict(action='stop',log_id=1),1000001)
  lines=list(csv.reader(io.StringIO(rec.msl(1)),delimiter='\t'));self.assertIn('LOG 007',lines[0][0]);self.assertEqual(len(lines[2]),229);self.assertEqual(len(lines[3]),229);self.assertEqual(len(lines[4]),229)
  row=dict(zip(lines[2],lines[4]));self.assertEqual(row['MAP'],'NaN');self.assertEqual(row['LoadFuelSource'],'1');self.assertEqual(row['LoadFuel'],'10');self.assertEqual(row['LoadBaro'],'NaN');self.assertEqual(row['LoadAvailable'],'1')
  text=export_msl([dict(time=0,engine_sample=d)],'boundary');sil=list(csv.reader(io.StringIO(text),delimiter='\t'));self.assertEqual(len(sil[2]),186);self.assertEqual(len(sil[4]),186);self.assertEqual(dict(zip(sil[2],sil[4]))['LoadFuelSource'],'1')
  # A maximum-width metadata header and F32 row must fit the target buffer.
  self.assertLess(len(lines[1][0])+len('\t'.join(lines[2]))+len('\t'.join(lines[3]))+12,6144)

if __name__=='__main__':unittest.main(verbosity=2)
