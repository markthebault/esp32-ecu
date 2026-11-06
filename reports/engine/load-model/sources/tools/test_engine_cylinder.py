"""Cylinder configuration/storage/observability and own004 tuning contract and historical own003 imports."""
import copy,csv,io,json,struct,tempfile,unittest
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from engine_observability import EngineRecorder
from engine_protocol import pages,decode_pages,Session,live_block,SIGNATURE
from engine_msq import export_msq,import_msq

class CylinderTests(unittest.TestCase):
 def setUp(self):
  self.tune=json.loads((R/'config/engine/defaults.json').read_text());self.tune['strategy']='sequential_4cyl';self.tune['cylinder_trims']['enabled']=True;self.tune['settings']['afterstart_pct']=0
 def test_fuel_and_spark_adjust_physical_cylinder2_before_deadtime(self):
  self.tune['cylinder_trims']['fuel_maps'][1]['cells']=[120]*36;self.tune['cylinder_trims']['spark_deg'][1]=-3
  with_runtime=EngineRuntime(self.tune)
  try:
   out=with_runtime.step(dict(rpm=1200,synced=True,phase_synced=True),1000,use_decoder=False);c=out['cylinders']['proposals']
   self.assertEqual(out['faults'],0);self.assertAlmostEqual(c[1]['pulse_ms']-out['deadtime_ms'],(out['pulse_ms']-out['deadtime_ms'])*1.2)
   self.assertEqual(c[1]['advance_deg'],out['advance_deg']-3)
   for i in (0,2,3):self.assertEqual(c[i]['pulse_ms'],out['pulse_ms']);self.assertEqual(c[i]['advance_deg'],out['advance_deg'])
   snapshot=with_runtime.data();self.assertEqual(snapshot['cylinders']['valid_mask'],15);self.assertTrue(snapshot['cylinders']['enabled'])
   recorder=EngineRecorder();self.assertEqual(recorder.command(dict(action='start',period_ms=20,duration_s=1),1000),200);self.assertTrue(recorder.append(snapshot,1000));recorder.command(dict(action='stop',log_id=1),2000)
   replay=recorder.page(1,0)['records'][0]['sample']['cylinders'];self.assertEqual(replay,snapshot['cylinders'])
   rows=list(csv.reader(io.StringIO(recorder.msl(1)),delimiter='\t'));self.assertEqual(len(rows[2]),126);row=dict(zip(rows[2],rows[4]));self.assertEqual(float(row['C2FuelTrim']),120);self.assertAlmostEqual(float(row['C2PW']),c[1]['pulse_ms'],places=5);recorder.close()
  finally:with_runtime.close()
 def test_v1_and_v2_imports_reset_every_trim_without_rewriting_file(self):
  for schema in (1,2):
   old=json.loads((R/'config/engine/defaults-v2.json').read_text());old['revision']=31
   if schema==1:old['schema_version']=1;del old['timing']
   with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'tune.json';body=json.dumps(old).encode();path.write_bytes(body);store=EngineStore(path)
    self.assertTrue(store.storage_ok);self.assertEqual(path.read_bytes(),body);self.assertEqual(store.tune['revision'],31);self.assertEqual(store.tune['schema_version'],7)
    self.assertFalse(store.tune['cylinder_trims']['enabled']);self.assertEqual(store.tune['cylinder_trims']['spark_deg'],[0]*4)
    self.assertTrue(all(m['cells']==[100]*36 for m in store.tune['cylinder_trims']['fuel_maps']))
 def test_legacy_near_limit_migrates_above16k_and_keeps_source(self):
  fixture=R/'config/engine/fixtures/legacy-near-limit-v2.json'
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'tune.json';body=fixture.read_bytes();path.write_bytes(body);store=EngineStore(path)
   self.assertTrue(store.storage_ok);self.assertEqual(path.read_bytes(),body);self.assertGreater(len(json.dumps(store.tune,separators=(',',':')).encode()),16384)
   revision=store.tune['revision'];code,saved=store.save(json.dumps(store.tune).encode());self.assertEqual(code,200);self.assertEqual(saved['revision'],revision+1);self.assertLessEqual(path.stat().st_size,24576)
 def test_strict_maps_and_enable_validation(self):
  for mutate in [lambda t:t['cylinder_trims']['fuel_maps'][0]['cells'].__setitem__(0,49),lambda t:t['cylinder_trims']['spark_deg'].__setitem__(2,11),lambda t:t['cylinder_trims']['fuel_maps'][1]['rpm'].__setitem__(1,80),lambda t:t.__setitem__('strategy','batch_wasted_4cyl'),lambda t:t['cylinder_trims']['fuel_maps'].pop()]:
   bad=copy.deepcopy(self.tune);mutate(bad)
   with self.assertRaises(ValueError):EngineRuntime(bad)
 def test_004_msq_and_single_page_preserve_distinct_corners_and_cylinder_ids(self):
  self.tune['cylinder_trims']['fuel_maps'][1]['cells'][17]=113.25;self.tune['cylinder_trims']['spark_deg']=[1,-3,4,0]
  text=export_msq(self.tune);self.assertIn(SIGNATURE.decode(),text);decoded=import_msq(text);self.assertEqual(decoded,self.tune)
  blocks=pages(decoded);self.assertEqual(len(blocks),1);self.assertEqual(len(blocks[1]),5376)
  self.assertEqual(struct.unpack_from('<f',blocks[1],3968+192+48+17*4)[0],113.25)
  self.assertEqual(struct.unpack_from('<4fI',blocks[1],4736),(1,-3,4,0,1))
  self.assertEqual(pages(decode_pages(blocks,decoded)),blocks)
  broken=copy.deepcopy(blocks);broken[1][4767]=1
  with self.assertRaises(ValueError):decode_pages(broken,decoded)
 def test_old_application_msqs_migrate_to_disabled_neutral(self):
  for filename in ('tunerstudio-roundtrip.msq','tunerstudio-sequential-roundtrip.msq'):
   tune=import_msq((R/'tuning/examples'/filename).read_bytes());self.assertEqual(tune['schema_version'],7);self.assertFalse(tune['cylinder_trims']['enabled']);self.assertTrue(all(m['cells']==[100]*36 for m in tune['cylinder_trims']['fuel_maps']))
 def test_actual_tunerstudio003_saved_cylinder_cell_and_spark(self):
  tune=import_msq((R/'tuning/examples/tunerstudio-cylinder-roundtrip.msq').read_bytes())
  self.assertTrue(tune['cylinder_trims']['enabled']);self.assertEqual(tune['cylinder_trims']['spark_deg'],[0,-2.5,0,0])
  cells=tune['cylinder_trims']['fuel_maps'][1]['cells'];self.assertEqual(cells[14],117.25)
  self.assertEqual([v for i,v in enumerate(cells) if i!=14],[120]*35)
  for i in (0,2,3):self.assertEqual(tune['cylinder_trims']['fuel_maps'][i]['cells'],[100]*36)
 def test_whole_page_burn_is_transactional_and_old_output_prefix_is_retained(self):
  with tempfile.TemporaryDirectory() as directory:
   store=EngineStore(Path(directory)/'tune.json');session=Session(store);blocks=pages(self.tune)
   for offset in range(0,5120,256):
    body=bytes(blocks[1][offset:offset+256]);self.assertEqual(session.command(b'M'+struct.pack('<BBHH',0,1,offset,len(body))+body),b'\0')
   self.assertEqual(session.command(b'b\0\1'),b'\4');self.assertTrue(store.tune['cylinder_trims']['enabled']);self.assertEqual(len(live_block(store)),416);self.assertEqual(struct.unpack_from('<I',live_block(store),52)[0],1)
   revision=store.tune['revision'];self.assertEqual(session.command(b'b\0\1'),b'\4');self.assertEqual(store.tune['revision'],revision)

if __name__=='__main__':unittest.main(verbosity=2)
