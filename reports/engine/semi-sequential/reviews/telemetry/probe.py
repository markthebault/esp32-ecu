import ctypes,copy,hmac,importlib.util,json,struct,subprocess,sys
from pathlib import Path
R=Path('/home/mark/persospace/esp32-ecu');D=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tools'))
import engine_receiver as current
oldfile=D/'baseline_receiver.py';oldfile.write_text(subprocess.run(['git','show','HEAD:tools/engine_receiver.py'],cwd=R,check=True,capture_output=True,text=True).stdout)
spec=importlib.util.spec_from_file_location('baseline_receiver',oldfile);baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
b=ctypes.CDLL(str(D/'probe.so'));P=ctypes.c_void_p;S=ctypes.c_char_p;U=ctypes.c_uint32;T=ctypes.c_uint64
for name,args,ret in [('data_create',[],P),('data_destroy',[P],None),('review_sample',[U,U,U],S),('review_supports',[U,U,U,U],ctypes.c_int),('data_validate',[S],ctypes.c_int),('data_capability_reply',[P,S,U,S,U,S,T,T,P],ctypes.c_int),('data_radio_frame',[S,S,S,U,T,U,U,U,T,U,P],ctypes.c_int)]:
 f=getattr(b,name);f.argtypes=args;f.restype=ret
LMK=bytes(range(16));BOOT=bytes(range(16,32));MAC='02:EC:00:00:00:01';SESSION=123;results={}
class Native:
 def __init__(self):self.handle=b.data_create();assert self.handle
 def close(self):b.data_destroy(self.handle)
 def reply(self,q,floor=100,sent=1000000):
  out=ctypes.create_string_buffer(108)
  if not b.data_capability_reply(self.handle,q,len(q),LMK,SESSION,BOOT,floor,sent,out):raise ValueError('Native request rejected')
  return out.raw
 def frame(self,strategy=0,fault=0,last=0,schema=2,seq=101,age=0,sent=1020000):
  sample=b.review_sample(strategy,fault,last);assert sample and b.data_validate(sample)
  out=ctypes.create_string_buffer(232)
  if not b.data_radio_frame(sample,LMK,BOOT,SESSION,seq,age,age,age,sent,schema,out):raise ValueError('Native frame rejected')
  return out.raw
 def begin(self,schema=2,receiver_module=current):
  r=receiver_module.EngineReceiver(MAC,LMK,**({'schema':schema} if receiver_module is current else {}))
  q=r.query(0,bytes([1])*16);r.receive_reply(self.reply(q),MAC,10)
  q=r.update(True,10,bytes([2])*16);r.receive_reply(self.reply(q,sent=1010000),MAC,20)
  return r
key=current.derive_engine_key(LMK,BOOT,SESSION)
def rejection(r,packet,now):
 old=(r.session,r.counter,r.features,r.last_packet,r.last_snapshot,r.received_ms,copy.deepcopy(r.latest),r.data_key)
 try:r.receive(packet,MAC,now)
 except ValueError:pass
 else:raise AssertionError('Unexpected frame acceptance')
 assert (r.session,r.counter,r.features,r.last_packet,r.last_snapshot,r.received_ms,r.latest,r.data_key)==old
# Exercise current production C++ bridge ABI and both codecs through real samples.
count=0
for schema in (1,2):
 for strategy in (0,1,2):
  for fault,last in ((0,0),(16,0),(0,16),(17,0),(0,17),(17,17)):
   expected=strategy<=(1 if schema==1 else 2) and fault<=(16 if schema==1 else 17) and last<=(16 if schema==1 else 17)
   assert bool(b.review_supports(schema,strategy,fault,last))==expected
   n=Native()
   try:
    try:packet=n.frame(strategy,fault,last,schema)
    except ValueError:assert not expected
    else:
     assert expected;parsed=current.engine_telemetry(packet,key,expected_schema=schema)
     assert parsed['strategy_code']==strategy and parsed['worker_observation']['timing_fault_code']==fault and parsed['worker_observation']['last_timing_fault_code']==last
     assert parsed['scalar_proposal_basis']=='untrimmed_base_demand' and not parsed['per_cylinder_available']
    count+=1
   finally:n.close()
results['native_frame_strategy_fault_matrix']={'cases':count,'passed':True}
# Genuine pre-change schema-1 receiver must still negotiate and parse valid old modes.
for strategy in (0,1):
 n=Native()
 try:
  r=n.begin(1,baseline);packet=n.frame(strategy,schema=1);parsed=r.receive(packet,MAC,30)
  assert parsed['schema_version']==1 and parsed['strategy_code']==strategy and r.status(30)['fresh']
  other=n.frame(strategy,schema=2);assert packet[:20]+packet[22:200]==other[:20]+other[22:200]
 finally:n.close()
