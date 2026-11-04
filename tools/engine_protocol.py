"""Own007 development protocol, shared with the inhibited target USB service.

One complete calibration page avoids automatic cross-page burn transitions.
Historical own001/002/003 INIs and own003 codec remain separate records.
"""
import struct,copy,json
from types import SimpleNamespace
from engine_runtime import R
from idle_config import ALGORITHMS,SCALARS,ARRAYS,SCALAR_OFFSETS,ARRAY_OFFSETS,USED_END as IDLE_USED_END
from transient_config import PAGE_BYTES,LIVE_BYTES,OFFSET as AE_OFFSET,USED_END as AE_USED_END,SCALARS as AE_SCALARS,ARRAYS as AE_ARRAYS,SCALAR_OFFSETS as AE_SCALAR_OFFSETS,ARRAY_OFFSETS as AE_ARRAY_OFFSETS,MODES,APPLIES,VALUE_NAMES
import engine_protocol_legacy as legacy
from engine_protocol_legacy import (NUMBERS,FLAGS,CURVES,REVISION_OFFSET,
 TIMING_FIELDS,LIVE_FIELDS,field_units as legacy_field_units,envelope,LEGACY_SIGNATURE,
 SEQUENTIAL_SIGNATURE,SERIAL_PROTOCOL)
from tuning_runtime import Session,Stream

DEFAULT=json.loads((R/'config/engine/defaults.json').read_text())
WHOLE_SIGNATURE=b'ESP32ECU DEV 004 INHIBITED'
CYLINDER_SIGNATURE=legacy.SIGNATURE
IDLE_SIGNATURE=b'ESP32ECU DEV 005 INHIBITED'
SEMI_SIGNATURE=b'ESP32ECU DEV 006 INHIBITED'
SIGNATURE=b'ESP32ECU DEV 007 INHIBITED'
STRATEGIES=legacy.STRATEGIES+('semi_sequential_4cyl',)
STRATEGY_LABELS=('Batch / wasted','Sequential','Semi-sequential')
VERSION=b'ESP32ECU development; staged whole-tune burn; outputs inhibited'
PAGE_SIZES={1:PAGE_BYTES}
PAGE_OFFSETS={1:0,2:512,3:1664,4:2816,5:3968}
def field_units(name):return {'idle_kp':'%/RPM','idle_ki':'%/(RPM*s)'}.get(name,legacy_field_units(name))

def pages(tune):
 # Reuse the frozen prefix serializer, then write the new identity's enum.
 # The placeholder is private and never emitted or assigned to a live tune.
 compatible=tune if tune['strategy'] in legacy.STRATEGIES else dict(tune,strategy=legacy.STRATEGIES[0])
 old=legacy.pages(compatible)
 page=bytearray(b''.join(old[i] for i in range(1,6))+bytes(PAGE_BYTES-4768));control=tune['idle_control']
 struct.pack_into('<I',page,272,STRATEGIES.index(tune['strategy']))
 struct.pack_into('<I',page,4768,ALGORITHMS.index(control['algorithm']))
 for name in SCALARS:struct.pack_into('<f',page,SCALAR_OFFSETS[name],control[name])
 for name,n in ARRAYS:struct.pack_into('<'+str(n)+'f',page,ARRAY_OFFSETS[name],*control[name])
 ae=tune['transient_enrichment'];struct.pack_into('<II',page,AE_OFFSET,MODES.index(ae['mode']),APPLIES.index(ae['apply']))
 for name in AE_SCALARS:struct.pack_into('<f',page,AE_SCALAR_OFFSETS[name],ae[name])
 for name in AE_ARRAYS:struct.pack_into('<4f',page,AE_ARRAY_OFFSETS[name],*ae[name])
 return {1:page}

