import json, tempfile, time, unittest
from pathlib import Path
from radio_simulator import RadioSimulator
from espnow_protocol import *

class RadioTests(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'peers.json';self.radio=RadioSimulator(self.path)
 def tearDown(self):self.folder.cleanup()
 def action(self,action,**kw):return self.radio.command(dict(action=action,**kw))
 def pair(self):
  self.assertEqual(self.action('open')[0],202);self.assertEqual(self.action('simulate')[0],202)
  return self.action('confirm',window=self.radio.window,mac=self.radio.candidate['mac'])
 def test_open_cancel_expiry_and_new_key(self):
  self.action('open');old=self.radio.key;self.assertEqual(self.radio.status()['led'],'blue_blink')
  self.assertEqual(self.action('cancel',window='wrong')[0],422);self.assertTrue(self.radio.status()['pairing'])
  self.action('cancel',window=self.radio.window);self.assertFalse(self.radio.status()['pairing']);self.assertEqual(self.radio.key,'')
  self.action('open');self.assertNotEqual(old,self.radio.key);self.radio.deadline=time.monotonic()-1
  self.assertFalse(self.radio.status()['pairing']);self.assertEqual(self.action('simulate')[0],422)
 def test_approval_bound_to_candidate_and_window(self):
  self.action('open');self.action('simulate');self.assertEqual(self.action('confirm',window='wrong',mac=self.radio.candidate['mac'])[0],409)
  self.assertEqual(self.action('confirm',window=self.radio.window,mac='02:00:00:00:00:00')[0],409);self.assertEqual(self.radio.peers,[])
 def test_pair_persist_unpair_and_restart(self):
  self.assertEqual(self.pair()[0],202);saved=RadioSimulator(self.path);self.assertEqual(len(saved.peers),1)
  self.assertFalse(saved.status()['peers'][0]['connected']);self.assertFalse(saved.status()['pairing'])
  self.assertEqual(saved.command(dict(action='unpair',mac=saved.peers[0]['mac']))[0],202);self.assertEqual(RadioSimulator(self.path).peers,[])
 def test_capacity_and_unpair_reuse(self):
  for i in range(4):self.assertEqual(self.pair()[0],202)
  self.assertEqual(self.action('open')[0],409);self.action('unpair',mac=self.radio.peers[0]['mac']);self.assertEqual(self.pair()[0],202)
 def test_storage_corruption_not_overwritten(self):
  self.path.write_text('{corrupt');r=RadioSimulator(self.path);self.assertFalse(r.storage_ok);self.assertEqual(r.command(dict(action='open'))[0],503);self.assertEqual(self.path.read_text(),'{corrupt');self.assertEqual(r.status()['led'],'red_blink')
 def test_failed_commit_preserves_runtime_peers(self):
  self.path.mkdir();self.assertEqual(self.pair()[0],507);self.assertEqual(self.radio.peers,[])
 def test_codec_pair_and_confirmation(self):
  window=bytes(range(16));beacon=header(1,24)+window;key=bytes(range(16,32))
  request,lmk=pairing_request(beacon,'02:EC:00:00:00:01','02:EC:00:00:01:01',key,'Screen',bytes(range(32,48)))
  self.assertEqual(len(request),96);self.assertEqual(len(lmk),16)
  self.assertEqual(request.hex(),'45434e3101026000000102030405060708090a0b0c0d0e0f202122232425262728292a2b2c2d2e2f53637265656e000000000000000000000000000000000000fa0d4bed654e65e1658314a5f35d81f2fa100cde0ec8de0eca0f071d42f8e1b9')
  self.assertEqual(lmk.hex(),'7ca99a488a7dbb3d184b208649f47681')
  packet=accepted(window,lmk);verify_accepted(packet,window,lmk)
  with self.assertRaises(ValueError):verify_accepted(packet,bytes(16),lmk)
  with self.assertRaises(ValueError):verify_accepted(packet,window,bytes(16))
  self.assertEqual(len(acknowledgement(1,2,lmk)),52)
 def test_codec_rejects_unknown_and_bad_inputs(self):
  with self.assertRaises(ValueError):pairing_request(header(1,24)+bytes(16),'FF:FF:FF:FF:FF:FF','02:00:00:00:00:01',bytes(16),'x')
  with self.assertRaises(ValueError):telemetry(bytes(88))
  with self.assertRaises(ValueError):pairing_request(header(1,24)+bytes(16),bytes([2,0,0,0,0,1]),bytes([2,0,0,0,0,2]),bytes(16),'<bad>\n')
if __name__=='__main__':unittest.main(verbosity=2)
