#!/usr/bin/env python3
"""Create A3 from the audited A2 electrical contract. KiCad Python required.
Components remain leaded; ordinary 1/4W resistors stand vertically. No SMD conversion.
"""
import json,shutil,subprocess,sys,math
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact';STOCK=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
if '--place' not in sys.argv:
 shutil.copytree(R/'hardware/a2-through-hole',O,dirs_exist_ok=True)
 b=p.LoadBoard(str(O/'esp32-ecu.kicad_pcb'))
 for obj in list(b.GetTracks())+list(b.Zones())+list(b.GetDrawings()):b.Remove(obj)
 p.SaveBoard(str(O/'esp32-ecu.kicad_pcb'),b)
 subprocess.run([sys.executable,__file__,'--place'],check=True)
 subprocess.run([sys.executable,str(R/'scripts/fix_a3_capacitor_labels.py')],check=True)
 subprocess.run([sys.executable,str(R/'scripts/sync_a3_symbols.py')],check=True)
 raise SystemExit
c=json.loads((O/'net_contract.json').read_text());b=p.LoadBoard(str(O/'esp32-ecu.kicad_pcb'));b.SetCopperLayerCount(6);b.SetLayerType(p.In4_Cu,p.LT_POWER);oldfps={f.GetReference():f for f in b.GetFootprints()}
vertical='Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical';diode='Diode_THT:D_DO-35_SOD27_P3.81mm_Vertical_AnodeUp'
# Replacement happens before saving and reloading in a fresh process, avoiding SWIG type invalidation.
if '--packed' not in sys.argv:
 for d in c['parts']:
  new=vertical if d['ref'].startswith('R') and d['ref']!='R150' else diode if d['value']=='BAT85' else None
  if not new:continue
  old=oldfps[d['ref']];group,stem=new.split(':');src=STOCK/(group+'.pretty')/(stem+'.kicad_mod');shutil.copyfile(src,O/'lib/ecu.pretty'/src.name)
  f=p.FootprintLoad(str(O/'lib/ecu.pretty'),stem);f.SetReference(d['ref']);f.SetValue(d['value']);f.SetFPID(p.LIB_ID('ECU',stem));f.SetPath(old.GetPath());f.SetUuid(old.m_Uuid)
  oldpads={x.GetNumber():x for x in old.Pads() if x.GetNumber()}
  for pad in f.Pads():
   if pad.GetNumber():pad.SetNet(oldpads[pad.GetNumber()].GetNet())
  if d['dnp']:f.SetAttributes(f.GetAttributes()|p.FP_DNP)
  f.Reference().SetLayer(p.F_Fab);f.Value().SetVisible(False);b.Add(f);b.Remove(old);d['footprint']=new
 for sch in O.glob('*.kicad_sch'):
  s=sch.read_text().replace('A2 THROUGH HOLE','A3 COMPACT 120mm').replace('A2','A3')
  s=s.replace('R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal','R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical')
  # R150 alone remains horizontal; correct its footprint by symbol UUID block if needed via generator later.
  s=s.replace('D_DO-35_SOD27_P7.62mm_Horizontal','D_DO-35_SOD27_P3.81mm_Vertical_AnodeUp');sch.write_text(s)
 # R150 must retain the horizontal footprint in both schematic and PCB.
 import re
 sch=O/'power.kicad_sch';s=sch.read_text()
 # The generated symbols store Reference before Footprint. Scope replacement to R150's instance.
 start=s.index('(property "Reference" "R150"');end=s.find('(property "Reference"',start+1)
 block=s[start:end if end>=0 else len(s)].replace(vertical.split(':')[1],'R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal');s=s[:start]+block+s[end if end>=0 else len(s):];sch.write_text(s)
 c['revision']='A3-120';c['status']='unrouted_not_for_fabrication';(O/'net_contract.json').write_text(json.dumps(c,indent=2));p.SaveBoard(str(O/'esp32-ecu.kicad_pcb'),b)
 subprocess.run([sys.executable,__file__,'--place','--packed'],check=True);raise SystemExit
