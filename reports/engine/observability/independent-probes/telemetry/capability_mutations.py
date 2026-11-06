import ctypes,copy,json,sys
from pathlib import Path
ROOT=Path('/home/mark/persospace/esp32-ecu');P=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from engine_receiver import EngineReceiver,capability_request
b=ctypes.CDLL(str(P/'probe.so'));b.reset.argtypes=[];b.reply.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p];b.reply.restype=ctypes.c_int
MAC='02:EC:00:00:00:01';LMK=bytes(range(16))
b.reset();r=EngineReceiver(MAC,LMK);q=r.query(0,bytes([5])*16);out=ctypes.create_string_buffer(108)
for i in range(76):
 changed=bytearray(q);changed[i]^=1;assert not b.reply(bytes(changed),len(changed),100,1000000,out),i
assert b.reply(q,len(q),100,1000000,out);packet=out.raw
for i in range(108):
 changed=bytearray(packet);changed[i]^=1
 initial=(r.session,r.counter,r.features,r.data_key,r.reply,r.last_packet,copy.deepcopy(r.pending))
 try:r.receive_reply(bytes(changed),MAC,10)
 except ValueError:pass
 else:raise AssertionError(('Reply mutation accepted',i))
 assert (r.session,r.counter,r.features,r.data_key,r.reply,r.last_packet,r.pending)==initial,i
r.receive_reply(packet,MAC,10);assert r.session==123 and r.counter==0 and r.features==0
results={'request_single_byte_mutations':76,'reply_single_byte_mutations':108,'unchanged_state_on_rejection':True,'valid_original_recovers':True}
(P/'capability-mutations.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
