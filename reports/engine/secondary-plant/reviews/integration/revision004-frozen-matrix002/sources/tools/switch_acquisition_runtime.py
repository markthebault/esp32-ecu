"""Actual portable acquisition in a synthetic, explicitly timed device fixture."""
import ctypes,fcntl,hashlib,json,os,re,subprocess,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
_lock=threading.Lock()
def bridge():
 with _lock:
  cache=ROOT/'.cache/engine/switch-acquisition-native';cache.mkdir(parents=True,exist_ok=True)
  source=ROOT/'tools/switch_acquisition_bridge.cpp';dependencies=[source,Path(__file__),*sorted((ROOT/'firmware/include/ecu').glob('*.hpp'))]
  fingerprint={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in dependencies}
  library=cache/'libswitch_acquisition.so';stamp=cache/'source-bindings.json'
  with(cache/'build.lock').open('a+b')as locked:
   fcntl.flock(locked,fcntl.LOCK_EX)
   if not library.exists()or not stamp.exists()or json.loads(stamp.read_text())!=fingerprint:
    temporary=library.with_suffix('.new.so')
    subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(ROOT/'firmware/include'),str(source),'-o',str(temporary)],check=True)
    os.replace(temporary,library);stamp.write_text(json.dumps(fingerprint,indent=2)+'\n')
  result=ctypes.CDLL(str(library));P=ctypes.c_void_p;U=ctypes.c_uint64;I=ctypes.c_uint;S=ctypes.c_char_p;B=ctypes.POINTER(ctypes.c_uint8)
  for name,(args,output)in {'create':([],P),'destroy':([P],None),'next':([P,I,U],S),'complete':([P,U,I,B,I,U,U],ctypes.c_int),'ack':([P,U,ctypes.c_int],ctypes.c_int),'snapshot':([P],S)}.items():
   f=getattr(result,'switch_model_'+name);f.argtypes=args;f.restype=output
  return result
class AcquisitionRuntime:
 def __init__(self):
  self.api=bridge();self.handle=self.api.switch_model_create()
  if not self.handle:raise MemoryError('Native acquisition fixture allocation failed')
 def _active(self):
  if not self.handle:raise ValueError('Acquisition fixture closed')
 def _json(self,text):
  if not text:raise RuntimeError('Missing native acquisition result')
  value=json.loads(text)
  if 'error'in value:raise RuntimeError(value['error'])
  return value
 @staticmethod
 def _time(value):
  if type(value)is not int or not 0<=value<=2**64-1:raise ValueError('ExactU64 time required')
 @classmethod
 def _word(cls,value):
  if type(value)is not str or not re.fullmatch(r'0|[1-9][0-9]{0,19}',value):raise ValueError('Canonical decimal U64 field required')
  result=int(value);cls._time(result);return result
 def next(self,mask,now):
  self._active();self._time(now)
  if type(mask)is not int or not 0<=mask<=3:raise ValueError('Two-channel acquisition mask required')
  return self._json(self.api.switch_model_next(self.handle,mask,now))
 def complete(self,request,result,data,started,ended):
  self._active();self._time(started);self._time(ended)
  if type(result)is not int or not 0<=result<=5 or len(data)>12 or any(type(v)is not int or not 0<=v<=255 for v in data):raise ValueError('Invalid synthetic transfer reply')
  raw=(ctypes.c_uint8*len(data))(*data)
  return self.api.switch_model_complete(self.handle,self._word(request['token']),result,raw,len(data),started,ended)==1
 def snapshot(self):self._active();return self._json(self.api.switch_model_snapshot(self.handle))
 def consumed(self,snapshot,completed):
  self._active()
  if type(completed)is not bool:raise ValueError('Completed observation flag required')
  return self.api.switch_model_ack(self.handle,self._word(snapshot['fault_id']),int(completed and snapshot['fault_pending']and not snapshot['ready']))==1
 def close(self):
  if self.handle:self.api.switch_model_destroy(self.handle);self.handle=None
