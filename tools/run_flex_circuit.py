#!/usr/bin/env python3
"""Conditional protected-flex circuit experiments; no physical qualification.

The authored comparator, diode, GPIO load and sensor equivalents are assumptions.
Classic LM2903P has typical-only delay data; a B-version model is not its model.
No temperature/rating, surge, target timing or safe arbitrary wiring is inferred.
"""
import argparse,hashlib,itertools,json,subprocess
from dataclasses import asdict,dataclass
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FRONTEND=Path('hardware/flex-input/frontend.json')
@dataclass
class Case:
 name:str
 sensor_v:float=12
 rail5:float=5
 rail33:float=3.3
 frequency_hz:float=100
 low_us:float=3000
 raw_shunt_pf:float=500
 filter_cap_scale:float=1
 comparator_input_pf:float=5
 comparator_output_pf:float=15
 module_input_pf:float=10
 gpio_leak_ua:float=0
 sensor_ron:float=50
 sensor_leak_ua:float=10
 offset_mv:float=0
 bias_na:float=25
 temperature_c:float=25
 delay_us:float=1.3
 output_rise_delay_us:float|None=None
 output_fall_delay_us:float|None=None
 output_floor_v:float=.15
 clamp_leak_ua:float=0
 clamp_forward_v:float|None=None
 analog_ramp_us:float=0
 noise_mv:float=0
 max_step_us:float=5
 duration_ms:float=200
 fault_v:float|None=None
 powered:bool=True
 connected5:bool|None=None
 connected33:bool|None=None
 rail_bleeder_ohm:float=100
 dc:bool=False
 expect_capture_valid:bool|None=None
 tcr_ppm_per_k:float=50
 tolerance_sign:int=0

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_json(path):
 def unique(pairs):
  result={}
  for key,value in pairs:
   assert key not in result,('Duplicate JSON key',key)
   result[key]=value
  return result
 return json.loads(path.read_text(),object_pairs_hook=unique)

