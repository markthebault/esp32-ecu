"""Schema5 flex fragment codec/validation. A fragment is never an observation.

F32 fields describe a completed controller decision. They are not reassessed
as the original F64 capture, nor do they qualify hardware or a physical engine.
"""
import hmac,math,struct
from espnow_protocol import check
from flex_config import FLAGS,VALUES,TIMES,CAPTURE_FLOATS,SOURCE_NAMES,REASONS

FLEX_SIZE=232;FLEX_BODY=200;UINT32_MAX=2**32-1
def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
def inside(v,low,high):return math.isfinite(v) and low<=v<=high
def stale_limit(cal):return math.floor(cal['stale_ms']*1000+.5)
def timestamp_known(f):return f['source_code']==3 and (f['sample_value_valid'] or f['sample_us']!='0') or f['source_code'] in (1,2) and f['sample_us']!='0'

def calibration_valid(c):
 low,high,fault,tolerance,stale,filter_ms=[c[k] for k in CAPTURE_FLOATS]
 return all(math.isfinite(v) for v in (low,high,fault,tolerance,stale,filter_ms)) and 10<=low<=180 and f32(low+10)<=high<=200 and f32(high+5)<=fault<=500 and 0<=tolerance<=2 and 250<=stale<=2000 and stale>=2000/f32(low-tolerance) and 0<=filter_ms<=5000 and 2<=c['cycles']<=32

def decode_record(packet):
 times=struct.unpack_from('<7Q',packet,56);values=struct.unpack_from('<10f',packet,112);calibration=struct.unpack_from('<6f',packet,152)
 flags,revision=struct.unpack_from('<II',packet,176);codes=struct.unpack_from('<7B',packet,184)
 source,reason,capture_reason,last_fault,correction_reason,cycles,cal_cycles=codes
 if flags&~131071 or source>3 or max(codes[1:5])>22 or cycles>32 or cal_cycles>32:raise ValueError('Invalid flex enums/flags')
 if any(math.isinf(v) for v in values) or any(not math.isfinite(v) for v in calibration):raise ValueError('Invalid flex numeric value')
 # All sender unknowns use its canonical quiet NaN; no hidden NaN payload.
 for n,v in enumerate(values):
  if math.isnan(v) and struct.unpack_from('<I',packet,112+4*n)[0]!=0x7fc00000:raise ValueError('Noncanonical flex NaN')
 f={name:bool(flags&(1<<n)) for n,name in enumerate(FLAGS)}
 f.update(zip(VALUES,values));f.update((name,str(v)) for name,v in zip(TIMES,times))
 f.update(source=SOURCE_NAMES[source],source_code=source,reason=REASONS[reason],reason_code=reason,capture_reason=REASONS[capture_reason],capture_reason_code=capture_reason,last_fault=REASONS[last_fault],last_fault_code=last_fault,correction_reason=REASONS[correction_reason],correction_reason_code=correction_reason,window_cycles=cycles,configuration_revision=revision,capture_calibration=dict(zip(CAPTURE_FLOATS,calibration),cycles=cal_cycles))
 if f['available'] and not calibration_valid(f['capture_calibration']):raise ValueError('Invalid flex producer calibration')
 if f['corrections_enabled'] and not f['required']:raise ValueError('Flex correction must be required')
 if f['value_qualified'] and (source==0 or source==1 and not f['input_confirmed']):raise ValueError('Invalid flex source qualification')
 if f['raw_capture_qualified']!=bool(f['value_qualified'] and source in (1,2)) or f['capture_valid']!=bool(f['sample_value_valid'] and source in (1,2)):raise ValueError('Invalid flex capture qualification')
 if f['value_qualified'] and (not f['configuration_match'] or not f['sample_value_valid'] or f['pending_fault'] or times[4]!=times[5] or not inside(values[2],0,100) or not times[6] or not revision or not inside(values[6],0,stale_limit(f['capture_calibration'])/1000+.001)):raise ValueError('Invalid flex qualified sample')
 if f['raw_capture_qualified'] and (not f['capture_valid'] or reason!=2 or capture_reason!=2 or cycles!=cal_cycles or not times[1]<times[0]<=times[2] or not inside(values[0],1,500) or not inside(values[1],998,5002) or not inside(values[3],-40,125)):raise ValueError('Invalid flex window')
 if source==3 and (f['capture_valid'] or f['raw_capture_qualified'] or cycles or any(math.isfinite(values[n]) for n in (0,1,3,4,5)) or f['value_qualified'] and (reason!=21 or capture_reason!=4)):raise ValueError('Scalar is not raw flex capture')
 if f['corrections_enabled'] and f['corrections_valid'] and not f['raw_capture_qualified'] or f['required'] and f['control_ok'] and (not f['value_qualified'] or f['corrections_enabled'] and not f['corrections_valid']):raise ValueError('Invalid flex control decision')
 if f['corrections_valid'] and not (inside(values[7],0,255) and inside(values[8],-40,40) and inside(values[9],0,255)):raise ValueError('Invalid flex correction factors')
 if f['zero_factor']!=bool(f['corrections_enabled'] and f['corrections_valid'] and (values[7]==0 or values[9]==0)):raise ValueError('Invalid flex zero factor')
 if not f['available'] and (flags or revision or any(codes) or any(times) or any(calibration) or any(not math.isnan(v) for v in values)):raise ValueError('Unavailable flex is not canonical empty')
 for key in VALUES:
  if math.isnan(f[key]):f[key]=None
 return f

def engine_flex_fragment(packet,key):
 if len(key)!=32:raise ValueError('Engine key must be32 bytes')
 check(packet,11,FLEX_SIZE)
 if not hmac.compare_digest(packet[FLEX_BODY:],hmac.digest(key,packet[:FLEX_BODY],'sha256')):raise ValueError('Flex authentication failed')
 session,sequence,schema,reserved=struct.unpack_from('<IQHH',packet,8)
 if not session or not sequence or schema!=5 or reserved or packet[191]:raise ValueError('Invalid flex fragment header')
 f=decode_record(packet);age,stale=struct.unpack_from('<II',packet,192)
 if stale!=(stale_limit(f['capture_calibration']) if f['available'] else 0):raise ValueError('Flex stale limit changed')
 if age!=UINT32_MAX and (not f['available'] or not timestamp_known(f)):raise ValueError('Unknown flex timestamp cannot have an age')
 return dict(complete=False,session=session,packet_sequence=sequence,schema_version=5,base_mac=packet[24:56],flex_fuel=f,raw_age_ms=None if age==UINT32_MAX else age,stale_limit_us=stale,immutable=packet[56:192]+packet[196:200])
