"""Shared native ECU core and persistent shadow-engine tune. No GPIO transport."""
import copy, ctypes, fcntl, json, os, subprocess, tempfile, threading, time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
_build_lock=threading.Lock()
def load_engine_bridge():
 with _build_lock:
  out=R/'.cache/engine';out.mkdir(parents=True,exist_ok=True)
  cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
  if not (cjson/'cJSON.c').exists():raise RuntimeError('Build firmware with pinned PlatformIO framework first')
  # Include transitive headers: a scheduler-only fix must rebuild the SIL binary.
  deps=[Path(__file__),R/'tools/engine_bridge.cpp',R/'firmware/main/config_json.hpp',cjson/'cJSON.c',cjson/'cJSON.h',*sorted((R/'firmware/include/ecu').glob('*.hpp'))]
  lib=out/'libengine.so'
  with (out/'build.lock').open('a+b') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if not lib.exists() or max(p.stat().st_mtime for p in deps)>lib.stat().st_mtime:
    subprocess.run(['cc','-O2','-fPIC','-c',str(cjson/'cJSON.c'),'-o',str(out/'cJSON.o')],check=True)
    subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(cjson),'-I'+str(R/'firmware/main'),'-I'+str(R/'firmware/include'),str(R/'tools/engine_bridge.cpp'),str(out/'cJSON.o'),'-o',str(out/'libengine.new.so')],check=True)
    os.replace(out/'libengine.new.so',lib)
  b=ctypes.CDLL(str(lib));b.engine_create.restype=ctypes.c_void_p;b.engine_destroy.argtypes=[ctypes.c_void_p]
  b.engine_validate.argtypes=[ctypes.c_char_p];b.engine_validate.restype=ctypes.c_int
  b.engine_configure.argtypes=[ctypes.c_void_p,ctypes.c_char_p];b.engine_configure.restype=ctypes.c_int
  b.engine_wheel.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint];b.engine_wheel.restype=ctypes.c_int
  b.engine_trigger.argtypes=[ctypes.c_void_p,ctypes.c_uint64];b.engine_trigger.restype=ctypes.c_int
  b.engine_step.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint64,ctypes.c_uint64];b.engine_step.restype=ctypes.c_char_p
  b.engine_cut.argtypes=[ctypes.c_void_p]
  b.engine_timing_reason.argtypes=[ctypes.c_void_p];b.engine_timing_reason.restype=ctypes.c_char_p
  b.engine_next_time.argtypes=[ctypes.c_void_p];b.engine_next_time.restype=ctypes.c_uint64
  b.engine_pop.argtypes=[ctypes.c_void_p];b.engine_pop.restype=ctypes.c_uint
  b.engine_event_dwell.argtypes=[ctypes.c_void_p];b.engine_event_dwell.restype=ctypes.c_uint64
  b.engine_event_advance.argtypes=[ctypes.c_void_p];b.engine_event_advance.restype=ctypes.c_double
  b.engine_plan.argtypes=[ctypes.c_void_p];b.engine_plan.restype=ctypes.c_char_p
  return b
class EngineRuntime:
 def __init__(self,tune=None,bridge=None):
  self.bridge=bridge or load_engine_bridge();self.handle=self.bridge.engine_create()
  self.configure(tune or json.loads((R/'config/engine/defaults.json').read_text()))
 def configure(self,tune):
  body=json.dumps(tune,separators=(',',':'),allow_nan=False).encode()
  if not self.bridge.engine_configure(self.handle,body):raise ValueError('Engine tune violates schema or current hardware limits')
  self.tune=tune
 def wheel(self,slots=60,missing=2,max_rpm=8000):
  if not self.bridge.engine_wheel(self.handle,slots,missing,max_rpm):raise ValueError('Invalid trigger wheel geometry')
 def trigger(self,time_us):return self.bridge.engine_trigger(self.handle,int(time_us))
 def step(self,inputs,time_us,sampled_us=None,use_decoder=True):
  sample=dict(rpm=0,map_kpa=45,tps_pct=10,clt_c=85,iat_c=25,lambda_=1,battery_v=13.8,sensor_v=5,synced=False,sensors_valid=True,lambda_ready=True,use_decoder=use_decoder)
  sample['lambda']=sample.pop('lambda_');sample.update(inputs)
  out=json.loads(self.bridge.engine_step(self.handle,json.dumps(sample,allow_nan=False).encode(),int(time_us),int(time_us if sampled_us is None else sampled_us)))
  if 'error' in out:raise ValueError(out['error'])
  return out
 def cut(self):self.bridge.engine_cut(self.handle)
 def timing_reason(self):return self.bridge.engine_timing_reason(self.handle).decode()
 def next_event_us(self):return self.bridge.engine_next_time(self.handle)
 def pop_event(self):
  code=self.bridge.engine_pop(self.handle)
  if not code&0x10000:return None
  if code&0x20000:return None,False,0,0
  return code&255,bool(code&0x100),self.bridge.engine_event_advance(self.handle),self.bridge.engine_event_dwell(self.handle)
 def plan(self):return json.loads(self.bridge.engine_plan(self.handle))
 def close(self):
  if self.handle:self.bridge.engine_destroy(self.handle);self.handle=None
 def __del__(self):
  if getattr(self,'handle',None):self.close()
