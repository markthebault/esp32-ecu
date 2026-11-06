"""Shared target/native tuning core through real callbacks and atomic file store."""
import copy,json,struct,tempfile,unittest,zlib
from pathlib import Path
from unittest import mock
from engine_runtime import EngineStore,R
from engine_protocol import Session,Stream,pages,decode_pages,envelope,SIGNATURE,LIVE_BYTES
from tuning_runtime import status


def request(command,offset=0,data=None,count=4):
 return command+struct.pack('<BBHH',0,1,offset,len(data) if data is not None else count)+(data or b'')

def stage(session,tune):
 body=pages(tune)[1]
 for offset in range(0,len(body),256):
  chunk=body[offset:offset+256]
  assert session.command(request(b'M',offset,chunk))==b'\0'

class TuningTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
  self.path=Path(self.directory.name)/'tune.json';self.store=EngineStore(self.path)
 def session(self):
  s=Session(self.store);self.addCleanup(s.close);return s
 def test_current_msq_units_match_ini_storage_constants(self):
  from engine_msq import export_msq,tag
  import xml.etree.ElementTree as ET
  fields={e.get('name'):e.get('units') for e in ET.fromstring(export_msq(self.store.tune)).iter(tag('constant'))}
  import csv
  expected={}
  constants=(R/'tuning/esp32-ecu-profiles.ini').read_text().split('[Constants]',1)[1].split('\n[',1)[0]
  for line in constants.splitlines():
   if '=' not in line:continue
   name,definition=line.split('=',1);parts=next(csv.reader([definition],skipinitialspace=True))
   if parts[0] in ('scalar','array'):expected[name.strip()]=parts[3 if parts[0]=='scalar' else 4]
   elif parts[0]=='bits':expected[name.strip()]=''
  self.assertGreater(len(expected),200)
  dynamic=dict(secondary_fuel_threshold='RPM',secondary_spark_threshold='RPM',
   secondary_fuel_mapLoad='kPa',secondary_spark_mapLoad='kPa',
   secondary_fuel_mapTable='% coefficient',secondary_spark_mapTable='deg BTDC')
  self.assertEqual(set(fields),set(expected))
  for name,unit in expected.items():self.assertEqual(fields[name],dynamic[name] if unit.startswith('{') else unit,name)

 def test_actual_app_omits_readonly_origin_without_omitting_tune(self):
  from engine_msq import import_msq,SIGNATURE,LEGACY_SIGNATURE
  body=(R/'tuning/examples/tunerstudio-development-roundtrip.msq').read_text()
  self.assertNotIn('name="baseRevision"',body)
  tune=import_msq(body);self.assertEqual(tune['revision'],1);self.assertEqual(tune['cylinder_trims']['spark_deg'],[0,-2.5,0,0,0,0,0,0]);self.assertEqual(tune['cylinder_trims']['fuel_maps'][1]['cells'],[120]*36)
  self.assertEqual(import_msq(body,base_revision=17)['revision'],17)
  for revision in (True,0,4294967296,float('nan')):
   with self.assertRaises(ValueError):import_msq(body,base_revision=revision)
  with self.assertRaises(ValueError):import_msq(body.replace('name="c1SparkTrim"','name="unknown"'))
  old=(R/'tuning/examples/tunerstudio-roundtrip.msq').read_text()
  import re
  old=re.sub(r'<constant[^>]*name="baseRevision"[^>]*>.*?</constant>','',old,flags=re.S)
  with self.assertRaises(ValueError):import_msq(old)
 def test_native_golden_whole_tune_and_historical_layout(self):
  tune=copy.deepcopy(self.store.tune);tune['strategy']='sequential';tune['cylinder_trims']['enabled']=True
  tune['maps']['ve']['cells'][17]=93.25;tune['cylinder_trims']['fuel_maps'][1]['cells'][14]=117.25;tune['cylinder_trims']['spark_deg']=[-1,2,-3,4,0,0,0,0]
  self.assertEqual(self.store.save(json.dumps(tune).encode())[0],200)
  s=self.session();expected=pages(self.store.tune)[1]
  self.assertEqual(s.buffers[1],expected);self.assertEqual(pages(decode_pages({1:expected},self.store.tune))[1],expected)
  self.assertEqual(s.command(b'd\0\1'),b'\0'+struct.pack('>I',zlib.crc32(expected)))
 def test_successive_burns_keep_wire_origin_and_crc_stable(self):
  s=self.session()
  for rev,ve in [(2,86),(3,87),(4,88)]:
   self.assertEqual(s.command(request(b'M',640,struct.pack('<f',ve))),b'\0');crc=s.command(b'd\0\1');page=s.buffers[1]
   self.assertEqual(s.command(b'b\0\1'),b'\4');self.assertEqual(s.buffers[1],page);self.assertEqual(s.command(b'd\0\1'),crc)
   self.assertEqual(struct.unpack_from('<I',page,268)[0],1);self.assertEqual(self.store.tune['revision'],rev)
   self.assertEqual(s.command(b'b\0\1'),b'\4');self.assertEqual(self.store.tune['revision'],rev)
  self.assertEqual(EngineStore(self.path).tune['maps']['ve']['cells'][0],88)
 def test_two_native_writers_and_clean_burn_require_explicit_discovery(self):
  a,b=self.session(),self.session();a.command(request(b'M',640,struct.pack('<f',86)));self.assertEqual(a.command(b'b\0\1'),b'\4')
  self.assertEqual(b.command(b'b\0\1'),b'\x84');self.assertEqual(b.command(request(b'M',644,struct.pack('<f',87))),b'\x84')
  self.assertEqual(b.feed(b'\xf0F',100000),[b'002']);self.assertEqual(b.diagnostics()['origin_revision'],2)
  b.command(request(b'M',644,struct.pack('<f',87)));self.assertEqual(b.command(b'b\0\1'),b'\4');self.assertEqual(self.store.tune['revision'],3)
 def test_strategy_and_trim_disable_are_one_transaction(self):
  tune=copy.deepcopy(self.store.tune);tune['strategy']='sequential';tune['cylinder_trims']['enabled']=True;self.assertEqual(self.store.save(json.dumps(tune).encode())[0],200);s=self.session()
  s.command(request(b'M',272,bytes(4)));self.assertEqual(s.command(b'b\0\1'),b'\x84');self.assertEqual(self.store.tune['strategy'],'sequential')
  s.command(request(b'M',4752,bytes(4)));self.assertEqual(s.command(b'b\0\1'),b'\4');self.assertFalse(self.store.tune['cylinder_trims']['enabled']);self.assertEqual(self.store.tune['strategy'],'batch_wasted')
 def test_readonly_and_reserved_violations_reject_entire_chunk(self):
  s=self.session();original=s.buffers[1]
  for offset,body in [(268,struct.pack('<I',2)),(288,bytes([1,3,4,2,1])),(4752,bytes([1,0,0,0,1]))]:
   self.assertEqual(s.command(request(b'M',offset,body)),b'\x84');self.assertEqual(s.buffers[1],original);self.assertFalse(s.dirty)
 def test_preparation_memory_error_is_retryable_without_activation(self):
  s=self.session();s.command(request(b'M',640,struct.pack('<f',86)))
  with mock.patch('engine_runtime.EngineRuntime',side_effect=MemoryError):self.assertEqual(s.command(b'b\0\1'),b'\x85')
  self.assertEqual(self.store.tune['revision'],1);self.assertTrue(s.dirty);self.assertFalse(self.path.exists());self.assertEqual(s.command(b'b\0\1'),b'\4')
 def test_persistence_failure_is_permanent_until_store_recovery(self):
  self.store.save(json.dumps(self.store.tune).encode());before=self.path.read_bytes();s=self.session();s.command(request(b'M',640,struct.pack('<f',86)))
  with mock.patch('engine_runtime.os.replace',side_effect=OSError('injected storage failure')):self.assertEqual(s.command(b'b\0\1'),b'\x84')
  self.assertEqual(self.path.read_bytes(),before);self.assertEqual(self.store.tune['maps']['ve']['cells'][0],85);self.assertEqual(s.diagnostics()['state'],'storage_blocked');self.assertTrue(s.dirty)
  self.assertEqual(s.command(b'b\0\1'),b'\x84')
 def test_corruption_timeout_discovery_and_chunk_limits(self):
  stream=Stream(self.store);self.addCleanup(stream.close);frame=envelope(request(b'M',640,struct.pack('<f',86)))
  broken=frame[:-1]+bytes([frame[-1]^1]);self.assertEqual(stream.feed(broken,1000),[envelope(b'\x82')]);self.assertFalse(stream.session.dirty)
  self.assertEqual(stream.feed(frame[:5],2000),[]);self.assertEqual(stream.expire(27000),[envelope(b'\x80')]);self.assertFalse(stream.session.dirty)
  self.assertEqual(stream.feed(b'\xf0F',52000),[b'002']);self.assertEqual(stream.feed(frame,53000),[envelope(b'\0')]);self.assertTrue(stream.session.dirty)
  self.assertEqual(stream.feed(b'F',54000),[b'002']);self.assertTrue(stream.session.dirty)
  self.assertEqual(stream.feed(b'F',79000),[b'002']);self.assertFalse(stream.session.dirty)
  self.assertEqual(stream.session.command(request(b'p',512,count=257)),b'\x84')
  self.assertEqual(stream.session.command(b''),b'\x83')
 def test_live_metadata_clears_old_sample_and_preserves_session_origin(self):
  s=self.session();empty=s.command(b'r'+struct.pack('<BBHH',0,0x30,0,LIVE_BYTES))[1:];self.assertEqual(struct.unpack_from('<I',empty,56)[0],0)
  self.assertEqual(self.store.run(dict(scenario='warm_start',duration_s=3))[0],200)
  completed=s.command(b'r'+struct.pack('<BBHH',0,0x30,0,LIVE_BYTES))[1:];self.assertEqual(struct.unpack_from('<II',completed,56),(1,1));self.assertGreater(struct.unpack_from('<I',completed,208)[0],0)
  tune=copy.deepcopy(self.store.tune);tune['maps']['ve']['cells'][0]=86;self.store.save(json.dumps(tune).encode())
  block=s.command(b'r'+struct.pack('<BBHH',0,0x30,0,LIVE_BYTES))[1:]
  self.assertEqual(len(block),LIVE_BYTES);self.assertEqual(struct.unpack_from('<II',block,56),(0,0));self.assertEqual(struct.unpack_from('<III',block,184),(2,1,1));self.assertEqual(struct.unpack_from('<I',block,208)[0],0)
 def test_closed_session_registry_and_use_are_explicit(self):
  s=self.session();self.assertEqual(status(self.store)['session_count'],1);s.close();s.close();self.assertEqual(status(self.store)['session_count'],0)
  with self.assertRaises(RuntimeError):s.command(b'Q')
 def test_failed_host_observation_preserves_inhibition_and_unknown_age(self):
  s=self.session()
  with mock.patch.object(self.store,'coherent_sample',side_effect=MemoryError):block=s.command(b'r'+struct.pack('<BBHH',0,0x30,0,256))[1:]
  self.assertEqual(struct.unpack_from('<I',block,52)[0],1);self.assertEqual(struct.unpack_from('<I',block,64)[0],4294967295);self.assertEqual(struct.unpack_from('<I',block,72)[0],0);self.assertEqual(struct.unpack_from('<II',block,208),(0,0))

if __name__=='__main__':unittest.main(verbosity=2)
