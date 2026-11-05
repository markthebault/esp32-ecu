"""Independent schema5 bytes and adversarial coherent-pair receiver tests."""
import copy,hmac,math,struct,unittest
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,engine_telemetry,engine_acknowledgement,derive_engine_key
from engine_runtime import EngineRuntime
from engine_protocol import DEFAULT
from test_engine_flex import tune,edges,step
from test_secondary_radio import independent4
from test_load_radio import LMK,BOOT,MAC,SESSION

FLOOR=2**53+91
FLAGS=('required','configuration_match','value_qualified','raw_capture_qualified','control_ok','capture_valid','sample_value_valid','pending_fault','frequency_clamped','temperature_clamped','input_confirmed','corrections_enabled','corrections_valid','spark_bypassed','spark_clamped','zero_factor','available')
VALUES=('frequency_hz','low_pulse_us','ethanol_pct','fuel_temp_c','unfiltered_ethanol_pct','unfiltered_fuel_temp_c','sample_age_ms','fuel_pct','spark_add_deg','temperature_pct')
TIMES=('sample_us','window_start_us','last_edge_us','raw_edges','fault_generation','acknowledged_generation','config_epoch')
CAL=('low_hz','high_hz','fault_hz','tolerance_hz','stale_ms','filter_ms')
KEY=derive_engine_key(LMK,BOOT,SESSION)
def sign(packet):
 b=bytearray(packet);b[-32:]=hmac.digest(KEY,b[:-32],'sha256');return bytes(b)
def independent_pair(sample,sequence=FLOOR+1,sent=5030000,raw_age=8,control_age=8,sample_age=12):
 # Independent legacy body plus schema5; new Record layout is packed here,
 # without calling the C++ serializer or Python receiver's decoder.
 base=bytearray(independent4(sample,seq=sequence,sent=sent));struct.pack_into('<H',base,20,5)
 struct.pack_into('<II',base,24,sample_age,control_age);base=sign(base)
 f=sample['flex_fuel'];out=bytearray(232);struct.pack_into('<4sBBHIQHH',out,0,b'ECN1',1,11,232,SESSION,sequence,5,0);out[24:56]=base[-32:]
 struct.pack_into('<7Q',out,56,*(int(f[k]) for k in TIMES));struct.pack_into('<10f',out,112,*(math.nan if f[k] is None else f[k] for k in VALUES));struct.pack_into('<6f',out,152,*(f['capture_calibration'][k] for k in CAL))
 struct.pack_into('<II7B',out,176,sum(int(f[k])<<n for n,k in enumerate(FLAGS)),f['configuration_revision'],*(f[k] for k in ('source_code','reason_code','capture_reason_code','last_fault_code','correction_reason_code','window_cycles')),f['capture_calibration']['cycles'])
 stale=math.floor(f['capture_calibration']['stale_ms']*1000+.5) if f['available'] else 0
 struct.pack_into('<II',out,192,raw_age,stale);return base,sign(out)

