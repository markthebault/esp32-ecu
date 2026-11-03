"""Own004 development protocol, shared with the inhibited target USB service.

One complete calibration page avoids automatic cross-page burn transitions.
Historical own001/002/003 INIs and own003 codec remain separate records.
"""
import struct
import engine_protocol_legacy as legacy
from engine_protocol_legacy import (DEFAULT,NUMBERS,FLAGS,CURVES,REVISION_OFFSET,
 TIMING_FIELDS,STRATEGIES,LIVE_FIELDS,field_units,envelope,LEGACY_SIGNATURE,
 SEQUENTIAL_SIGNATURE,SERIAL_PROTOCOL)
from tuning_runtime import Session,Stream

CYLINDER_SIGNATURE=legacy.SIGNATURE
SIGNATURE=b'ESP32ECU DEV 004 INHIBITED'
VERSION=b'ESP32ECU development; staged whole-tune burn; outputs inhibited'
PAGE_SIZES={1:4768}
PAGE_OFFSETS={1:0,2:512,3:1664,4:2816,5:3968}
LIVE_BYTES=216

def pages(tune):
 old=legacy.pages(tune)
 return {1:bytearray(b''.join(old[i] for i in range(1,6)))}

def decode_pages(buffers,base):
 if set(buffers)!={1} or len(buffers[1])!=4768:raise ValueError('Own004 requires one complete 4768-byte page')
 p=buffers[1]
 if any(p[292:512]) or any(p[4756:]):raise ValueError('Reserved tune bytes must be zero')
 old={i:p[offset:offset+legacy.PAGE_SIZES[i]] for i,offset in PAGE_OFFSETS.items()}
 candidate=legacy.decode_pages(old,base)
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
  return bytes(block)+struct.pack('<8I',store.tune['revision'],0,0,0,6,0,sample.get('input_valid_mask',0),sample.get('flags',0))
