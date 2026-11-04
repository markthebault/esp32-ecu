"""Retained own003 codec and offsets. Its Session/Stream are historical records.
Current endpoints use the own005 target-shared core in engine_protocol.py.
"""
import copy,json,struct,zlib,time
from pathlib import Path
from engine_runtime import R
LEGACY_SIGNATURE=b'ESP32ECU SIL 001 INHIBITED'
SEQUENTIAL_SIGNATURE=b'ESP32ECU SIL 002 INHIBITED'
SIGNATURE=b'ESP32ECU SIL 003 INHIBITED'
# Serial envelope protocol revision is independent of our tune-layout identity.
SERIAL_PROTOCOL=b'002'
STRATEGIES=('batch_wasted_4cyl','sequential_4cyl')
TIMING_FIELDS=(('injection_end_deg',276),('cam_sync_deg',280),('cam_window_deg',284))
VERSION=b'ESP32ECU completed SIL snapshot; physical outputs inhibited'
DEFAULT=json.loads((R/'config/engine/defaults-v3.json').read_text())
NUMBERS=[('engine',k) for k,v in DEFAULT['engine'].items()]+[('settings',k) for k,v in DEFAULT['settings'].items() if not isinstance(v,bool)]
FLAGS=[k for k,v in DEFAULT['settings'].items() if isinstance(v,bool)]
CURVES=[(k,len(v)) for k,v in DEFAULT['curves'].items()]
REVISION_OFFSET=268
PAGE_SIZES={1:512,2:1152,3:1152,4:1152,5:800}
LIVE_FIELDS=('time','rpm','map_kpa','tps','lambda_measured','pulse_ms','advance_deg','dwell_ms','ve_pct','target_lambda','ego')
def field_units(name):
 special={'displacement_cc':'cc','injector_cc_min':'cc/min','fuel_density_g_cc':'g/cc','stoich_afr':'AFR','soft_limit_band':'RPM','rpm_hysteresis':'RPM','dfco_hysteresis':'RPM','dfco_tps':'%','afterstart_pct':'%','accel_threshold_pct_s':'%/s','accel_gain':'s/%','ego_min_clt':'C','max_duty':'ratio','ego_limit':'ratio'}
 return special.get(name,'RPM' if 'rpm' in name else 'ms' if name.endswith('_ms') else 'deg' if 'deg' in name else 's' if name.endswith('_s') else 'C' if name.endswith('_c') else '')
def pages(tune):
 result={i:bytearray(n) for i,n in PAGE_SIZES.items()};p=result[1]
 struct.pack_into('<I',p,0,sum(int(tune['settings'][name])<<i for i,name in enumerate(FLAGS)))
 for i,(group,name) in enumerate(NUMBERS):struct.pack_into('<f',p,4+i*4,tune[group][name])
 offset=4+4*len(NUMBERS)
 for name,n in CURVES:struct.pack_into('<'+str(n)+'f',p,offset,*tune['curves'][name]);offset+=n*4
 assert offset==REVISION_OFFSET
 struct.pack_into('<I',p,REVISION_OFFSET,tune['revision'])
 struct.pack_into('<I',p,272,STRATEGIES.index(tune['strategy']))
 for name,offset in TIMING_FIELDS:struct.pack_into('<f',p,offset,tune['timing'][name])
 struct.pack_into('<4B',p,288,*tune['timing']['firing_order'])
 for page,name in [(2,'ve'),(3,'spark'),(4,'lambda')]:
  m=tune['maps'][name];struct.pack_into('<288f',result[page],0,*(m['rpm']+m['load']+m['cells']))
 for cylinder in range(4):
  m=tune['cylinder_trims']['fuel_maps'][cylinder];struct.pack_into('<48f',result[5],192*cylinder,*(m['rpm']+m['load']+m['cells']))
 struct.pack_into('<4fI',result[5],768,*tune['cylinder_trims']['spark_deg'],int(tune['cylinder_trims']['enabled']))
 return result