class EngineStore:
 def __init__(self,path,bridge=None):
  self.path=path;self.bridge=bridge or load_engine_bridge();self.lock=threading.RLock();self.storage_ok=True
  self.defaults=json.loads((R/'config/engine/defaults.json').read_text());self.tune=copy.deepcopy(self.defaults);self.error=''
  if path.exists():
   try:
    body=path.read_bytes()
    if len(body)>16384 or b'\0' in body or not self.bridge.engine_validate(body):raise ValueError('Invalid saved engine tune')
    self.tune=json.loads(body);self.tune['revision']=int(self.tune['revision'])
   except (ValueError,OSError):self.storage_ok=False;self.error='Saved engine tune invalid; file preserved, defaults shadow-only'
  self.runtime=EngineRuntime(self.tune,self.bridge);self.latest=None;self.last_run=None
 def save(self,body):
  if len(body)>16384:return 413,{'error':'Engine tune exceeds 16 KiB'}
  if b'\0' in body or not self.bridge.engine_validate(body):return 422,{'error':'Invalid engine tune: schema, axes or pulse limits'}
  candidate=json.loads(body)
  with self.lock:
   if not self.storage_ok:return 503,{'error':self.error}
   if candidate['revision']!=self.tune['revision'] or candidate['revision']==4294967295:return 409,{'error':'Engine tune revision changed; reload'}
   candidate['revision']=int(candidate['revision'])+1;encoded=json.dumps(candidate,separators=(',',':'),allow_nan=False).encode();temp=None
   if len(encoded)>16384:return 413,{'error':'Encoded engine tune exceeds 16 KiB; previous data retained'}
   try:
    self.path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as f:temp=Path(f.name);f.write(encoded);f.flush();os.fsync(f.fileno())
    os.replace(temp,self.path)
    descriptor=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
   except OSError:
    if temp and temp.exists():temp.unlink()
    self.storage_ok=False;self.error='Engine persistence failed; runtime retained, saves blocked until restart and inspection'
    return 507,{'error':self.error}
   self.tune=candidate;self.runtime.configure(candidate);self.latest=None;self.last_run=None;return 200,candidate
 def status(self):
  with self.lock:
   result=dict(self.latest or dict(state='stopped',faults=0,execution='SIL not yet run',physical_outputs_enabled=False))
   result.update(simulator=True,revision=self.tune['revision'],storage_ok=self.storage_ok,binding='Native C++ core; independent reduced-order SIL plant, unvalidated',error=self.error)
   result['data_source']='completed_sil_snapshot' if self.last_run else 'no_sil_result'
   result['sample_age_ms']=int(max(0,time.monotonic()-self.completed_monotonic)*1000) if self.last_run else None
   result['fresh']=False
   if self.last_run:result['last_run']=self.last_run['summary']
   return result

 def run(self,request):
  from engine_sil import Simulation
  if not isinstance(request,dict) or set(request)-{'scenario','duration_s','seed'}:return 422,{'error':'Invalid SIL request'}
  with self.lock:
   if getattr(self,'running',False):return 409,{'error':'An engine SIL run is already active'}
   self.running=True;tune=copy.deepcopy(self.tune);revision=tune['revision']
  try:
   result=Simulation(tune,request.get('scenario','warm_start'),request.get('duration_s',10),request.get('seed',1)).run()
   with self.lock:
    if self.tune['revision']!=revision:return 409,{'error':'Tune changed during simulation; result not published'}
    result['summary']['tune_revision']=revision;self.last_run=result;self.completed_monotonic=time.monotonic();self.latest=dict(result['final']);return 200,result
  except (ValueError,TypeError) as e:return 422,{'error':str(e)}
  finally:
   with self.lock:self.running=False
 def msl(self):
  with self.lock:
   if not self.last_run:raise ValueError('Run a SIL scenario before exporting a log')
   rows=copy.deepcopy(self.last_run['trace']);scenario=self.last_run['summary']['scenario']
  from engine_log import export_msl
  return export_msl(rows,scenario)
