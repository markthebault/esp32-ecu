"""Shared native ECU core and persistent shadow-engine tune. No GPIO transport."""
import copy, ctypes, fcntl, json, os, secrets, subprocess, tempfile, threading, time, weakref
from pathlib import Path
R=Path(__file__).resolve().parents[1]
_build_lock=threading.Lock()
def load_engine_bridge():
 with _build_lock:
  out=R/'.cache/engine';out.mkdir(parents=True,exist_ok=True)
  cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
  if not (cjson/'cJSON.c').exists():raise RuntimeError('Build firmware with pinned PlatformIO framework first')
  # Include transitive headers: a scheduler-only fix must rebuild the SIL binary.
  deps=[Path(__file__),R/'tools/engine_bridge.cpp',R/'tools/trigger_capture_bridge.hpp',R/'firmware/main/config_json.hpp',cjson/'cJSON.c',cjson/'cJSON.h',*sorted((R/'firmware/include/ecu').glob('*.hpp'))]
  lib=out/'libengine.so'
  with (out/'build.lock').open('a+b') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if not lib.exists() or max(p.stat().st_mtime for p in deps)>lib.stat().st_mtime:
    subprocess.run(['cc','-O2','-fPIC','-c',str(cjson/'cJSON.c'),'-o',str(out/'cJSON.o')],check=True)
    subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(cjson),'-I'+str(R/'firmware/main'),'-I'+str(R/'firmware/include'),str(R/'tools/engine_bridge.cpp'),str(out/'cJSON.o'),'-o',str(out/'libengine.new.so')],check=True)
    os.replace(out/'libengine.new.so',lib)
  b=ctypes.CDLL(str(lib));b.engine_create.restype=ctypes.c_void_p;b.engine_destroy.argtypes=[ctypes.c_void_p]
  b.engine_canonicalize.argtypes=[ctypes.c_char_p];b.engine_canonicalize.restype=ctypes.c_char_p
  b.engine_validate.argtypes=[ctypes.c_char_p];b.engine_validate.restype=ctypes.c_int
  b.engine_configure.argtypes=[ctypes.c_void_p,ctypes.c_char_p];b.engine_configure.restype=ctypes.c_int
  b.engine_wheel.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint];b.engine_wheel.restype=ctypes.c_int
  b.engine_cam.argtypes=[ctypes.c_void_p,ctypes.c_uint64];b.engine_cam.restype=ctypes.c_int
  b.engine_trigger.argtypes=[ctypes.c_void_p,ctypes.c_uint64];b.engine_trigger.restype=ctypes.c_int
  b.engine_step.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint64,ctypes.c_uint64];b.engine_step.restype=ctypes.c_char_p
  b.engine_cut.argtypes=[ctypes.c_void_p]
  b.engine_timing_reason.argtypes=[ctypes.c_void_p];b.engine_timing_reason.restype=ctypes.c_char_p
  b.engine_crank_timeout.argtypes=[ctypes.c_void_p];b.engine_crank_timeout.restype=ctypes.c_uint64
  b.engine_next_time.argtypes=[ctypes.c_void_p];b.engine_next_time.restype=ctypes.c_uint64
  b.engine_pop.argtypes=[ctypes.c_void_p];b.engine_pop.restype=ctypes.c_uint
  b.engine_event_dwell.argtypes=[ctypes.c_void_p];b.engine_event_dwell.restype=ctypes.c_uint64
  b.engine_event_advance.argtypes=[ctypes.c_void_p];b.engine_event_advance.restype=ctypes.c_double
  b.engine_data_json.argtypes=[ctypes.c_void_p];b.engine_data_json.restype=ctypes.c_char_p
  b.engine_plan.argtypes=[ctypes.c_void_p];b.engine_plan.restype=ctypes.c_char_p
  return b
