#!/usr/bin/env python3
"""Independent literal/interface/CAD checks. Run with KiCad9 Python.

Never edits a board. Copper-path lengths are graph measurements, not inductance
or electrical qualification. Native DRC remains the connectivity authority.
"""
import csv,hashlib,heapq,json,math,sys,xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
import pcbnew as pcb
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
checks=0
def check(ok,why):
 global checks
 checks+=1
 if not ok:raise AssertionError(why)
hw=root/'hardware/switch-inputs';c=json.loads((hw/'net_contract.json').read_text());parts={p['reference']:p for p in c['parts']}
expected={
 'J1':{'1':'GND','2':'+3V3','3':'SDA_CARRIER','4':'SCL_CARRIER'},
 'J2':{'1':'SW0','2':'GND'},'J3':{'1':'SW1','2':'GND'},
 'U1':dict(zip(map(str,range(1,19)),['SCL','SDA','GND','GND','GND','RESET_N',None,None,'GND','GP0','GP1','GP2','GP3','GP4','GP5','GP6','GP7','+3V3'])),
 'U2':{'1':'RESET_N','2':'+3V3','3':'GND'},
 'Q1':{'1':'GND','2':'BASE0','3':'COL0'},'Q2':{'1':'GND','2':'BASE1','3':'COL1'},
 'D1':{'1':'BIAS0','2':'+3V3'},'D2':{'1':'BIAS1','2':'+3V3'},
 'D3':{'1':'BASE0','2':'GND'},'D4':{'1':'BASE1','2':'GND'},
}
for ref,a,b in [('R1','BIAS0','SW0'),('R2','BIAS1','SW1'),('R3','SW0','MID0'),('R4','MID0','BASE0'),('R5','SW1','MID1'),('R6','MID1','BASE1'),('R7','BASE0','GND'),('R8','BASE1','GND'),('R9','+3V3','COL0'),('R10','+3V3','COL1'),('R11','COL0','GP0'),('R12','COL1','GP1'),('R13','GP2','GND'),('R14','GP3','+3V3'),('R15','GP4','GND'),('R16','GP5','+3V3'),('R17','GP7','GP6'),('R18','GP6','GND'),('R19','RESET_N','+3V3'),('R20','+3V3','GND'),('R21','SDA_CARRIER','SDA'),('R22','SCL_CARRIER','SCL'),('C1','+3V3','GND'),('C2','+3V3','GND'),('C3','COL0','GND'),('C4','COL1','GND'),('C5','+3V3','GND')]:expected[ref]={'1':a,'2':b}
check(set(parts)==set(expected)|{'H1','H2','H3','H4'},'exact reference set')
check(c['board_mm']==[80,60] and c['copper_layers']==2 and c['physical_qualification'] is False,'prototype domain')
for ref,pins in expected.items():check(parts[ref]['pins']==pins,'independent literal map '+ref)
check(c['acquisition']['marker_mask']==0x3c and c['acquisition']['marker_value']==0x28,'marker definition')
check(parts['U1']['pin_types']['17']=='output','GP7 is output only')
check(parts['J1']['footprint'].endswith('JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical'),'internal XH4')
for ref in ('J2','J3'):check(parts[ref]['footprint'].endswith('JST_VH_B2P-VH_1x02_P3.96mm_Vertical'),'incompatible contact family '+ref)
check(not any('SAFE_N'==n for p in parts.values()for n in p['pins'].values()),'no SAFE_N net')
check(parts['U1']['mpn']=='MCP23008-E/P' and parts['U2']['mpn']=='MCP121-300E/TO','exact chip candidates')
for ref in ('Q1','Q2'):check(parts[ref]['mpn']=='2N3904BU','onsemi bondout '+ref)
values=[2200,2200,4990,4990,4990,4990,100000,100000,4700,4700,1000,1000,10000,10000,10000,10000,1000,100000,100000,1000,100,100]
for n,value in enumerate(values,1):
 p=parts['R'+str(n)];check(p['value']==f'{value}R 1% 0.6W','resistor value')
 code=p['mpn'][9:13];check(int(code[:3])*10**int(code[3])==value,'Vishay candidate resistance code')
bom={r['Reference']:r for r in csv.DictReader((hw/'bom.csv').open())}
check(set(bom)==set(parts),'BOM references')
for ref,p in parts.items():
 check(bom[ref]['Value']==p['value'] and bom[ref]['Footprint']==p['footprint'] and bom[ref]['MPN candidate']==p['mpn'],'BOM values '+ref)
