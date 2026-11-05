from pathlib import Path
import hashlib,json,sys
own=Path(__file__).resolve().parents[1];sys.path.insert(0,str(own/'freeze-final-001/tools'));from engine_receiver import EngineReceiver
f=own/'sender-001/fixtures';lmk=bytes(range(16));mac='02:EC:00:00:00:01';results=[]
for reverse in (False,True):
 r=EngineReceiver(mac,lmk);assert r.query(100,bytes([1])*16)==(f/'query-request.bin').read_bytes();r.receive_reply((f/'query-reply.bin').read_bytes(),mac,110);assert r.update(True,120,bytes([2])*16)==(f/'update-request.bin').read_bytes();r.receive_reply((f/'update-reply.bin').read_bytes(),mac,125)
 parts=[(f/'base.bin').read_bytes(),(f/'flex.bin').read_bytes()];parts=parts[::-1]if reverse else parts
 assert r.receive(parts[0],mac,140)is None and r.latest is None and r.received_ms is None
 try:r.acknowledgement();raise AssertionError('Partial ACK allowed')
 except ValueError:pass
 d=r.receive(parts[1],mac,200);assert d['complete_observation'] and d['packet_sequence']==2**53+92 and d['flex_fuel']['source_code']==1 and d['flex_fuel']['sample_age_ms']==0 and d['flex_sample_age_ms']==30
 ack=r.acknowledgement();assert ack==(f/'engine-ack.bin').read_bytes();assert r.status(200)['flex_value_qualified'] and not r.status(500)['flex_value_qualified'];assert r.status(500)['fresh']
 results.append({'reversed':reverse,'packet_sequence':str(d['packet_sequence']),'raw_age_ms_at_base':d['flex_sample_age_ms'],'bounded_flex_age_ms_at_complete':d['bounded_flex_sample_age_ms'],'ack_matches_actual_handler_fixture':True})
r={'accepted':True,'actual_source_native_model_to_frozen_receiver':results,'capture_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(f.glob('*.bin'))},'scope':'Actual sender functions and handler in native API model; no infinite RTOS task, ESP-IDF, RF, physical LED or device'}
(own/'sender-receiver-002.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'passed':True,'orders':len(results),'raw_age_ms':30,'completion_bound_ms':96,'ACK_exact':True}))