def binding(frontend=FRONTEND):
 path=ROOT/frontend;x=read_json(path);parts={p['ref']:p for p in x['parts']}
 compact=x['contract']=='FLEX-G38-FRONTEND-COMPACT-DRAFT2'
 assert compact or x['contract']=='FLEX-G38-FRONTEND-DRAFT1'
 expected_refs={'F3','J22','D212','D213','U18','C158','C159','C160'}|{f'R{i}'for i in range(155,167)}
 if compact:expected_refs.add('C164')
 assert len(parts)==len(x['parts'])and set(parts)==expected_refs,'Unexpected or duplicate modeled reference'
 if compact:
  assert x['parent_revision']['source_sha256']==digest(ROOT/FRONTEND),'Compact parent binding changed'
  assert set(x.get('existing_package_changes',{}))=={'J20'}
  shield=x['existing_package_changes']['J20']
  assert shield['pins']=={'1':'CHASSIS','2':'CHASSIS'}and shield['mpn']=='B2B-PH-K-S(LF)(SN)'
  assert shield['mounting']['footprint']=='JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical'
  for ref,mpn,label in (('C158','C315C470J5G5TA','47pF C0G 5% 50V'),('C159','C315C103J5G5TA','10nF C0G 5% 50V'),('C160','C315C104K5R5TA','100nF X7R 10% 50V'),('C164','C315C104K5R5TA','100nF X7R 10% 50V')):
   assert parts[ref]['mpn']==mpn and parts[ref]['value']==label,ref
   assert parts[ref]['mounting']['footprint']=='C_Radial_KEMET_C315_L3.81mm_W2.54mm_P2.54mm'
   assert parts[ref]['mounting']['side']=='F.Cu'
  assert parts['C164']['farad']==1e-7 and parts['C164']['pins']=={'1':'+3V3','2':'GND'}
 else:
  assert not x.get('existing_package_changes',{})
  for ref,label in [('C158','47pF C0G 5% 50V candidate'),('C159','10nF 50V candidate'),('C160','100nF 50V candidate')]:
   assert parts[ref]['value']==label and 'mpn'not in parts[ref],ref
 resistors={p['ref']:p['ohm']for p in x['parts']if 'ohm'in p}
 assert resistors==dict(zip(('R155','R156','R157','R158','R159','R160','R161','R162','R163','R164','R165','R166'),(750,750,27400,24900,4990,330000,100000,4990,2200,4700,47000,750)))
 for ref,ohm in resistors.items():
  rating=.4 if compact and 157<=int(ref[1:])<=165 else .6
  assert parts[ref]['value']==f'{ohm:g}R 1% {rating:.1f}W',ref
  assert 'mpn'not in parts[ref],('Unexpected resistor identity override',ref)
  if rating==.4:
   assert parts[ref]['mounting']['series']=='Vishay MRS16'
   assert parts[ref]['mounting']['footprint']=='R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical'
   assert parts[ref]['mounting']['side']=='F.Cu'
 resistor_pins={
  'R155':('FLEX_BIAS','FLEX_PULL_MID'),'R156':('FLEX_PULL_MID','FLEX_PULL_MID2'),'R166':('FLEX_PULL_MID2','FLEX_RAW'),
  'R157':('FLEX_RAW','FLEX_INPUT_MID'),'R158':('FLEX_INPUT_MID','FLEX_IN'),'R159':('FLEX_IN','GND'),
  'R160':('FLEX_CMP','FLEX_IN'),'R161':('+5V','FLEX_REF'),'R162':('FLEX_REF','GND'),
  'R163':('+3V3','FLEX_CMP'),'R164':('FLEX_CMP','FLEX'),'R165':('FLEX','GND')}
 assert all(parts[ref]['pins']==dict(zip(('1','2'),pins))for ref,pins in resistor_pins.items())
 for ref,farad,net in (('C158',4.7e-11,'FLEX_INPUT_MID'),('C159',1e-8,'FLEX_REF'),('C160',1e-7,'+5V')):
  assert parts[ref]['farad']==farad and parts[ref]['pins']=={'1':net,'2':'GND'}
 assert {ref for ref,part in parts.items()if'farad'in part}==({'C158','C159','C160','C164'}if compact else{'C158','C159','C160'})
 for ref,value in [('F3','PTC 100mA radial candidate'),('J22','FLEX 12V SENSOR'),('D212','1N4148-TAP'),('D213','1N4148-TAP'),('U18','LM2903P')]:assert parts[ref]['value']==value,ref
 assert parts['U18']['mpn']=='LM2903P' and parts['U18']['pins']=={'1':'FLEX_CMP','2':'FLEX_REF','3':'FLEX_IN','4':'GND','5':'GND','6':'FLEX_REF','7':None,'8':'+5V'}
 assert parts['D212']['pins']=={'1':'FLEX_BIAS','2':'FLEX_12V'} and parts['D212']['mpn']=='1N4148-TAP'
 assert parts['D213']['pins']=={'1':'FLEX_INPUT_MID','2':'GND'} and parts['D213']['mpn']=='1N4148-TAP'
 assert parts['C158']['pins']=={'1':'FLEX_INPUT_MID','2':'GND'}
 assert parts['J22']['pins']=={'1':'GND','2':'FLEX_12V','3':'FLEX_RAW'}
 assert parts['J22']['mpn']=='B3P-VH(LF)(SN)'
 assert parts['F3']['pins']=={'1':'VIN_PROT','2':'FLEX_12V'}
 assert parts['F3']['mpn']=='MF-R010'
 assert x['existing_part_changes']=={'U3':{'32':'FLEX'}}
 assert parts['R164']['pins']=={'1':'FLEX_CMP','2':'FLEX'}
 carrier=read_json(ROOT/'hardware/a5-idle-interface/net_contract.json');old={p['ref']:p for p in carrier['parts']}
 assert len(old)==len(carrier['parts'])
 assert old['R7']['pins']=={'1':'+3V3','2':'GND'}and old['R7']['value']=='100R 0.25W'
 assert old['U7']['pins']['14']=='+3V3'and old['U3']['pins']['32']is None
 return dict(frontend_sha256=digest(path),frontend_contract=x['contract'],frontend_profile=str(frontend),carrier_sha256=digest(ROOT/'hardware/a5-idle-interface/net_contract.json'),resistors_ohm=resistors,modeled_capacitors_farad={ref:part['farad']for ref,part in parts.items()if'farad'in part},unmodeled_package_changes=sorted(x.get('existing_package_changes',{})),scope='Literal circuit/parent contract only; capacitor values are nominal ideal parts, and models, supply impedance and sensor/cable limits are assumptions. No X7R effective-value, ESR/ESL or physical-layout guarantee.')