def decode_pages(buffers,base):
 candidate=copy.deepcopy(base);p=buffers[1];flag=struct.unpack_from('<I',p)[0]
 if struct.unpack_from('<I',p,REVISION_OFFSET)[0]!=base['revision']:raise ValueError('Tune base revision is read-only')
 if flag>>len(FLAGS):raise ValueError('Unknown tune flag')
 for i,k in enumerate(FLAGS):candidate['settings'][k]=bool(flag&(1<<i))
 for i,(group,name) in enumerate(NUMBERS):
  value=struct.unpack_from('<f',p,4+i*4)[0]
  if name=='cylinders':
   if value!=4:raise ValueError('Only four cylinders supported')
   value=4
  candidate[group][name]=value
 offset=4+4*len(NUMBERS)
 for name,n in CURVES:candidate['curves'][name]=list(struct.unpack_from('<'+str(n)+'f',p,offset));offset+=n*4
 strategy=struct.unpack_from('<I',p,272)[0]
 if strategy>=len(STRATEGIES):raise ValueError('Unknown engine strategy')
 candidate['schema_version']=3;candidate['strategy']=STRATEGIES[strategy]
 for name,offset in TIMING_FIELDS:candidate['timing'][name]=struct.unpack_from('<f',p,offset)[0]
 candidate['timing']['firing_order']=list(struct.unpack_from('<4B',p,288))
 for page,name in [(2,'ve'),(3,'spark'),(4,'lambda')]:
  v=list(struct.unpack('<288f',buffers[page]));candidate['maps'][name]=dict(rpm=v[:16],load=v[16:32],cells=v[32:])
 for cylinder in range(4):
  v=list(struct.unpack_from('<48f',buffers[5],192*cylinder));candidate['cylinder_trims']['fuel_maps'][cylinder]=dict(rpm=v[:6],load=v[6:12],cells=v[12:])
 values=struct.unpack_from('<4fI',buffers[5],768)
 if values[4] not in (0,1) or any(buffers[5][788:]):raise ValueError('Unknown cylinder trim flags/reserved bytes')
 candidate['cylinder_trims']['spark_deg']=list(values[:4]);candidate['cylinder_trims']['enabled']=bool(values[4])
 return candidate

def envelope(payload):return struct.pack('>H',len(payload))+payload+struct.pack('>I',zlib.crc32(payload)&0xffffffff)

def live_block(store):
 # One lock protects the result, revision and completion clock. This endpoint
 # exposes a completed historical SIL snapshot, not a stream from a real ECU.
 with store.lock:
  strategy=STRATEGIES.index(store.tune['strategy'])
  last=store.last_run;has_result=bool(last and last['trace'])
  data=copy.deepcopy(last['trace'][-1]) if has_result else {}
  revision=last['summary']['tune_revision'] if has_result else store.tune['revision']
  age_ms=min(4294967295,int(max(0,time.monotonic()-getattr(store,'completed_monotonic',time.monotonic()))*1000)) if has_result else 4294967295
 values=[float(data.get(k,0) or 0) for k in LIVE_FIELDS]
 prefix=struct.pack('<11f8I',*values,int(data.get('faults',0)),int(data.get('synced',False)),1,int(revision),1 if has_result else 0,age_ms,int(has_result),int(has_result))
 phase=struct.pack('<6I',int(data.get('crank_synced',False)),int(data.get('phase_synced',False)),int(data.get('phase_required',False)),int(data.get('phase_losses',0)),strategy,int(data.get('cam_rejected',0)))
 cyl=data.get('cylinders',{});proposals=cyl.get('proposals',[])
 channels=[float(proposals[i].get(name,0) or 0) if i<len(proposals) else 0. for i in range(4) for name in ('pulse_ms','advance_deg','fuel_pct','duty_pct')]
 extension=struct.pack('<16f5I',*channels,int(bool(cyl.get('available')))*15,int(bool(cyl.get('enabled'))),int(cyl.get('capacity_mask',0)),int(cyl.get('spark_clamp_mask',0)),int(cyl.get('retard_floor_mask',0)))
 return prefix+phase+extension