results['actual_prechange_receiver_compatibility']={'strategies':[0,1],'schema1_body_layout_unchanged':True,'passed':True}
# Signed invalid new values must also be rejected by decoder, independently of encoder guards.
for schema,mutations in ((1,((81,2),(85,17),(86,17))),(2,((81,3),(85,18),(86,18)))):
 n=Native()
 try:
  packet=n.frame(schema=schema)
  for offset,value in mutations:
   changed=bytearray(packet);changed[offset]=value;changed[200:]=hmac.digest(key,changed[:200],'sha256')
   try:current.engine_telemetry(bytes(changed),key,expected_schema=schema)
   except ValueError:pass
   else:raise AssertionError((schema,offset,value))
 finally:n.close()
results['authenticated_schema_enum_limits']='pass'
# Unknown schema codes are blocked by native support check and authenticated decoder.
for schema in (0,3,65537):assert not b.review_supports(schema,0,0,0)
n=Native()
try:
 p=n.frame(schema=2)
 for schema in (0,3,65535):
  changed=bytearray(p);struct.pack_into('<H',changed,20,schema);changed[200:]=hmac.digest(key,changed[:200],'sha256')
  try:current.engine_telemetry(bytes(changed),key)
  except ValueError:pass
  else:raise AssertionError(schema)
finally:n.close()
results['unknown_schemas']='pass'
# Per-peer schema changes require a new counter; replay/query cannot change the choice.
n=Native()
try:
 r=n.begin(1);old_request=current.capability_request(LMK,SESSION,1,1,bytes([2])*16,schema=1)
 n.reply(old_request);n.reply(old_request)
 conflict=current.capability_request(LMK,SESSION,1,1,bytes([2])*16,schema=2)
 try:n.reply(conflict)
 except ValueError:pass
 else:raise AssertionError('Same-counter schema substitution')
 r.receive(n.frame(schema=1),MAC,30)
 r.desired_schema=2;q=r.update(True,40,bytes([3])*16);reply=n.reply(q,floor=101,sent=1030000)
 # Even a correctly authenticated echo/counter reply may not silently downgrade a requested schema.
 bad=bytearray(reply);struct.pack_into('<I',bad,36,1);bad[76:]=hmac.digest(LMK,bad[:76],'sha256')
 before=(r.counter,r.features,r.data_key,copy.deepcopy(r.reply),r.last_packet)
 try:r.receive_reply(bytes(bad),MAC,40)
 except ValueError:pass
 else:raise AssertionError('Authenticated reply downgraded request')
 assert (r.counter,r.features,r.data_key,r.reply,r.last_packet)==before
 r.receive_reply(reply,MAC,40)
 try:n.reply(old_request)
 except ValueError:pass
 else:raise AssertionError('Recorded old enable request changed newer schema')
 query=current.capability_request(LMK,nonce=bytes([4])*16)
 state=current.capability_reply(n.reply(query,floor=101,sent=1030000),LMK,bytes([4])*16)
 assert state['schema']==2 and state['counter']==2 and state['features']==1
 rejection(r,n.frame(schema=1,seq=102,sent=1040000),50)
 r.receive(n.frame(schema=2,seq=102,sent=1040000),MAC,50)
 r.desired_schema=1;q=r.update(True,60,bytes([5])*16);r.receive_reply(n.reply(q,floor=102,sent=1050000),MAC,60)
 rejection(r,n.frame(schema=2,seq=103,sent=1060000),70)
 r.receive(n.frame(schema=1,seq=103,sent=1060000),MAC,70)
 assert r.counter==3 and r.reply['schema']==1
 results['counter_schema_upgrade_downgrade_query_replay']='pass'
finally:n.close()
# Both versions retain HMAC-before-state behavior and source age conservatism.
for schema in (1,2):
 n=Native()
 try:
  r=n.begin(schema);packet=n.frame(schema=schema)
  for i in range(232):
   changed=bytearray(packet);changed[i]^=1;rejection(r,bytes(changed),30)
  assert r.rejected==232;r.receive(packet,MAC,30)
  ack=r.acknowledgement();assert len(ack)==56 and ack[24:]==hmac.digest(key,ack[:24],'sha256') and struct.unpack_from('<IQI',ack,8)==(SESSION,101,0)
 finally:n.close()
 n=Native()
 try:
  r=current.EngineReceiver(MAC,LMK,schema=schema);q=r.query(0,bytes([6])*16);r.receive_reply(n.reply(q,sent=1000000),MAC,0)
  q=r.update(True,0,bytes([7])*16);r.receive_reply(n.reply(q,sent=1000000),MAC,0)
  value=r.receive(n.frame(schema=schema,age=990,sent=1009800),MAC,10)
  assert value['bounded_sample_age_ms']>=1010 and not r.status(10)['fresh']
  assert value['bounded_worker_age_ms']>=1010
 finally:n.close()
results['schema_1_and_2_auth_age_ACK']={'frame_byte_mutations':464,'slow_clock_history':'pass','ACK56_full_derived_key':'pass'}
(D/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
