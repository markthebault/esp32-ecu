"""Audit A2 actual PCB nets, home-soldering construction and EMI layout provisions."""
import json,math
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact';b=p.LoadBoard(str(O/'esp32-ecu.kicad_pcb'));c=json.loads((O/'net_contract.json').read_text());fps={f.GetReference():f for f in b.GetFootprints()};count=0;drills=[]
assert len(fps)==len(c['parts'])
for d in c['parts']:
 f=fps[d['ref']];assert str(f.GetFPID().GetLibItemName())==d['footprint'].split(':')[1],d['ref']
 actual={x.GetNumber():x.GetNetname() for x in f.Pads() if x.GetNumber()};expected={}
 for n,net in d['pins'].items():
  name=d['names'].get(n,'');expected[n]=net if net is not None else f'unconnected-({d["ref"]}-'+(name+'-' if name else '')+f'Pad{n})'
 assert actual==expected,(d['ref'],actual,expected)
 for pad in f.Pads():
  if not pad.GetNumber():continue
  assert pad.GetAttribute()==p.PAD_ATTRIB_PTH,(d['ref'],'user-soldered pad is not plated through-hole')
  drills.append(pad.GetDrillSize().x/1e6)
 count+=len(actual)
# Follow module I/O through its physical header and the two added source resistors.
left_gpio={4:4,5:5,6:6,7:7,8:15,9:16,10:17,11:18,12:8,13:3,14:46,15:9,16:10,17:11,18:12,19:13,20:14}
right_gpio={24:43,25:44,26:1,27:2,28:42,29:41,30:40,31:39,32:38,33:37,34:36,35:35,36:0,37:45,38:48,39:47,40:21,41:20,42:19}
actual={int(x.GetNumber()):x.GetNetname() for x in fps['U3'].Pads()}
for net,gpio in c['gpio'].items():
 pin=next(k for k,v in {**left_gpio,**right_gpio}.items() if v==gpio)
 assert actual[pin]==net+('_MCU' if net in ['SPI_CLK','SPI_MOSI'] else ''),(net,pin)
assert c['gpio']['ARM']==47
padlist={int(x.GetNumber()):x for x in fps['U3'].Pads()}
assert abs((padlist[23].GetPosition().x-padlist[1].GetPosition().x)/1e6-22.86)<1e-6
assert abs((padlist[2].GetPosition().y-padlist[1].GetPosition().y)/1e6-2.54)<1e-6
# All 8 sensor sockets have the same documented three-pin assignment.
for i,sig in enumerate(['MAP','TPS','CLT','IAT','LAMBDA_WB','POSTCAT_BUF','CRANK_RAW','CAM_RAW']):
 pads={x.GetNumber():x.GetNetname() for x in fps['J'+str(11+i)].Pads()};assert pads=={'1':'GND','2':'SENSOR_5V','3':sig}
# Mechanical datums: four supports plus the independent chassis lug.
for ref,xy in {'H1':(14,14),'H2':(126,14),'H3':(14,126),'H4':(126,126),'H5':(15,110)}.items():
 f=fps[ref];assert math.dist((f.GetPosition().x/1e6,f.GetPosition().y/1e6),xy)<1e-6
assert any(z.GetLayer()==p.In1_Cu and z.GetNetname()=='GND' and not z.GetIsRuleArea() for z in b.Zones())
assert not any(t.GetLayer()==p.In1_Cu and not isinstance(t,p.PCB_VIA) for t in b.GetTracks())
assert any(z.GetLayer()==p.B_Cu and z.GetNetname()=='CHASSIS' for z in b.Zones())
assert b.GetCopperLayerCount()==6
assert any(z.GetLayer()==p.In4_Cu and z.GetNetname()=='GND' for z in b.Zones())
assert not any(t.GetLayer()==p.In4_Cu and not isinstance(t,p.PCB_VIA) for t in b.GetTracks())
points=[(s.GetStart().x/1e6,s.GetStart().y/1e6) for s in b.GetDrawings() if s.GetLayer()==p.Edge_Cuts]
assert max(v[0] for v in points)-min(v[0] for v in points)==120
assert max(v[1] for v in points)-min(v[1] for v in points)==120
# Record distances as layout evidence, not an RF immunity result.
decouplers={'C15':('U4','8'),'C16':('U5','2'),'C28':('U6','16'),'C32':('U7','14'),'C33':('U8','3'),'C34':('U8','5'),'C35':('U9','14'),'C36':('U10','14'),'C37':('U11','14'),'C38':('U12','16'),'C39':('U13','16'),'C40':('U14','16'),'C41':('U15','16'),'C42':('U16','14'),'C43':('U17','14')}
distances={}
for cap,(ic,n) in decouplers.items():
 pad=next(x for x in fps[ic].Pads() if x.GetNumber()==n);a=pad.GetPosition();distance=min(math.hypot((x.GetPosition().x-a.x)/1e6,(x.GetPosition().y-a.y)/1e6) for x in fps[cap].Pads() if x.GetNetname()==pad.GetNetname());distances[cap]=round(distance,3)
 assert distance<16,(cap,'bypass capacitor is too far from the supply pin')
s=json.loads((R/'reports/a3/drc.json').read_text());assert not s['violations'] and not s['unconnected_items'] and not s['schematic_parity']
e=json.loads((R/'reports/a3/erc.json').read_text());assert all(not sh.get('violations') for sh in e['sheets'])
result={'revision':'A3-120','footprints':len(fps),'pads_checked':count,'user_soldered_smd_pads':0,'minimum_component_drill_mm':min(drills),'gpio_to_header_audit':'pass','sensor_pinout_audit':'pass','mechanical_datums':'pass','erc_violations':0,'drc_violations':0,'unconnected':0,'schematic_parity_issues':0,'bypass_cap_supply_pin_distances_mm':distances,'physical_fit_tested':False,'emi_immunity_tested':False,'vehicle_qualified':False,'copper_layers':6,'pcb_outline_mm':[120,120],'ground_planes':['In1.Cu','In4.Cu']}
result['mounting_hole_centers_board_mm']={ref:[fps[ref].GetPosition().x/1e6,fps[ref].GetPosition().y/1e6] for ref in ['H1','H2','H3','H4']}
(R/'reports/a3/validation-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
