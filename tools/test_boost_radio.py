"""Independent schema6 wire bytes and adversarial complete-observation tests.

Uses real native control samples and the firmware serializer, without RF.
"""
import copy,hmac,itertools,math,struct,unittest
from engine_runtime import EngineRuntime
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,engine_telemetry,engine_acknowledgement
from boost_config import VALUES
from boost_radio import engine_boost_fragment
from test_engine_flex import tune,edges,step
from test_flex_radio import independent_pair,sign,KEY,FLOOR
from test_load_radio import LMK,BOOT,MAC,SESSION

def independent_triple(sample,**kw):
 base,flex=map(bytearray,independent_pair(sample,**kw));struct.pack_into('<H',base,20,6);base=sign(base)
 struct.pack_into('<H',flex,20,6);flex[24:56]=base[-32:]
 b=sample['boost_control'];out=bytearray(144)
 struct.pack_into('<4sBBHIQHH',out,0,b'ECN1',1,12,144,SESSION,struct.unpack_from('<Q',base,12)[0],6,0);out[24:56]=base[-32:]
 struct.pack_into('<8f',out,56,*(math.nan if b[k] is None else b[k] for k in VALUES))
 struct.pack_into('<QQIBBBB',out,88,int(b['pid_updates']),int(b['overboost_events']),b['flags'],b['reason_code'],b['mode_code'],int(b['available'])|int(b['pressure_enabled'])<<1|int(b['inhibit_engine'])<<2,0)
 return base,sign(flex),sign(out)

def replace_part(triple,index,offset,kind,value):
 parts=list(triple);p=bytearray(parts[index]);struct.pack_into('<'+kind,p,offset,value);parts[index]=sign(p)
 if index==0:
  for n in (1,2):
   p=bytearray(parts[n]);p[24:56]=parts[0][-32:];parts[n]=sign(p)
 return tuple(parts)

