"""Owned adversarial receiver oracle; consumes a separately compiled native capture."""
from pathlib import Path
import copy,hashlib,hmac,json,math,os,struct,sys,unittest
OWN=Path(__file__).resolve().parents[1]
FREEZE=OWN/(sys.argv[1]if len(sys.argv)>1 else'freeze-final-001')
CAPTURE=OWN/(sys.argv[2]if len(sys.argv)>2 else'independent-native-001.ndjson')
if len(sys.argv)>1:del sys.argv[1:]
sys.path.insert(0,str(FREEZE/'tools'))
from engine_receiver import EngineReceiver,engine_telemetry,derive_engine_key,DISPLAY_FRESH
from flex_radio import engine_flex_fragment
from espnow_protocol import header
LMK=bytes(range(16));BOOT=bytes(range(16,32));MAC='02:EC:00:00:00:01';SESSION=0x12345678
KEY=derive_engine_key(LMK,BOOT,SESSION)
ROWS={r['name']:r for r in map(json.loads,CAPTURE.read_text().splitlines())}

def sign(b):return bytes(b[:-32])+hmac.digest(KEY,b[:-32],'sha256')
def pair(seq=1,proposal=100,sent=5030000,raw=8,control=4,sample=0,row='target_raw'):
 r=ROWS[row];b=bytearray.fromhex(r['base']);x=bytearray.fromhex(r['extension']);struct.pack_into('<Q',b,12,seq);struct.pack_into('<Q',x,12,seq)
 struct.pack_into('<Q',b,40,proposal);struct.pack_into('<Q',b,92,sent);struct.pack_into('<II',b,24,sample,control)
 flags=struct.unpack_from('<H',b,22)[0]&~DISPLAY_FRESH
 if sample<=1000 and control<=1000:flags|=DISPLAY_FRESH
 struct.pack_into('<H',b,22,flags);b=sign(b);x[24:56]=b[-32:];struct.pack_into('<I',x,192,raw);return b,sign(x)

def reply(q,floor=0,sent=5000000,counter=1,features=1,boot=BOOT):
 b=header(8,108)+struct.pack('<II16sIII16sQQ',SESSION,counter,q[16:32],features,5 if features else 0,0,boot,floor,sent)
 return b+hmac.digest(LMK,b,'sha256')
def receiver(now=100,floor=0):
 r=EngineReceiver(MAC,LMK,schema=5);q=r.query(now,b'1'*16);r.receive_reply(reply(q,floor),MAC,now+10);return r

def complete(r,p=None,first=150,second=151,reverse=False):
 b,x=p or pair();parts=(x,b)if reverse else(b,x)
 assert r.receive(parts[0],MAC,first)is None
 return r.receive(parts[1],MAC,second)

