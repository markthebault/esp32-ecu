"""Own011 development protocol, shared with the inhibited target USB service.

One complete calibration page avoids automatic cross-page burn transitions.
Historical own001/002/003 INIs and own003 codec remain separate records.
"""
import struct,copy,json,math
from types import SimpleNamespace
from engine_runtime import R
from idle_config import ALGORITHMS,SCALARS,ARRAYS,SCALAR_OFFSETS,ARRAY_OFFSETS,USED_END as IDLE_USED_END
from transient_config import OFFSET as AE_OFFSET,USED_END as AE_USED_END,SCALARS as AE_SCALARS,ARRAYS as AE_ARRAYS,SCALAR_OFFSETS as AE_SCALAR_OFFSETS,ARRAY_OFFSETS as AE_ARRAY_OFFSETS,MODES,APPLIES,VALUE_NAMES
from load_config import OFFSET as LOAD_OFFSET,USED_END as LOAD_USED_END,ENUM_FIELDS as LOAD_ENUM_FIELDS,SCALARS as LOAD_SCALARS,ENUM_OFFSETS as LOAD_ENUM_OFFSETS,SCALAR_OFFSETS as LOAD_SCALAR_OFFSETS,ENUMS as LOAD_ENUMS,VALUE_NAMES as LOAD_VALUE_NAMES
from secondary_config import KINDS,ENUM_FIELDS as SEC_ENUM_FIELDS,SCALARS as SEC_SCALARS,ENUMS as SEC_ENUMS,OFFSET as SEC_OFFSET,CONTROL_END as SEC_CONTROL_END,MAP_OFFSETS as SEC_MAP_OFFSETS,USED_END as SEC_USED_END,VALUE_NAMES as SEC_VALUE_NAMES,CODE_FIELDS as SEC_CODE_FIELDS,enum_offset,scalar_offset,rule_offset
from flex_config import OFFSET as FLEX_OFFSET,USED_END as FLEX_END,BOOLEANS as FLEX_BOOLS,CAPTURE_FLOATS as FLEX_FLOATS,ARRAYS as FLEX_ARRAYS,OFFSETS as FLEX_OFFSETS,get as flex_get,set_value as flex_set,DEFAULT as FLEX_DEFAULT,VALUES as FLEX_VALUES,FLAGS as FLEX_FLAGS,CODES as FLEX_CODES,TIMES as FLEX_TIMES
from boost_config import PAGE_BYTES,LIVE_BYTES,OFFSET as BOOST_OFFSET,SCALARS as BOOST_SCALARS,SCALAR_OFFSETS as BOOST_SCALAR_OFFSETS,TABLES as BOOST_TABLES,TABLE_OFFSETS as BOOST_TABLE_OFFSETS,USED_END as BOOST_END,DEFAULT as BOOST_DEFAULT,MODES as BOOST_MODES,ACTIVATIONS as BOOST_ACTIVATIONS,VALUES as BOOST_VALUES
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
TRANSIENT_SIGNATURE=b'ESP32ECU DEV 007 INHIBITED'
LOAD_SIGNATURE=b'ESP32ECU DEV 008 INHIBITED'
SECONDARY_SIGNATURE=b'ESP32ECU DEV 009 INHIBITED'
FLEX_SIGNATURE=b'ESP32ECU DEV 010 INHIBITED'
SIGNATURE=b'ESP32ECU DEV 011 INHIBITED'
STRATEGIES=legacy.STRATEGIES+('semi_sequential_4cyl',)
STRATEGY_LABELS=('Batch / wasted','Sequential','Semi-sequential')
VERSION=b'ESP32ECU development; staged whole-tune burn; outputs inhibited'
PAGE_SIZES={1:PAGE_BYTES}
PAGE_OFFSETS={1:0,2:512,3:1664,4:2816,5:3968}
def field_units(name):return {'idle_kp':'%/RPM','idle_ki':'%/(RPM*s)'}.get(name,legacy_field_units(name))

