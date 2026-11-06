"""Expanded native core profiles cannot escape through current public formats."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from engine_protocol import DEFAULT,pages
from engine_runtime import EngineRuntime,EngineStore
from engine_msq import export_msq


class ProfileBoundaryTests(unittest.TestCase):
 def candidate(self,count):
  tune=copy.deepcopy(DEFAULT);tune['engine']['cylinders']=count
  tune['timing']['firing_order']=list(range(1,count+1))+[0]*max(0,4-count)
  return tune

 def test_native_public_parser_and_msq_export_reject_nonfour_profiles(self):
  for count in (1,2,3,5,6,7,8):
   with self.subTest(cylinders=count):
    candidate=self.candidate(count)
    with self.assertRaises(ValueError):EngineRuntime(candidate)
    with self.assertRaises(ValueError):export_msq(candidate)

 def test_current_binary_encoder_rejects_nonfour_without_truncation(self):
  for count in (1,2,3,5,6,7,8):
   with self.subTest(cylinders=count):
    with self.assertRaises(ValueError):pages(self.candidate(count))

 def test_rejected_save_preserves_tune_page_and_storage(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'engine.json';store=EngineStore(path)
   try:
    original=copy.deepcopy(store.tune);encoded=bytes(pages(original)[1])
    for count in (1,2,3,5,6,7,8):
     code,_=store.save(json.dumps(self.candidate(count)).encode())
     self.assertEqual(code,422);self.assertEqual(store.tune,original)
     self.assertEqual(bytes(pages(store.tune)[1]),encoded)
     self.assertFalse(path.exists())
   finally:store.runtime.close();store.data_recorder.close()


if __name__=='__main__':unittest.main(verbosity=2)