class Codec(unittest.TestCase):
 def test_native_extensions_match_independent_explicit_record_encoding(self):
  for row in ROWS.values():
   b=bytes.fromhex(row['base']);x=bytes.fromhex(row['extension']);f=row['record']
   self.assertEqual(len(b),250);self.assertEqual(len(x),232);self.assertEqual(b[-32:],hmac.digest(KEY,b[:-32],'sha256'));self.assertEqual(x[-32:],hmac.digest(KEY,x[:-32],'sha256'))
   self.assertEqual(x[24:56],b[-32:]);expected=struct.pack('<7Q10f6fII7BB',*map(int,f['times']),*[math.nan if n is None else n for n in f['values']],*f['calibration'],f['flags'],f['revision'],*f['codes'],0)
   self.assertEqual(len(expected),136);self.assertEqual(x[56:192],expected)
   decoded=engine_flex_fragment(x,KEY);self.assertEqual(decoded['flex_fuel']['sample_us'],f['times'][0]);self.assertFalse(decoded['complete'])
   with self.assertRaises(ValueError):engine_telemetry(b,KEY)
 def test_each_byte_tamper_and_every_wrong_peer_rejected_before_liveness(self):
  for original in pair():
   for i in range(len(original)):
    r=receiver();bad=bytearray(original);bad[i]^=1
    with self.assertRaises(ValueError):r.receive(bad,MAC,150)
    self.assertIsNone(r.latest);self.assertEqual(r.last_packet,0);self.assertIsNone(r.received_ms)
    with self.assertRaises(ValueError):r.acknowledgement()
  r=receiver()
  for p in pair():
   with self.assertRaises(ValueError):r.receive(p,'02:EC:00:00:00:02',150)
  self.assertEqual(len(r.partials),0)
 def test_original_u64_fields_stay_lossless_and_sources_are_explicit(self):
  for name in ('target_raw','synthetic_raw','u64_raw','acquiring','scalar_epoch_zero','absent','stale'):
   raw=4294967295 if name in ('acquiring','absent')else 0 if name=='scalar_epoch_zero'else 283 if name=='stale'else 8
   control=0 if name=='scalar_epoch_zero'else 4
   r=receiver();d=complete(r,pair(row=name,raw=raw,control=control))
   self.assertEqual(d['flex_fuel']['sample_us'],ROWS[name]['record']['times'][0]);self.assertTrue(d['complete_observation']);self.assertEqual(struct.unpack_from('<Q',r.acknowledgement(),12)[0],1)
   if name in ('acquiring','absent'):self.assertIsNone(d['bounded_flex_sample_age_ms']);self.assertFalse(r.status(151)['flex_sample_fresh'])
   if name=='scalar_epoch_zero':self.assertTrue(r.status(151)['flex_value_qualified']);self.assertFalse(r.status(151)['flex_raw_capture_qualified'])
 def test_reserved_enums_calibration_and_nan_mutations_reject_authenticated(self):
  mutations=[(22,'<H',1),(184,'<B',4),(185,'<B',23),(189,'<B',33),(190,'<B',33),(191,'<B',1),(152,'<f',0),(168,'<f',0),(112,'<f',math.inf),(112,'<I',0x7fc00001),(176,'<I',2**31)]
  for offset,fmt,value in mutations:
   r=receiver();b,x=pair();bad=bytearray(x);struct.pack_into(fmt,bad,offset,value);bad=sign(bad)
   with self.assertRaises(ValueError):complete(r,(b,bad))
   self.assertIsNone(r.latest)
 def test_full_base_mac_and_cross_source_revision_reject(self):
  for changed in ('mac','revision','synthetic','control_age','raw_age'):
   r=receiver();b,x=pair();x=bytearray(x)
   if changed=='mac':x[24+31]^=1
   if changed=='revision':struct.pack_into('<I',x,180,8)
   if changed=='synthetic':x[184]=2
   if changed=='control_age':b,x=pair(control=9)
   if changed=='raw_age':struct.pack_into('<I',x,192,0)
   with self.assertRaises(ValueError):complete(r,(b,sign(x)))
   self.assertIsNone(r.latest)

