#!/usr/bin/env python3
"""Conditional SW2 circuit experiments in ngspice, not hardware qualification.

The separately authored BJT/diode/clamp/supervisor models are assumptions, not
manufacturer models or a parasitic extraction. Full-temperature saturation,
leakage, reset and unpowered behavior remain physical characterization gates.
"""
import argparse,hashlib,json,subprocess
from dataclasses import dataclass,asdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
@dataclass
class Case:
 name:str
 supply:float=3.3
 temperature:float=25
 beta:float=40
 contact0:float=1e12
 contact1:float=1e12
 fault0:float|None=None
 fault1:float|None=None
 power_connected:bool=True
 bus_powered:bool=True
 transition:bool=False
 max_step_us:float=1
 bus_v:float|None=None

def binding():
 c=json.loads((ROOT/'hardware/switch-inputs/net_contract.json').read_text());p={x['reference']:x for x in c['parts']}
 literal={'R1':2200,'R2':2200,'R3':4990,'R4':4990,'R5':4990,'R6':4990,'R7':100000,'R8':100000,'R9':4700,'R10':4700,'R11':1000,'R12':1000,'R13':10000,'R14':10000,'R15':10000,'R16':10000,'R17':1000,'R18':100000,'R19':100000,'R20':1000,'R21':100,'R22':100}
 assert all(p[k]['value']==f'{v}R 1% 0.6W' for k,v in literal.items())
 expected_pins={
  'R1':['BIAS0','SW0'],'R2':['BIAS1','SW1'],'R3':['SW0','MID0'],'R4':['MID0','BASE0'],
  'R5':['SW1','MID1'],'R6':['MID1','BASE1'],'R7':['BASE0','GND'],'R8':['BASE1','GND'],
  'R9':['+3V3','COL0'],'R10':['+3V3','COL1'],'R11':['COL0','GP0'],'R12':['COL1','GP1'],
  'R13':['GP2','GND'],'R14':['GP3','+3V3'],'R15':['GP4','GND'],'R16':['GP5','+3V3'],
  'R17':['GP7','GP6'],'R18':['GP6','GND'],'R19':['RESET_N','+3V3'],'R20':['+3V3','GND'],
  'R21':['SDA_CARRIER','SDA'],'R22':['SCL_CARRIER','SCL']}
 assert all(p[k]['pins']=={'1':a,'2':b}for k,(a,b)in expected_pins.items())
 assert p['J1']['pins']=={'1':'GND','2':'+3V3','3':'SDA_CARRIER','4':'SCL_CARRIER'}
 assert p['J2']['pins']=={'1':'SW0','2':'GND'} and p['J3']['pins']=={'1':'SW1','2':'GND'}
 assert p['U1']['pins']=={'1':'SCL','2':'SDA','3':'GND','4':'GND','5':'GND','6':'RESET_N','7':None,'8':None,'9':'GND','10':'GP0','11':'GP1','12':'GP2','13':'GP3','14':'GP4','15':'GP5','16':'GP6','17':'GP7','18':'+3V3'}
 assert p['U2']['pins']=={'1':'RESET_N','2':'+3V3','3':'GND'}
 assert p['Q1']['pins']=={'1':'GND','2':'BASE0','3':'COL0'} and p['Q2']['pins']=={'1':'GND','2':'BASE1','3':'COL1'}
 for ref,k,a in [('D1','BIAS0','+3V3'),('D2','BIAS1','+3V3'),('D3','BASE0','GND'),('D4','BASE1','GND')]:
  assert p[ref]['pins']=={'1':k,'2':a} and p[ref]['mpn']=='1N4148-TAP'
 for ref,value,positive in [('C1','100nF 50V','+3V3'),('C2','100nF 50V','+3V3'),('C3','10nF 50V','COL0'),('C4','10nF 50V','COL1'),('C5','10uF 16V','+3V3')]:
  assert p[ref]['value']==value and p[ref]['pins']=={'1':positive,'2':'GND'}
 assert p['U1']['mpn']=='MCP23008-E/P' and p['U2']['mpn']=='MCP121-300E/TO'
 assert p['Q1']['mpn']==p['Q2']['mpn']=='2N3904BU'
 carrier=json.loads((ROOT/'hardware/a5-idle-interface/net_contract.json').read_text());cp={x['ref']:x for x in carrier['parts']}
 assert cp['J4']['pins']=={'1':'GND','2':'+3V3','3':'I2C_SDA','4':'I2C_SCL','5':'SAFE_N'}
 assert cp['U3']['pins']['21'] is None and cp['R16']['value']=='4.7k' and cp['R17']['value']=='4.7k'
 return {'literal_resistors_ohm':literal,'literal_resistor_pins':expected_pins,'scope':'Literal CAD/interface binding only; independent model parameters below are assumptions'}