def deck(c,frontend=FRONTEND):
 binding(frontend)
 spec=read_json(ROOT/frontend);r={p['ref']:p['ohm']for p in spec['parts']if'ohm'in p}
 # Deliberately opposed1percent component signs exercise threshold and
 # bandwidth, without calling them independent per-resistor exhaustive corners.
 def v(ref):return r[ref]*(1+(.01+abs(c.temperature_c-25)*c.tcr_ppm_per_k*1e-6)*c.tolerance_sign*(1 if ref in ('R157','R158','R161','R160')else -1))
 on5=c.powered if c.connected5 is None else c.connected5
 on33=c.powered if c.connected33 is None else c.connected33
 nodes={'GND':'0','+5V':'rail5','+3V3':'rail33','FLEX':'gpio'}
 for p in spec['parts']:
  for net in p['pins'].values():
   if net is not None:nodes.setdefault(net,net.lower())
 lines=[f'FLEX-G38 conditional circuit {c.name}',
  '* Authored assumed equivalents, not manufacturer models or hardware guarantees.',
  '* Delay1.3us is a declared symmetric assumption, not a full-temperature bound.',
  '.options reltol=1e-5 abstol=1e-12 vntol=1e-8 method=gear',f'.temp {c.temperature_c}',
  '.model DFEED D(IS=1e-9 N=1.8 RS=2 CJO=2p TT=4n)',
  f'.model SENSOR SW(RON={c.sensor_ron} ROFF=1e12 VT=.5 VH=.1)',
  f'V5 supply5 0 {c.rail5}',f'V33 supply33 0 {c.rail33}',
  f'R5wire supply5 rail5 {0.1 if on5 else 1e12}',f'R33wire supply33 rail33 {0.1 if on33 else 1e12}',
  '* Actual inherited R7 bleeder, not an ideal powered-off rail sink.',
  f'Rcarrier7 rail33 0 {c.rail_bleeder_ohm}','Ccarrier9 rail33 0 22u','Rload5 rail5 0 10000',
  f'Vsensor flex_12v 0 {c.sensor_v}',
  'D212 flex_12v flex_bias DFEED']
 if c.clamp_forward_v is None:lines.append('D213 0 flex_input_mid DFEED')
 else:lines.append(f'Bclamp_limit flex_input_mid 0 I=-max(-v(flex_input_mid)-{c.clamp_forward_v},0)')
 for p in spec['parts']:
  if'ohm'in p:lines.append(f"{p['ref']} {nodes[p['pins']['1']]} {nodes[p['pins']['2']]} {v(p['ref'])}")
  if'farad'in p:lines.append(f"{p['ref']} {nodes[p['pins']['1']]} {nodes[p['pins']['2']]} {p['farad']*(c.filter_cap_scale if p['ref']=='C158' else 1)}")
 period=1/c.frequency_hz;low=c.low_us*1e-6
 lines +=[f'Craw_shunt flex_raw 0 {c.raw_shunt_pf}p',f'Ileak flex_raw 0 {c.sensor_leak_ua}u',
  f'Ibiasp 0 flex_in {c.bias_na if c.powered else 0}n',f'Ibiasn 0 flex_ref {c.bias_na if c.powered else 0}n',
  f'Bclamp_leak flex_input_mid 0 I=min(max(v(flex_input_mid)/.01,0),1)*{c.clamp_leak_ua}u',
  f'Ccomparator_input flex_in 0 {c.comparator_input_pf}p',f'Ccomparator_output flex_cmp 0 {c.comparator_output_pf}p',f'Igpio_leak gpio 0 {c.gpio_leak_ua}u']
 if c.fault_v is None:
  transition=c.analog_ramp_us*1e-6 if c.analog_ramp_us else 1e-8
  lines +=[f'Vwave wave 0 PULSE(0 1 2m {transition} {transition} {low} {period})']
  if c.analog_ramp_us:lines +=[f'Banalog_drive analog_drive 0 V=.4+{c.sensor_v-.4}*(1-v(wave))+{c.noise_mv}m*sin(2*pi*80000*time)','Ranalog_drive analog_drive flex_raw 100']
  else:lines.append('Ssensor flex_raw 0 wave 0 SENSOR')
 else:lines +=[f'Vfault fault_source 0 {c.fault_v}','Rfault fault_source flex_raw 1','Vwave wave 0 0']
 # Comparator goes open above IN-, sinks below it. It has a finite-pole
 # decision delay and an open-collector output. Powered-off behavior is a
 # declared open equivalent, not a claim about real below-minimum supply.
 rise=c.delay_us if c.output_rise_delay_us is None else c.output_rise_delay_us
 fall=c.delay_us if c.output_fall_delay_us is None else c.output_fall_delay_us
 lines +=[f'Bdecision decision 0 V=ternary_fcn(v(rail5)>2,ternary_fcn(v(flex_in)>v(flex_ref)+{c.offset_mv}m,0,1),0)',
  f'Bdelay decision delayed I=(v(decision)-v(delayed))/ternary_fcn(v(decision)>v(delayed),{max(.001,fall)*1e-6/(1e-9*np.log(2))},{max(.001,rise)*1e-6/(1e-9*np.log(2))})','Cdelay delayed 0 1n',
  f'Boutput flex_cmp 0 I=ternary_fcn(v(delayed)>.5, max(v(flex_cmp)-{c.output_floor_v},0)/30,0)']
 lines +=[f'Cmodule gpio 0 {c.module_input_pf}p',
  '* Generic GPIO protection equivalents; no real unpowered-chip model.',
  '.model DGPIO D(IS=1e-12 N=1 RS=10 CJO=5p)','Dgpiohi gpio rail33 DGPIO','Dgpiolo 0 gpio DGPIO',
  '.control','set wr_singlescale','set wr_vecnames',
  'op'if c.dc else f'tran {c.max_step_us}u {c.duration_ms}m 0 {c.max_step_us}u',
  'wrdata values.txt v(wave) v(flex_raw) v(flex_in) v(flex_ref) v(flex_cmp) v(gpio) v(rail33) v(rail5) v(flex_bias) v(flex_pull_mid) v(flex_input_mid) i(Vsensor) i(V5) i(V33) v(flex_pull_mid2)',
  'quit','.endc','.end','']
 return '\n'.join(lines)