def decode_pages(buffers,base):
 if set(buffers)!={1} or len(buffers[1])!=PAGE_BYTES:raise ValueError('Own007 requires one complete 5120-byte page')
 p=buffers[1]
 if any(p[292:512]) or any(p[4756:4768]) or any(p[IDLE_USED_END:AE_OFFSET]) or any(p[AE_USED_END:]):raise ValueError('Reserved tune bytes must be zero')
 strategy=struct.unpack_from('<I',p,272)[0]
 if strategy>=len(STRATEGIES):raise ValueError('Unknown engine strategy')
 old={i:bytearray(p[offset:offset+legacy.PAGE_SIZES[i]]) for i,offset in PAGE_OFFSETS.items()}
 struct.pack_into('<I',old[1],272,strategy if strategy<len(legacy.STRATEGIES) else 0)
 candidate=legacy.decode_pages(old,base);candidate['schema_version']=6;candidate['strategy']=STRATEGIES[strategy];candidate['idle_control']=copy.deepcopy(DEFAULT['idle_control'])
 algorithm=struct.unpack_from('<I',p,4768)[0]
 if algorithm>=len(ALGORITHMS):raise ValueError('Unknown idle algorithm')
 candidate['idle_control']['algorithm']=ALGORITHMS[algorithm]
 for name in SCALARS:candidate['idle_control'][name]=struct.unpack_from('<f',p,SCALAR_OFFSETS[name])[0]
 for name,n in ARRAYS:candidate['idle_control'][name]=list(struct.unpack_from('<'+str(n)+'f',p,ARRAY_OFFSETS[name]))
 mode,apply=struct.unpack_from('<II',p,AE_OFFSET)
 if mode>=len(MODES) or apply>=len(APPLIES):raise ValueError('Unknown transient mode or application')
 ae=candidate['transient_enrichment']=dict(mode=MODES[mode],apply=APPLIES[apply])
 for name in AE_SCALARS:ae[name]=struct.unpack_from('<f',p,AE_SCALAR_OFFSETS[name])[0]
 for name in AE_ARRAYS:ae[name]=list(struct.unpack_from('<4f',p,AE_ARRAY_OFFSETS[name]))
 # Keep offline binary helpers under the same native whole-tune validator.
 from engine_runtime import EngineRuntime
 runtime=EngineRuntime(candidate);candidate=runtime.tune;runtime.close()
 return candidate

def live_block(store):
 # Completed host snapshots are synthetic and may precede the active tune.
 # Session metadata is filled by the shared native Session, not this helper.
 with store.lock:
  view=SimpleNamespace(lock=store.lock,tune=dict(store.tune,strategy=legacy.STRATEGIES[0]),last_run=store.last_run)
  if hasattr(store,'completed_monotonic'):view.completed_monotonic=store.completed_monotonic
  block=bytearray(legacy.live_block(view));struct.pack_into('<I',block,92,STRATEGIES.index(store.tune['strategy']));sample=store.coherent_sample()
  if not sample.get('flags',0)&1:struct.pack_into('<I',block,56,0)
  idle=sample.get('idle',{});values=[float(idle.get(k,0) or 0) for k in ('target_rpm','feedforward_pct','p_term','i_term','d_term','duty_pct')]
  prefix=bytes(block)+struct.pack('<8I',store.tune['revision'],0,0,0,6,0,sample.get('input_valid_mask',0),sample.get('flags',0))+struct.pack('<6f4I',*values,idle.get('flags',0)|(256 if idle.get('available',False) else 0),idle.get('state_code',0),idle.get('reason_code',0),idle.get('algorithm_code',0))
  ae=sample.get('transient_enrichment',{}) if sample.get('flags',0)&1 else {};known=bool(ae.get('available'));values=[float(ae.get(k,0) or 0) if known else 0. for k in VALUE_NAMES]
  return prefix+struct.pack('<8f8I',*values,int(ae.get('flags',0))|(256 if known else 0),int(ae.get('mode_code',0)),int(ae.get('apply_code',0)),int(ae.get('phase_code',0)),int(ae.get('reason_code',0)),0,0,0)
