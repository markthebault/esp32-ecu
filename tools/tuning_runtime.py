"""The target's own009 task-side tuning codec on native shared-library callbacks."""
import copy,ctypes,fcntl,json,os,struct,subprocess,threading,time
from pathlib import Path
from engine_runtime import R
from secondary_config import PAGE_BYTES,LIVE_BYTES

_build_lock=threading.Lock()
LOAD=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t)
CURRENT=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32))
COMMIT=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_uint32))
SAMPLE=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t)

def load_bridge():
 with _build_lock:
  cache=R/'.cache/engine/tuning-native';cache.mkdir(parents=True,exist_ok=True)
  cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
  source=R/'tools/tuning_bridge.cpp';lib=cache/'libtuning.so'
  deps=[Path(__file__),source,cjson/'cJSON.c',cjson/'cJSON.h',*sorted((R/'firmware/include/ecu').glob('*.hpp'))]
  with (cache/'build.lock').open('a+b') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if not lib.exists() or max(p.stat().st_mtime for p in deps)>lib.stat().st_mtime:
    subprocess.run(['cc','-O2','-fPIC','-c',str(cjson/'cJSON.c'),'-o',str(cache/'cJSON.o')],check=True)
    subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(cjson),'-I'+str(R/'firmware/include'),str(source),str(cache/'cJSON.o'),'-o',str(cache/'libtuning.new.so')],check=True);os.replace(cache/'libtuning.new.so',lib)
  b=ctypes.CDLL(str(lib));P=ctypes.c_void_p;Z=ctypes.c_size_t;B=ctypes.POINTER(ctypes.c_uint8)
  signatures={'tuning_create':([P,LOAD,CURRENT,COMMIT,SAMPLE],P),'tuning_destroy':([P],None),'tuning_command':([P,P,Z,ctypes.POINTER(Z)],B),'tuning_feed':([P,P,Z,ctypes.c_uint64,ctypes.POINTER(Z)],B),'tuning_page':([P],B),'tuning_status':([P],ctypes.c_char_p),'tuning_buffered':([P],Z),'tuning_disconnect':([P],None)}
  for name,(args,result) in signatures.items():fn=getattr(b,name);fn.argtypes=args;fn.restype=result
  return b

def result_code(http):return 0 if http==200 else 1 if http==409 else 2 if http in (503,507) else 4 if http==500 else 5

