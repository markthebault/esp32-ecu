"""Authenticated schema7 cylinder part; publication requires all four parts."""
import hmac,math,struct
from espnow_protocol import check
from engine_geometry import INJECTOR_CHANNELS,COIL_CHANNELS

CYLINDER_SIZE=236;CYLINDER_BODY=204
VALUES=('pulse_ms','advance_deg','fuel_pct','duty_pct')

def channel_mask(count):
 return sum(1<<ch for ch in INJECTOR_CHANNELS[:count]+COIL_CHANNELS[:count])

def engine_cylinder_fragment(packet,key):
 if len(key)!=32:raise ValueError('Engine key must be32 bytes')
 check(packet,13,CYLINDER_SIZE)
 if not hmac.compare_digest(packet[CYLINDER_BODY:],hmac.digest(key,packet[:CYLINDER_BODY],'sha256')):raise ValueError('Cylinder authentication failed')
 session,sequence,schema,reserved=struct.unpack_from('<IQHH',packet,8)
 if not session or not sequence or schema!=7 or reserved or any(packet[65:68]):raise ValueError('Invalid cylinder part header')
 count,worker,injectors,coils,valid,enabled,capacity,spark,floor=struct.unpack_from('<9B',packet,56)
 virtual,physical=struct.unpack_from('<II',packet,68)
 if not 1<=count<=8 or worker>8 or injectors!=4 or coils!=4 or enabled>1:raise ValueError('Invalid cylinder counts or fitted command capacity')
 if (valid|capacity|spark|floor)&~((1<<count)-1):raise ValueError('Cylinder mask exceeds proposal count')
 if virtual&~channel_mask(worker) or physical&~channel_mask(min(worker,4)):raise ValueError('Worker mask exceeds its own declared cylinder capacity')
 rows=[]
 for i in range(8):
  values=struct.unpack_from('<4f',packet,76+16*i);known=bool(valid&(1<<i))
  for k,value in enumerate(values):
   if known:
    if not math.isfinite(value):raise ValueError('Known cylinder proposal must be finite')
   elif not math.isnan(value) or struct.unpack_from('<I',packet,76+16*i+4*k)[0]!=0x7fc00000:raise ValueError('Unknown cylinder proposal must be canonical NaN')
  rows.append(dict(cylinder=i+1,active=i<count,injector_logical_channel=INJECTOR_CHANNELS[i],coil_logical_channel=COIL_CHANNELS[i],**dict(zip(VALUES,values if known else (None,)*4))))
 cylinders=dict(count=count,valid_mask=valid,enabled=bool(enabled),capacity_mask=capacity,spark_clamp_mask=spark,retard_floor_mask=floor,proposals=rows)
 return dict(complete=False,session=session,packet_sequence=sequence,schema_version=7,base_mac=packet[24:56],
             cylinders=cylinders,worker_cylinder_count=worker,virtual_high_mask=virtual,physical_command_mask=physical,
             board_capacity=dict(injector_commands=injectors,coil_commands=coils,additional_outputs_allocated=False),immutable=packet[56:204])
