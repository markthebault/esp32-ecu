"""Schema7 native wire interoperability and adversarial four-part assembly."""
import copy,hmac,itertools,json,math,struct,unittest
from engine_runtime import EngineRuntime,R
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,engine_acknowledgement,engine_telemetry
from cylinder_radio import engine_cylinder_fragment
from test_boost_radio import independent_triple
from test_flex_radio import sign,KEY,FLOOR
from test_load_radio import LMK,BOOT,MAC,SESSION

def independent_profile(sample,**kw):
 # The historical independent encoder takes byte worker masks. Explicitly
 # truncate only its private prefix; the extension below carries all32 bits.
 prefix=copy.deepcopy(sample);worker=prefix['worker_observation']
 worker['virtual_high_mask']&=255;worker['physical_command_mask']&=255
 parts=[bytearray(p) for p in independent_triple(prefix,**kw)]
 struct.pack_into('<H',parts[0],20,7);parts[0]=sign(parts[0])
 for i in (1,2):
  struct.pack_into('<H',parts[i],20,7);parts[i][24:56]=parts[0][-32:];parts[i]=sign(parts[i])
 c=sample['cylinders'];w=sample['worker_observation'];out=bytearray(236)
 struct.pack_into('<4sBBHIQHH',out,0,b'ECN1',1,13,236,SESSION,struct.unpack_from('<Q',parts[0],12)[0],7,0);out[24:56]=parts[0][-32:]
 struct.pack_into('<9B',out,56,c['count'],w['cylinder_count'],4,4,c['valid_mask'],int(c['enabled']),c['capacity_mask'],c['spark_clamp_mask'],c['retard_floor_mask'])
 struct.pack_into('<II',out,68,w['virtual_high_mask'],w['physical_command_mask'])
 for i,row in enumerate(c['proposals']):
  for k,name in enumerate(('pulse_ms','advance_deg','fuel_pct','duty_pct')):
   struct.pack_into('<f' if c['valid_mask']&(1<<i) else '<I',out,76+16*i+4*k,row[name] if c['valid_mask']&(1<<i) else 0x7fc00000)
 return tuple(parts+[sign(out)])