def pages(tune):
 if tune['engine']['cylinders']!=4:raise ValueError('Own011 represents exactly four cylinders; expanded profiles need a new definition')
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
 model=tune['load_model']
 for name in LOAD_ENUM_FIELDS:struct.pack_into('<I',page,LOAD_ENUM_OFFSETS[name],LOAD_ENUMS[name].index(model[name]))
 for name in LOAD_SCALARS:struct.pack_into('<f',page,LOAD_SCALAR_OFFSETS[name],model[name])
 for kind in KINDS:
  rule=tune['secondary_tables'][kind]
  for name in SEC_ENUM_FIELDS:struct.pack_into('<I',page,enum_offset(kind,name),SEC_ENUMS[name].index(rule[name]))
  for name in SEC_SCALARS:struct.pack_into('<f',page,scalar_offset(kind,name),rule[name])
  struct.pack_into('<II',page,rule_offset(kind)+28,rule['input_channel'],int(rule['active_high']))
  grid=rule['map'];struct.pack_into('<288f',page,SEC_MAP_OFFSETS[kind],*grid['rpm'],*grid['load'],*grid['cells'])

 flex=tune['flex_fuel']
 for name in FLEX_BOOLS:struct.pack_into('<I',page,FLEX_OFFSETS[name],int(flex_get(flex,name)))
 struct.pack_into('<I',page,FLEX_OFFSETS['cycles'],flex['capture']['cycles'])
 for name in FLEX_FLOATS:struct.pack_into('<f',page,FLEX_OFFSETS[name],flex_get(flex,name))
 for name in FLEX_ARRAYS:struct.pack_into('<6f',page,FLEX_OFFSETS[name],*flex_get(flex,name))
 boost=tune['boost_control']
 struct.pack_into('<3I',page,BOOST_OFFSET,int(boost['pressure_enabled']),BOOST_MODES.index(boost['mode']),BOOST_ACTIVATIONS.index(boost['activation']))
 for name in BOOST_SCALARS:struct.pack_into('<f',page,BOOST_SCALAR_OFFSETS[name],boost[name])
 for name in BOOST_TABLES:
  table=boost[name];struct.pack_into('<80f',page,BOOST_TABLE_OFFSETS[name],*table['rpm'],*table['axis'],*table['cells'])
 return {1:page}