def edges(time,values,low,high):
 result=[]
 for indexes,threshold,level in ((np.flatnonzero((values[:-1]<high)&(values[1:]>=high))+1,high,True),(np.flatnonzero((values[:-1]>low)&(values[1:]<=low))+1,low,False)):
  for i in indexes:
   before=values[i-1];after=values[i];fraction=np.clip((threshold-before)/(after-before),0,1)
   result.append((float(time[i-1]+fraction*(time[i]-time[i-1])),level))
 return sorted(result)

def run(c,binary,out,frontend=FRONTEND):
 folder=out/c.name;folder.mkdir();(folder/'circuit.cir').write_text(deck(c,frontend))
 p=subprocess.run([str(binary),'-b','circuit.cir'],cwd=folder,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45)
 (folder/'ngspice.log').write_text(p.stdout)
 if p.returncode or not(folder/'values.txt').is_file():raise RuntimeError(c.name+': '+p.stdout[-1500:])
 a=np.loadtxt(folder/'values.txt',skiprows=1,ndmin=2);assert a.shape[1]==16 and np.isfinite(a).all(),c.name
 tail=a if c.dc else a[a[:,0]>=.001];last=a[-1];period=1/c.frequency_hz
 result=dict(case=asdict(c),rows=len(a),final_v=dict(zip(('raw','in','ref','cmp','gpio','rail33','rail5'),map(float,last[[2,3,4,5,6,7,8]]))),
  max_pullup_resistor_w=[float(np.max((tail[:,i]-tail[:,j])**2/(750*(1-(.01+abs(c.temperature_c-25)*c.tcr_ppm_per_k*1e-6)*c.tolerance_sign))))for i,j in ((9,10),(10,15),(15,2))],
  max_input_series_current_ua=[float(np.max(np.abs((tail[:,i]-tail[:,j])/(ohm*(1+(.01+abs(c.temperature_c-25)*c.tcr_ppm_per_k*1e-6)*c.tolerance_sign))))*1e6)for i,j,ohm in ((2,11,27400),(11,3,24900))],
  input_min_v=float(np.min(tail[:,3])),input_max_v=float(np.max(tail[:,3])),
  final_sensor_feed_ma=float(-last[12]*1000),final_5v_feed_ma=float(-last[13]*1000),final_3v3_feed_ma=float(-last[14]*1000))
 normalized=a[:,6]/np.maximum(a[:,7],1e-9)
 observed=edges(a[:,0],normalized,.25,.75)if c.powered and not c.dc else []
 # Exclude power-up. Output-derived edge times retain circuit delay/skew.
 observed=[(t,level)for t,level in observed if t>=.001]
 if c.fault_v is None and c.powered:
  lows=[(t,observed[i+1][0]-t)for i,(t,level)in enumerate(observed[:-1])if not level and observed[i+1][1]]
  assert len(lows)>=2,(c.name,observed)
  widths=[w*1e6 for _,w in lows];falls=[t for t,level in observed if not level]
  periods=np.diff(falls);assert len(periods)>0
  result.update(low_pulse_us=widths,low_pulse_error_us=[w-c.low_us for w in widths],frequency_hz=list(1/periods),edges_us=[dict(time_us=t*1e6,high=level)for t,level in observed])
  result['threshold_replays']=[]
  for rising,falling in itertools.product((.25,.5,.75),repeat=2):
   alternative=[(t,level)for t,level in edges(a[:,0],normalized,falling,rising)if t>=.001]
   widths=[(alternative[i+1][0]-t)*1e6 for i,(t,level)in enumerate(alternative[:-1])if not level and alternative[i+1][1]]
   result['threshold_replays'].append(dict(rising_fraction=rising,falling_fraction=falling,low_error_us=[w-c.low_us for w in widths],edges_us=[dict(time_us=t*1e6,high=level)for t,level in alternative]))
  assert np.max(np.abs(periods-period))<2e-6,(c.name,'period distortion')
  if c.analog_ramp_us:assert len(observed)==2*int((c.duration_ms/1000-.002)/period)+2,(c.name,'slow/noisy drive created extra edges')
  assert np.all(a[a[:,0]>.001,3]<a[a[:,0]>.001,8]-2),(c.name,'outside classic common-mode')
  assert np.min(a[a[:,0]>.001,3])>=0,(c.name,'negative normal input')
 if c.clamp_forward_v is not None:assert result['input_min_v']>=-.3,(c.name,'assumed cold-clamp bound failed')
 # Save exact adaptive source output compactly; no raw captures are discarded.
 import gzip
 data=(folder/'values.txt').read_bytes();(folder/'values.txt.gz').write_bytes(gzip.compress(data,mtime=0));(folder/'values.txt').unlink()
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ngspice',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--frontend',type=Path,default=FRONTEND);a=p.parse_args()
 frontend=(ROOT/a.frontend).resolve().relative_to(ROOT)
 bound=binding(frontend);out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);binary=a.ngspice.resolve()
 cases=[Case('nominal')]
 if not a.smoke:
  for sensor,frequency,width in itertools.product((9,18),(50,150),(1000,3000,5000)):
   cases.append(Case(f'wave-{len(cases):02d}',sensor_v=sensor,frequency_hz=frequency,low_us=width))
  for sign in (-1,1):cases.append(Case(f'opposed-corner-{sign}',offset_mv=sign*15,bias_na=500,rail5=4.75 if sign<0 else 5.25,rail33=3.0 if sign<0 else 3.6,tolerance_sign=sign,output_floor_v=.65,clamp_leak_ua=50))
  for temperature in (-20,85):cases.append(Case(f'temperature-{temperature}',temperature_c=temperature))
  for temperature in (-20,85):
   for width in (1000,5000):cases.append(Case(f'joined-corner-{temperature}-{width}',sensor_v=9,rail5=5.25,rail33=3.6,offset_mv=15,bias_na=500,clamp_leak_ua=50,output_floor_v=.65,tolerance_sign=1,temperature_c=temperature,frequency_hz=50,low_us=width))
  for dt in (2.5,1.25):
   for width in (1000,5000):cases.append(Case(f'joined-refined-{dt}-{width}',sensor_v=9,rail5=5.25,rail33=3.6,offset_mv=15,bias_na=500,clamp_leak_ua=50,output_floor_v=.65,tolerance_sign=1,temperature_c=-20,frequency_hz=50,low_us=width,max_step_us=dt))
  for scale,dt,width in itertools.product((.95,1.05),(5,2.5,1.25),(1000,5000)):
   cases.append(Case(f'joined-cap-{scale}-{dt}-{width}',sensor_v=9,rail5=5.25,rail33=3.6,offset_mv=15,bias_na=500,clamp_leak_ua=50,output_floor_v=.65,tolerance_sign=1,temperature_c=-20,frequency_hz=50,low_us=width,max_step_us=dt,filter_cap_scale=scale))
  for leak in (-1,1):cases.append(Case(f'gpio-leak-{leak}',rail33=3.0,output_floor_v=.65,gpio_leak_ua=leak))
  for dt in (2.5,1.25):cases.append(Case(f'refinement-{dt}',max_step_us=dt))
  for fault,powered in itertools.product((-36,-18,0,18,36),(False,True)):
   cases.append(Case(f'fault-{fault}-{int(powered)}',fault_v=fault,powered=powered,rail5=5 if powered else 0,rail33=3.3 if powered else 0,sensor_v=18 if powered else 0,duration_ms=10))
  for bleed in (100,1e12):cases.append(Case(f'poweroff-dc-bleed-{bleed:g}',fault_v=36,powered=False,rail5=0,rail33=0,sensor_v=0,rail_bleeder_ohm=bleed,dc=True))
  for on5,on33 in ((True,False),(False,True)):cases.append(Case(f'partial-power-{int(on5)}-{int(on33)}',fault_v=18,powered=False,rail5=5,rail33=3.3,connected5=on5,connected33=on33,sensor_v=18,dc=True))
  for powered in (True,False):cases.append(Case(f'cold-clamp-bound-{int(powered)}',fault_v=-36,powered=powered,rail5=5 if powered else 0,rail33=3.3 if powered else 0,sensor_v=18 if powered else 0,clamp_forward_v=1.5,temperature_c=-20,tolerance_sign=1,dc=True))
  cases +=[Case('slow-noisy-drive',analog_ramp_us=200,noise_mv=50),Case('skew-reject-long',low_us=5000,output_rise_delay_us=7,expect_capture_valid=False),Case('skew-reject-short',low_us=1000,output_fall_delay_us=7,expect_capture_valid=False),Case('skew-plausible-mid',low_us=3000,output_rise_delay_us=7),Case('capacitance-overrun-rejected',sensor_v=9,rail5=5.25,rail33=3.6,offset_mv=15,bias_na=500,clamp_leak_ua=50,output_floor_v=.65,tolerance_sign=1,temperature_c=-20,frequency_hz=50,low_us=5000,raw_shunt_pf=5000,expect_capture_valid=False)]
 sources=list(dict.fromkeys([frontend,FRONTEND,Path('hardware/a5-idle-interface/net_contract.json'),Path('tools/run_flex_circuit.py'),Path('tools/flex_circuit_capture.cpp'),Path('firmware/include/ecu/flex_fuel.hpp')]));before={str(p):digest(ROOT/p)for p in sources}
 for name in sources:
  destination=out/'sources'/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes((ROOT/name).read_bytes())
 (out/'source-hashes.json').write_text(json.dumps(before,indent=2)+'\n')
 results=[run(c,binary,out,frontend)for c in cases];assert before=={str(p):digest(ROOT/p)for p in sources}
 (out/'ngspice-results.json').write_text(json.dumps(dict(binding=bound,source_sha256=before,cases=results),indent=2)+'\n')
 command=['g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(ROOT/'firmware/include'),str(ROOT/'tools/flex_circuit_capture.cpp'),'-o',str(out/'capture')]
 with(out/'capture-build.log').open('xb')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 for result in results:
  c=result['case']
  if'threshold_replays'not in result:result['threshold_replays']=[dict(edges_us=[])]
  patterns=result['threshold_replays']
  for pattern in patterns:
   text=''.join(f"{e['time_us']:.12f} {int(e['high'])}\n"for e in pattern['edges_us'])
   process=subprocess.run([str(out/'capture'),str(c['duration_ms']*1000)],input=text,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
   observations=json.loads(process.stdout);pattern['capture_replay_10_clock_phases']=observations
   (out/'capture-results.json').write_text(json.dumps(results,indent=2)+'\n')
   expected=c['expect_capture_valid']if c['expect_capture_valid']is not None else c['fault_v']is None and c['powered']
   for observation in observations:assert observation['valid']==expected,(c['name'],pattern.get('rising_fraction'),pattern.get('falling_fraction'),observation)
 assert before=={str(p):digest(ROOT/p)for p in sources}
 report=dict(passed=True,pass_means='All declared positive controls and intentional rejection witnesses matched expectations, not that every circuit condition produces valid data',qualification=__doc__,binding=bound,source_sha256=before,ngspice_sha256=digest(binary),cases=results,claims=dict(physical_qualification=False,manufacturer_model=False,guaranteed_timing=False,pinout_qualified=False,sensor_supply_qualified=False))
 (out/'index.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=True,cases=len(cases),output=str(out))))
if __name__=='__main__':main()