def deck(c):
 bus_voltage=(c.bus_v if c.bus_v is not None else c.supply if c.power_connected else 3.3)if c.bus_powered else 0
 lines=[f'SW2-J4-DRAFT1 conditional experiment {c.name}',
  '* Generic assumed models, not manufacturer guarantees or actual unpowered IC behavior.',
  '.options reltol=1e-5 abstol=1e-11 vntol=1e-7 method=gear',f'.temp {c.temperature}',
  f'.model QASSUMED NPN(IS=1e-14 BF={c.beta} NF=1 VAF=75 IKF=.05 ISE=1e-14 NE=1.3 BR=4 CJE=4p CJC=3p TF=.3n TR=100n)',
  '.model DASSUMED D(IS=1e-9 N=1.8 RS=2 CJO=2p TT=4n)',
  '.model CONTACT SW(RON=.1 ROFF=1e12 VT=.5 VH=.3)',
  f'Vsupply source 0 {c.supply}',f'Rwire source rail {.2 if c.power_connected else 1e12}',
  'Rbleeder rail 0 1000','Cbulk rail 0 10u','Cchip rail 0 100n','Creset_supply rail 0 100n',
  f'Ichip rail 0 {"1m" if c.power_connected else "0"}',
  'Rreset rail resetn 100000','Ireset_leak resetn 0 100n',
  '* Idealized supervisor static behavior ONLY. No ramp/delay/leakage guarantee.',
  'Breset resetn 0 I=ternary_fcn(v(rail)<2.93,v(resetn)/10,0)',
  f'Vbus bus_source 0 {bus_voltage}']
 for pin in ('sda','scl'):
  lines +=[f'Rcarrier_{pin} bus_source bus_{pin} 4700',f'Rseries_{pin} bus_{pin} {pin} 100',
   f'Dhi_{pin} {pin} rail DASSUMED',f'Dlo_{pin} 0 {pin} DASSUMED']
 for i,(contact,fault)in enumerate(((c.contact0,c.fault0),(c.contact1,c.fault1))):
  lines +=[f'Dfeed{i} rail bias{i} DASSUMED',f'Rbias{i} bias{i} sw{i} 2200',
   f'RinA{i} sw{i} mid{i} 4990',f'RinB{i} mid{i} base{i} 4990',f'Rbe{i} base{i} 0 100000',
   f'Dbe{i} 0 base{i} DASSUMED',f'Qinput{i} col{i} base{i} 0 QASSUMED',
   f'Rcol{i} rail col{i} 4700',f'Ccol{i} col{i} 0 10n',f'Riso{i} col{i} gp{i} 1000',
   f'Dgphi{i} gp{i} rail DASSUMED',f'Dgplo{i} 0 gp{i} DASSUMED',f'Igp{i} gp{i} 0 {"1u" if i else "-1u"}']
  if fault is not None:lines +=[f'Vfault{i} external{i} 0 {fault}',f'Rfault{i} external{i} sw{i} 1']
  elif c.transition and i==0:lines +=['Vcontactctl contactctl 0 PULSE(0 1 2m 10n 10n 4m 8m)','Scontact0 sw0 0 contactctl 0 CONTACT']
  else:lines +=[f'Rcontact{i} sw{i} 0 {contact}']
 # Input marker/loop resistors have no intentional DC load in correct input
 # mode, except a high loopback GP6 pulldown. I/O leakage remains unqualified.
 lines+=['Rloop rail loop 1000','Rloop_bias loop 0 100000',
  '.control','set wr_singlescale','set wr_vecnames']
 vectors='v(rail) v(sw0) v(sw1) v(base0) v(base1) v(col0) v(col1) v(gp0) v(gp1) v(bias0) v(bias1) v(resetn) i(Vsupply) i(Vbus)'
 if c.transition:lines +=[f'tran {c.max_step_us}u 10m 0 {c.max_step_us}u',f'wrdata values.txt {vectors}']
 else:lines +=['op',f'wrdata values.txt {vectors}']
 return '\n'.join(lines+['quit','.endc','.end',''])