board=pcb.LoadBoard(str(hw/'switches.kicad_pcb'));fps={f.GetReference():f for f in board.GetFootprints()}
check(set(fps)==set(parts),'PCB references')
check(board.GetCopperLayerCount()==2,'two copper layers')
actual_pads={}
for ref,p in parts.items():
 f=fps[ref];check(f.GetValue()==p['value'] and (str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()))==p['footprint'],'PCB value/FPID '+ref)
 check(abs(f.GetPosition().x/1e6-p['placed_xy_mm'][0])<1e-6 and abs(f.GetPosition().y/1e6-p['placed_xy_mm'][1])<1e-6,'placement '+ref)
 pp={pad.GetNumber():pad for pad in f.Pads() if pad.GetNumber()};check(set(pp)==set(p['pins']),'PCB pad numbers '+ref)
 for number,net in p['pins'].items():
  pad=pp[number];check(pad.GetAttribute()==pcb.PAD_ATTRIB_PTH,'only leaded electrical pads')
  check(pad.GetNetname()==net if net is not None else pad.GetNetname().startswith('unconnected-'),'PCB net '+ref+':'+number)
  actual_pads[(ref,number)]=pad
for chip,n in [('U1',18),('Q1',3),('Q2',3),('U2',3)]:check(len(list(fps[chip].Pads()))==n,'package pin count '+chip)
check(abs((actual_pads['U1','18'].GetPosition().x-actual_pads['U1','1'].GetPosition().x)/1e6-7.62)<1e-9,'PDIP row pitch')
for ref,n,pitch in [('J1',4,2.5),('J2',2,3.96),('J3',2,3.96)]:
 for k in range(1,n):check(abs((actual_pads[ref,str(k+1)].GetPosition().x-actual_pads[ref,str(k)].GetPosition().x)/1e6-pitch)<1e-9,'connector pad pitch')
carrier=json.loads((root/'hardware/a5-idle-interface/net_contract.json').read_text());cp={p['ref']:p for p in carrier['parts']}
expected_carrier={'J4':{'1':'GND','2':'+3V3','3':'I2C_SDA','4':'I2C_SCL','5':'SAFE_N'},'R16':{'1':'+3V3','2':'I2C_SDA'},'R17':{'1':'+3V3','2':'I2C_SCL'}}
cb=pcb.LoadBoard(str(root/'hardware/a5-idle-interface/esp32-ecu.kicad_pcb'));cf={f.GetReference():f for f in cb.GetFootprints()}
for ref,pins in expected_carrier.items():
 check(cp[ref]['pins']==pins,'carrier contract '+ref)
 for number,net in pins.items():check(next(p for p in cf[ref].Pads()if p.GetNumber()==number).GetNetname()==net,'actual carrier pad '+ref+':'+number)
check(cp['U3']['pins']['21'] is None and next(p for p in cf['U3'].Pads()if p.GetNumber()=='21').GetNetname().startswith('unconnected-'),'module5V pad NC')
for ref in ('R16','R17'):check(cp[ref]['value']=='4.7k','existing carrier pullups')
project=json.loads((hw/'switches.kicad_pro').read_text());check(not project['board']['design_settings'].get('drc_exclusions',[]),'no DRC exclusions')
check(len(list(board.GetTracks()))>0,'routed copper present')
zones=list(board.Zones());check(len(zones)==1,'one reviewed ground return zone')
zone=zones[0];check(zone.GetNetname()=='GND' and zone.GetLayerSet().Contains(pcb.B_Cu),'back copper ground zone')
check(zone.IsFilled() and zone.GetFilledPolysList(pcb.B_Cu).OutlineCount()>0,'filled ground copper retained')
check(zone.GetIslandRemovalMode()==pcb.ISLAND_REMOVAL_MODE_ALWAYS,'floating islands removed')
check(zone.GetPadConnection()==pcb.ZONE_CONNECTION_THERMAL,'default thermal relief')
for value,wanted,name in [(zone.GetLocalClearance(),.35,'pour clearance'),(zone.GetMinThickness(),.25,'pour minimum fill'),(zone.GetThermalReliefGap(),.35,'thermal gap'),(zone.GetThermalReliefSpokeWidth(),.4,'thermal spoke')]:check(abs(value/1e6-wanted)<1e-9,name)
overrides={ref+'.'+number:pad.GetLocalZoneConnection()for(ref,number),pad in actual_pads.items()if pad.GetLocalZoneConnection()!=pcb.ZONE_CONNECTION_INHERITED}
check(overrides=={'R18.2':pcb.ZONE_CONNECTION_FULL},'only documented local full-connection override')
connectivity=board.GetConnectivity();connectivity.Build(board)
zone_pads={(pad.GetParentFootprint().GetReference(),pad.GetNumber())for pad in connectivity.GetConnectedPads(zone)}
check({('C1','2'),('U1','9'),('C2','2'),('U2','3')}<=zone_pads,'zone connectivity reaches bypass and chip return pads')
poly=zone.GetFilledPolysList(pcb.B_Cu);nearby_outlines={}
for ref,number in [('C1','2'),('U1','9')]:
 xy=actual_pads[ref,number].GetPosition();seen=set()
 for dx,dy in [(1500000,0),(-1500000,0),(0,1200000),(0,-1200000)]:
  for i in range(poly.OutlineCount()):
   if poly.Contains(pcb.VECTOR2I(xy.x+dx,xy.y+dy),i):seen.add(i)
 nearby_outlines[ref]=seen
