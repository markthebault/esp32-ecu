import copy,csv,json,struct,tempfile,unittest
from unittest import mock
from pathlib import Path
from engine_runtime import EngineRuntime,EngineStore,R
from engine_sil import Simulation
from engine_protocol import Session,Stream,envelope,pages,decode_pages,SIGNATURE,SERIAL_PROTOCOL
from engine_msq import export_msq,import_msq

class EngineTests(unittest.TestCase):
 def setUp(self):self.tune=json.loads((R/'config/engine/defaults.json').read_text())
 def test_default_tune_is_valid_but_cannot_enable_physical_outputs(self):
  r=EngineRuntime(self.tune);out=r.step(dict(rpm=1000,synced=True),1000,use_decoder=False);self.assertFalse(out['physical_outputs_enabled']);self.assertGreater(out['pulse_ms'],0)
  bad=copy.deepcopy(self.tune);bad['physical_outputs']='enabled'
  with self.assertRaises(ValueError):r.configure(bad)
 def test_unconfirmed_or_stale_inputs_inhibit_proposals(self):
  for changes,now,sampled in [({'sensors_valid':False},1000,1000),({},30000,0),({'synced':False},1000,1000)]:
   r=EngineRuntime();out=r.step(dict(rpm=1000,synced=True,**changes) if 'synced' not in changes else dict(rpm=1000,**changes),now,sampled,use_decoder=False);self.assertNotEqual(out['faults'],0);self.assertTrue(out['fuel_cut']);self.assertFalse(r.plan()['valid']);r.close()
 def test_stored_tune_revision_and_restart(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'tune.json';store=EngineStore(path);self.tune['maps']['ve']['cells'][10]=90
   code,saved=store.save(json.dumps(self.tune).encode());self.assertEqual(code,200);self.assertEqual(saved['revision'],2)
   self.assertEqual(store.save(json.dumps(self.tune).encode())[0],409)
   self.assertEqual(EngineStore(path).tune['maps']['ve']['cells'][10],90)
 def test_corrupt_store_preserved_and_invalid_axes_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'tune.json';path.write_text('{corrupt');store=EngineStore(path);self.assertFalse(store.storage_ok);self.assertEqual(store.save(json.dumps(self.tune).encode())[0],503);self.assertEqual(path.read_text(),'{corrupt')
   path.unlink();store=EngineStore(path);bad=copy.deepcopy(self.tune);bad['maps']['ve']['rpm'][1]=80;self.assertEqual(store.save(json.dumps(bad).encode())[0],422)
   self.assertEqual(store.save(json.dumps(self.tune).encode()+b'\0junk')[0],422)
 def test_protocol_query_read_write_burn_restart_and_bounds(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'tune.json';store=EngineStore(path);session=Session(store)
   self.assertEqual(session.command(b'Q'),b'\0'+SIGNATURE)
   self.assertEqual(session.command(b'F'),b'\0'+b'002')
   self.assertEqual(session.command(b'f\0')[1],int(SERIAL_PROTOCOL))
   stream=Stream(store);self.assertEqual(stream.feed(b'F'),[b'002'])
   self.assertEqual(stream.feed(envelope(b'F')),[envelope(b'\0'+b'002')])
   request=b'p'+struct.pack('<BBHH',0,1,640,4)
   self.assertAlmostEqual(struct.unpack('<f',session.command(request)[1:])[0],85)
   write=b'M'+struct.pack('<BBHH',0,1,640,4)+struct.pack('<f',91)
   self.assertEqual(session.command(write),b'\0');self.assertEqual(store.tune['maps']['ve']['cells'][0],85)
   self.assertEqual(session.command(b'b\0\1'),b'\x04');self.assertEqual(EngineStore(path).tune['maps']['ve']['cells'][0],91)
   self.assertEqual(session.command(b'p'+struct.pack('<BBHH',0,1,4990,10)),b'\x84')
   self.assertEqual(session.command(b'M'+struct.pack('<BBHH',0,1,640,4)+struct.pack('<f',999)),b'\0')
   self.assertEqual(session.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['maps']['ve']['cells'][0],91)
 def test_tuner_and_http_writers_conflict_instead_of_overwriting(self):
  with tempfile.TemporaryDirectory() as d:
   store=EngineStore(Path(d)/'tune.json');s=Session(store)
   self.assertEqual(s.command(b'M'+struct.pack('<BBHH',0,1,640,4)+struct.pack('<f',91)),b'\0')
   self.tune['maps']['ve']['cells'][0]=88;self.assertEqual(store.save(json.dumps(self.tune).encode())[0],200)
   self.assertEqual(s.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['maps']['ve']['cells'][0],88)
 def test_offline_msq_roundtrip_and_identity_rejection(self):
  self.tune['maps']['ve']['cells'][53]=93.75;self.tune['settings']['ego_enabled']=True
  body=export_msq(self.tune);decoded=import_msq(body)
  self.assertEqual(decoded,self.tune)
  for invalid in [body.replace(SIGNATURE.decode(),'speeduino 202504-dev'),body.replace('93.75','999'),body.replace('<msq ','<!DOCTYPE msq><msq ',1),body.replace('baseRevision','unknownConstant')]:
   with self.assertRaises(ValueError):import_msq(invalid)
 def test_tuning_snapshot_stays_pinned_and_revision_is_read_only(self):
  with tempfile.TemporaryDirectory() as d:
   store=EngineStore(Path(d)/'tune.json');session=Session(store)
   self.tune['maps']['ve']['cells'][0]=88;self.assertEqual(store.save(json.dumps(self.tune).encode())[0],200)
   request=b'p'+struct.pack('<BBHH',0,1,640,4)
   self.assertEqual(struct.unpack('<f',session.command(request)[1:])[0],85)
   self.assertEqual(struct.unpack('<f',Session(store).command(request)[1:])[0],88)
   self.assertEqual(session.command(b'M'+struct.pack('<BBHH',0,1,268,4)+struct.pack('<I',99)),b'\x84')
   self.assertEqual(session.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['revision'],2)
 def test_clean_cached_tuner_cannot_overwrite_an_http_edit(self):
  with tempfile.TemporaryDirectory() as d:
   store=EngineStore(Path(d)/'tune.json');session=Session(store)
   before=session.command(b'p'+struct.pack('<BBHH',0,1,512,256))[1:]
   self.tune['maps']['ve']['cells'][0]=88;self.assertEqual(store.save(json.dumps(self.tune).encode())[0],200)
   # Live polling and later chunks must not change the calibration base.
   session.command(b'r'+struct.pack('<BBHH',0,0x30,0,76))
   self.assertEqual(session.command(b'p'+struct.pack('<BBHH',0,1,512,256))[1:],before)
   cached=bytearray(before);struct.pack_into('<f',cached,132,90)
   self.assertEqual(session.command(b'M'+struct.pack('<BBHH',0,1,512,256)+cached),b'\x84')
   self.assertEqual(session.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['maps']['ve']['cells'][0],88)
 def test_msq_revision_is_lossless_at_uint32_boundaries(self):
  for revision in (1,1.0,1000000001,1000000001.0,4294967295,4294967295.0):
   self.tune['revision']=revision;self.assertEqual(import_msq(export_msq(self.tune))['revision'],revision)
 def test_dwell_protection_recovers_only_after_acknowledged_fresh_stop(self):
  evidence=Simulation(self.tune,'load_stall_restart',12,17).run()
  self.assertEqual(evidence['summary']['timing_protection_stops'],1)
  self.assertEqual(evidence['summary']['timing_recoveries'],1)
  self.assertEqual(evidence['summary']['final_faults'],0);self.assertGreater(evidence['summary']['final_rpm'],500)
  self.assertEqual(evidence['timing_stops'][0]['reason'],'dwell_limit')
  runtime=EngineRuntime(self.tune);teeth=iter(evidence['trigger_edges']);tooth=next(teeth,None);now=0;failed=False
  while now<6000000 and not failed:
   while tooth and tooth[0]<=now:
    while runtime.next_event_us()<=tooth[0]:runtime.pop_event()
    failed=runtime.trigger(tooth[0])==3;tooth=next(teeth,None)
    if failed:break
   if failed:break
   while runtime.next_event_us()<=now:runtime.pop_event()
   runtime.step({},now,use_decoder=True);now+=1000
  self.assertTrue(failed)
  # Deliberately withhold the executor's global-low acknowledgement.
  for i in range(1000):status=runtime.step({},now+1000*i,use_decoder=True)
  self.assertGreater(status['executor_high_mask'],0);self.assertEqual(status['timing_recoveries'],0)
  self.assertEqual(status['rpm'],0);runtime.cut();now+=1000000
  for i in range(9):status=runtime.step({},now+1000*i,use_decoder=True)
  self.assertEqual(status['timing_recoveries'],0)
  with self.assertRaises(ValueError):runtime.step({'lambda':'invalid'},now+9000,use_decoder=True)
  for i in range(10,25):status=runtime.step({},now+1000*i,use_decoder=True)
  self.assertEqual(status['timing_recoveries'],0)
  # A control-sample gap beyond the deadman period also restarts the interval.
  status=runtime.step({},now+50000,use_decoder=True);self.assertEqual(status['timing_recoveries'],0)
  for i in range(51,71):status=runtime.step({},now+1000*i,use_decoder=True)
  self.assertEqual(status['timing_recoveries'],1);self.assertEqual(status['timing_stop_reason'],'dwell_limit')
  self.assertEqual(status['state'],'stopped');runtime.close()
 def test_integral_json_float_revision_stays_canonical_across_restart(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'tune.json';self.tune['revision']=1.0;path.write_text(json.dumps(self.tune))
   store=EngineStore(path);self.assertIs(type(store.tune['revision']),int);Session(store)
   self.assertEqual(store.save(json.dumps(self.tune).encode())[0],200)
   self.assertIs(type(store.tune['revision']),int);Session(store);Session(EngineStore(path))
 def test_persistence_error_blocks_later_saves_until_restart(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'tune.json';store=EngineStore(path);code,current=store.save(json.dumps(self.tune).encode());self.assertEqual(code,200);before=path.read_bytes()
   with mock.patch('engine_runtime.os.replace',side_effect=OSError('injected write error')):
    self.assertEqual(store.save(json.dumps(current).encode())[0],507)
   self.assertFalse(store.storage_ok);self.assertEqual(path.read_bytes(),before);self.assertEqual(store.tune,current)
   self.assertEqual(store.save(json.dumps(current).encode())[0],503);self.assertTrue(EngineStore(path).storage_ok)
 def test_partition_layout_preserves_existing_records_and_app_offsets(self):
  rows=list(csv.reader(line for line in (R/'firmware/partitions.csv').read_text().splitlines() if line and not line.startswith('#')))
  parts={row[0]:(int(row[3],0),int(row[4],0)) for row in rows}
  self.assertEqual(parts['nvs'],(0x9000,0x6000));self.assertEqual(parts['phy_init'],(0xf000,0x1000));self.assertEqual(parts['factory'],(0x10000,0x200000));self.assertEqual(parts['engine_nvs'],(0x210000,0x10000))
  ranges=sorted((offset,offset+size,name) for name,(offset,size) in parts.items())
  for earlier,later in zip(ranges,ranges[1:]):self.assertLessEqual(earlier[1],later[0])
  self.assertLessEqual(ranges[-1][1],8*1024*1024)
 def test_warm_and_cold_closed_loop_start_on_generated_teeth(self):
  for scenario in ['warm_start','cold_start']:
   result=Simulation(self.tune,scenario,10).run();s=result['summary'];self.assertTrue(s['sync_acquired']);self.assertGreater(s['final_rpm'],500,s);self.assertGreater(s['fuel_mg'],0);self.assertGreater(s['sparks'],0);self.assertEqual(s['rejected_plans'],0);self.assertLessEqual(s['max_injector_high_us'],15000);self.assertLessEqual(s['max_dwell_high_us'],3500);self.assertLess(s['max_spark_error_deg'],2);self.assertEqual(s['final_outputs_high'],0)
 def test_dropouts_and_sensor_short_stop_virtual_outputs(self):
  for scenario in ['trigger_dropout','sensor_short']:
   result=Simulation(self.tune,scenario,6).run();s=result['summary'];self.assertEqual(s['final_outputs_high'],0);self.assertLess(s['final_rpm'],100,s);self.assertTrue(any(p['fuel_cut'] for p in result['trace'] if p['time']>4.2))
 def test_hard_rev_limit_in_closed_loop(self):
  self.tune['settings'].update(rpm_limit=3000,rpm_hysteresis=150,soft_limit_band=0)
  result=Simulation(self.tune,'overrev',12).run();s=result['summary'];self.assertTrue(s['fault_mask_seen']&32,s);self.assertLess(s['max_rpm'],3300,s);self.assertEqual(s['rejected_plans'],0);self.assertLess(s['max_spark_error_deg'],2)
 def test_stale_control_deadline_and_invalid_sample_cut_native_events(self):
  runtime=EngineRuntime();runtime.wheel()
  def advance(until,control):
   events=[]
   for slot in range(advance.slot,until):
    now=slot*1000
    while runtime.next_event_us()<=now:
     event_us=runtime.next_event_us();event=runtime.pop_event();events.append((event_us,event))
    if slot%60<58:runtime.trigger(now)
    if control:runtime.step({},now,use_decoder=True)
   advance.slot=until
   return events
  advance.slot=0;advance(180,True);events=advance(360,False)
  self.assertTrue(any(event[0] is None for us,event in events),'Freshness expiry must produce an explicit cut')
  self.assertFalse(any(us>199000 and event[0] is not None and event[1] for us,event in events))
  self.assertEqual(runtime.next_event_us(),2**64-1)
  advance(540,True);runtime.step({'sensors_valid':False},540000,use_decoder=True)
  self.assertEqual(runtime.next_event_us(),2**64-1);runtime.close()
 def test_saved_edge_trace_reconstructs_shutdown(self):
  # More than 4096 edges catches the old silent log truncation.
  result=Simulation(self.tune,'overrev',12).run();mask=0
  self.assertGreater(len(result['edges']),4096)
  self.assertGreater(result['edges'][-1][0],11000000)
  for us,ch,high,cause in result['edges']:
   self.assertNotEqual(bool(mask&(1<<ch)),high)
   mask=mask|(1<<ch) if high else mask&~(1<<ch)
  self.assertEqual(mask,0)
 def test_plant_is_deterministic_and_parameters_are_seeded(self):
  a=Simulation(self.tune,'warm_start',3,3).run();b=Simulation(self.tune,'warm_start',3,3).run();c=Simulation(self.tune,'warm_start',3,4).run();self.assertEqual(a,b);self.assertNotEqual(a['summary']['plant_parameters'],c['summary']['plant_parameters'])
 def test_zero_fuel_tune_cannot_make_the_plant_run(self):
  # Faulted control must not be bypassed by a pre-recorded RPM trajectory.
  self.tune['engine']['injector_cc_min']=100;self.tune['settings']['max_injection_ms']=1
  result=Simulation(self.tune,'warm_start',6).run();self.assertEqual(result['summary']['fuel_mg'],0);self.assertEqual(result['summary']['final_rpm'],0)
if __name__=='__main__':unittest.main(verbosity=2)
