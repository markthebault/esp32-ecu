"""Independent schema4 bytes, legacy gating and authenticated receive state."""
import copy,hmac,struct,unittest
from engine_runtime import EngineRuntime
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,engine_telemetry,derive_engine_key,capability_request
from test_load_radio import independent3,LMK,BOOT,MAC,SESSION
from test_engine_observability import independent_frame
from test_secondary_model import tune,configure,inputs

def observation(t=None):
 r=EngineRuntime(t or tune())
 try:r.step(inputs(),1000000,use_decoder=False);return r.data()
 finally:r.close()
def independent4(sample,seq=1,sent=5030000):
 b=bytearray(independent3(sample,seq=seq,sent=sent));struct.pack_into('<H',b,20,4)
 fuel,spark=[sample['secondary_tables'][kind] for kind in ('fuel','spark')]
 b[90]=fuel['mode_code']|(spark['mode_code']<<3)|(int(fuel['active'])<<6)|(int(spark['active'])<<7)
 b[91]=fuel['source_code']|(spark['source_code']<<2)|(int(fuel['available'])<<4)|(int(spark['available'])<<5)|(int(fuel['evaluated'])<<6)|(int(spark['evaluated'])<<7)
 b[218:]=hmac.digest(derive_engine_key(LMK,BOOT,SESSION),b[:218],'sha256');return bytes(b)

class SecondaryRadioTests(unittest.TestCase):
 def setUp(self):self.native=EngineRecorder();self.addCleanup(self.native.close);self.key=derive_engine_key(LMK,BOOT,SESSION)
 def frame(self,s,seq=1,sent=5030000,**kw):return self.native.frame(s,LMK,BOOT,SESSION,seq,sample_age=12,control_age=8,sent=sent,schema=kw.pop('schema',4),**kw)
 def receiver(self):
  r=EngineReceiver(MAC,LMK,schema=4);q=r.query(100,bytes([1])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,0,5000000),MAC,110)
  q=r.update(True,120,bytes([2])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,0,5010000),MAC,125);return r
 def test_all225_mode_and_source_pairs_match_independent_bytes(self):
  for fuel_mode in ('off','multiply','add','conditional','input'):
   for spark_mode in ('off','multiply','add','conditional','input'):
    for fuel_source in ('map','tps','imap_emap'):
     for spark_source in ('map','tps','imap_emap'):
      t=tune();configure(t,'fuel',fuel_mode,fuel_source);configure(t,'spark',spark_mode,spark_source);s=observation(t);packet=self.frame(s)
      self.assertEqual(len(packet),250);self.assertEqual(packet,independent4(s));d=engine_telemetry(packet,self.key,4)['secondary_tables']
      for kind in ('fuel','spark'):
       self.assertEqual(d[kind]['mode'],s['secondary_tables'][kind]['mode']);self.assertEqual(d[kind]['source'],s['secondary_tables'][kind]['source']);self.assertEqual(d[kind]['active'],s['secondary_tables'][kind]['active']);self.assertEqual(d[kind]['evaluated'],s['secondary_tables'][kind]['evaluated'])
 def test_legacy_off_bytes_are_unchanged_and_inactive_nonoff_modes_block(self):
  s=observation()
  for schema in (1,2):self.assertEqual(self.frame(s,schema=schema),independent_frame(s,seq=1,schema=schema))
  self.assertEqual(self.frame(s,schema=3),independent3(s))
  for kind in ('fuel','spark'):
   for mode in ('multiply','add','conditional','input'):
    t=tune();configure(t,kind,mode)
    if mode=='conditional':t['secondary_tables'][kind]['threshold']=100
    s=observation(t)
    if mode=='conditional':self.assertFalse(s['secondary_tables'][kind]['active'])
    for schema in (1,2,3):
     with self.assertRaises(ValueError):self.frame(s,schema=schema)
    self.assertEqual(engine_telemetry(self.frame(s),self.key,4)['secondary_tables'][kind]['mode'],mode)
 def test_every_tampered_byte_rejects_without_advancing_receiver(self):
  t=tune();configure(t,'fuel','multiply');s=observation(t);r=self.receiver();packet=self.frame(s)
  for i in range(250):
   bad=bytearray(packet);bad[i]^=1
   with self.assertRaises(ValueError):r.receive(bytes(bad),MAC,150)
   self.assertEqual(r.last_packet,0)
  self.assertEqual(r.rejected,250);self.assertEqual(r.receive(packet,MAC,150)['schema_version'],4);self.assertEqual(len(r.acknowledgement()),56)
  changed=copy.deepcopy(s);changed['secondary_tables']['fuel']['source']='tps';changed['secondary_tables']['fuel']['source_code']=1;changed['secondary_tables']['fuel']['axis']='tps_pct';changed['secondary_tables']['fuel']['axis_code']=1;changed['secondary_tables']['fuel']['flags']|=1<<20
  with self.assertRaises(ValueError):r.receive(self.frame(changed,seq=2,sent=5040000),MAC,160)
  self.assertEqual(r.last_packet,1)
 def test_authenticated_reserved_codes_and_inconsistent_availability_reject(self):
  packet=self.frame(observation());mutations=[]
  for index,value in ((90,7),(90,7<<3),(90,64),(91,3),(91,3<<2),(91,64),(91,16|128)):
   b=bytearray(packet);b[index]=value;mutations.append(b)
  b=bytearray(packet);struct.pack_into('<H',b,20,3);mutations.append(b)
  for b in mutations:
   b[218:]=hmac.digest(self.key,b[:218],'sha256')
   with self.assertRaises(ValueError):engine_telemetry(bytes(b),self.key,4)
  with self.assertRaises(ValueError):engine_telemetry(packet,self.key,3)
 def test_schema_upgrade_needs_new_counter_and_exact_nonce_retry(self):
  old=capability_request(LMK,SESSION,1,1,bytes([1])*16,schema=3);self.native.capability_reply(old,LMK,SESSION,BOOT,0,0)
  with self.assertRaises(ValueError):self.native.capability_reply(capability_request(LMK,SESSION,1,1,bytes([1])*16,schema=4),LMK,SESSION,BOOT,0,0)
  update=capability_request(LMK,SESSION,2,1,bytes([2])*16,schema=4);reply=self.native.capability_reply(update,LMK,SESSION,BOOT,0,0);self.assertEqual(reply,self.native.capability_reply(update,LMK,SESSION,BOOT,0,0))
  with self.assertRaises(ValueError):self.native.capability_reply(capability_request(LMK,SESSION,2,1,bytes([3])*16,schema=4),LMK,SESSION,BOOT,0,0)

if __name__=='__main__':unittest.main(verbosity=2)