class EngineRuntime:
 def __init__(self,tune=None,bridge=None):
  self.bridge=bridge or load_engine_bridge();self.handle=self.bridge.engine_create()
  self.configure(tune or json.loads((R/'config/engine/defaults.json').read_text()))
 def configure(self,tune):
  body=json.dumps(tune,separators=(',',':'),allow_nan=False).encode()
  canonical=self.bridge.engine_canonicalize(body)
  if not canonical:raise ValueError('Engine tune violates schema or current hardware limits')
  value=json.loads(canonical)
  if not self.bridge.engine_configure(self.handle,canonical):raise ValueError('Engine tune violates schema or current hardware limits')
  self.tune=value
 def wheel(self,slots=60,missing=2,max_rpm=8000):
  if not self.bridge.engine_wheel(self.handle,slots,missing,max_rpm):raise ValueError('Invalid trigger wheel geometry')
 def cam(self,time_us):return self.bridge.engine_cam(self.handle,int(time_us))
 def trigger(self,time_us):return self.bridge.engine_trigger(self.handle,int(time_us))
 def step(self,inputs,time_us,sampled_us=None,use_decoder=True):
  sample=dict(rpm=0,map_kpa=45,tps_pct=10,clt_c=85,iat_c=25,lambda_=1,battery_v=13.8,sensor_v=5,synced=False,sensors_valid=True,lambda_ready=True,use_decoder=use_decoder)
  sample['lambda']=sample.pop('lambda_');sample.update(inputs)
  out=json.loads(self.bridge.engine_step(self.handle,json.dumps(sample,allow_nan=False).encode(),int(time_us),int(time_us if sampled_us is None else sampled_us)))
  if 'error' in out:raise ValueError(out['error'])
  return out
 def data(self):
  body=self.bridge.engine_data_json(self.handle)
  if not body:raise MemoryError('Engine observation allocation failed')
  data=json.loads(body)
  if data.get('schema_version')!=1:raise MemoryError('Engine observation serialization failed')
  return data
 def cut(self):self.bridge.engine_cut(self.handle)
 def timing_reason(self):return self.bridge.engine_timing_reason(self.handle).decode()
 def crank_timeout_us(self):return self.bridge.engine_crank_timeout(self.handle)
 def next_event_us(self):return self.bridge.engine_next_time(self.handle)
 def pop_event(self):
  code=self.bridge.engine_pop(self.handle)
  if code==0x40000:return -1,False,0,0 # Native PWM cycle boundary with no pin transition.
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
  self.tuning_registry_lock=threading.Lock();self.tuning_sessions=weakref.WeakSet()
  self.defaults=json.loads((R/'config/engine/defaults.json').read_text());self.tune=copy.deepcopy(self.defaults);self.error=''
  if path.exists():
   try:
    body=path.read_bytes()
    if len(body)>49152 or b'\0' in body or not self.bridge.engine_validate(body):raise ValueError('Invalid saved engine tune')
    self.tune=self.canonical(body)
   except (ValueError,OSError):self.storage_ok=False;self.error='Saved engine tune could not be loaded or migrated (invalid, too large, or allocation failure); file preserved, defaults shadow-only'
  self.runtime=EngineRuntime(self.tune,self.bridge);self.latest=None;self.last_run=None
  from trigger_capture import TriggerCapture
  self.trigger_capture=TriggerCapture(self.bridge);self.trigger_metadata={}
  from engine_observability import EngineRecorder
  self.data_recorder=EngineRecorder();self.data_boot=secrets.token_hex(16);self.data_log_metadata={}
 def canonical(self,body):
  encoded=self.bridge.engine_canonicalize(body)
  if not encoded:raise ValueError('Engine tune canonicalization failed')
  value=json.loads(encoded);value['revision']=int(value['revision']);return value
 def save(self,body):
  if len(body)>49152:return 413,{'error':'Engine tune exceeds 48 KiB'}
  if b'\0' in body or not self.bridge.engine_validate(body):return 422,{'error':'Invalid engine tune: schema, axes or pulse limits'}
  try:candidate=self.canonical(body)
  except (ValueError,MemoryError):return 500,{'error':'Engine tune canonicalization failed; previous data retained'}
  with self.lock:
   if not self.storage_ok:return 503,{'error':self.error}
   if candidate['revision']!=self.tune['revision'] or candidate['revision']==4294967295:return 409,{'error':'Engine tune revision changed; reload'}
   candidate['revision']=int(candidate['revision'])+1;encoded=json.dumps(candidate,separators=(',',':'),allow_nan=False).encode();temp=None
   if len(encoded)>49152:return 413,{'error':'Encoded engine tune exceeds 48 KiB; previous data retained'}
   try:prepared=EngineRuntime(candidate,self.bridge)
   except (ValueError,MemoryError):return 500,{'error':'Engine runtime allocation failed; previous data retained'}
   try:
    self.path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=self.path.parent,delete=False) as f:temp=Path(f.name);f.write(encoded);f.flush();os.fsync(f.fileno())
    os.replace(temp,self.path)
    descriptor=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
   except OSError:
    prepared.close()
    if temp and temp.exists():temp.unlink()
    self.storage_ok=False;self.error='Engine persistence failed; runtime retained, saves blocked until restart and inspection'
    return 507,{'error':self.error}
   old=self.runtime;self.runtime=prepared;old.close();self.tune=candidate;self.latest=None;self.last_run=None;return 200,candidate
 def status(self):
  with self.lock:
   result=dict(self.latest or dict(state='stopped',faults=0,execution='SIL not yet run',physical_outputs_enabled=False))
   result.update(simulator=True,revision=self.tune['revision'],active_strategy=self.tune['strategy'],storage_ok=self.storage_ok,binding='Native C++ core; independent reduced-order SIL plant, unvalidated',error=self.error)
   result['data_source']='completed_sil_snapshot' if self.last_run else 'no_sil_result'
   result['sample_age_ms']=int(max(0,time.monotonic()-self.completed_monotonic)*1000) if self.last_run else None
   result['fresh']=False
   if self.last_run:result['last_run']=self.last_run['summary']
   result['timing']=self.timing_status()
   result['switch_accessory']=dict(source='host_no_target_i2c',contract='SW2-J4-DRAFT1',phase='not_measured',fault='unknown',last_fault='unknown',requested_mask=None,raw_known=False,ready=False,fault_pending=False,fresh=False,bus_allocated=False,sample_age_ms=None,qualification='Host synthetic stimuli do not measure J4, an expander or contact wiring')
   return result

 def timing_status(self):
  # Host data comes from a completed SIL trace, never from a target timer.
  edges=self.last_run.get('edges',[]) if self.last_run else []
  summary=self.last_run.get('summary',{}) if self.last_run else {}
  return dict(available=False,mode='completed_native_sil' if self.last_run else 'host_no_timing_run',
              physical_policy_enabled=False,physical_high_mask=0,virtual_high_mask=0,
              dispatched=len(edges),trace_sequence=len(edges),trace_overwritten=max(0,len(edges)-128),
              max_coil_high_us=summary.get('max_dwell_high_us'),max_injector_high_us=summary.get('max_injector_high_us'),
              fault='none',last_fault=self.latest.get('timing_stop_reason','none') if self.latest else 'none',
              qualification='Completed synthetic SIL only; no target clock, IRQ or GPIO measurements')

 def timing_trace(self):
  with self.lock:
   source=self.last_run.get('edges',[]) if self.last_run else []
   start=max(0,len(source)-128)
   rows=[dict(sequence=i+1,scheduled_us=e[0],actual_us=e[0],channel=e[1],high=e[2],
              cause=e[3] if len(e)>3 else 'scheduled',tune_revision=self.tune['revision']) for i,e in enumerate(source[start:],start)]
   return dict(timing=self.timing_status(),events=rows,missed_during_snapshot=0,data_source='completed_synthetic_sil')

 def trigger_frame(self,expected=0,offset=0,records=False):
  with self.lock:
   frame=self.trigger_capture.frame(expected,offset,64 if records else 0)
   for row in frame['records']:row['raw_counter']=None
   includes_cam=self.trigger_metadata.get('includes_cam',False)
   frame.update(data_source='completed_sil_rising_crank_cam' if includes_cam else 'completed_sil_rising_crank',simulator=True,available=bool(self.last_run),
                includes_falling_edges=False,clock_uncertainty_us=None,
                diagnostic_interrupts_enabled=False,driver_error='not_applicable',
                qualification='Completed synthetic SIL rising crank'+(' and cam' if includes_cam else '')+' edges. Falling edges are not simulated; no hardware capture or voltage measurements.',**self.trigger_metadata)
   frame['includes_cam']=includes_cam
   return frame

 def trigger_command(self,body):
  if len(body)>256:return 413,{'error':'Trigger command exceeds 256 bytes'}
  with self.lock:
   if not self.trigger_capture.validate(body):return 422,{'error':'Invalid trigger command'}
   request=json.loads(body)
   if request['action']=='start':
    if not self.last_run:return 409,{'error':'Run a SIL scenario before replaying a completed trigger window'}
    end=round(self.last_run['summary']['duration_s']*1e6);start=max(0,end-request['timeout_ms']*1000)
    code=self.trigger_capture.command(body,start)
    if code!=200:return code,{'error':'Capture is active or frame changed'}
    edges=[(edge[0],False) for edge in self.last_run['trigger_edges']]+[(edge[0],True) for edge in self.last_run.get('cam_edges',[])]
    for timestamp,cam in sorted(edges):
     if timestamp>=start:self.trigger_capture.append(timestamp,cam=cam)
    self.trigger_capture.expire(start+request['timeout_ms']*1000)
    self.trigger_metadata=dict(includes_cam=bool(self.last_run.get('cam_edges')),source_scenario=self.last_run['summary']['scenario'],source_tune_revision=self.last_run['summary']['tune_revision'])
   else:
    frame=self.trigger_capture.frame();now=max(frame['ended_us'],frame['started_us'])
    code=self.trigger_capture.command(body,now)
    if code!=200:return code,{'error':'Frame changed; reload before stopping'}
   return 200,self.trigger_frame()

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
   rows=copy.deepcopy(self.last_run['trace']);scenario=self.last_run['summary']['scenario'];strategy=self.last_run['summary']['strategy']
  from engine_log import export_msl
  return export_msl(rows,scenario,strategy)

 def coherent_sample(self):
  with self.lock:
   data=copy.deepcopy(self.last_run['trace'][-1]['engine_sample']) if self.last_run else self.runtime.data()
   elapsed=round(max(0,time.monotonic()-self.completed_monotonic)*1e6) if self.last_run else 0
   end=round(self.last_run['summary']['duration_s']*1e6) if self.last_run else 0
   for key,stamp in [('sample_age_ms','sampled_us'),('control_age_ms','control_us')]:
    point=int(data[stamp]);data[key]=(max(0,end-point)+elapsed+999)//1000 if self.last_run else None
   data.update(display_fresh=False,historical=True,simulator=True,qualification='Completed synthetic SIL observation; original virtual timestamps retained, never live target measurements')
   return data

 def data_log_header(self):
  with self.lock:
   return dict(self.data_recorder.header(),boot_id=self.data_boot,producer_lock_contention_attempts=0,export_busy=False,
               scope='Completed synthetic SIL replay through the native bounded recorder; no RF, target clock or GPIO measurements',**self.data_log_metadata)

 def data_log_page(self,log_id,after,boot):
  with self.lock:
   if boot!=self.data_boot:return 409,{'error':'Device boot changed; reload log metadata'}
   page=self.data_recorder.page(log_id,after)
   page.update(boot_id=self.data_boot,copied_page=True,producer_lock_contention_attempts=0,export_busy=False,**self.data_log_metadata)
   return (409 if page['snapshot_superseded'] or page['future_cursor'] or page['invalid_row'] else 200),page

 def data_log_command(self,body,boot):
  if len(body)>256:return 413,{'error':'Log command exceeds 256 bytes'}
  with self.lock:
   if boot!=self.data_boot:return 409,{'error':'Device boot changed; reload log metadata'}
   # The C++ parser is authoritative, including duplicate keys and unknown fields.
   # Validate on a temporary recorder before touching the retained previous log.
   from engine_observability import EngineRecorder
   temporary=EngineRecorder(self.data_recorder.bridge)
   try:valid=temporary.command(body,0)
   finally:temporary.close()
   if valid==422:return 422,{'error':'Invalid log command'}
   request=json.loads(body)
   if request['action']=='start':
    if not self.last_run:return 409,{'error':'Run a SIL scenario before replaying engine observations'}
    end=round(self.last_run['summary']['duration_s']*1e6);start=max(0,end-request['duration_s']*1000000)
    result=self.data_recorder.command(body,start)
    if result!=200:return result,{'error':'Log is active or its identity changed'}
    for row in self.last_run['trace']:
     observation=row['engine_sample'];timestamp=int(observation['control_us'])
     if start<=timestamp<end:self.data_recorder.append(observation,timestamp)
    self.data_recorder.expire(start+request['duration_s']*1000000)
    self.data_log_metadata=dict(historical=True,simulator=True,source_scenario=self.last_run['summary']['scenario'],source_tune_revision=self.last_run['summary']['tune_revision'])
   else:
    h=self.data_recorder.header();result=self.data_recorder.command(body,max(int(h['started_us']),int(h['ended_us'])))
    if result!=200:return result,{'error':'Log changed; reload before stopping'}
   return 200,self.data_log_header()

 def data_log_msl(self,log_id,boot):
  with self.lock:
   if boot!=self.data_boot:raise ValueError('Device boot changed; reload log metadata')
   return self.data_recorder.msl(log_id,boot)