check(bool(nearby_outlines['C1']&nearby_outlines['U1']),'same filled outline adjacent to C1 and U1 return pads')
for ref in ('H1','H2','H3','H4'):
 holes=list(fps[ref].Pads());check(len(holes)==1 and holes[0].GetAttribute()==pcb.PAD_ATTRIB_NPTH,'unplated isolated mount')
 check(abs(holes[0].GetDrillSize().x/1e6-3.2)<1e-9,'M3 mounting hole diameter')
if (out/'netlist.xml').exists():
 xml=ET.parse(out/'netlist.xml').getroot();components={n.attrib['ref']:n for n in xml.find('components')}
 check(set(components)==set(expected),'schematic exported component set')
 for ref,component in components.items():
  check(component.findtext('value')==parts[ref]['value'],'schematic value '+ref)
  check(component.findtext('footprint')==parts[ref]['footprint'],'schematic footprint '+ref)
  check((component.findtext('fields/field[@name="MPN"]')or'')==parts[ref]['mpn'],'schematic MPN '+ref)
 nodes={}
 for net in xml.find('nets'):
  for node in net.findall('node'):nodes[(node.attrib['ref'],node.attrib['pin'])]=net.attrib['name']
 for ref,pins in expected.items():
  for number,net in pins.items():
   actual=nodes.get((ref,number));check(actual==net if net is not None else actual is None or actual.startswith('unconnected-'),'schematic exported pin '+ref+':'+number)

def path(net,start,end):
 tracks=[t for t in board.GetTracks()if t.GetNetname()==net];points=set();lines=[];vias=[]
 def xy(v):return(v.x,v.y)
 for t in tracks:
  a,b=xy(t.GetStart()),xy(t.GetEnd())
  if isinstance(t,pcb.PCB_VIA):vias.append(a);points.update([(pcb.F_Cu,*a),(pcb.B_Cu,*a)])
  else:lines.append((t.GetLayer(),a,b));points.update([(t.GetLayer(),*a),(t.GetLayer(),*b)])
 pads=[p for p in actual_pads.values()if p.GetNetname()==net]
 for p in pads:
  a=xy(p.GetPosition());points.update([(pcb.F_Cu,*a),(pcb.B_Cu,*a)])
 graph=defaultdict(list)
 def edge(a,b,w):graph[a].append((b,w));graph[b].append((a,w))
 for layer,a,b in lines:
  dx,dy=b[0]-a[0],b[1]-a[1];square=dx*dx+dy*dy
  if not square:continue
  on=[]
  for node in points:
   if node[0]!=layer:continue
   px,py=node[1]-a[0],node[2]-a[1];u=(px*dx+py*dy)/square
   if -1e-9<=u<=1+1e-9 and abs(px*dy-py*dx)/math.sqrt(square)<500:on.append((u,node))
  on.sort()
  for(_,x),(_,y)in zip(on,on[1:]):edge(x,y,math.hypot(x[1]-y[1],x[2]-y[2])/1e6)
 for a in vias:edge((pcb.F_Cu,*a),(pcb.B_Cu,*a),0)
 for p in pads:
  a=xy(p.GetPosition());edge((pcb.F_Cu,*a),(pcb.B_Cu,*a),0)
  for node in points:
   if p.HitTest(pcb.VECTOR2I(node[1],node[2])):edge((node[0],*a),node,math.hypot(node[1]-a[0],node[2]-a[1])/1e6)
 a=actual_pads[start].GetPosition();b=actual_pads[end].GetPosition();source=(pcb.F_Cu,a.x,a.y);dest=(pcb.F_Cu,b.x,b.y)
 distances={source:0};q=[(0,source)]
 while q:
  length,node=heapq.heappop(q)
  if length!=distances[node]:continue
  if node==dest:return length
  for after,w in graph[node]:
   next_length=length+w
   if next_length<distances.get(after,math.inf):distances[after]=next_length;heapq.heappush(q,(next_length,after))
 return None
paths={}
for name,net,start,end in [('U1_bypass_supply','+3V3',('C1','1'),('U1','18')),('U1_bypass_return','GND',('C1','2'),('U1','9')),('U2_bypass_supply','+3V3',('C2','1'),('U2','2')),('U2_bypass_return','GND',('C2','2'),('U2','3'))]:paths[name]=path(net,start,end)
result=dict(passed=True,checks=checks,footprints=len(fps),tracks=len(list(board.GetTracks())),zones=len(zones),ground_zone_direct_pad_neighbors=len(zone_pads),common_filled_outline_near_bypass=sorted(nearby_outlines['C1']&nearby_outlines['U1']),track_only_bypass_path_lengths_mm=paths,zone_path_not_in_track_graph=bool(zones),physical_qualification=False)
(out/'cad-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
