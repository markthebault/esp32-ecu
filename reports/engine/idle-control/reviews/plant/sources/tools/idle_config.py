"""Own005 idle fields. Physical validation remains in the shared C++ validator."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
DEFAULT=json.loads((R/'config/engine/defaults.json').read_text())['idle_control']
ALGORITHMS=('on_off','open_loop','closed_loop')
SCALARS=[name for name,value in DEFAULT.items() if isinstance(value,(int,float))]
ARRAYS=[(name,len(value)) for name,value in DEFAULT.items() if isinstance(value,list)]
OFFSET=4768
SCALAR_OFFSETS={name:OFFSET+4+i*4 for i,name in enumerate(SCALARS)}
ARRAY_OFFSETS={};offset=OFFSET+4+4*len(SCALARS)
for name,size in ARRAYS:ARRAY_OFFSETS[name]=offset;offset+=size*4
USED_END=offset
PAGE_BYTES=4992
assert USED_END<=PAGE_BYTES and len(SCALARS)==18 and len(ARRAYS)==4
UNITS={
 'frequency_hz':'Hz','control_period_ms':'ms','min_pct':'%','max_pct':'%','tps_closed_pct':'%','tps_hysteresis_pct':'%',
 'entry_rpm_above':'RPM','exit_rpm_above':'RPM','entry_delay_s':'s','afterstart_taper_s':'s','dashpot_pct':'%',
 'dashpot_decay_pct_s':'%/s','slew_pct_s':'%/s','integral_limit_pct':'%','kd':'%*s/RPM','derivative_filter_s':'s',
 'fast_idle_temp_c':'C','fast_idle_hysteresis_c':'C','coolant_c':'C','run_pct':'%','crank_pct':'%','target_add_rpm':'RPM'}
LIMITS={
 'frequency_hz':(50,250),'control_period_ms':(10,250),'min_pct':(0,99),'max_pct':(1,100),'tps_closed_pct':(0,10),'tps_hysteresis_pct':(.1,3),
 'entry_rpm_above':(0,1000),'exit_rpm_above':(0,1500),'entry_delay_s':(0,5),'afterstart_taper_s':(0,10),'dashpot_pct':(0,30),
 'dashpot_decay_pct_s':(1,100),'slew_pct_s':(1,1000),'integral_limit_pct':(0,100),'kd':(0,.1),'derivative_filter_s':(.01,1),
 'fast_idle_temp_c':(0,90),'fast_idle_hysteresis_c':(1,15),'coolant_c':(-40,140),'run_pct':(0,100),'crank_pct':(0,100),'target_add_rpm':(-500,1000)}
def name(field):return 'iac_'+field