class Assembly(unittest.TestCase):
 def test_reorder_duplicate_no_partial_display_ack_or_liveness(self):
  for reverse in (False,True):
   r=receiver();parts=pair()[::-1]if reverse else pair()
   self.assertIsNone(r.receive(parts[0],MAC,150));self.assertIsNone(r.receive(parts[0],MAC,200));self.assertIsNone(r.latest);self.assertIsNone(r.received_ms);self.assertFalse(r.status(200)['fresh'])
   with self.assertRaises(ValueError):r.acknowledgement()
   d=r.receive(parts[1],MAC,250);self.assertEqual(d['packet_sequence'],1);self.assertTrue(r.status(250)['fresh']);ack=r.acknowledgement()
   for p in parts:
    with self.assertRaises(ValueError):r.receive(p,MAC,251)
   self.assertEqual(r.received_ms,250);self.assertEqual(r.acknowledgement(),ack)
 def test_exact_first_fragment_deadline_and_duplicate_never_extends_it(self):
  for delay,ok in ((249,True),(250,True),(251,False)):
   r=receiver();b,x=pair();r.receive(b,MAC,150);r.receive(b,MAC,399)
   if ok:self.assertIsNotNone(r.receive(x,MAC,150+delay))
   else:
    with self.assertRaises(ValueError):r.receive(x,MAC,150+delay)
    self.assertIsNone(r.latest);self.assertEqual(r.retired_through,1)
    for p in (b,x):
     with self.assertRaises(ValueError):r.receive(p,MAC,402)
 def test_capacity_eviction_retires_without_resetting_old_deadline(self):
  r=receiver()
  for seq in (2,3,4):r.receive(pair(seq=seq)[0],MAC,150+seq)
  self.assertEqual(sorted(r.partials),[3,4]);self.assertEqual(r.retired_through,2);self.assertEqual(r.evicted_pairs,1);self.assertEqual(r.last_packet,0)
  for p in pair(seq=2):
   with self.assertRaises(ValueError):r.receive(p,MAC,160)
  r.receive(pair(seq=3)[1],MAC,161);self.assertEqual(r.last_packet,3);self.assertIn(4,r.partials)
  with self.assertRaises(ValueError):r.receive(pair(seq=1)[0],MAC,162)
 def test_new_older_pair_at_capacity_cannot_evict_newer_slots(self):
  r=receiver()
  for seq in (3,4):r.receive(pair(seq=seq)[0],MAC,150+seq)
  with self.assertRaises(ValueError):r.receive(pair(seq=2)[0],MAC,160)
  self.assertEqual(sorted(r.partials),[3,4]);self.assertEqual(r.retired_through,2)
 def test_authenticated_conflicts_including_invalid_semantic_duplicates_quarantine(self):
  for kind in (0,1):
   for invalid in (False,True):
    r=receiver();parts=pair();r.receive(parts[kind],MAC,150);bad=bytearray(parts[kind]);bad[80 if kind==0 else 191 if invalid else 192]^=128 if invalid else 1;bad=sign(bad)
    with self.assertRaises(ValueError):r.receive(bad,MAC,151)
    self.assertEqual(r.conflicting_pairs,1);self.assertEqual(r.retired_through,1);self.assertEqual(r.last_packet,0)
    with self.assertRaises(ValueError):r.receive(parts[1-kind],MAC,152)
    self.assertIsNone(r.latest)
 def test_partial_expiry_and_conflict_cannot_refresh_completed_ack(self):
  r=receiver();complete(r);ack=r.acknowledgement();received=r.received_ms
  r.receive(pair(seq=2,proposal=101)[0],MAC,200);r.status(451)
  self.assertEqual(r.acknowledgement(),ack);self.assertEqual(r.received_ms,received);self.assertEqual(r.last_packet,1);self.assertEqual(r.retired_through,2)
 def test_clock_reversal_after_fragment_and_after_status_requires_query(self):
  for status_only in (False,True):
   r=receiver();complete(r)
   if status_only:r.status(500)
   else:r.receive(pair(seq=2)[0],MAC,500)
   state=r.status(200);self.assertTrue(state['query_required']);self.assertFalse(state['fresh'])
   with self.assertRaises(ValueError):r.receive(pair(seq=3)[0],MAC,501)
 def test_query_update_and_new_boot_drop_all_partials(self):
  r=receiver();r.receive(pair()[0],MAC,150);q=r.query(160,b'2'*16);self.assertEqual(r.partials,{});self.assertIsNone(r.latest)
  with self.assertRaises(ValueError):r.receive(pair()[1],MAC,161)
  r.receive_reply(reply(q,floor=1),MAC,170)
  with self.assertRaises(ValueError):r.receive(pair()[1],MAC,171)
  r.receive(pair(seq=2)[0],MAC,180);r.update(False,190,b'3'*16);self.assertEqual(r.partials,{})
  with self.assertRaises(ValueError):r.receive(pair(seq=2)[1],MAC,191)