fps={f.GetReference():f for f in b.GetFootprints()};data={d['ref']:d for d in c['parts']};fixed={}
def pos(ref,x,y,a=0):f=fps[ref];f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(a)
def bounds(f):
 items=[i.GetBoundingBox() for i in f.GraphicalItems() if i.GetLayer()==p.F_CrtYd]
 if not items:items=[i.GetBoundingBox() for i in f.Pads()]
 return tuple(v/1e6 for v in [min(i.GetX() for i in items),min(i.GetY() for i in items),max(i.GetRight() for i in items),max(i.GetBottom() for i in items)])
def overlap(a,c,gap=.15):return a[0]<c[2]+gap and a[2]>c[0]-gap and a[1]<c[3]+gap and a[3]>c[1]-gap
def fix(ref,x,y,a=0):pos(ref,x,y,a);fixed[ref]=bounds(fps[ref])
for ref,xy in zip(['H1','H2','H3','H4'],[(14,14),(126,14),(14,126),(126,126)]):fix(ref,*xy)
fix('U3',18,39);fix('J1',22,23);fix('J19',107,18);fix('J20',108,107);fix('H5',15,110)
fix('J9',122,25,270);fix('J10',122,65,270);fix('J8',122,95,270)
for i in range(8):fix('J'+str(11+i),23+i*12.2,123)
for i in range(4):fix('Q'+str(i+1),49+14*i,19)
# Entry filter and conversion remain near J1, away from the analog bank.
for ref,x,y,a in [('D1',32,16,0),('D2',50,26,180),('L2',55,37,0),('C2',68,35,0),('U1',65,45,0),('C45',79,35,0),('R150',88,28,0),('U2',72,54,0)]:fix(ref,x,y,a)
occupied=list(fixed.values())+[(16,29,43,36)]
for r,a in fixed.items():
 for other,cbb in fixed.items():
  if r<other and overlap(a,cbb,.2):raise RuntimeError('fixed overlap '+str((r,other,a,cbb)))
print('Court area',sum((bounds(f)[2]-bounds(f)[0])*(bounds(f)[3]-bounds(f)[1]) for f in fps.values()),'available',118**2)
decouplers={'C10':('U2','2'),'C15':('U4','8'),'C16':('U5','2'),'C28':('U6','16'),'C32':('U7','14'),'C33':('U8','3'),'C34':('U8','5'),'C35':('U9','14'),'C36':('U10','14'),'C37':('U11','14'),'C38':('U12','16'),'C39':('U13','16'),'C40':('U14','16'),'C41':('U15','16'),'C42':('U16','14'),'C43':('U17','14')}
preferred={'U6':(52,106),'U7':(101,102),'U8':(41,92),'U4':(50,58),'U5':(60,60),'U9':(51,74),'U10':(79,58),'U11':(99,58),'U12':(79,80),'U13':(98,80),'U14':(61,94),'U15':(83,100),'U16':(99,45),'U17':(53,47),'J7':(22,98)}
movable=[d for d in c['parts'] if d['ref'] not in fixed]
def area(ref):bb=bounds(fps[ref]);return (bb[2]-bb[0])*(bb[3]-bb[1])
ics=sorted([d for d in movable if d['ref'].startswith('U')],key=lambda d:-area(d['ref']))
ordered=[d for d in movable if d['ref'] in decouplers and decouplers[d['ref']][0] in fixed]
for ic in ics:
 ordered.append(ic)
 ordered.extend(d for d in movable if d['ref'] in decouplers and decouplers[d['ref']][0]==ic['ref'])
used={d['ref'] for d in ordered}
ordered.extend(sorted([d for d in movable if d['ref'] not in used],key=lambda d:(0 if d['ref'].startswith('J') else 1,-area(d['ref']))))
movable=ordered