class FlexRadioTests(unittest.TestCase):
 def setUp(self):
  self.native=EngineRecorder();self.addCleanup(self.native.close);r=EngineRuntime(tune());self.addCleanup(r.close);edges(r);step(r);self.sample=r.data();self.runtime=r
 def pair(self,s=None,sequence=FLOOR+1,sent=5030000,raw_age=8,control_age=8,sample_age=12):
  return self.native.frame_pair(s or self.sample,LMK,BOOT,SESSION,sequence,sent=sent,raw_age=raw_age,control_age=control_age,sample_age=sample_age)
 def receiver(self):
  self.native.reset_capabilities();r=EngineReceiver(MAC,LMK);q=r.query(100,bytes([1])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5000000),MAC,110)
  q=r.update(True,120,bytes([2])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5010000),MAC,125);return r
 def complete(self,r,pair=None,times=(140,150),reverse=False):
  p=pair or self.pair();order=(1,0) if reverse else (0,1);self.assertIsNone(r.receive(p[order[0]],MAC,times[0]));return r.receive(p[order[1]],MAC,times[1])
 def test_native_matches_independent_full_bytes_and_hmac(self):
  actual=self.pair();expected=independent_pair(self.sample);self.assertEqual(actual,expected);self.assertEqual(tuple(map(len,actual)),(250,232))
  with self.assertRaises(ValueError):engine_telemetry(actual[0],KEY,5)
  with self.assertRaises(ValueError):self.native.frame(self.sample,LMK,BOOT,SESSION,FLOOR+1,schema=5)
 def test_each_half_is_not_a_sample_or_ack_in_either_order(self):
  for reverse in (False,True):
   r=self.receiver();data=self.complete(r,reverse=reverse);self.assertTrue(data['complete_observation']);self.assertEqual(data['flex_fuel']['ethanol_pct'],50);self.assertEqual(data['flex_fuel']['fuel_temp_c'],42.5)
   self.assertTrue(r.status(150)['flex_raw_capture_qualified']);self.assertEqual(r.acknowledgement(),engine_acknowledgement(SESSION,FLOOR+1,KEY))
  r=self.receiver();self.assertIsNone(r.receive(self.pair()[0],MAC,140));self.assertIsNone(r.latest);self.assertIsNone(r.received_ms);self.assertEqual(r.last_packet,FLOOR)
  with self.assertRaises(ValueError):r.acknowledgement()
 def test_completion_age_includes_wait_exactly_once(self):
  bounds=[]
  for reverse in (False,True):
   r=self.receiver();data=self.complete(r,times=(140,190),reverse=reverse);bounds.append(data['bounded_flex_sample_age_ms']);self.assertEqual(data['flex_sample_age_ms'],8)
  self.assertEqual(bounds,[64,64])
 def test_fresh_adc_and_new_control_cannot_refresh_old_capture(self):
  r=self.receiver();self.complete(r);self.assertTrue(r.status(150)['flex_value_qualified']);self.assertFalse(r.status(380)['flex_value_qualified']);self.assertTrue(r.status(380)['fresh'])
  step(self.runtime,1240000);old=self.runtime.data();self.assertEqual(old['flex_fuel']['sample_us'],'1000000')
  p=self.pair(old,sequence=FLOOR+2,sent=5270000,control_age=8,raw_age=248);r.receive(p[0],MAC,390);r.receive(p[1],MAC,400);self.assertFalse(r.status(400)['flex_value_qualified'])
 def test_expiry_duplicate_and_eviction_retire_without_ack(self):
  r=self.receiver();p=self.pair();r.receive(p[0],MAC,140);r.receive(p[0],MAC,300);self.assertEqual(r.partials[FLOOR+1]['started_ms'],140);r.status(391)
  self.assertEqual(r.last_packet,FLOOR);self.assertGreaterEqual(r.retired_through,FLOOR+1)
  with self.assertRaises(ValueError):r.receive(p[1],MAC,392)
  with self.assertRaises(ValueError):r.acknowledgement()
  r=self.receiver();pairs=[self.pair(sequence=FLOOR+n,sent=5020000+n*10000,control_age=n*10-2,raw_age=n*10-2,sample_age=n*10+2) for n in (1,2,3)]
  for n,p in enumerate(pairs):r.receive(p[0],MAC,140+10*n)
  self.assertEqual(len(r.partials),2);self.assertEqual(r.evicted_pairs,1)
  with self.assertRaises(ValueError):r.receive(pairs[0][1],MAC,170)
  self.assertEqual(r.last_packet,FLOOR);self.assertIsNotNone(r.receive(pairs[1][1],MAC,180));self.assertIsNotNone(r.receive(pairs[2][1],MAC,200))
 def test_conflict_even_semantically_invalid_retires_sequence(self):
  for part,offset in ((0,81),(1,191)):
   r=self.receiver();p=self.pair();r.receive(p[part],MAC,140);bad=bytearray(p[part]);bad[offset]=255
   with self.assertRaises(ValueError):r.receive(sign(bad),MAC,150)
   with self.assertRaises(ValueError):r.receive(p[1-part],MAC,160)
   self.assertEqual(r.last_packet,FLOOR);self.assertIsNone(r.latest);self.assertEqual(r.conflicting_pairs,1)
 def test_full_base_mac_binds_all_fields(self):
  r=self.receiver();p=self.pair();bad=bytearray(p[1]);bad[24]^=1;r.receive(p[0],MAC,140)
  with self.assertRaises(ValueError):r.receive(sign(bad),MAC,150)
  self.assertEqual(r.last_packet,FLOOR)
 def test_every_byte_tamper_rejects_without_partial_liveness(self):
  pair=self.pair()
  for part in pair:
   for position in range(len(part)):
    r=self.receiver();bad=bytearray(part);bad[position]^=1
    with self.assertRaises(ValueError):r.receive(bytes(bad),MAC,140)
    self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR);self.assertIsNone(r.received_ms)
 def test_source_flags_and_revision_and_stale_limit_signed_negatives(self):
  mutations=[(176,'I',2**31),(184,'B',4),(185,'B',23),(189,'B',33),(191,'B',1),(196,'I',250001),(180,'I',99),(112,'I',0x7fc01234),(192,'I',0)]
  for offset,kind,value in mutations:
   r=self.receiver();base,ext=self.pair();bad=bytearray(ext);struct.pack_into('<'+kind,bad,offset,value);r.receive(base,MAC,140)
   with self.assertRaises(ValueError):r.receive(sign(bad),MAC,150)
   self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR)
  r=self.receiver();base,ext=self.pair();base=bytearray(base);base[82]=1;base=sign(base);ext=bytearray(ext);ext[24:56]=base[-32:];r.receive(base,MAC,140)
  with self.assertRaises(ValueError):r.receive(sign(ext),MAC,150)
 def test_repeated_snapshot_immutability_and_unknown_age_survive_query(self):
  r=self.receiver();self.complete(r,self.pair(raw_age=2**32-1));self.assertIsNone(r.status(150)['flex_sample_age_ms'])
  q=r.query(200,bytes([3])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR+10,5090000),MAC,210)
  p=self.pair(sequence=FLOOR+11,sent=5100000,raw_age=78,control_age=78,sample_age=82);self.complete(r,p,(220,230));self.assertIsNone(r.status(230)['flex_sample_age_ms'])
  changed=copy.deepcopy(self.sample);changed['flex_fuel']['capture_calibration']['filter_ms']=1;p=self.pair(changed,sequence=FLOOR+12,sent=5110000,raw_age=88,control_age=88,sample_age=92);r.receive(p[0],MAC,240)
  with self.assertRaises(ValueError):r.receive(p[1],MAC,250)
  self.assertEqual(r.last_packet,FLOOR+11)
 def test_retirement_cannot_ack_partial_after_previous_completion(self):
  r=self.receiver();self.complete(r);ack=r.acknowledgement();p=self.pair(sequence=FLOOR+2,sent=5040000,raw_age=18,control_age=18);r.receive(p[0],MAC,160);r.status(411)
  self.assertEqual(r.acknowledgement(),ack);self.assertEqual(r.last_packet,FLOOR+1);self.assertGreater(r.retired_through,r.last_packet)
 def test_clock_reversal_after_status_cannot_requalify(self):
  r=self.receiver();self.complete(r);self.assertFalse(r.status(400)['flex_value_qualified']);self.assertFalse(r.status(200)['flex_value_qualified']);self.assertTrue(r.status(410)['query_required'])
  p=self.pair(sequence=FLOOR+2,sent=5040000,raw_age=18,control_age=18)
  with self.assertRaises(ValueError):r.receive(p[0],MAC,220)
 def test_complete_fault_is_accepted_and_acknowledged(self):
  self.runtime.flex_edge(1000001,True);step(self.runtime,1000001);s=self.runtime.data();self.assertTrue(s['flex_fuel']['pending_fault']);r=self.receiver();data=self.complete(r,self.pair(s,raw_age=1,control_age=0));self.assertTrue(data['flex_fuel']['pending_fault']);self.assertFalse(r.status(150)['flex_control_allowed']);self.assertEqual(struct.unpack_from('<Q',r.acknowledgement(),12)[0],FLOOR+1)
 def test_scalar_epoch_zero_and_unavailable_acquisition_age(self):
  t=copy.deepcopy(DEFAULT);t['secondary_tables']['fuel'].update(mode='conditional',condition='ethanol_pct',threshold=40);runtime=EngineRuntime(t);self.addCleanup(runtime.close);step(runtime,0,ethanol_pct=50,ethanol_qualified=True);s=runtime.data();self.assertEqual(s['flex_fuel']['sample_us'],'0');self.assertTrue(s['flex_fuel']['value_qualified']);r=self.receiver();data=self.complete(r,self.pair(s));self.assertEqual(data['flex_fuel']['source'],'synthetic_value');self.assertFalse(r.status(150)['flex_raw_capture_qualified'])
  runtime=EngineRuntime(tune());self.addCleanup(runtime.close);runtime.flex_edge(999000,True);step(runtime,1000000);s=runtime.data();self.assertIsNone(s['flex_fuel']['sample_age_ms']);self.assertIsNone(s['flex_fuel']['read_age_ms'])
  with self.assertRaises(ValueError):self.pair(s,raw_age=0)
  r=self.receiver();self.complete(r,self.pair(s,raw_age=2**32-1));self.assertIsNone(r.status(150)['flex_sample_age_ms'])
 def test_legacy_neutral_bytes_and_gating_are_preserved(self):
  neutral=EngineRuntime();self.addCleanup(neutral.close);step(neutral);s=neutral.data()
  for schema in (1,2,3,4):
   frame=self.native.frame(s,LMK,BOOT,SESSION,FLOOR+1,schema=schema,sent=5030000,sample_age=12,control_age=8);self.assertEqual(engine_telemetry(frame,KEY,schema)['schema_version'],schema)
   with self.assertRaises(ValueError):self.native.frame(self.sample,LMK,BOOT,SESSION,FLOOR+1,schema=schema)

if __name__=='__main__':unittest.main(verbosity=2)