def decode_pages(buffers,base):
 if set(buffers)!={1} or len(buffers[1])!=PAGE_BYTES:raise ValueError('Own011 requires one complete 12288-byte page')
 p=buffers[1]
 if any(p[292:512]) or any(p[4756:4768]) or any(p[IDLE_USED_END:AE_OFFSET]) or any(p[AE_USED_END:LOAD_OFFSET]) or any(p[LOAD_USED_END:SEC_OFFSET]) or any(p[SEC_CONTROL_END:SEC_MAP_OFFSETS['fuel']]) or any(p[SEC_USED_END:FLEX_OFFSET]) or any(p[FLEX_END:BOOST_OFFSET]) or any(p[BOOST_SCALAR_OFFSETS[BOOST_SCALARS[-1]]+4:BOOST_TABLE_OFFSETS['open_duty']]) or any(p[BOOST_END:]):raise ValueError('Reserved tune bytes must be zero')
 strategy=struct.unpack_from('<I',p,272)[0]
 if strategy>=len(STRATEGIES):raise ValueError('Unknown engine strategy')
 old={i:bytearray(p[offset:offset+legacy.PAGE_SIZES[i]]) for i,offset in PAGE_OFFSETS.items()}
 struct.pack_into('<I',old[1],272,strategy if strategy<len(legacy.STRATEGIES) else 0)
 candidate=legacy.decode_pages(old,base);candidate['schema_version']=10;candidate['strategy']=STRATEGIES[strategy];candidate['idle_control']=copy.deepcopy(DEFAULT['idle_control'])
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
 model=candidate['load_model']=copy.deepcopy(DEFAULT['load_model'])
 for name in LOAD_ENUM_FIELDS:
  value=struct.unpack_from('<I',p,LOAD_ENUM_OFFSETS[name])[0]
  if value>=len(LOAD_ENUMS[name]):raise ValueError('Unknown load-model choice: '+name)
  model[name]=LOAD_ENUMS[name][value]
 for name in LOAD_SCALARS:model[name]=struct.unpack_from('<f',p,LOAD_SCALAR_OFFSETS[name])[0]
 candidate['secondary_tables']=copy.deepcopy(DEFAULT['secondary_tables'])
 for kind in KINDS:
  rule=candidate['secondary_tables'][kind]
  for name in SEC_ENUM_FIELDS:
   value=struct.unpack_from('<I',p,enum_offset(kind,name))[0]
   if value>=len(SEC_ENUMS[name]):raise ValueError('Unknown secondary selection: '+name)
   rule[name]=SEC_ENUMS[name][value]
  for name in SEC_SCALARS:rule[name]=struct.unpack_from('<f',p,scalar_offset(kind,name))[0]
  channel,polarity=struct.unpack_from('<II',p,rule_offset(kind)+28)
  if channel>1 or polarity>1:raise ValueError('Invalid secondary input channel or polarity')
  rule['input_channel']=channel;rule['active_high']=bool(polarity)
  values=struct.unpack_from('<288f',p,SEC_MAP_OFFSETS[kind]);rule['map']=dict(rpm=list(values[:16]),load=list(values[16:32]),cells=list(values[32:]))

 flex=candidate['flex_fuel']=copy.deepcopy(FLEX_DEFAULT)
 for name in FLEX_BOOLS:
  value=struct.unpack_from('<I',p,FLEX_OFFSETS[name])[0]
  if value>1:raise ValueError('Invalid flex boolean')
  flex_set(flex,name,bool(value))
 flex['capture']['cycles']=struct.unpack_from('<I',p,FLEX_OFFSETS['cycles'])[0]
 for name in FLEX_FLOATS:flex_set(flex,name,struct.unpack_from('<f',p,FLEX_OFFSETS[name])[0])
 for name in FLEX_ARRAYS:flex_set(flex,name,list(struct.unpack_from('<6f',p,FLEX_OFFSETS[name])))
 boost=candidate['boost_control']=copy.deepcopy(BOOST_DEFAULT)
 enabled,mode,activation=struct.unpack_from('<3I',p,BOOST_OFFSET)
 if enabled>1 or mode>=len(BOOST_MODES) or activation>=len(BOOST_ACTIVATIONS):raise ValueError('Invalid boost selection')
 boost.update(pressure_enabled=bool(enabled),mode=BOOST_MODES[mode],activation=BOOST_ACTIVATIONS[activation])
 for name in BOOST_SCALARS:boost[name]=struct.unpack_from('<f',p,BOOST_SCALAR_OFFSETS[name])[0]
 for name in BOOST_TABLES:
  values=struct.unpack_from('<80f',p,BOOST_TABLE_OFFSETS[name]);boost[name]=dict(rpm=list(values[:8]),axis=list(values[8:16]),cells=list(values[16:]))
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
  prefix+=struct.pack('<8f8I',*values,int(ae.get('flags',0))|(256 if known else 0),int(ae.get('mode_code',0)),int(ae.get('apply_code',0)),int(ae.get('phase_code',0)),int(ae.get('reason_code',0)),0,0,0)
  present=bool(sample.get('flags',0)&1);model=sample.get('load_model',{}) if present else {};known=bool(model.get('available'));afr=model.get('afr_factor')
  values=[float(model[k]) if model.get(k) is not None else float('nan') for k in LOAD_VALUE_NAMES] if known else [float('nan') if present else 0.]*9
  flags=int(model.get('flags',0))|(65536 if known else 0)|(131072 if known and isinstance(afr,(int,float)) and math.isfinite(afr) else 0)|(int(model.get('reason_code',0))<<24)
  codes=[int(model.get(k+'_code',1 if present and k in ('pressure','afr') else 0)) for k in ('fuel_source','spark_source','lambda_source','trim_source','pressure','aux_role','baro_source','afr')]
  prefix+=struct.pack('<9f9I',*values,flags,*codes)+bytes(24)
  second=sample.get('secondary_tables',{}) if present else {}
  for kind in KINDS:
   observation=second.get(kind,{})
   values=[float(observation[k]) if observation.get(k) is not None else float('nan') for k in SEC_VALUE_NAMES] if present else [0.]*9
   word=int(observation.get('flags',1024 if present else 0))
   codes=[int(observation.get(k+'_code',0)) for k in SEC_CODE_FIELDS]
   when=int(observation.get('input_observed_us') or 0)
   prefix+=struct.pack('<9f7IQ',*values,word,*codes,when)+bytes(8)
  prefix+=bytes(64)
  f=sample.get('flex_fuel',{}) if present else {};known=bool(f.get('available'))
  values=[float(f[k]) if f.get(k)is not None else float('nan') for k in FLEX_VALUES] if known else [0.]*10
  flags=sum(1<<n for n,key in enumerate(FLEX_FLAGS) if f.get(key,False)) if known else 0
  codes=[int(f.get(key,0)) for key in FLEX_CODES] if known else [0]*7
  times=[int(f.get(key,0)) for key in FLEX_TIMES] if known else [0]*7
  cal=f.get('capture_calibration',{}) if known else {}
  prefix+=struct.pack('<10f8I7Q6fI',*values,flags,*codes,*times,*[float(cal.get(key,0)) for key in FLEX_FLOATS],int(cal.get('cycles',0)))
  prefix+=bytes(832-len(prefix))
  boost=sample.get('boost_control',{}) if present else {};known=bool(boost.get('available'))
  values=[float(boost[k]) if boost.get(k) is not None else float('nan') for k in BOOST_VALUES] if known else [float('nan')]*8
  flags=int(boost.get('flags',0))|(65536 if known else 0)|(131072 if boost.get('pressure_enabled',False) else 0)|(262144 if boost.get('inhibit_engine',False) else 0)
  prefix+=struct.pack('<8f4I2Q',*values,flags,int(boost.get('reason_code',0)),int(boost.get('mode_code',0)),0,int(boost.get('pid_updates',0)),int(boost.get('overboost_events',0)))
  return prefix+bytes(LIVE_BYTES-len(prefix))