for d in movable:
 ref=d['ref'];f=fps[ref];desired=preferred.get(ref,{'power':(60,39),'core':(55,68),'analog':(64,112),'trigger_can':(102,109),'injectors':(85,68),'ignition':(90,86),'outputs':(107,94)}[d['page']])
 if ref in decouplers:
  ic,pin=decouplers[ref];pad=next(x for x in fps[ic].Pads() if x.GetNumber()==pin);desired=(pad.GetPosition().x/1e6,pad.GetPosition().y/1e6)
 # 1 mm candidate grid supports ordinary manual rework clearances.
 candidates=[(x,y,a) for a in [0,90,180,270] for x in [v/2 for v in range(24,257)] for y in [v/2 for v in range(24,257)]]
 candidates.sort(key=lambda v:(v[0]-desired[0])**2+(v[1]-desired[1])**2+(.05 if v[2] else 0))
 offsets={}
 for a in [0,90,180,270]:
  pos(ref,0,0,a);offsets[a]=bounds(f)
 for x,y,a in candidates:
  offset=offsets[a];bb=(x+offset[0],y+offset[1],x+offset[2],y+offset[3])
  if min(bb[:2])<11 or max(bb[2:])>129:continue
  if any(overlap(bb,cbb) for cbb in occupied):continue
  if ref in decouplers:
   pos(ref,x,y,a)
   supply=data[ref]['pins']['1'];distance=min(math.dist((pad.GetPosition().x/1e6,pad.GetPosition().y/1e6),desired) for pad in f.Pads() if pad.GetNetname()==supply)
   if distance>13:continue
  pos(ref,x,y,a);occupied.append(bb);break
 else:raise RuntimeError('no room '+ref)
 d['placed_xy_mm']=[x,y];d['placed_angle_deg']=a
for ref in fixed:
 d=data[ref];f=fps[ref];d['placed_xy_mm']=[f.GetPosition().x/1e6,f.GetPosition().y/1e6];d['placed_angle_deg']=f.GetOrientationDegrees()
for a,bb in [((10,10),(130,10)),((130,10),(130,130)),((130,130),(10,130)),((10,130),(10,10))]:
 s=p.PCB_SHAPE();s.SetShape(p.SHAPE_T_SEGMENT);s.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])));s.SetEnd(p.VECTOR2I(p.FromMM(bb[0]),p.FromMM(bb[1])));s.SetLayer(p.Edge_Cuts);s.SetWidth(p.FromMM(.05));b.Add(s)
nets={n.GetNetname():n for n in b.GetNetsByNetcode().values()}
def zone(layer,net,points,clearance):
 z=p.ZONE(b);z.SetLayer(layer);z.SetNet(nets[net]);z.SetLocalClearance(p.FromMM(clearance));z.SetPadConnection(p.ZONE_CONNECTION_THERMAL);z.SetThermalReliefGap(p.FromMM(.25));z.SetThermalReliefSpokeWidth(p.FromMM(.5));z.Outline().NewOutline()
 for x,y in points:z.Outline().Append(p.FromMM(x),p.FromMM(y))
 b.Add(z)
zone(p.In1_Cu,'GND',[(10.5,10.5),(129.5,10.5),(129.5,129.5),(10.5,129.5)],.25)
zone(p.In4_Cu,'GND',[(10.5,10.5),(129.5,10.5),(129.5,129.5),(10.5,129.5)],.25)
zone(p.B_Cu,'CHASSIS',[(11,107),(19,107),(19,114),(129,114),(129,129),(11,129)],.35)
# Keep copper away from the purchased module antenna; service requires the lid open.
k=p.ZONE(b);k.SetIsRuleArea(True);k.SetLayerSet(p.LSET.AllCuMask());k.SetDoNotAllowTracks(True);k.SetDoNotAllowVias(True);k.SetDoNotAllowZoneFills(True);k.Outline().NewOutline()
for x,y in [(20,32),(39,32),(39,40),(20,40)]:k.Outline().Append(p.FromMM(x),p.FromMM(y))
b.Add(k)
# Low impedance injector source bus returns directly to J19, above the logic circuits.
def gtrack(a,bb):
 t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])));t.SetEnd(p.VECTOR2I(p.FromMM(bb[0]),p.FromMM(bb[1])));t.SetWidth(p.FromMM(2.5));t.SetLayer(p.F_Cu);t.SetNet(nets['GND']);b.Add(t)
# Footprint reference labels remain available on Fab; no false empty sockets.
for f in fps.values():f.Reference().SetLayer(p.F_Fab)
p.SaveBoard(str(O/'esp32-ecu.kicad_pcb'),b);(O/'net_contract.json').write_text(json.dumps(c,indent=2))
import csv
with (O/'bom.csv').open('w') as out:
 w=csv.writer(out);w.writerow(['Reference','Value','MPN','Footprint','DNP','Assembly','Note'])
 for d in c['parts']:w.writerow([d['ref'],d['value'],d['mpn'],d['footprint'],d['dnp'],'Purchased assembled module' if d['ref'] in ['U1','U3'] else 'Through hole',d['note']])
print('A3 120 x 120 placed',len(fps),'footprints')
