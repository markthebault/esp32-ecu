"""Current1..8 profiles and strict historical four-cylinder format boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from engine_protocol import DEFAULT,pages,decode_pages,Session,SIGNATURE
from engine_runtime import EngineRuntime,EngineStore
from engine_msq import export_msq,import_msq
from profile_config import spark_offset
import struct


class ProfileBoundaryTests(unittest.TestCase):
 def candidate(self,count):
  tune=copy.deepcopy(DEFAULT);tune['engine']['cylinders']=count
  tune['timing']['firing_order']=list(range(1,count+1))+[0]*max(0,8-count)
  return tune

 def test_all24_native_and_msq_profiles_preserve_inactive_calibration(self):
  for count in range(1,9):
   for mode in ('batch_wasted','semi_sequential','sequential'):
    with self.subTest(cylinders=count,strategy=mode):
     candidate=self.candidate(count);candidate['strategy']=mode;candidate['cylinder_trims']['fuel_maps'][7]['cells'][17]=124.25;candidate['cylinder_trims']['spark_deg'][7]=2.5
     runtime=EngineRuntime(candidate)
     try:self.assertEqual(runtime.tune,candidate)
     finally:runtime.close()
     self.assertEqual(pages(import_msq(export_msq(candidate))),pages(candidate))

 def test_binary_count_requires_finite_integral_value_before_conversion(self):
  original=self.candidate(8);page=pages(original)
  for count in (0,9,-1,4.5,float('nan'),float('inf')):
   with self.subTest(cylinders=count):
    changed=copy.deepcopy(page);struct.pack_into('<f',changed[1],4,count)
    with self.assertRaises(ValueError):decode_pages(changed,original)
  self.assertEqual(pages(decode_pages(page,original)),page)

 def test_historical_json_profiles_stay_four_and_keep_their_engine_limits(self):
  for file in sorted((Path(__file__).resolve().parents[1]/'config/engine').glob('defaults-v*.json')):
   legacy=json.loads(file.read_text())
   migrated=EngineRuntime(legacy)
   try:
    self.assertEqual(migrated.tune['engine']['cylinders'],4);self.assertEqual(migrated.tune['timing']['firing_order'][4:],[0]*4)
    self.assertTrue(all(m['cells']==[100]*36 for m in migrated.tune['cylinder_trims']['fuel_maps'][4:]));self.assertEqual(migrated.tune['cylinder_trims']['spark_deg'][4:],[0]*4)
   finally:migrated.close()
   for key,value in [('cylinders',1),('cylinders',3),('cylinders',8),('displacement_cc',4001),('injector_cc_min',99)]:
    candidate=copy.deepcopy(legacy);candidate['engine'][key]=value
    with self.subTest(identity=file.name,key=key,value=value),self.assertRaises(ValueError):EngineRuntime(candidate)

 def test_rejected_save_preserves_tune_page_and_storage(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'engine.json';store=EngineStore(path)
   try:
    original=copy.deepcopy(store.tune);encoded=bytes(pages(original)[1])
    for count in (0,9,-1,4.5,True):
     candidate=copy.deepcopy(original);candidate['engine']['cylinders']=count
     code,_=store.save(json.dumps(candidate).encode())
     self.assertEqual(code,422);self.assertEqual(store.tune,original)
     self.assertEqual(bytes(pages(store.tune)[1]),encoded)
     self.assertFalse(path.exists())
   finally:store.runtime.close();store.data_recorder.close()

 def test_c8_native_burn_is_atomic_and_keeps_cas_across_count_changes(self):
  with tempfile.TemporaryDirectory() as directory:
   store=EngineStore(Path(directory)/'engine.json');self.addCleanup(store.runtime.close);self.addCleanup(store.data_recorder.close)
   code,tune=store.save(json.dumps(self.candidate(8)).encode());self.assertEqual(code,200);s=Session(store);self.addCleanup(s.close)
   self.assertEqual(s.command(b'Q'),b'\0'+SIGNATURE);self.assertEqual(s.buffers[1],pages(tune)[1])
   write=b'M'+struct.pack('<BBHH',0,1,spark_offset(7),4)+struct.pack('<f',3.75);self.assertEqual(s.command(write),b'\0');self.assertEqual(store.tune['cylinder_trims']['spark_deg'][7],0)
   self.assertEqual(s.command(b'b\0\1'),b'\4');self.assertEqual(store.tune['cylinder_trims']['spark_deg'][7],3.75)
   stale=Session(store);self.addCleanup(stale.close);before=copy.deepcopy(store.tune);small=copy.deepcopy(before);small['engine']['cylinders']=1;small['timing']['firing_order']=[1]+[0]*7
   self.assertEqual(store.save(json.dumps(small).encode())[0],200);self.assertEqual(store.tune['cylinder_trims']['spark_deg'][7],3.75)
   self.assertEqual(stale.command(write),b'\x84');self.assertEqual(store.tune['engine']['cylinders'],1)


if __name__=='__main__':unittest.main(verbosity=2)
