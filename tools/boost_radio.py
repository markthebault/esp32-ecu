"""Schema6 boost fragment. Authentication never turns a part into an observation.

Values describe the original control decision, not valve execution or current
permission. Complete BASE/FLEX/BOOST assembly and receiver ages are required.
"""
import hmac,math,struct
from espnow_protocol import check
from boost_config import VALUES,REASONS,MODES

BOOST_SIZE=144;BOOST_BODY=112
FLAGS=('enabled','pressure_valid','valve_allowed','pid_updated','low_limited','high_limited','slew_limited','integral_held','overboost_latched','recovery_waiting','no_new_sample')

def engine_boost_fragment(packet,key):
 if len(key)!=32:raise ValueError('Engine key must be32 bytes')
 check(packet,12,BOOST_SIZE)
 if not hmac.compare_digest(packet[BOOST_BODY:],hmac.digest(key,packet[:BOOST_BODY],'sha256')):raise ValueError('Boost authentication failed')
 session,sequence,schema,reserved=struct.unpack_from('<IQHH',packet,8)
 if not session or not sequence or schema!=6 or reserved or packet[111]:raise ValueError('Invalid boost fragment header')
 values=struct.unpack_from('<8f',packet,56);updates,events,flags,reason,mode,bits=struct.unpack_from('<QQIBBB',packet,88)
 if flags>2047 or reason>16 or mode>2 or bits&~7:raise ValueError('Invalid boost enums/flags')
 available,pressure,inhibit=[bool(bits&(1<<n)) for n in range(3)]
 if mode and not pressure:raise ValueError('Boost mode requires pressure protection')
 for n,v in enumerate(values):
  if math.isinf(v) or math.isnan(v) and struct.unpack_from('<I',packet,56+4*n)[0]!=0x7fc00000:raise ValueError('Invalid boost numeric value')
 if not available:
  if flags or reason or updates or events or inhibit or any(not math.isnan(v) for v in values):raise ValueError('Unavailable boost is not canonical empty')
 else:
  inside=lambda v,lo,hi:math.isfinite(v) and lo<=v<=hi
  if not inside(values[0],0,100) or any(not math.isfinite(values[n]) for n in (1,5,6,7)):raise ValueError('Invalid boost duty or PID demand')
  if any(math.isfinite(values[n]) and not inside(values[n],lo,hi) for n,lo,hi in ((2,50,400),(3,0,100),(4,-400,400))):raise ValueError('Invalid boost pressure or feedforward')
  if inhibit and (values[0]!=0 or flags&4) or bool(flags&1)!=pressure:raise ValueError('Inconsistent boost decision')
 b=dict(zip(VALUES,(v if math.isfinite(v) else None for v in values)))
 b.update((name,bool(flags&(1<<n))) for n,name in enumerate(FLAGS))
 b.update(available=available,pressure_enabled=pressure,inhibit_engine=inhibit,flags=flags,reason_code=reason,reason=REASONS[reason],mode_code=mode,mode=MODES[mode],pid_updates=str(updates),overboost_events=str(events),meaning='Original controller proposal; no valve or physical output measurement')
 return dict(complete=False,session=session,packet_sequence=sequence,schema_version=6,base_mac=packet[24:56],boost_control=b,immutable=packet[56:112])
