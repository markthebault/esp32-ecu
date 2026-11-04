"""Sequential configuration, phase supervision and compatibility regression."""
import copy,json,struct,tempfile,unittest
from pathlib import Path
from unittest import mock
from engine_runtime import EngineRuntime,EngineStore,R
from target_runtime import TargetRuntime
from engine_protocol import Session,pages,decode_pages,live_block,SIGNATURE,LEGACY_SIGNATURE
from engine_msq import export_msq,import_msq
from engine_sil import Simulation

class SequentialTests(unittest.TestCase):
 def setUp(self):
  self.tune=json.loads((R/'config/engine/defaults.json').read_text())
  self.seq=copy.deepcopy(self.tune);self.seq['strategy']='sequential_4cyl'
 def legacy(self):
  old=copy.deepcopy(self.tune);old['schema_version']=1;del old['timing'];del old['cylinder_trims'];del old['idle_control'];del old['transient_enrichment'];del old['load_model'];del old['secondary_tables'];return old
 def test_exact_legacy_migration_preserves_file_and_revision(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'old.json';old=self.legacy();old['revision']=1000000001;body=json.dumps(old,indent=1).encode();path.write_bytes(body)
   store=EngineStore(path);self.assertTrue(store.storage_ok);self.assertEqual(path.read_bytes(),body);self.assertEqual(store.tune['schema_version'],8);self.assertEqual(store.tune['revision'],old['revision']);self.assertEqual(store.tune['timing'],self.tune['timing'])
   code,saved=store.save(body);self.assertEqual(code,200);self.assertEqual(saved['revision'],1000000002);self.assertEqual(json.loads(path.read_bytes())['schema_version'],8)
 def test_schema_aliases_unknown_modes_and_invalid_orders_rejected(self):
  r=EngineRuntime()
  for old in (False,True):
   body=json.dumps(self.legacy() if old else self.seq)
   for src,dst in [('"revision"','"revision\\u0000alias"'),('"inhibited"','"inhibited\\u0000alias"'),('"batch_wasted_4cyl"' if old else '"sequential_4cyl"','"batch_wasted_4cyl\\u0000alias"')]:self.assertFalse(r.bridge.engine_validate(body.replace(src,dst).encode()))
  for strategy in ('unknown','semi_sequential_6cyl'):
   bad=copy.deepcopy(self.seq);bad['strategy']=strategy
   with self.assertRaises(ValueError):r.configure(bad)
  for order in ([1,3,3,2],[2,1,3,4],[1,2,3],[1,2,3,5],[1,2,3,True],[1,2,3,3.5]):
   bad=copy.deepcopy(self.seq);bad['timing']['firing_order']=order
   with self.assertRaises(ValueError):r.configure(bad)
  for version in (0,1,3,9):
   bad=copy.deepcopy(self.seq);bad['schema_version']=version
   with self.assertRaises(ValueError):r.configure(bad)
  r.close()
 def test_event_mode_classification_separates_partial_and_unsynced(self):
  from sequential_metrics import sequential_metrics
  rows=[dict(sync_status=sync,ignition_cycle_deg=span,phase_error_deg=350,rpm=1000) for sync,span in [(2,720),(1,360),(0,360),(0,720)]]
  m=sequential_metrics(rows);self.assertEqual(m['wrong_stroke_sparks'],1);self.assertEqual(m['wasted_fallback_discharges'],1);self.assertEqual(m['unsynced_discharges'],2);self.assertEqual(m['unsynced_720_discharges'],1)
 def test_msq002_roundtrip_and001_explicit_batch_migration(self):
  self.seq['timing']['firing_order']=[1,2,4,3];self.seq['timing']['cam_sync_deg']=123.5
  decoded=import_msq(export_msq(self.seq));self.assertEqual(decoded,self.seq);pages(decoded)
  old=import_msq((R/'tuning/examples/tunerstudio-roundtrip.msq').read_bytes());self.assertEqual(old['strategy'],'batch_wasted_4cyl');self.assertEqual(old['schema_version'],8);self.assertEqual(old['timing'],self.tune['timing']);self.assertEqual(old['maps']['ve']['cells'][53],92.5)
  body=export_msq(self.seq)
  with self.assertRaises(ValueError):import_msq(body.replace(SIGNATURE.decode(),LEGACY_SIGNATURE.decode()))
 def test_protocol_appended_fields_commit_and_legacy_prefix(self):
  p=pages(self.seq);self.assertEqual(struct.unpack_from('<I',p[1],268)[0],1);self.assertEqual(struct.unpack_from('<I',p[1],272)[0],1);self.assertEqual(list(p[1][288:292]),[1,3,4,2]);self.assertEqual(decode_pages(p,self.seq)['timing'],self.seq['timing'])
  self.assertEqual(p[1][:272],pages(self.tune)[1][:272])
  with tempfile.TemporaryDirectory() as d:
   store=EngineStore(Path(d)/'tune.json');session=Session(store)
   data=p[1][272:292];self.assertEqual(session.command(b'M'+struct.pack('<BBHH',0,1,272,20)+data),b'\0');self.assertEqual(session.command(b'b\0\1'),b'\4');self.assertEqual(store.tune['strategy'],'sequential_4cyl')
   block=live_block(store);self.assertEqual(len(block),640);self.assertEqual(struct.unpack_from('<I',block,92)[0],1);self.assertEqual(struct.unpack_from('<I',block,52)[0],1)
 def test_prepare_failure_cannot_change_persistent_or_runtime_tune(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'tune.json';store=EngineStore(path);self.assertEqual(store.save(json.dumps(self.tune).encode())[0],200);before=path.read_bytes();runtime=store.runtime;self.seq['revision']=2
   with mock.patch('engine_runtime.EngineRuntime',side_effect=MemoryError):self.assertEqual(store.save(json.dumps(self.seq).encode())[0],500)
   self.assertEqual(path.read_bytes(),before);self.assertIs(store.runtime,runtime);self.assertEqual(store.tune['strategy'],'batch_wasted_4cyl')
 def test_sequential_warm_sil_uses_full_phase_and_cold_limits_remain(self):
  r=Simulation(self.seq,duration_s=6).run();s=r['summary'];self.assertTrue(s['sync_acquired']);self.assertGreater(s['final_rpm'],500);self.assertEqual(s['wrong_stroke_sparks'],0);self.assertLess(s['max_spark_720_error_deg'],.2);self.assertGreater(len(r['cam_edges']),5);self.assertEqual(r['final']['phase_losses'],0)
  runtime=EngineRuntime(self.seq);out=runtime.step(dict(rpm=200,synced=True,phase_synced=True,clt_c=0,map_kpa=100),1000,use_decoder=False);self.assertTrue(out['faults']&64);self.assertTrue(out['fuel_cut']);runtime.close()
 def test_phase_latch_requires_both_inputs_quiet_before_recovery(self):
  for cls in (EngineRuntime,TargetRuntime):
   runtime=cls(self.seq);runtime.wheel()
   def drain(us):
    while runtime.next_event_us()<=us:
     event=runtime.pop_event()
     if event is None:raise AssertionError('Missing due virtual event')
     if event[0] is None:runtime.cut()
   for n in range(500):
    us=n*1000;drain(us)
    if n%60<58:runtime.trigger(us)
    if n in (90,210,330):runtime.cam(us)
    if n==350:self.assertEqual(runtime.cam(us),3)
    out=runtime.step({},us)
    if out['faults'] or out['state']=='stopped':runtime.cut()
   self.assertEqual(out['phase_losses'],1);self.assertEqual(out['timing_recoveries'],0);self.assertEqual(out['timing_stop_reason'],'cam_phase_lost')
   for n in range(500,800):
    us=n*1000;drain(us)
    if n%10==0:runtime.cam(us)
    out=runtime.step({},us);runtime.cut()
   self.assertEqual(out['timing_recoveries'],0)
   for n in range(800,980):
    us=n*1000;drain(us);out=runtime.step({},us);runtime.cut()
   self.assertEqual(out['timing_recoveries'],1);self.assertEqual(out['phase_losses'],1);self.assertFalse(out['phase_synced']);self.assertEqual(out['faults'],0);runtime.close()

if __name__=='__main__':unittest.main()