class Epoch(unittest.TestCase):
 def test_u64_sequence_exhaustion_preserves_exact_ack_without_wrap(self):
  r=receiver(floor=2**64-2);complete(r,pair(seq=2**64-1));self.assertEqual(r.last_packet,2**64-1);self.assertEqual(struct.unpack_from('<Q',r.acknowledgement(),12)[0],2**64-1)
  for p in pair(seq=0):
   with self.assertRaises(ValueError):r.receive(p,MAC,152)
 def test_new_boot_key_rejects_old_pair_even_when_session_collides(self):
  r=receiver();complete(r);q=r.query(200,b'7'*16);boot=b'8'*16;r.receive_reply(reply(q,floor=10,sent=5050000,boot=boot),MAC,210)
  for p in pair(seq=11,sent=5080000):
   with self.assertRaises(ValueError):r.receive(p,MAC,250)
  self.assertIsNone(r.latest);self.assertEqual(r.partials,{})
  key=derive_engine_key(LMK,boot,SESSION);b,x=pair(seq=11,sent=5080000);b=b[:-32]+hmac.digest(key,b[:-32],'sha256');x=bytearray(x);x[24:56]=b[-32:];x=bytes(x[:-32])+hmac.digest(key,x[:-32],'sha256')
  self.assertIsNotNone(complete(r,(b,x),250,251))

class Age(unittest.TestCase):
 def test_delay_and_drift_floor_include_first_pair_and_wait(self):
  r=receiver();d=complete(r,first=150,second=350)
  self.assertGreaterEqual(d['bounded_flex_sample_age_ms'],8+200);self.assertGreaterEqual(d['bounded_flex_sample_age_ms'],d['transport_age_bound_ms']+8)
  self.assertFalse(r.status(600)['flex_sample_fresh']);self.assertFalse(r.status(600)['flex_control_allowed']);self.assertTrue(r.status(600)['fresh'])
 def test_repeated_payload_ages_cannot_decrease_or_change(self):
  r=receiver();a=complete(r);old=a['bounded_flex_sample_age_ms'];d=complete(r,pair(seq=2,sent=5130000),first=250,second=251)
  self.assertGreaterEqual(d['bounded_flex_sample_age_ms'],old+100)
  b,x=pair(seq=3,sent=5140000);x=bytearray(x);struct.pack_into('<f',x,120,51)
  with self.assertRaises(ValueError):complete(r,(b,sign(x)),260,261)
  self.assertEqual(r.last_packet,2)
 def test_unknown_is_never_refreshed_by_transport_or_query(self):
  r=receiver();complete(r,pair(raw=4294967295));self.assertIsNone(r.latest['bounded_flex_sample_age_ms'])
  complete(r,pair(seq=2,sent=5130000,raw=8),250,251)
  self.assertIsNone(r.latest['bounded_flex_sample_age_ms'])
 def test_unknown_timestamp_finite_age_cannot_be_fabricated(self):
  for name in ('acquiring','absent'):
   r=receiver()
   with self.assertRaises(ValueError):complete(r,pair(row=name,raw=0))
 def test_complete_source_faults_are_acknowledgeable_not_control_permission(self):
  r=receiver();d=complete(r,pair(row='stale',raw=283));self.assertTrue(d['complete_observation']);self.assertEqual(r.last_packet,1);self.assertEqual(len(r.acknowledgement()),56);state=r.status(151);self.assertTrue(state['fresh']);self.assertFalse(state['flex_control_allowed']);self.assertFalse(state['flex_value_qualified'])
 def test_query_preserves_repeated_immutable_and_non_refreshing_age(self):
  r=receiver();complete(r);previous=r.latest['bounded_flex_sample_age_ms'];q=r.query(200,b'5'*16);r.receive_reply(reply(q,floor=1,sent=5050000),MAC,210)
  d=complete(r,pair(seq=2,sent=5080000),250,251);self.assertGreaterEqual(d['bounded_flex_sample_age_ms'],previous+100)
  q=r.query(260,b'6'*16);r.receive_reply(reply(q,floor=2,sent=5110000),MAC,270);b,x=pair(seq=3,sent=5130000);x=bytearray(x);struct.pack_into('<f',x,120,51)
  with self.assertRaises(ValueError):complete(r,(b,sign(x)),280,281)

if __name__=='__main__':unittest.main(verbosity=2)