class Session:
 def __init__(self,store):
  self.store=store;self.dirty=False
  with store.lock:self.base=copy.deepcopy(store.tune)
  self.buffers=pages(self.base)
 def command(self,payload):
  if payload==b'Q':return b'\0'+SIGNATURE
  if payload==b'S':return b'\0'+VERSION
  if payload==b'F':return b'\0'+SERIAL_PROTOCOL
  if payload==b'C':return b'\0\xff'
  if payload==b'I':return b'\0\0' # Local controller CAN identifier, no forwarding.
  if payload in (b'f\0',b'f\xff'):return b'\0\x02'+struct.pack('>HH',256,256)
  if not payload:return b'\x83'
  cmd=payload[0:1]
  try:
   # Calibration is pinned to this connection's snapshot. Even a previously
   # clean client may hold cached constants; another writer requires reconnect.
   # Runtime polling must never silently acknowledge a newer calibration.
   if cmd==b'r':
    if len(payload)!=7:return b'\x84'
    can,page,offset,count=struct.unpack('<BBHH',payload[1:7]);block=live_block(self.store)
    if can or page!=0x30 or count>len(block) or offset+count>len(block):return b'\x84'
    return b'\0'+block[offset:offset+count]
   if cmd in (b'p',b'M'):
    if len(payload)<7:return b'\x84'
    can,page,offset,count=struct.unpack('<BBHH',payload[1:7])
    if can or page not in self.buffers or offset+count>len(self.buffers[page]):return b'\x84'
    if cmd==b'p':
     if len(payload)!=7:return b'\x84'
     return b'\0'+self.buffers[page][offset:offset+count]
    if len(payload)!=7+count:return b'\x84'
    self.buffers[page][offset:offset+count]=payload[7:];self.dirty=True;return b'\0'
   if cmd in (b'd',b'b'):
    if len(payload)!=3 or payload[1]!=0 or payload[2] not in self.buffers:return b'\x84'
    page=payload[2]
    if cmd==b'd':return b'\0'+struct.pack('>I',zlib.crc32(self.buffers[page])&0xffffffff)
    if not self.dirty:return b'\x04'
    candidate=decode_pages(self.buffers,self.base)
    code,value=self.store.save(json.dumps(candidate,separators=(',',':'),allow_nan=False).encode())
    if code!=200:return b'\x85' if code in (409,503,507) else b'\x84'
    self.base=copy.deepcopy(value);self.buffers=pages(value);self.dirty=False;return b'\x04'
  except (ValueError,OverflowError,struct.error):return b'\x84'
  return b'\x83'

class Stream:
 def __init__(self,store):self.store=store;self.session=Session(store);self.buffer=bytearray()
 def feed(self,data):
  self.buffer.extend(data);responses=[]
  while self.buffer:
   if self.buffer[0] in b'QSF':
    cmd=bytes(self.buffer[:1]);del self.buffer[:1];responses.append({b'Q':SIGNATURE,b'S':VERSION,b'F':SERIAL_PROTOCOL}[cmd]);continue
   if len(self.buffer)<2:break
   size=struct.unpack('>H',self.buffer[:2])[0]
   if not 1<=size<=4096:self.buffer.clear();responses.append(envelope(b'\x84'));break
   if len(self.buffer)<size+6:break
   payload=bytes(self.buffer[2:2+size]);crc=struct.unpack('>I',self.buffer[2+size:6+size])[0];del self.buffer[:6+size]
   responses.append(envelope(self.session.command(payload) if zlib.crc32(payload)&0xffffffff==crc else b'\x82'))
  return responses
