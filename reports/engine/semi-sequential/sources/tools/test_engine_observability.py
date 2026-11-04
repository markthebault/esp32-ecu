"""Shared C++ recorder/wire tests and an independent Python receiver oracle."""
import copy,csv,hmac,io,json,math,struct,tempfile,unittest
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore
from engine_observability import EngineRecorder
from engine_receiver import (EngineReceiver,capability_request,capability_reply,
 derive_engine_key,engine_telemetry,engine_acknowledgement,DISPLAY_FRESH)
from espnow_protocol import header

LMK=bytes(range(16));BOOT=bytes(range(16,32));MAC='02:EC:00:00:00:01';SESSION=0x12345678
FLOOR=2**53+123

def fixture(sequence=1,now=0):
 with_runtime=EngineRuntime()
 try:
  with_runtime.step(dict(rpm=1234,map_kpa=46,tps_pct=12.5,lambda_ready=False,synced=True),now,use_decoder=False)
  data=with_runtime.data();data['sequence']=str(sequence);return data
 finally:with_runtime.close()

def independent_frame(s,seq=FLOOR+1,sample_age=12,control_age=8,worker_age=4294967295,sent=5030000,nonce=BOOT,schema=2):
 """Encode offsets independently with struct rather than the C++ wire helpers."""
 b=bytearray(232);b[:8]=header(9,232);w=s['worker_observation']
 flags=s['flags']&~DISPLAY_FRESH
 if sample_age<=1000 and control_age<=1000:flags|=DISPLAY_FRESH
 struct.pack_into('<IQHHIIII',b,8,SESSION,seq,schema,flags,sample_age,control_age,s['tune_revision'],s['sensor_revision'])
 struct.pack_into('<QQIIIIIf',b,40,int(s['sequence']),int(w['command_sequence']),s['phase_epoch'],w['epoch'],s['controller_faults'],s['phase_losses'],s['cam_rejected'],s['cam_error_deg'] if s['cam_error_deg'] is not None else math.nan)
 struct.pack_into('<10B',b,80,s['state_code'],s['strategy_code'],s['source_code'],s['phase_reason_code'],s['input_valid_mask'],w['timing_fault_code'],w['last_timing_fault_code'],w['virtual_high_mask'],w['physical_command_mask'],s['board_flags'])
 struct.pack_into('<QIII',b,92,sent,w['tune_revision'],w['sensor_revision'],worker_age)
 struct.pack_into('<8f',b,112,*[v if v is not None else math.nan for v in s['inputs'].values()])
 struct.pack_into('<14f',b,144,*[v if v is not None else math.nan for v in s['proposals'].values()])
 b[200:]=hmac.digest(derive_engine_key(LMK,nonce,SESSION),b[:200],'sha256');return bytes(b)

class ObservationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.sample=fixture(2**53+1,0)
 def setUp(self):self.native=EngineRecorder()
 def tearDown(self):self.native.close()
 def negotiate(self,receiver=None,features=True,boot=BOOT,now=100):
  r=receiver or EngineReceiver(MAC,LMK)
  query=r.query(now,bytes([1])*16)
  reply=self.native.capability_reply(query,LMK,SESSION,boot,FLOOR,5000000)
  r.receive_reply(reply,MAC,now+10)
  if features and not r.features:
   update=r.update(True,now+20,bytes([2])*16)
   reply=self.native.capability_reply(update,LMK,SESSION,boot,FLOOR,5010000)
   r.receive_reply(reply,MAC,now+25)
  return r
 def frame(self,s=None,seq=FLOOR+1,**kw):return self.native.frame(s or self.sample,LMK,BOOT,SESSION,seq,sent=kw.pop('sent',5030000),**kw)
 def test_actual_core_snapshot_preserves_inputs_proposals_and_unknown_lambda(self):
  s=self.sample;self.assertEqual(s['source_code'],2);self.assertEqual(s['inputs']['rpm'],1234)
  self.assertAlmostEqual(s['inputs']['tps_pct'],12.5);self.assertIsNone(s['inputs']['lambda'])
  self.assertEqual(s['raw_adc'],[None]*8);self.assertEqual(s['sensor_revision'],0)
  self.assertEqual(s['sequence'],str(2**53+1));self.assertGreater(s['proposals']['pulse_ms'],0)
  self.assertIn('not proof',s['worker_observation']['meaning'])
 def test_independent_python_and_cpp_engine_frames_are_byte_identical(self):
  native=self.frame(sample_age=12,control_age=8)
  self.assertEqual(native,independent_frame(self.sample));self.assertEqual(len(native),232)
  data=engine_telemetry(native,derive_engine_key(LMK,BOOT,SESSION))
  self.assertEqual(data['proposal_sequence'],2**53+1);self.assertEqual(data['packet_sequence'],FLOOR+1)
  self.assertIsNone(data['inputs']['lambda']);self.assertEqual(data['worker_observation']['age_ms'],None)
 def test_independent_capability_reply_and_full_length_derived_hmac(self):
  request=capability_request(LMK,nonce=bytes([7])*16)
  reply=self.native.capability_reply(request,LMK,SESSION,BOOT,FLOOR,5000000)
  body=header(8,108)+struct.pack('<II16sIII16sQQ',SESSION,0,bytes([7])*16,0,0,0,BOOT,FLOOR,5000000)
  self.assertEqual(reply,body+hmac.digest(LMK,body,'sha256'))
  data=capability_reply(reply,LMK,bytes([7])*16);self.assertEqual(data['sequence_floor'],FLOOR)
  key=derive_engine_key(LMK,BOOT,SESSION);frame=self.frame()
  self.assertFalse(hmac.compare_digest(frame[200:],hmac.digest(key[:16],frame[:200],'sha256')))
 def test_capability_retries_counter_conflicts_and_query_recovery(self):
  r=self.negotiate();self.assertEqual(r.counter,1);self.assertEqual(r.features,1)
  request=capability_request(LMK,SESSION,1,1,bytes([2])*16)
  self.native.capability_reply(request,LMK,SESSION,BOOT,FLOOR,5010000)
  for old in [capability_request(LMK,SESSION,1,1,bytes([3])*16),capability_request(LMK,SESSION+1,2,0,bytes([4])*16),request[:-1]+bytes([request[-1]^1])]:
   with self.assertRaises(ValueError):self.native.capability_reply(old,LMK,SESSION,BOOT,FLOOR,5010000)
  restarted=EngineReceiver(MAC,LMK);self.negotiate(restarted)
  self.assertEqual(restarted.counter,1);update=restarted.update(False,130,bytes([3])*16)
  self.assertEqual(restarted.retry(),update)
  restarted.receive_reply(self.native.capability_reply(update,LMK,SESSION,BOOT,FLOOR,5020000),MAC,135)
  self.assertEqual(restarted.features,0);self.assertEqual(restarted.counter,2)
  self.native.reset_capabilities();q=capability_request(LMK,nonce=bytes([9])*16)
  self.assertEqual(capability_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,0,0),LMK,bytes([9])*16)['counter'],0)
 def test_authenticated_nonce_reply_must_match_request_and_deadline(self):
  r=EngineReceiver(MAC,LMK);q=r.query(100,bytes([1])*16)
  reply=self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5000000)
  for packet,mac,stamp in [(reply[:-1]+bytes([reply[-1]^1]),MAC,110),(reply,'02:EC:00:00:00:02',110),(reply,MAC,1101)]:
   with self.assertRaises(ValueError):r.receive_reply(packet,mac,stamp)
   self.assertIsNone(r.data_key)
  r.receive_reply(reply,MAC,110);self.assertFalse(r.status(111)['query_required']);self.assertFalse(r.status(111)['fresh'])
 def test_receiver_ages_clock_interval_and_stale_gap_require_query(self):
  r=self.negotiate();data=r.receive(self.frame(sample_age=12,control_age=8),MAC,150)
  self.assertEqual(data['transport_age_bound_ms'],13);self.assertEqual(data['bounded_sample_age_ms'],26)
  self.assertTrue(r.status(150)['fresh']);self.assertEqual(r.status(200)['sample_age_ms'],76)
  self.assertTrue(r.status(1151)['query_required']);self.assertFalse(r.status(1151)['fresh'])
  with self.assertRaisesRegex(ValueError,'Stale gap'):r.receive(self.frame(seq=FLOOR+2,sent=6100000),MAC,1200)
  with self.assertRaisesRegex(ValueError,'clock query'):r.receive(self.frame(seq=FLOOR+2,sent=10000000),MAC,5200)
 def test_slow_source_clock_history_cannot_cross_freshness_threshold(self):
  r=EngineReceiver(MAC,LMK);q=r.query(0,bytes([1])*16)
  r.receive_reply(self.native.capability_reply(q,LMK,SESSION,BOOT,FLOOR,5000000),MAC,0)
  update=r.update(True,0,bytes([2])*16)
  r.receive_reply(self.native.capability_reply(update,LMK,SESSION,BOOT,FLOOR,5000000),MAC,0)
  packet=self.frame(sample_age=990,control_age=990,worker_age=990,sent=5009800)
  value=r.receive(packet,MAC,10)
  self.assertGreater(value['bounded_sample_age_ms'],1000);self.assertGreater(value['bounded_worker_age_ms'],1000);self.assertFalse(r.status(10)['fresh'])
 def test_first_frame_after_a_long_initial_gap_requires_new_query(self):
  r=self.negotiate();self.assertTrue(r.status(1126)['query_required'])
  with self.assertRaisesRegex(ValueError,'Stale gap'):r.receive(self.frame(sent=6010000),MAC,1126)
 def test_new_screen_query_floor_rejects_same_boot_recorded_frame(self):
  r=self.negotiate()
  for seq in (FLOOR-1,FLOOR):
   with self.assertRaises(ValueError):r.receive(self.frame(seq=seq),MAC,150)
  r.receive(self.frame(seq=FLOOR+1),MAC,150)
  with self.assertRaises(ValueError):r.receive(self.frame(seq=FLOOR+1),MAC,151)
  self.assertEqual(r.last_packet,FLOOR+1)
 def test_boot_nonce_rejects_old_engine_even_if_session32_collides(self):
  old=self.frame();self.native.reset_capabilities();boot=bytes([55])*16
  r=self.negotiate(boot=boot)
  with self.assertRaisesRegex(ValueError,'authentication'):r.receive(old,MAC,150)
  new=self.native.frame(self.sample,LMK,boot,SESSION,FLOOR+1,sent=5030000)
  r.receive(new,MAC,150);self.assertTrue(r.status(150)['fresh'])
 def test_each_tampered_byte_fails_without_advancing_receiver_state(self):
  r=self.negotiate();frame=self.frame()
  for i in range(len(frame)):
   changed=bytearray(frame);changed[i]^=1
   with self.assertRaises(ValueError):r.receive(bytes(changed),MAC,150)
   self.assertIsNone(r.latest);self.assertEqual(r.last_packet,FLOOR)
  self.assertEqual(r.rejected,232);r.receive(frame,MAC,150)
 def test_repeated_observation_cannot_rejuvenate_age_or_change_payload(self):
  r=self.negotiate();r.receive(self.frame(sample_age=900,control_age=900),MAC,150)
  again=r.receive(self.frame(seq=FLOOR+2,sample_age=0,control_age=0,sent=5130000),MAC,250)
  self.assertGreaterEqual(again['bounded_sample_age_ms'],1013);self.assertFalse(r.status(250)['fresh'])
  changed=copy.deepcopy(self.sample);changed['proposals']['advance_deg']+=1
  with self.assertRaisesRegex(ValueError,'payload changed'):r.receive(self.frame(changed,seq=FLOOR+3,sent=5140000),MAC,260)
  self.assertEqual(r.last_packet,FLOOR+2)
 def test_signed_schema_faults_and_sender_clock_reversal_are_rejected(self):
  key=derive_engine_key(LMK,BOOT,SESSION);original=self.frame()
  for offset,value in [(20,3),(82,0),(89,16),(90,1)]:
   packet=bytearray(original);packet[offset]=value;packet[200:]=hmac.digest(key,packet[:200],'sha256')
   with self.assertRaises(ValueError):engine_telemetry(bytes(packet),key)
  r=self.negotiate();r.receive(original,MAC,150)
  with self.assertRaises(ValueError):r.receive(self.frame(seq=FLOOR+2,sent=5029000),MAC,151)
 def test_engine_ack_is_bound_to_boot_session_and_64bit_packet_id(self):
  r=self.negotiate();r.receive(self.frame(),MAC,150);packet=r.acknowledgement()
  body=header(10,56)+struct.pack('<IQI',SESSION,FLOOR+1,0)
  self.assertEqual(packet,body+hmac.digest(derive_engine_key(LMK,BOOT,SESSION),body,'sha256'))
  self.assertEqual(packet,engine_acknowledgement(SESSION,FLOOR+1,r.data_key));self.assertEqual(len(packet),56)
 def test_ring_overwrite_copied_pages_and_superseded_log_identity(self):
  self.assertEqual(self.native.command(dict(action='start',period_ms=20,duration_s=60),0),200)
  for i in range(600):
   s=copy.deepcopy(self.sample);s.update(sequence=str(i+1),control_us=str(i*20000),sampled_us=str(i*20000));self.assertTrue(self.native.append(s,i*20000))
  h=self.native.header();self.assertEqual((h['total'],h['retained'],h['overwritten']),(600,256,344))
  page=self.native.page(h['log_id'],0);self.assertEqual((page['gap_first'],page['gap_last'],page['next_after']),(1,344,360));saved=copy.deepcopy(page)
  for i in range(600,620):
   s=copy.deepcopy(self.sample);s.update(sequence=str(i+1),control_us=str(i*20000),sampled_us=str(i*20000));self.native.append(s,i*20000)
  self.assertEqual(saved,page)
  self.assertEqual(self.native.command(dict(action='stop',log_id=1),12400000),200)
  self.assertEqual(self.native.command(dict(action='start',period_ms=100,duration_s=1),12400000),200)
  self.assertTrue(self.native.page(1,0)['snapshot_superseded']);self.assertEqual(self.native.command(dict(action='stop',log_id=1),12400001),409)
 def test_schedule_misses_repeats_invalid_and_expire_without_new_data(self):
  self.native.command(dict(action='start',period_ms=100,duration_s=2),0)
  self.assertTrue(self.native.append(self.sample,0))
  s=copy.deepcopy(self.sample);s['sequence']=str(2**53+2);s['control_us']=s['sampled_us']='375000';self.assertTrue(self.native.append(s,375000))
  self.assertFalse(self.native.append(s,400000));s['sequence']=str(2**53+3);s['control_us']=s['sampled_us']='600000';self.assertFalse(self.native.append(s,500000))
  h=self.native.header();self.assertEqual((h['total'],h['missed_periods'],h['repeated_skipped'],h['invalid_skipped']),(2,2,1,1))
  self.native.expire(2000000);self.assertEqual(self.native.header()['state'],'timeout');self.assertEqual(self.native.header()['missed_periods'],16)
 def test_strict_commands_and_unknown_or_future_snapshot_fields(self):
  for body in [b'{"action":"start","period_ms":20,"duration_s":1,"x":0}',b'{"action":"start","action":"stop","period_ms":20,"duration_s":1}',b'{"action":"start","period_ms":20,"duration_s":1}\0',b'{"action":"start","period_ms":true,"duration_s":1}',b'{"action":"start","period_ms":20,"duration_s":901}']:
   self.assertEqual(self.native.command(body,0),422)
  bad=copy.deepcopy(self.sample);bad['sequence']='18446744073709551616'
  with self.assertRaises(ValueError):self.native.append(bad,0)
 def test_msl_has_equal_79_columns_and_unknown_values_are_nan(self):
  self.native.command(dict(action='start',period_ms=20,duration_s=1),0);self.native.append(self.sample,0)
  with self.assertRaises(ValueError):self.native.msl(1)
  self.native.command(dict(action='stop',log_id=1),1000)
  text=self.native.msl(1);rows=list(csv.reader(io.StringIO(text),delimiter='\t'))
  self.assertIn('SYNTHETIC ENGINE REPLAY',text);self.assertEqual([len(r) for r in rows[2:]],[91,91,91])
  record=dict(zip(rows[2],rows[4]));self.assertEqual(record['SnapshotSequence'],str(2**53+1));self.assertEqual(record['Lambda'],'NaN');self.assertEqual(record['ADC0'],'NaN')
 def test_completed_sil_replay_preserves_original_revisions_after_tune_save(self):
  with tempfile.TemporaryDirectory() as directory:
   store=EngineStore(Path(directory)/'engine.json');h=store.data_log_header();boot=h['boot_id']
   self.assertEqual(store.data_log_command(b'{"action":"start","period_ms":100,"duration_s":3}',boot)[0],409)
   self.assertEqual(store.run(dict(scenario='warm_start',duration_s=3))[0],200)
   code,h=store.data_log_command(b'{"action":"start","period_ms":100,"duration_s":3}',boot);self.assertEqual(code,200)
   self.assertTrue(h['historical']);self.assertEqual(h['data_source'],'synthetic_control_observation');self.assertGreaterEqual(h['total'],29)
   page=store.data_log_page(h['log_id'],0,boot)[1];self.assertEqual(page['records'][0]['sample']['tune_revision'],1)
   tune=copy.deepcopy(store.tune);self.assertEqual(store.save(json.dumps(tune).encode())[0],200)
   self.assertEqual(store.data_log_page(h['log_id'],0,boot)[1]['records'],page['records']);self.assertFalse(store.coherent_sample()['available'])
   self.assertEqual(store.data_log_page(h['log_id'],0,'0'*32)[0],409)

if __name__=='__main__':unittest.main(verbosity=2)