def run(c,binary,out):
 folder=out/c.name;folder.mkdir();(folder/'circuit.cir').write_text(deck(c))
 r=subprocess.run([str(binary),'-b','circuit.cir'],cwd=folder,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
 (folder/'ngspice.log').write_text(r.stdout)
 assert r.returncode==0 and (folder/'values.txt').exists(),(c.name,r.stdout[-1200:])
 values=np.loadtxt(folder/'values.txt',skiprows=1,ndmin=2);assert values.shape[1]==15 and np.isfinite(values).all(),c.name
 final=values[-1];rail=final[1];bias_power=[(final[10+i]-final[2+i])**2/2200 for i in (0,1)]
 result={'case':asdict(c),'rail_v':float(rail),'gp_v':final[8:10].tolist(),'base_v':final[4:6].tolist(),'bias_resistor_w':list(map(float,bias_power)),'carrier_3v3_feed_current_ma':float(-final[13]*1000),'bus_feed_current_ma':float(-final[14]*1000),'reset_v_assumed_model_only':float(final[12]),'rows':len(values)}
 if c.power_connected and c.fault0 is None and c.fault1 is None:
  for i,contact in enumerate((c.contact0,c.contact1)):
   if c.transition and i==0:continue
   assert final[8+i]<=rail*.2 if contact>1e6 else final[8+i]>=rail*.8,(c.name,result)
  result['declared_static_logic_check']=True
 if c.transition:
  # Settled digital levels, separately from firmware20ms qualification.
  for begin,end,closed in ((.001,.0019,False),(.0022,.0059,True),(.0063,.0099,False)):
   rows=values[(values[:,0]>=begin)&(values[:,0]<=end)];assert len(rows)>10
   assert (rows[:,8]>=rows[:,1]*.8).all() if closed else (rows[:,8]<=rows[:,1]*.2).all(),c.name
  result['settled_transitions_check']=True
  crossings=values[(values[:,0]>=.002)&(values[:,8]>=values[:,1]*.8)]
  result['conditional_rise_to_0_8vdd_us']=float((crossings[0,0]-.002)*1e6)
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ngspice',type=Path,required=True);p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args()
 binary=a.ngspice.resolve();out=a.report_dir.resolve();bound=binding();out.mkdir(parents=True,exist_ok=False);cases=[]
 for supply in (2.97,3.3,3.63):
  for temperature in (-20,25,85):
   for beta in (40,200):
    for n,(c0,c1)in enumerate(((1e12,1e12),(0.1,100),(100,1e12))):cases.append(Case(f'normal-{len(cases):03d}',supply,temperature,beta,c0,c1))
 for supply in (0,3.3,3.63):
  for temperature in (-20,25,85):
   for volts in (-18,18):
    for both in (False,True):cases.append(Case(f'fault-{len(cases):03d}',supply,temperature,40,fault0=volts,fault1=volts if both else None,power_connected=supply!=0))
 for bus in (False,True):cases.append(Case(f'poweroff-{int(bus)}',supply=0,power_connected=False,bus_powered=bus))
 cases.append(Case('poweroff-bus3.63',supply=0,power_connected=False,bus_v=3.63))
 for dt in (1,.5):cases.append(Case(f'transition-{dt}',transition=True,max_step_us=dt))
 results=[run(c,binary,out)for c in cases]
 source_paths=['tools/run_switch_circuit.py','scripts/build_switch_inputs.py','hardware/switch-inputs/net_contract.json','hardware/switch-inputs/switches.kicad_pcb','hardware/a5-idle-interface/net_contract.json']
 report={'passed_declared_model_checks':True,'physical_qualification':False,'manufacturer_models':False,'cases':len(results),'binding':bound,
  'max_bias_resistor_w':max(max(r['bias_resistor_w'])for r in results),'max_connected_3v3_feed_current_ma':max(r['carrier_3v3_feed_current_ma']for r in results if r['case']['power_connected']),
  'poweroff_results':[r for r in results if not r['case']['power_connected']],
  'assumptions':['Generic BJT beta/diode/ESD/supervisor assumptions, not vendor macro-models','Connected bus pullups track the carrier rail; disconnected supply cases use3.3V bus, with a separate3.63V bus-only case','Steady ±18V is a conditional bench experiment, not a protected-input rating or automotive pulse qualification','Open wires/short-to-return are indistinguishable from valid contact states','Unpowered IC and full-temperature loaded reset behavior remain unknown','3V3-feed and bus-feed currents are separate; neither includes ESP32/carrier loads or switching peaks; no headroom or thermal qualification'],
  'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'sources':{s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest()for s in source_paths},'results':results}
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report[k]for k in ('passed_declared_model_checks','physical_qualification','manufacturer_models','cases','max_bias_resistor_w','max_connected_3v3_feed_current_ma')}))
if __name__=='__main__':main()