class BoostRadioTests(unittest.TestCase):
 def setUp(self):
  self.native=EngineRecorder();self.addCleanup(self.native.close)
  c=tune();c['engine']['injector_cc_min']=600;c['settings']['dfco_enabled']=False
  c['boost_control'].update(pressure_enabled=True,mode='open_loop');c['boost_control']['open_duty']['cells']=[40]*64
  self.runtime=EngineRuntime(c);self.addCleanup(self.runtime.close);edges(self.runtime);step(self.runtime,map_kpa=150);self.sample=self.runtime.data()
 def triple(self,s=None,sequence=FLOOR+1,sent=5030000,raw_age=8,control_age=8,sample_age=12):
  return self.native.frame_triple(s or self.sample,LMK,BOOT,SESSION,sequence,sent=sent,raw_age=raw_age,control_age=control_age,sample_age=sample_age)
 def receiver(self,schema=6):
  self.native.reset_capabilities();r=EngineReceiver(MAC,LMK,schema=schema);q=r.query(100,bytes([1])*16)
  r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5000000),MAC,110);q=r.update(True,120,bytes([2])*16)
  r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5010000),MAC,125);return r
 def complete(self,r,triple=None,order=(0,1,2),times=(140,150,160)):
  p=triple or self.triple()
  for index,when in zip(order[:-1],times[:-1]):self.assertIsNone(r.receive(p[index],MAC,when))
  return r.receive(p[order[-1]],MAC,times[-1])
 def test_native_full_bytes_match_independent_layout_and_64bit_counters(self):
  s=copy.deepcopy(self.sample);s['boost_control'].update(pid_updates=str(2**64-1),overboost_events=str(2**53+123))
  p=self.triple(s);self.assertEqual(p,independent_triple(s));self.assertEqual(tuple(map(len,p)),(250,232,144))
  d=self.complete(self.receiver(),p);self.assertEqual(d['boost_control']['pid_updates'],str(2**64-1));self.assertEqual(d['boost_control']['overboost_events'],str(2**53+123))
  self.assertEqual(d['inputs']['map_kpa'],150);self.assertEqual(d['flex_fuel']['ethanol_pct'],50)
  with self.assertRaises(ValueError):engine_telemetry(p[0],KEY,6)
 def test_all_six_orders_only_final_part_can_publish_and_ack(self):
  for order in itertools.permutations(range(3)):
   r=self.receiver();p=self.triple()
   for n,index in enumerate(order):
    data=r.receive(p[index],MAC,140+10*n)
    if n<2:
     self.assertIsNone(data);self.assertIsNone(r.latest);self.assertIsNone(r.received_ms);self.assertEqual(r.last_packet,FLOOR)
     with self.assertRaises(ValueError):r.acknowledgement()
    else:
     self.assertTrue(data['complete_observation']);self.assertEqual(data['datagrams_per_observation'],3)
     self.assertEqual(r.acknowledgement(),engine_acknowledgement(SESSION,FLOOR+1,KEY))
     self.assertTrue(r.status(160)['boost_observation_fresh'])
 def test_missing_any_part_and_duplicate_never_renew_deadline_or_liveness(self):
  for missing in range(3):
   r=self.receiver();p=self.triple();present=[n for n in range(3) if n!=missing]
   r.receive(p[present[0]],MAC,140);r.receive(p[present[1]],MAC,150);r.receive(p[present[0]],MAC,380)
   self.assertEqual(r.partials[FLOOR+1]['started_ms'],140);r.status(391)
   with self.assertRaises(ValueError):r.receive(p[missing],MAC,392)
   self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR)
   with self.assertRaises(ValueError):r.acknowledgement()
 def test_every_tampered_byte_rejects_before_partial_or_liveness(self):
  r=self.receiver();count=0
  for part in self.triple():
   for position in range(len(part)):
    p=bytearray(part);p[position]^=1
    with self.assertRaises(ValueError):r.receive(p,MAC,140)
    self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR);self.assertEqual(len(r.partials),0);count+=1
  self.assertEqual(count,626);self.assertEqual(r.rejected,626)
 def test_signed_bad_metadata_and_numeric_fields_are_retired(self):
  mutations=((20,'H',5),(22,'H',1),(104,'I',2048),(108,'B',17),(109,'B',3),(110,'B',8),(111,'B',1),
             (56,'f',101),(60,'f',math.nan),(64,'f',49),(68,'f',101),(72,'f',401),(76,'f',math.nan),(80,'f',math.inf),(84,'f',-math.inf),(64,'I',0x7fc01234))
  for offset,kind,value in mutations:
   with self.subTest(offset=offset,value=value):
    r=self.receiver();p=replace_part(self.triple(),2,offset,kind,value);r.receive(p[0],MAC,140);r.receive(p[1],MAC,150)
    with self.assertRaises(ValueError):r.receive(p[2],MAC,160)
    self.assertEqual(r.last_packet,FLOOR);self.assertIsNone(r.latest);self.assertGreaterEqual(r.retired_through,FLOOR+1)
 def test_authenticated_conflicts_retire_each_part_even_if_invalid(self):
  for n,offset,value in ((0,81,255),(1,191,1),(2,111,1)):
   r=self.receiver();p=self.triple();r.receive(p[n],MAC,140)
   bad=replace_part(p,n,offset,'B',value)[n]
   with self.assertRaises(ValueError):r.receive(bad,MAC,150)
   self.assertEqual(r.conflicting_pairs,1);self.assertEqual(r.last_packet,FLOOR)
   for index in set(range(3))-{n}:
    with self.assertRaises(ValueError):r.receive(p[index],MAC,160)
 def test_both_extensions_bind_the_full_original_base_mac(self):
  for n in (1,2):
   r=self.receiver();p=self.triple();bad=bytearray(p[n]);bad[24]^=1;p=list(p);p[n]=sign(bad)
   with self.assertRaises(ValueError):self.complete(r,p)
   self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR)
  r=self.receiver();p=replace_part(self.triple(),0,36,'I',77);p=(p[0],self.triple()[1],self.triple()[2])
  with self.assertRaises(ValueError):self.complete(r,p)
 def test_assembly_wait_and_stale_display_do_not_requalify_control(self):
  bounds=[]
  for order in itertools.permutations(range(3)):
   r=self.receiver();d=self.complete(r,order=order,times=(140,150,240));bounds.append(d['bounded_control_age_ms'])
  self.assertEqual(len(set(bounds)),1);self.assertGreater(bounds[0],100)
  r=self.receiver();self.complete(r);s=r.status(160);self.assertTrue(s['boost_valve_allowed_at_source']);self.assertTrue(s['boost_observation_fresh'])
  self.assertFalse(r.status(1140)['boost_observation_fresh']);self.assertEqual(r.status(1140)['boost_current_reason'],'receiver_observation_stale')
  self.assertFalse(r.status(1140)['query_required']);self.assertTrue(r.status(1161)['query_required'])
 def test_flex_can_expire_before_boost_diagnostic_display(self):
  r=self.receiver();self.complete(r);status=r.status(380)
  self.assertFalse(status['flex_value_qualified']);self.assertTrue(status['boost_observation_fresh']);self.assertTrue(status['fresh'])
 def test_incomplete_next_observation_does_not_refresh_prior_ack_or_gap(self):
  r=self.receiver();self.complete(r);ack=r.acknowledgement();p=self.triple(sequence=FLOOR+2,sent=5040000,control_age=18,raw_age=18,sample_age=22)
  r.receive(p[2],MAC,300);r.receive(p[2],MAC,500)
  self.assertEqual(r.acknowledgement(),ack);self.assertEqual(r.received_ms,160);self.assertTrue(r.status(1161)['query_required'])
 def test_capacity_and_absolute_250ms_boundary(self):
  r=self.receiver();p=self.triple();self.assertIsNotNone(self.complete(r,p,times=(140,200,390)))
  r=self.receiver();p=[self.triple(sequence=FLOOR+n,sent=5020000+n*10000,raw_age=n*10-2,control_age=n*10-2,sample_age=n*10+2) for n in (1,2,3)]
  for n in range(3):r.receive(p[n][2],MAC,140+10*n)
  self.assertEqual(len(r.partials),2);self.assertEqual(r.evicted_pairs,1)
  with self.assertRaises(ValueError):r.receive(p[0][0],MAC,170)
  r.receive(p[1][1],MAC,180);self.assertIsNotNone(r.receive(p[1][0],MAC,190));r.receive(p[2][0],MAC,200);self.assertIsNotNone(r.receive(p[2][1],MAC,210))
 def test_pressure_fault_parent_cuts_and_inhibit_are_coherent(self):
  step(self.runtime,1005000,map_kpa=230);s=self.runtime.data();self.assertTrue(s['boost_control']['inhibit_engine']);self.assertEqual(s['controller_faults']&512,512)
  p=self.triple(s,control_age=3,raw_age=8);r=self.receiver();d=self.complete(r,p)
  self.assertTrue(d['boost_control']['overboost_latched']);self.assertTrue(r.status(160)['boost_engine_inhibited_at_source']);self.assertEqual(d['proposals']['pulse_ms'],0)
  for offset,kind,value in ((64,'I',0),(80,'B',3),(22,'H',struct.unpack_from('<H',p[0],22)[0]&~1024),(160,'f',1),(164,'f',1),(192,'f',1)):
   with self.subTest(offset=offset):
    r=self.receiver();bad=replace_part(p,0,offset,kind,value)
    with self.assertRaises(ValueError):self.complete(r,bad)
    self.assertIsNone(r.latest)
  bad=copy.deepcopy(s);bad['proposals']['pulse_ms']=1
  with self.assertRaises(ValueError):self.triple(bad,control_age=3)
 def test_raw_pid_demand_and_terms_are_not_clamped_to_valve_duty(self):
  c=copy.deepcopy(self.runtime.tune);c['boost_control'].update(mode='closed_loop',kp=10,cut_kpa=250)
  for pressure in (120,200):
   r=EngineRuntime(c);self.addCleanup(r.close);edges(r);step(r,map_kpa=pressure);s=r.data();p=self.triple(s)
   self.assertEqual(p,independent_triple(s));d=self.complete(self.receiver(),p)['boost_control']
   self.assertEqual(d['demand_pct'],10*(150-pressure));self.assertTrue(d['demand_pct']>100 or d['demand_pct']<0);self.assertTrue(0<=d['duty_pct']<=100)
 def test_new_format_does_not_relax_na_map_or_legacy_timing_limit(self):
  p=replace_part(self.triple(),2,109,'B',0);p=replace_part(p,2,110,'B',1);p=replace_part(p,2,104,'I',0)
  with self.assertRaises(ValueError):self.complete(self.receiver(),p)
  neutral=EngineRuntime();self.addCleanup(neutral.close);step(neutral);s=neutral.data()
  p=replace_part(self.triple(s,raw_age=2**32-1),0,85,'B',18);d=self.complete(self.receiver(),p);self.assertEqual(d['worker_observation']['timing_fault_code'],18)
  # Timing is the worker's earlier observation; it must not relabel the
  # separately captured, healthy current boost proposal as executed/off.
  p=replace_part(self.triple(),0,85,'B',18);self.assertTrue(self.complete(self.receiver(),p)['boost_control']['valve_allowed'])
  old=self.native.frame_pair(s,LMK,BOOT,SESSION,FLOOR+1,raw_age=2**32-1,sent=5030000);base=bytearray(old[0]);base[85]=18
  legacy=self.receiver(schema=5)
  with self.assertRaises(ValueError):legacy.receive(sign(base),MAC,140)
 def test_unavailable_record_keeps_configuration_but_never_qualifies(self):
  s=copy.deepcopy(self.sample);b=s['boost_control'];b.update(available=False,inhibit_engine=False,flags=0,reason_code=0,reason='disabled',pid_updates='0',overboost_events='0')
  b.update((k,None) for k in VALUES);p=self.triple(s);self.assertEqual(p,independent_triple(s));r=self.receiver();self.complete(r,p)
  status=r.status(160);self.assertTrue(status['boost_pressure_enabled']);self.assertFalse(status['boost_available']);self.assertFalse(status['boost_observation_fresh']);self.assertIsNone(status['boost_engine_inhibited_at_source'])
  for offset,kind,value in ((56,'f',0),(88,'Q',1),(104,'I',1),(108,'B',1),(110,'B',6)):
   with self.assertRaises(ValueError):engine_boost_fragment(replace_part(p,2,offset,kind,value)[2],KEY)
 def test_query_preserves_immutable_boost_and_unknown_age_floor(self):
  r=self.receiver();self.complete(r,self.triple(control_age=2**32-1,raw_age=2**32-1))
  q=r.query(200,bytes([3])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR+10,5090000),MAC,210)
  p=self.triple(sequence=FLOOR+11,sent=5100000,control_age=78,raw_age=78,sample_age=82);self.complete(r,p,times=(220,230,240));self.assertIsNone(r.status(240)['boost_control_age_ms']);self.assertFalse(r.status(240)['boost_observation_fresh'])
  s=copy.deepcopy(self.sample);s['boost_control']['pid_updates']='1';p=self.triple(s,sequence=FLOOR+12,sent=5110000,control_age=88,raw_age=88,sample_age=92)
  with self.assertRaises(ValueError):self.complete(r,p,times=(250,260,270))
  self.assertEqual(r.last_packet,FLOOR+11)
 def test_schema_mismatch_wrong_mac_and_boot_never_publish(self):
  for schema in (1,2,3,4,5):
   with self.subTest(schema=schema):
    r=self.receiver(schema=schema)
    with self.assertRaises(ValueError):r.receive(self.triple()[2],MAC,140)
    self.assertIsNone(r.latest)
  r=self.receiver()
  with self.assertRaises(ValueError):r.receive(self.triple()[0],'02:01:02:03:04:05',140)
  self.assertEqual(r.last_packet,FLOOR)
  p=self.triple();r.receive(p[2],MAC,140);q=r.query(200,bytes([3])*16);r.receive_reply(self.native.capability_reply(q,LMK,SESSION,bytes([99])*16,FLOOR,5090000),MAC,210)
  for part in p:
   with self.assertRaises(ValueError):r.receive(part,MAC,220)
  self.assertIsNone(r.latest);self.assertEqual(len(r.partials),0)

if __name__=='__main__':unittest.main(verbosity=2)
