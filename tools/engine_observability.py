"""Native bounded engine recorder and wire fixtures. No RF or GPIO transport."""
import ctypes, fcntl, json, os, subprocess, threading
from pathlib import Path

R=Path(__file__).resolve().parents[1]
_lock=threading.Lock()
def load_bridge():
 with _lock:
  out=R/'.cache/engine';out.mkdir(parents=True,exist_ok=True)
  cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
  source=R/'tools/engine_observability_bridge.cpp';lib=out/'libobservability.so'
  deps=[Path(__file__),source,R/'firmware/main/config_json.hpp',cjson/'cJSON.c',*sorted((R/'firmware/include/ecu').glob('*.hpp'))]
  with (out/'observability.lock').open('a+b') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if not lib.exists() or max(p.stat().st_mtime for p in deps)>lib.stat().st_mtime:
    subprocess.run(['cc','-O2','-fPIC','-c',str(cjson/'cJSON.c'),'-o',str(out/'observability-cJSON.o')],check=True)
    subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(cjson),'-I'+str(R/'firmware/include'),str(source),str(out/'observability-cJSON.o'),'-lcrypto','-o',str(out/'libobservability.new.so')],check=True)
    os.replace(out/'libobservability.new.so',lib)
  b=ctypes.CDLL(str(lib));P=ctypes.c_void_p;S=ctypes.c_char_p;U=ctypes.c_uint32;T=ctypes.c_uint64;I=ctypes.c_int
  signatures={'data_create':([],P),'data_destroy':([P],None),'data_validate':([S],I),
   'data_log_command':([P,S,U,T,U],I),'data_log_append':([P,S,T],I),'data_log_expire':([P,T],None),
   'data_log_header':([P],S),'data_log_page':([P,U,U],S),'data_log_msl':([P,U,S],S),
   'data_capability_reset':([P],None),'data_capability_reply':([P,S,U,S,U,S,T,T,P],I),
   'data_radio_frame':([S,S,S,U,T,U,U,U,T,U,P],I)}
  for name,(args,result) in signatures.items():fn=getattr(b,name);fn.argtypes=args;fn.restype=result
  return b

def encoded(sample):return json.dumps(sample,separators=(',',':'),allow_nan=False).encode()
def decoded(value):
 if not value:raise MemoryError('Native observation JSON allocation failed')
 return json.loads(value)

class EngineRecorder:
 def __init__(self,bridge=None):
  self.bridge=bridge or load_bridge();self.handle=self.bridge.data_create()
  if not self.handle:raise MemoryError('Native recorder allocation failed')
 def command(self,body,now,source=2):
  if not isinstance(body,bytes):body=encoded(body)
  return self.bridge.data_log_command(self.handle,body,len(body),now,source)
 def append(self,sample,now):
  result=self.bridge.data_log_append(self.handle,encoded(sample),now)
  if result<0:raise ValueError('Invalid native observation fixture')
  return bool(result)
 def expire(self,now):self.bridge.data_log_expire(self.handle,now)
 def header(self):return decoded(self.bridge.data_log_header(self.handle))
 def page(self,log_id,after):return decoded(self.bridge.data_log_page(self.handle,log_id,after))
 def msl(self,log_id,boot='0'*32):
  value=self.bridge.data_log_msl(self.handle,log_id,boot.encode())
  if not value:raise ValueError('Stop recording and select a nonempty current log before exporting')
  return value.decode()
 def capability_reply(self,request,key,session,nonce,floor,sent):
  out=ctypes.create_string_buffer(108)
  if not self.bridge.data_capability_reply(self.handle,request,len(request),key,session,nonce,floor,sent,out):raise ValueError('Capability request rejected')
  return out.raw
 def reset_capabilities(self):self.bridge.data_capability_reset(self.handle)
 def frame(self,sample,lmk,nonce,session,sequence,sample_age=0,control_age=0,worker_age=4294967295,sent=0,schema=2):
  out=ctypes.create_string_buffer(232)
  if not self.bridge.data_radio_frame(encoded(sample),lmk,nonce,session,sequence,sample_age,control_age,worker_age,sent,schema,out):raise ValueError('Invalid engine observation fixture or unsupported wire schema')
  return out.raw
 def close(self):
  if self.handle:self.bridge.data_destroy(self.handle);self.handle=None
 def __del__(self):
  if getattr(self,'handle',None):self.close()
