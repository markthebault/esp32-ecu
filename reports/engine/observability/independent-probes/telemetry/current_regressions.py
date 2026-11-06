import ctypes,copy,hmac,json,math,random,struct,sys
from pathlib import Path
ROOT=Path('/home/mark/persospace/esp32-ecu');P=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from engine_receiver import EngineReceiver
b=ctypes.CDLL(str(P/'probe.so'));S=ctypes.c_char_p;U=ctypes.c_uint32;T=ctypes.c_uint64;V=ctypes.c_void_p
b.reset.argtypes=[];b.reply.argtypes=[S,U,T,T,V];b.reply.restype=ctypes.c_int;b.frame.argtypes=[T,T,U,U,U,T,V];b.frame.restype=ctypes.c_int
LMK=bytes(range(16));MAC='02:EC:00:00:00:01';results={}
def reply(request,floor=100,sent=1000000):
 out=ctypes.create_string_buffer(108);assert b.reply(request,len(request),floor,sent,out);return out.raw
def frame(packet=101,observation=17,age=0,worker=None,sent=1020000):
 out=ctypes.create_string_buffer(232);assert b.frame(packet,observation,age,age,age if worker is None else worker,sent,out);return out.raw
def begin(stamp=1010000,received=20):
 b.reset();r=EngineReceiver(MAC,LMK);q=r.query(0,bytes([1])*16);r.receive_reply(reply(q),MAC,0)
 q=r.update(True,0,bytes([2])*16);r.receive_reply(reply(q,sent=stamp),MAC,received);return r
r=begin(stamp=1000000,received=0)
data=r.receive(frame(age=990,sent=1009800),MAC,10);state=r.status(10)
assert state['sample_age_ms']>=1010 and state['control_age_ms']>=1010 and state['worker_age_ms']>=1010 and not state['fresh']
results['source_clock_2_percent_slow_corrected']={'actual_age_ms':1010,'bounded_sample_age_ms':state['sample_age_ms'],'bounded_control_age_ms':state['control_age_ms'],'bounded_worker_age_ms':state['worker_age_ms'],'fresh':state['fresh']}
r=begin();assert r.status(1021)['query_required']
try:r.receive(frame(sent=2011000),MAC,1021)
except ValueError as e:assert 'Stale gap' in str(e)
else:raise AssertionError('Initial gap accepted')
assert r.latest is None and r.last_packet==100;results['initial_gap_after_1_second_rejected']='pass'
r=begin();packet=frame();initial=(r.last_packet,r.last_snapshot,r.received_ms,copy.deepcopy(r.latest))
for i in range(232):
 bad=bytearray(packet);bad[i]^=1
 try:r.receive(bytes(bad),MAC,30)
 except ValueError:pass
 else:raise AssertionError(('Tamper accepted',i))
 assert (r.last_packet,r.last_snapshot,r.received_ms,r.latest)==initial
r.receive(packet,MAC,30);results['authentication_before_mutation']={'byte_mutations':232,'passed':True}
r=begin();r.receive(frame(age=900),MAC,30)
for n in range(1,9):r.receive(frame(packet=101+n,age=0,sent=1020000+n*100000),MAC,30+n*100)
assert not r.status(830)['fresh'] and r.status(830)['sample_age_ms']>1700
results['repeated_source_age_floor']='pass'
r=begin();r.receive(frame(age=2**32-1),MAC,30);r.receive(frame(packet=102,age=0,sent=1120000),MAC,130)
assert r.status(130)['sample_age_ms'] is None and not r.status(130)['fresh'];results['repeated_unknown_does_not_recover']='pass'
# Physical timings in receiver milliseconds; the independent source clock can
# run anywhere within the documented relative 2 percent rate assumption.
rng=random.Random(13761);minimum_margin=math.inf;cases=4000
for n in range(cases):
 rate=rng.uniform(.98,1.02);out=rng.uniform(0,100);processing=rng.uniform(0,40);back=rng.uniform(0,100)
 reply_time=out+processing;reply_local=math.ceil(reply_time+back)
 delay=rng.uniform(back+2,800);transit=rng.uniform(0,80);received=math.ceil(reply_time+delay+transit)
 actual_source_age=rng.uniform(0,5000);source_age=math.ceil(actual_source_age*rate)
 stamp=1000000000+math.floor(reply_time*1000*rate)
 r=begin(stamp=stamp,received=reply_local)
 sent=stamp+math.floor(delay*1000*rate);data=r.receive(frame(age=source_age,sent=sent),MAC,received)
 bound=data['bounded_sample_age_ms'];actual=actual_source_age+transit
 assert bound>=actual,(n,rate,bound,actual)
 if actual>1000:assert not r.status(received)['fresh']
 assert data['bounded_worker_age_ms']>=actual
 minimum_margin=min(minimum_margin,bound-actual)
results['timed_clock_grid']={'cases':cases,'source_rate_min':.98,'source_rate_max':1.02,'minimum_bound_margin_ms':minimum_margin,'passed':True}
(P/'current-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
