"""Own005 development protocol, shared with the inhibited target USB service.

One complete calibration page avoids automatic cross-page burn transitions.
Historical own001/002/003 INIs and own003 codec remain separate records.
"""
import struct,copy,json
from engine_runtime import R
from idle_config import ALGORITHMS,SCALARS,ARRAYS,SCALAR_OFFSETS,ARRAY_OFFSETS,USED_END,PAGE_BYTES
import engine_protocol_legacy as legacy
from engine_protocol_legacy import (NUMBERS,FLAGS,CURVES,REVISION_OFFSET,
 TIMING_FIELDS,STRATEGIES,LIVE_FIELDS,field_units as legacy_field_units,envelope,LEGACY_SIGNATURE,
 SEQUENTIAL_SIGNATURE,SERIAL_PROTOCOL)
from tuning_runtime import Session,Stream

DEFAULT=json.loads((R/'config/engine/defaults.json').read_text())
WHOLE_SIGNATURE=b'ESP32ECU DEV 004 INHIBITED'
CYLINDER_SIGNATURE=legacy.SIGNATURE
SIGNATURE=b'ESP32ECU DEV 005 INHIBITED'
VERSION=b'ESP32ECU development; staged whole-tune burn; outputs inhibited'
PAGE_SIZES={1:PAGE_BYTES}
PAGE_OFFSETS={1:0,2:512,3:1664,4:2816,5:3968}
LIVE_BYTES=256
def field_units(name):return {'idle_kp':'%/RPM','idle_ki':'%/(RPM*s)'}.get(name,legacy_field_units(name))

def pages(tune):
 old=legacy.pages(tune)
 page=bytearray(b''.join(old[i] for i in range(1,6))+bytes(PAGE_BYTES-4768));control=tune['idle_control']
 struct.pack_into('<I',page,4768,ALGORITHMS.index(control['algorithm']))
 for name in SCALARS:struct.pack_into('<f',page,SCALAR_OFFSETS[name],control[name])
 for name,n in ARRAYS:struct.pack_into('<'+str(n)+'f',page,ARRAY_OFFSETS[name],*control[name])
 return {1:page}

def decode_pages(buffers,base):
 if set(buffers)!={1} or len(buffers[1])!=PAGE_BYTES:raise ValueError('Own005 requires one complete 4992-byte page')
 p=buffers[1]
 if any(p[292:512]) or any(p[4756:4768]) or any(p[USED_END:]):raise ValueError('Reserved tune bytes must be zero')
 old={i:p[offset:offset+legacy.PAGE_SIZES[i]] for i,offset in PAGE_OFFSETS.items()}
 candidate=legacy.decode_pages(old,base);candidate['schema_version']=4;candidate['idle_control']=copy.deepcopy(DEFAULT['idle_control'])
 algorithm=struct.unpack_from('<I',p,4768)[0]
 if algorithm>=len(ALGORITHMS):raise ValueError('Unknown idle algorithm')
 candidate['idle_control']['algorithm']=ALGORITHMS[algorithm]
 for name in SCALARS:candidate['idle_control'][name]=struct.unpack_from('<f',p,SCALAR_OFFSETS[name])[0]
 for name,n in ARRAYS:candidate['idle_control'][name]=list(struct.unpack_from('<'+str(n)+'f',p,ARRAY_OFFSETS[name]))
 # Keep offline binary helpers under the same native whole-tune validator.
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(candidate);candidate=runtime.tune;runtime.close()
 return candidate

def live_block(store):
 # Completed host snapshots are synthetic and may precede the active tune.
 # Session metadata is filled by the shared native Session, not this helper.
 with store.lock:
  block=bytearray(legacy.live_block(store));sample=store.coherent_sample()
  if not sample.get('flags',0)&1:struct.pack_into('<I',block,56,0)
  idle=sample.get('idle',{});values=[float(idle.get(k,0) or 0) for k in ('target_rpm','feedforward_pct','p_term','i_term','d_term','duty_pct')]
  return bytes(block)+struct.pack('<8I',store.tune['revision'],0,0,0,6,0,sample.get('input_valid_mask',0),sample.get('flags',0))+struct.pack('<6f4I',*values,idle.get('flags',0)|(256 if idle.get('available',False) else 0),idle.get('state_code',0),idle.get('reason_code',0),idle.get('algorithm_code',0))