class Session:
 def __init__(self,store):
  self.store=store;self.lock=threading.RLock();self.bridge=load_bridge();self.error='';self.handle=None
  def guarded(fn):
   def call(*args):
    try:return fn(*args)
    except Exception as error:self.error=type(error).__name__+': '+str(error);return 4 if isinstance(error,MemoryError) else 5
   return call
  @LOAD
  @guarded
  def load(_,target,capacity):
   with self.store.lock:
    value=copy.deepcopy(self.store.tune);body=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
    if len(body)>=capacity:return 5
    ctypes.memmove(target,body+b'\0',len(body)+1);return 0 if self.store.storage_ok else 2
  @CURRENT
  @guarded
  def current(_,revision):
   with self.store.lock:revision[0]=self.store.tune['revision'];return 0 if self.store.storage_ok else 2
  @COMMIT
  @guarded
  def commit(_,data,size,revision):
   code,value=self.store.save(ctypes.string_at(data,size))
   if code==200:revision[0]=value['revision']
   return result_code(code)
  @SAMPLE
  @guarded
  def sample(_,target,size):
   if size!=LIVE_BYTES:return 5
   with self.store.lock:
    from engine_protocol import live_block
    block=live_block(self.store)
    ctypes.memmove(target,block,size)
   return 0
  self.callbacks=load,current,commit,sample
  self.handle=self.bridge.tuning_create(None,*self.callbacks)
  if not self.handle:raise MemoryError('Native tuning session allocation failed')
  # Registry lock is separate from store/Session locks to avoid lock-order cycles.
  with store.tuning_registry_lock:store.tuning_sessions.add(self)
 @property
 def buffers(self):
  with self.lock:
   if not self.handle:raise RuntimeError('Tuning session is closed')
   return {1:bytearray(ctypes.string_at(self.bridge.tuning_page(self.handle),PAGE_BYTES))}
 @property
 def dirty(self):return self.diagnostics()['dirty']
 def command(self,payload):
  with self.lock:
   if not self.handle:raise RuntimeError('Tuning session is closed')
   size=ctypes.c_size_t();p=self.bridge.tuning_command(self.handle,payload,len(payload),ctypes.byref(size))
   if not p:raise ValueError('Tuning command exceeds bounded payload')
   return ctypes.string_at(p,size.value)
 def feed(self,data,now_us=None):
  with self.lock:
   if not self.handle:raise RuntimeError('Tuning session is closed')
   size=ctypes.c_size_t();p=self.bridge.tuning_feed(self.handle,data,len(data),time.monotonic_ns()//1000 if now_us is None else now_us,ctypes.byref(size))
   if not p:raise ValueError('Tuning input exceeds bounded read slice')
   raw=ctypes.string_at(p,size.value);out=[];offset=0
   while offset<len(raw):
    count=struct.unpack_from('<H',raw,offset)[0];offset+=2;out.append(raw[offset:offset+count]);offset+=count
   if offset!=len(raw):raise RuntimeError('Native response slice corrupted')
   return out
 def diagnostics(self):
  with self.lock:
   if not self.handle:raise RuntimeError('Tuning session is closed')
   body=self.bridge.tuning_status(self.handle)
   if not body:raise MemoryError('Native tuning status unavailable')
   return dict(json.loads(body),callback_error=self.error)
 def close(self):
  with self.lock:
   if self.handle:self.bridge.tuning_destroy(self.handle);self.handle=None
   with self.store.tuning_registry_lock:self.store.tuning_sessions.discard(self)
 def __del__(self):
  if getattr(self,'handle',None):self.close()

class Stream:
 def __init__(self,store):self.session=Session(store)
 @property
 def buffer(self):
  with self.session.lock:return bytes(self.session.bridge.tuning_buffered(self.session.handle))
 def feed(self,data,now_us=None):return self.session.feed(data,now_us)
 def expire(self,now_us=None):return self.feed(b'',now_us)
 def close(self):self.session.close()

def status(store):
 """Bounded observation of real native development sessions, without opening one."""
 with store.tuning_registry_lock:sessions=list(store.tuning_sessions)
 observations=[]
 for session in sessions[:16]:
  try:observations.append(session.diagnostics())
  except RuntimeError:continue # A transport may have closed after the snapshot.
 with store.lock:revision=store.tune['revision']
 keys=('initialized','dirty','state','origin_revision','base_revision','observed_active_revision','last_code','commands','reads','writes','burns','rejected','resets')
 def session_fields(o):return {k:o[k] for k in keys}
 def wire_fields(o):
  return {k:o[v] for k,v in dict(received='received_bytes',transmitted='fully_queued_reply_bytes',frames='frames',crc_errors='crc_errors',timeouts='timeouts',framing_errors='framing_errors',tx_errors='tx_errors').items()}
 current=observations[-1] if len(observations)==1 else None
 return dict(schema_version=1,transport='native_host_development',identity='ESP32ECU DEV 009 INHIBITED',serial_protocol='002',enabled=True,
  available=bool(observations),boot_allowed=True,host_present=None,reason='Host transport sessions observed' if observations else 'No native tuning session open',
  physical_outputs_inhibited=True,host_presence_meaning='Host TCP/PTY session records; no target USB hardware is connected',
  observed_clock_domain='host_monotonic',observed_us=str(time.monotonic_ns()//1000),active_revision=revision,
  application_support='Earlier own identities were rejected online; current identity acceptance unverified; use matching offline definition; vendor integration unresolved',
  commit_behavior='Any successful burn validates, persists and activates the whole tune, resets control and reacquires phase',
  qualification='Native host development only; no target USB enumeration or physical timing measurements',
  driver_rx_drop_count=None,driver_rx_drop_count_meaning='No target USB driver on this host endpoint',
  tx_fault=current['tx_fault'] if current else None,buffered_bytes=current['buffered_bytes'] if current else None,
  session=session_fields(current) if current else None,wire=wire_fields(current) if current else None,
  session_count=len(observations),sessions=[dict(session=session_fields(o),wire=wire_fields(o),tx_fault=o['tx_fault'],callback_error=o['callback_error']) for o in observations],
  sessions_truncated=len(sessions)>16)
