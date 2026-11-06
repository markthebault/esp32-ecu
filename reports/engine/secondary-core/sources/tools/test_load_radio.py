"""Independent schema3 codec, legacy byte preservation and authenticated state."""
import copy,hmac,math,struct,unittest
from engine_runtime import EngineRuntime
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,engine_telemetry,derive_engine_key,capability_request
from espnow_protocol import header
from test_engine_observability import independent_frame
from test_load_model import tune,alpha

LMK=bytes(range(16));BOOT=bytes(range(16,32));MAC='02:EC:00:00:00:01';SESSION=0x12345678

def observation(t=None,**inputs):
 r=EngineRuntime(t)
 try:r.step(dict(rpm=1200,synced=True,**inputs),1000000,use_decoder=False);return r.data()
 finally:r.close()
def independent3(sample,seq=1,sent=5030000):
 # Reuse the frozen base layout oracle, independently append the18-byte ABI.
 b=bytearray(250);b[:200]=independent_frame(sample,seq=seq,sent=sent)[:200];b[:8]=header(9,250);struct.pack_into('<H',b,20,3)
 d=sample['load_model'];sources=[d[k+'_source_code'] for k in ('fuel','spark','lambda','trim')]
 b[200]=sum(v<<(2*i) for i,v in enumerate(sources))
 b[201]=d['pressure_code']|(d['baro_source_code']<<2)|(int(d['available'])<<3)|(int(d['available'] and bool(d['flags']&1))<<4)|(d['afr_code']<<5)|(int(d['available'] and bool(d['flags']&256))<<7)
 struct.pack_into('<4f',b,202,*[d[k] if d['available'] and d[k] is not None else math.nan for k in ('fuel_load','afr_factor','baro_kpa','emap_kpa')]);b[218:]=hmac.digest(derive_engine_key(LMK,BOOT,SESSION),b[:218],'sha256');return bytes(b)

class LoadRadioTests(unittest.TestCase):
 def setUp(self):self.native=EngineRecorder();self.addCleanup(self.native.close);self.key=derive_engine_key(LMK,BOOT,SESSION)
 def frame(self,s,seq=1,sent=5030000,**kw):return self.native.frame(s,LMK,BOOT,SESSION,seq,sample_age=12,control_age=8,sent=sent,**kw)
 def test_schema3_is250_bytes_and_independent_bytes_match_mixed_sources(self):
  cases=[observation(),observation(alpha(),map_kpa=None,map_qualified=False,tps_pct=12.5)]
  t=tune();t['load_model'].update(fuel_source='imap_emap',ve_axis='imap_emap_pct',lambda_axis='imap_emap_pct',trim_axis='imap_emap_pct',aux_role='emap')
  cases.append(observation(t,map_kpa=80,aux_pressure_kpa=125,aux_pressure_qualified=True))
  for s in cases:
   packet=self.frame(s);self.assertEqual(len(packet),250);self.assertEqual(packet,independent3(s));d=engine_telemetry(packet,self.key,3)['load_model']
   self.assertTrue(d['available']);self.assertEqual(d['fuel_load'],s['load_model']['fuel_load']);self.assertEqual(d['pressure_code'],s['load_model']['pressure_code'])
  self.assertIsNone(engine_telemetry(self.frame(cases[1]),self.key,3)['inputs']['map_kpa'])
 def test_schema1_and2_remain_exact_legacy_bytes_and_new_modes_block(self):
  s=observation()
  for schema in (1,2):self.assertEqual(self.frame(s,schema=schema),independent_frame(s,seq=1,schema=schema))
  for settings in (dict(pressure='none'),dict(afr='off'),dict(aux_role='emap')):
   t=tune();t['load_model'].update(settings);s=observation(t)
   for schema in (1,2):
    with self.assertRaises(ValueError):self.frame(s,schema=schema)
   self.assertEqual(len(self.frame(s)),250)
  s=observation(alpha())
  for schema in (1,2):
   with self.assertRaises(ValueError):self.frame(s,schema=schema)
 def test_each250_tampered_bytes_rejects_before_advancing_negotiated_state(self):
  r=EngineReceiver(MAC,LMK);q=r.query(100,bytes([1])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,0,5000000),MAC,110)
  q=r.update(True,120,bytes([2])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,0,5010000),MAC,125)
  s=observation(alpha());packet=self.frame(s)
  for i in range(250):
   bad=bytearray(packet);bad[i]^=1
   with self.assertRaises(ValueError):r.receive(bytes(bad),MAC,150)
   self.assertEqual(r.last_packet,0)
  self.assertEqual(r.rejected,250);d=r.receive(packet,MAC,150);self.assertEqual(d['schema_version'],3)
  self.assertEqual(len(r.acknowledgement()),56)
  changed=copy.deepcopy(s);changed['load_model']['fuel_load']=11
  with self.assertRaises(ValueError):r.receive(self.frame(changed,seq=2,sent=5040000),MAC,160)
  self.assertEqual(r.last_packet,1)
 def test_authenticated_invalid_enums_lengths_unknowns_and_downgrade_reject(self):
  packet=self.frame(observation())
  mutations=[]
  for offset,value in ((200,255),(201,3),(201,0)):
   b=bytearray(packet);b[offset]=value;mutations.append(b)
  b=bytearray(packet);struct.pack_into('<H',b,20,2);mutations.append(b)
  b=bytearray(packet);struct.pack_into('<f',b,202,math.inf);mutations.append(b)
  b=bytearray(packet);struct.pack_into('<f',b,210,1);mutations.append(b)
  for b in mutations:
   b[218:]=hmac.digest(self.key,b[:218],'sha256')
   with self.assertRaises(ValueError):engine_telemetry(bytes(b),self.key,3)
  for body in (packet[:232],packet+b'\0',packet[1:]):
   with self.assertRaises(ValueError):engine_telemetry(body,self.key,3)
  with self.assertRaises(ValueError):engine_telemetry(self.frame(observation(),schema=2),self.key,3)
 def test_negotiated_upgrade_requires_new_counter_and_exact_nonce_retry(self):
  q=capability_request(LMK,SESSION,1,1,bytes([1])*16,schema=2);self.native.capability_reply(q,LMK,SESSION,BOOT,0,0)
  with self.assertRaises(ValueError):self.native.capability_reply(capability_request(LMK,SESSION,1,1,bytes([1])*16,schema=3),LMK,SESSION,BOOT,0,0)
  q=capability_request(LMK,SESSION,2,1,bytes([2])*16,schema=3);a=self.native.capability_reply(q,LMK,SESSION,BOOT,0,0);self.assertEqual(a,self.native.capability_reply(q,LMK,SESSION,BOOT,0,0))
  with self.assertRaises(ValueError):self.native.capability_reply(capability_request(LMK,SESSION,2,1,bytes([3])*16,schema=3),LMK,SESSION,BOOT,0,0)

if __name__=='__main__':unittest.main(verbosity=2)
