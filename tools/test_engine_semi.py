"""Semi-sequential execution, schema migration and negotiated telemetry oracles."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path

from engine_runtime import EngineRuntime,EngineStore,R
from target_runtime import TargetRuntime
from engine_protocol import pages,decode_pages,Session,SIGNATURE,IDLE_SIGNATURE
from engine_msq import export_msq,import_msq
from engine_observability import EngineRecorder
from engine_receiver import EngineReceiver,capability_request,capability_reply,engine_telemetry,derive_engine_key


def semi_tune():
    t=json.loads((R/'config/engine/defaults.json').read_text())
    t['strategy']='semi_sequential_4cyl';t['settings']['afterstart_pct']=0
    return t


def prescribed(runtime_type,tune,stray_cam=False,drop_at=None,rev_us=50000,accepted_crank=None):
    """Independent fixed shaft, timers before teeth, 1ms control; no engine plant."""
    runtime=runtime_type(tune);runtime.wheel();origin=200000;finish=origin+12*rev_us
    teeth=[origin+round((rev*60+slot)*rev_us/60) for rev in range(12) for slot in range(58)]
    if drop_at is not None:teeth=[t for t in teeth if t<drop_at]
    ti=0;sample=0;cam=origin+1234 if stray_cam else 2**64-1;edges=[];cuts=[];out={}
    try:
        while True:
            now=min(sample,teeth[ti] if ti<len(teeth) else 2**64-1,cam,runtime.next_event_us())
            if now>finish:break
            while runtime.next_event_us()<=now:
                due=runtime.next_event_us();event=runtime.pop_event()
                if event is None:raise AssertionError('Missing due event')
                if event[0]==-1:continue
                if event[0] is None:cuts.append(due);runtime.cut()
                else:edges.append((due,event[0],event[1]))
            if cam==now:runtime.cam(now);cam+=17003
            if ti<len(teeth) and teeth[ti]==now:
                result=runtime.trigger(now);ti+=1
                if result in (2,3):runtime.cut()
                elif accepted_crank is not None:
                    timeout=runtime.crank_timeout_us()
                    if timeout:accepted_crank.append((now,timeout))
            if sample==now:
                out=runtime.step({},now)
                if out['faults'] or out['state']=='stopped':runtime.cut()
                sample+=1000
        return edges,out,cuts
    finally:runtime.close()


class SemiTests(unittest.TestCase):
    def test_actual_tunerstudio006_export_retains_selected_mode_and_edit(self):
        tune=import_msq((R/'tuning/examples/tunerstudio-semi-roundtrip.msq').read_bytes())
        self.assertEqual(tune['strategy'],'semi_sequential_4cyl');self.assertEqual(tune['timing']['injection_end_deg'],535.5)
        self.assertTrue(tune['settings']['idle_enabled']);self.assertEqual(tune['idle_control']['frequency_hz'],80)
        self.assertEqual(pages(decode_pages(pages(tune),tune)),pages(tune))

    def test_two_effective_half_pulses_equal_one_full_mass_with_two_dead_times(self):
        semi=semi_tune();seq=copy.deepcopy(semi);seq['strategy']='sequential_4cyl'
        for rpm,map_kpa,battery in ((200,100,8),(1200,45,13.8),(6000,85,16)):
            # Use a neutral starting correction so this tests mass splitting,
            # not a default cold profile that can exceed sequential capacity.
            semi['curves']['crank_pct']=[100]*6;seq['curves']['crank_pct']=[100]*6
            observations=[]
            for t in (semi,seq):
                r=EngineRuntime(t)
                try:observations.append(r.step(dict(rpm=rpm,map_kpa=map_kpa,battery_v=battery,synced=True,phase_synced=t is seq),1000,use_decoder=False))
                finally:r.close()
            a,b=observations;self.assertEqual(a['faults'],0);self.assertEqual(b['faults'],0)
            self.assertAlmostEqual(2*(a['pulse_ms']-a['deadtime_ms']),b['pulse_ms']-b['deadtime_ms'])
            self.assertAlmostEqual(a['duty_pct'],a['pulse_ms']/(60000/rpm)*100)

    def test_executed_pairs_end_timing_and_width_on_both_dispatchers(self):
        tune=semi_tune()
        for cls in (EngineRuntime,TargetRuntime):
            edges,out,cuts=prescribed(cls,tune)
            self.assertFalse(out['phase_required']);self.assertFalse(out['phase_synced']);self.assertTrue(out['crank_synced']);self.assertEqual(out['faults'],0)
            self.assertEqual(out['phase_losses'],0);self.assertEqual(out['timing_stops'],0)
            stable=[e for e in edges if 300000<=e[0]<750000]
            by={ch:[(ts,level) for ts,c,level in stable if c==ch] for ch in range(8)}
            self.assertEqual(by[0],by[3]);self.assertEqual(by[1],by[2])
            self.assertNotEqual(by[0],by[1]);self.assertEqual(by[4],by[7]);self.assertEqual(by[5],by[6])
            for ch in range(4):
                falls=[t for t,high in by[ch] if not high];self.assertEqual(len(falls),9)
                expected=270 if ch in (0,3) else 90
                for t in falls:
                    angle=((t-200000)%50000)/50000*360
                    self.assertLess(abs(angle-expected),.1)
                last=None
                for t,high in by[ch]:
                    if high:last=t
                    elif last is not None:self.assertEqual(t-last,round(out['pulse_ms']*1000));last=None

    def test_stray_cam_does_not_create_phase_loss_or_move_semi_edges(self):
        for cls in (EngineRuntime,TargetRuntime):
            a,_,_=prescribed(cls,semi_tune());b,out,_=prescribed(cls,semi_tune(),stray_cam=True)
            self.assertEqual(a,b);self.assertEqual(out['phase_losses'],0);self.assertFalse(out['phase_required'])

    def test_trigger_loss_cuts_both_dispatchers_without_cam_fallback(self):
        for cls in (EngineRuntime,TargetRuntime):
            edges,out,_=prescribed(cls,semi_tune(),drop_at=550000)
            self.assertTrue(any(high and t<550000 for t,_,high in edges))
            self.assertFalse(any(high and t>600000 for t,_,high in edges))
            self.assertFalse(out['phase_required']);self.assertFalse(out['physical_outputs_enabled']);self.assertEqual(out['executor_high_mask'],0)

    def test_low_rpm_trigger_loss_uses_actual_longer_watchdog(self):
        #200RPM,5ms regular tooth period gives40ms rather than the20ms floor.
        for cls in (EngineRuntime,TargetRuntime):
            accepted=[];edges,out,_=prescribed(cls,semi_tune(),drop_at=1700000,rev_us=300000,accepted_crank=accepted)
            self.assertEqual(accepted[-1],(1685000,40000));deadline=sum(accepted[-1])
            self.assertTrue(any(high and t<1700000 for t,_,high in edges))
            self.assertFalse(any(t>deadline or high and t>=deadline for t,_,high in edges))
            self.assertFalse(out['physical_outputs_enabled']);self.assertEqual(out['executor_high_mask'],0)

    def test_schema4_preserves_stored_bytes_revision_idle_and_trims_until_save(self):
        old=json.loads((R/'config/engine/defaults-v4.json').read_text());old['revision']=37
        old['strategy']='sequential_4cyl';old['cylinder_trims']['enabled']=True;old['cylinder_trims']['spark_deg'][1]=-3
        old['settings']['idle_enabled']=True;old['idle_control']['frequency_hz']=80
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tune.json';body=json.dumps(old,indent=1).encode();path.write_bytes(body);store=EngineStore(path)
            self.assertTrue(store.storage_ok);self.assertEqual(path.read_bytes(),body)
            expected=copy.deepcopy(old);expected['schema_version']=8;expected['secondary_tables']=copy.deepcopy(json.loads((R/'config/engine/defaults.json').read_text())['secondary_tables']);expected['load_model']=copy.deepcopy(json.loads((R/'config/engine/defaults.json').read_text())['load_model']);expected['transient_enrichment']=copy.deepcopy(semi_tune()['transient_enrichment']);self.assertEqual(store.tune,expected)
            self.assertEqual(store.save(json.dumps(store.tune).encode())[0],200)
            self.assertEqual(json.loads(path.read_bytes())['schema_version'],8);self.assertEqual(store.tune['revision'],38)

    def test_identity_gates_new_mode_and_retains_old005_idle_values(self):
        t=semi_tune();p=pages(t);self.assertEqual(struct.unpack_from('<I',p[1],272)[0],2)
        self.assertEqual(pages(decode_pages(p,t)),p);text=export_msq(t);self.assertEqual(import_msq(text),t)
        with self.assertRaises(ValueError):import_msq(text.replace(SIGNATURE.decode(),IDLE_SIGNATURE.decode()))
        old=import_msq((R/'tuning/examples/tunerstudio-idle-roundtrip.msq').read_bytes())
        self.assertEqual(old['schema_version'],8);self.assertEqual(old['idle_control']['frequency_hz'],90)
        for schema in (1,2,3,4):
            bad=json.loads((R/'config/engine'/f'defaults-v{schema}.json').read_text()) if schema>1 else copy.deepcopy(t)
            bad['schema_version']=schema;bad['strategy']=t['strategy']
            with self.assertRaises(ValueError):EngineRuntime(bad)
        bad=copy.deepcopy(t);bad['cylinder_trims']['enabled']=True
        with self.assertRaises(ValueError):EngineRuntime(bad)

    def test_single_page_mode_change_keeps_cas_and_rejects_paired_trims(self):
        with tempfile.TemporaryDirectory() as folder:
            store=EngineStore(Path(folder)/'t.json');session=Session(store)
            try:
                command=lambda offset,b:b'M'+struct.pack('<BBHH',0,1,offset,len(b))+b
                self.assertEqual(session.command(command(272,struct.pack('<I',2))),b'\0')
                self.assertEqual(session.command(command(4752,struct.pack('<I',1))),b'\0')
                self.assertEqual(session.command(b'b\0\1'),b'\x84');self.assertEqual(store.tune['strategy'],'batch_wasted_4cyl')
                self.assertEqual(session.command(command(4752,bytes(4))),b'\0')
                self.assertEqual(session.command(b'b\0\1'),b'\4');self.assertEqual(store.tune['strategy'],'semi_sequential_4cyl')
                self.assertEqual(store.tune['revision'],2);self.assertEqual(struct.unpack_from('<I',session.buffers[1],268)[0],1)
            finally:session.close()

    def test_legacy_wire_blocks_new_mode_and_idle_fault_while_schema2_and_logs_keep_them(self):
        r=EngineRuntime(semi_tune());native=EngineRecorder();lmk=bytes(range(16));boot=bytes(range(16,32))
        try:
            r.step(dict(rpm=1200,synced=True),1000,use_decoder=False);s=r.data()
            for fault in (0,17):
                s['worker_observation']['timing_fault_code']=fault;s['worker_observation']['last_timing_fault_code']=fault
                packet=native.frame(s,lmk,boot,123,1,schema=2)
                parsed=engine_telemetry(packet,derive_engine_key(lmk,boot,123),expected_schema=2)
                self.assertEqual(parsed['strategy_code'],2);self.assertEqual(parsed['worker_observation']['timing_fault_code'],fault)
                with self.assertRaises(ValueError):native.frame(s,lmk,boot,123,1,schema=1)
            self.assertEqual(native.command(dict(action='start',period_ms=20,duration_s=1),1000),200)
            self.assertTrue(native.append(s,1000));self.assertEqual(native.page(1,0)['records'][0]['sample']['worker_observation']['timing_fault_code'],17)
        finally:r.close();native.close()

    def test_peer_schema_changes_need_new_counter_and_receiver_enforces_negotiated_version(self):
        native=EngineRecorder();lmk=bytes(range(16));boot=bytes(range(16,32));mac='02:EC:00:00:00:01'
        try:
            receiver=EngineReceiver(mac,lmk,schema=1);q=receiver.query(0,bytes([1])*16)
            receiver.receive_reply(native.capability_reply(q,lmk,123,boot,0,0),mac,0)
            q=receiver.update(True,0,bytes([2])*16);reply=native.capability_reply(q,lmk,123,boot,0,0);receiver.receive_reply(reply,mac,0)
            with self.assertRaises(ValueError):native.capability_reply(capability_request(lmk,123,1,1,bytes([2])*16,schema=2),lmk,123,boot,0,0)
            r=EngineRuntime();r.step(dict(rpm=1200,synced=True),0,use_decoder=False);s=r.data();r.close()
            packet=native.frame(s,lmk,boot,123,1,sent=1000,schema=1);receiver.receive(packet,mac,1)
            receiver.desired_schema=2;q=receiver.update(True,2,bytes([3])*16)
            receiver.receive_reply(native.capability_reply(q,lmk,123,boot,1,2000),mac,2)
            old=native.frame(s,lmk,boot,123,2,sent=3000,schema=1)
            with self.assertRaises(ValueError):receiver.receive(old,mac,3)
            current=native.frame(s,lmk,boot,123,2,sent=3000,schema=2);receiver.receive(current,mac,3)
            receiver.desired_schema=1;q=receiver.update(True,4,bytes([4])*16)
            receiver.receive_reply(native.capability_reply(q,lmk,123,boot,2,4000),mac,4)
            with self.assertRaises(ValueError):receiver.receive(native.frame(s,lmk,boot,123,3,sent=5000,schema=2),mac,5)
            receiver.receive(native.frame(s,lmk,boot,123,3,sent=5000,schema=1),mac,5)
        finally:native.close()

    def test_radio_schema_enum_matrix_checks_current_and_history_independently(self):
        native=EngineRecorder();lmk=bytes(range(16));boot=bytes(range(16,32));key=derive_engine_key(lmk,boot,123)
        try:
            for mode in ('batch_wasted_4cyl','sequential_4cyl','semi_sequential_4cyl'):
                tune=semi_tune();tune['strategy']=mode;r=EngineRuntime(tune)
                try:r.step(dict(rpm=1200,synced=True,phase_synced=True),1000,use_decoder=False);base=r.data()
                finally:r.close()
                for current,history in ((0,0),(16,16),(17,0),(0,17)):
                    s=copy.deepcopy(base);s['worker_observation']['timing_fault_code']=current;s['worker_observation']['last_timing_fault_code']=history
                    for schema in (1,2):
                        supported=schema==2 or mode!='semi_sequential_4cyl' and max(current,history)<=16
                        if not supported:
                            with self.assertRaises(ValueError):native.frame(s,lmk,boot,123,1,schema=schema)
                        else:
                            packet=native.frame(s,lmk,boot,123,1,schema=schema);parsed=engine_telemetry(packet,key,expected_schema=schema)
                            self.assertEqual(parsed['strategy_code'],base['strategy_code']);self.assertEqual(parsed['worker_observation']['timing_fault_code'],current);self.assertEqual(parsed['worker_observation']['last_timing_fault_code'],history)
        finally:native.close()


if __name__=='__main__':unittest.main(verbosity=2)