class CylinderRadioTests(unittest.TestCase):
 def setUp(self):
  self.native=EngineRecorder();self.addCleanup(self.native.close)
  t=json.loads((R/'config/engine/defaults.json').read_text());t['engine']['cylinders']=8;t['engine']['displacement_cc']=4000;t['strategy']='sequential';t['timing']['firing_order']=[1,8,4,3,6,5,7,2]
  t['cylinder_trims']['enabled']=True;t['cylinder_trims']['spark_deg'][7]=3;t['cylinder_trims']['fuel_maps'][7]['cells']=[123]*36
  r=EngineRuntime(t);self.addCleanup(r.close);r.step(dict(rpm=1500,synced=True,phase_synced=True),1000000,use_decoder=False);self.sample=r.data()
 def frame(self,sample=None,sequence=FLOOR+1,sent=5030000):
  return self.native.frame_profile(sample or self.sample,LMK,BOOT,SESSION,sequence,sample_age=12,control_age=8,sent=sent)
 def receiver(self,schema=7):
  self.native.reset_capabilities();r=EngineReceiver(MAC,LMK,schema=schema);q=r.query(100,b'1'*16)
  r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5000000),MAC,110);q=r.update(True,120,b'2'*16)
  r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5010000),MAC,125);return r
 def complete(self,r,parts=None,start=140):
  result=None
  for i,p in enumerate(parts or self.frame()):result=r.receive(p,MAC,start+10*i)
  return result
 def test_full_bytes_and_all_eight_rows(self):
  s=copy.deepcopy(self.sample);s['worker_observation'].update(cylinder_count=8,virtual_high_mask=1<<17,command_sequence=str(2**53+51))
  parts=self.frame(s);self.assertEqual(tuple(map(len,parts)),(250,232,144,236));self.assertEqual(parts,independent_profile(s,raw_age=2**32-1))
  data=self.complete(self.receiver(),parts);self.assertEqual(data['worker_observation']['virtual_high_mask'],1<<17);self.assertEqual(data['cylinders']['count'],8)
  self.assertEqual(data['cylinders']['proposals'][7]['fuel_pct'],123);self.assertEqual(data['cylinders']['proposals'][7]['coil_logical_channel'],17);self.assertTrue(data['per_cylinder_available'])
  with self.assertRaises(ValueError):engine_telemetry(parts[0],KEY,7)
 def test_all24_orders_publish_and_ack_only_after_last_part(self):
  for order in itertools.permutations(range(4)):
   r=self.receiver();parts=self.frame()
   for i,index in enumerate(order):
    result=r.receive(parts[index],MAC,140+10*i)
    if i<3:
     self.assertIsNone(result);self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR)
     with self.assertRaises(ValueError):r.acknowledgement()
    else:
     self.assertEqual(result['datagrams_per_observation'],4);self.assertEqual(r.acknowledgement(),engine_acknowledgement(SESSION,FLOOR+1,KEY))
 def test_missing_each_part_duplicates_do_not_extend_original_deadline(self):
  for missing in range(4):
   r=self.receiver();parts=self.frame()
   for i in range(4):
    if i!=missing:self.assertIsNone(r.receive(parts[i],MAC,140+i))
   r.receive(parts[(missing+1)%4],MAC,350);r.status(395)
   self.assertIsNone(r.latest);self.assertGreaterEqual(r.expired_pairs,1);self.assertEqual(r.last_packet,FLOOR)
   with self.assertRaises(ValueError):r.receive(parts[missing],MAC,396)
 def test_each862_byte_tamper_authentication_before_liveness(self):
  for part in self.frame():
   for index in range(len(part)):
    r=self.receiver();bad=bytearray(part);bad[index]^=1
    with self.assertRaises(ValueError):r.receive(bad,MAC,140)
    self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR)
 def test_signed_semantic_bounds_reserved_and_float_failures(self):
  p=self.frame()[3]
  for offset,kind,value in ((20,'H',6),(22,'H',1),(56,'B',0),(56,'B',9),(57,'B',9),(58,'B',8),(59,'B',8),(61,'B',2),(65,'B',1),(66,'B',1),(67,'B',1),(68,'I',1<<8),(72,'I',1<<17),(76,'f',math.nan),(76,'f',math.inf)):
   with self.subTest(offset=offset,value=value):
    b=bytearray(p);struct.pack_into('<'+kind,b,offset,value)
    with self.assertRaises(ValueError):engine_cylinder_fragment(sign(b),KEY)
 def test_proposal_four_and_earlier_worker_eight_are_distinct(self):
  r=EngineRuntime();self.addCleanup(r.close);r.step(dict(rpm=1000,synced=True),1000000,use_decoder=False);s=r.data();s['worker_observation'].update(cylinder_count=8,virtual_high_mask=1<<17)
  data=self.complete(self.receiver(),self.frame(s));self.assertEqual(data['cylinders']['count'],4);self.assertEqual(data['worker_observation']['cylinder_count'],8);self.assertEqual(data['worker_observation']['virtual_high_mask'],1<<17)
  for call in (self.native.frame_pair,self.native.frame_triple):
   with self.assertRaises(ValueError):call(s,LMK,BOOT,SESSION,FLOOR+1)
  for schema in (1,2,3,4):
   with self.assertRaises(ValueError):self.native.frame(s,LMK,BOOT,SESSION,FLOOR+1,schema=schema)
  p=self.frame(s)[3];b=bytearray(p);struct.pack_into('<I',b,76+16*4,0)
  with self.assertRaises(ValueError):engine_cylinder_fragment(sign(b),KEY)
 def test_repeated_snapshot_cylinder_payload_and_full_base_binding(self):
  r=self.receiver();self.complete(r);s=copy.deepcopy(self.sample);s['cylinders']['proposals'][7]['fuel_pct']=124
  with self.assertRaises(ValueError):self.complete(r,self.frame(s,FLOOR+2,5070000),start=190)
  r=self.receiver();parts=list(self.frame());p=bytearray(parts[3]);p[24]^=1;parts[3]=sign(p)
  with self.assertRaises(ValueError):self.complete(r,parts)
 def test_base_prefix_must_agree_with_full_worker_masks(self):
  s=copy.deepcopy(self.sample);s['worker_observation'].update(cylinder_count=8,virtual_high_mask=1)
  parts=list(self.frame(s));p=bytearray(parts[3]);struct.pack_into('<I',p,68,2);parts[3]=sign(p)
  with self.assertRaises(ValueError):self.complete(self.receiver(),parts)

if __name__=='__main__':unittest.main(verbosity=2)
