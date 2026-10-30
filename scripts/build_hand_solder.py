#!/usr/bin/env python3
"""Generate A1 separately. Run with KiCad Python. Replaces A1 PCB routing."""
import copy,csv,json,shutil,sys
from pathlib import Path
import pcbnew as pcb
import design
import build_hardware as gen
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/a1-hand-solder'; LIB=OUT/'lib'
parts=copy.deepcopy(design.PARTS)
remove={'R1','R2','R3','R4','R5','R6','R10','C4','C7','C8','L1','J5','J6'}
parts=[p for p in parts if p.ref not in remove]
by={p.ref:p for p in parts}
def replace(ref,value,fp,pins,names,types,mpn):
 p=by[ref];p.value=value;p.footprint=fp;p.pins={str(k):v for k,v in pins.items()};p.names={str(k):v for k,v in names.items()};p.types={str(k):v for k,v in types.items()};p.mpn=mpn;p.note='A1 hand-solder revision; see docs/hand-solder.md'
for p in parts:
 if p.ref.startswith('R'):p.footprint='Resistor_SMD:R_1206_3216Metric_Pad1.30x1.75mm_HandSolder'
 if p.ref.startswith('C') and 'CP_Elec' not in p.footprint:p.footprint='Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder'
 if p.value=='BAT54WS':
  p.value='BAT85';p.mpn='BAT85,113';p.footprint='Diode_THT:D_DO-35_SOD27_P3.81mm_Vertical_AnodeUp';p.note='Axial Schottky mounted vertically. Validate input clamp voltage/leakage at temperature.'
for i in range(61,65):
 by['R'+str(i)].value='270k 1%'
 by['C'+str(i)].value='100n 5% C0G'
replace('U1','Pololu D36V6F5','ECU:Pololu_D36V6F5_vertical', {1:None,2:'VIN_PROT',3:'GND',4:'+5V'},{1:'SHDN',2:'VIN',3:'GND',4:'VOUT'},{2:'power_in',3:'power_in',4:'power_out'},'Pololu 3792')
replace('U4','TPS3828-33DBVR','Package_TO_SOT_SMD:SOT-23-5',{1:'SAFE_N',2:'GND',3:'+3V3',4:'WDI',5:'+3V3'},{1:'RESET_N_OD',2:'GND',3:'MR_N',4:'WDI',5:'VDD'},{1:'open_collector',2:'power_in',5:'power_in'},'TPS3828-33DBVR')
# Two cascaded Schmitt inverters per signal preserve capture polarity.
replace('U7','SN74LVC14AD','Package_SO:SOIC-14_3.9x8.7mm_P1.27mm', {1:'CRANK_FILT',2:'CRANK_INV',3:'CRANK_INV',4:'CRANK',5:'CAM_FILT',6:'CAM_INV',7:'GND',8:'CAM',9:'CAM_INV',10:None,11:'GND',12:None,13:'GND',14:'+3V3'}, {}, {2:'output',4:'output',6:'output',8:'output',10:'output',12:'output',7:'power_in',14:'power_in'},'SN74LVC14AD')
gpio=dict(design.GPIO,ARM=47)
reverse={v:k for k,v in gpio.items()}
left=['+3V3','+3V3','EN',4,5,6,7,15,16,17,18,8,3,46,9,10,11,12,13,14,None,'GND']
right=['GND',43,44,1,2,42,41,40,39,38,37,36,35,0,45,48,47,21,20,19,'GND','GND']
def signal(v):return reverse.get(v,'BOOT_N' if v==0 else None) if isinstance(v,int) else v
pins={i+1:signal(v) for i,v in enumerate(left+right)}
replace('U3','ESP32-S3-DevKitC-1-N8R8 v1.1','ECU:ESP32_S3_DevKitC_1_socket',pins,{i+1:str(v) for i,v in enumerate(left+right)}, {i+1:('power_in' if v in ['+3V3','GND'] else 'bidirectional') for i,v in enumerate(left+right)},'ESP32-S3-DevKitC-1-N8R8')
by['U3'].names['35']=''
# Individual sensor sockets. Pin 1 is square and explicitly labelled.
connectors=[]
def extra(ref,value,nets,page,xy,footprint,mpn):
 p=design.Part(ref,value,footprint,{str(i+1):n for i,n in enumerate(nets)},{},{},page,xy,mpn=mpn,note='A1 internal locking connector; not sealed. See connector-pinout.csv')
 parts.append(p);by[ref]=p;return p
for i,(label,sig) in enumerate([(s,s) for s in design.analog_signals]+[('CRANK','CRANK_RAW'),('CAM','CAM_RAW')]):
 p=extra(f'J{11+i}',label,['GND','SENSOR_5V',sig],'analog' if i<6 else 'trigger_can',(0,0),'Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical','B3B-XH-A(LF)(SN)')
 connectors.append(p)
extra('U18','TLV803EA46DBZR',['GND','SAFE_N','+5V'],'power',(0,0),'Package_TO_SOT_SMD:SOT-23','TLV803EA46DBZR')
by['U18'].names={'1':'GND','2':'RESET_N','3':'VDD'};by['U18'].types={'1':'power_in','2':'open_collector','3':'power_in'}
extra('C44','100n',['+5V','GND'],'power',(0,0),'Capacitor_SMD:C_1206_3216Metric_Pad1.33x1.80mm_HandSolder','')
for ref in ['J1','J7','J8','J9','J10']:
 p=by[ref];n=len(p.pins)
 if ref=='J7':p.footprint='Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical';p.mpn='B3B-XH-A(LF)(SN)'
 else:p.footprint=f'Connector_JST:JST_VH_B{n}P-VH_1x{n:02d}_P3.96mm_Vertical';p.mpn=f'B{n}P-VH(LF)(SN)'
 p.note='Polarized internal loom connector. Separate fused relay-switched actuator supply. See pinout.'
LIB.mkdir(parents=True,exist_ok=True);(LIB/'ecu.pretty').mkdir(exist_ok=True)
# Custom footprints: module socket row spacing from Espressif drawing; module pin order from Pololu bottom view.
def custom(name,pads,box):
 lines=[f'(footprint "{name}" (version 20241229) (generator "esp32_ecu") (layer "F.Cu") (attr through_hole)', '(property "Reference" "U?" (at 0 -4) (layer "F.SilkS") (effects (font (size 1 1))))','(property "Value" "MODULE" (at 0 -6) (layer "F.Fab") (effects (font (size 1 1))))']
 x1,y1,x2,y2=box
 for layer in ['F.SilkS','F.CrtYd']:
  lines.append(f'(fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.15) (type default)) (fill none) (layer "{layer}"))')
 for n,x,y in pads:lines.append(f'(pad "{n}" thru_hole {"rect" if n==1 else "oval"} (at {x} {y}) (size 1.8 1.8) (drill 1.0) (layers "*.Cu" "*.Mask"))')
 lines.append(')');(LIB/'ecu.pretty'/f'{name}.kicad_mod').write_text('\n'.join(lines))
custom('ESP32_S3_DevKitC_1_socket',[(i+1,0,2.54*i) for i in range(22)]+[(i+23,22.86,2.54*i) for i in range(22)],(-1.5,-7,24.36,57))
custom('Pololu_D36V6F5_vertical',[(i+1,2.54*i,0) for i in range(4)],(-1.5,-1.5,9.2,3.5))
for p in parts:
 if p.footprint.startswith('ECU:'):continue
 group,stem=p.footprint.split(':');shutil.copyfile(gen.STOCK/'footprints'/f'{group}.pretty'/f'{stem}.kicad_mod',LIB/'ecu.pretty'/f'{stem}.kicad_mod')
gen.OUT=OUT;gen.LIB=LIB;gen.PARTS=parts;gen.GPIO=gpio;gen.add_power_returns=lambda board:None
# Generate sources without touching the A0 firmware or routed A0 PCB.
gen.schematic()
for path in OUT.glob('*.kicad_sch'):path.write_text(path.read_text().replace('A0','A1 HAND SOLDER'))
(OUT/'sym-lib-table').write_text('(sym_lib_table (lib (name "ECU") (type "KiCad") (uri "${KIPRJMOD}/lib/ecu.kicad_sym") (options "") (descr "A1")))')
(OUT/'fp-lib-table').write_text('(fp_lib_table (lib (name "ECU") (type "KiCad") (uri "${KIPRJMOD}/lib/ecu.pretty") (options "") (descr "A1")))')
# schematic has embedded symbols; retain a library for editing.
(LIB/'ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "esp32_ecu") '+ '\n'.join(gen.symbol(p)[0] for p in parts+[design.Part('#FLG0'+str(i),'PWR_FLAG','ECU:unused',{'1':net},{},{'1':'power_out'},'power',(0,0)) for i,net in enumerate(['GND','VIN_PROT','+5V'],1)] if p.pins)+')')
(OUT/'esp32-ecu.kicad_pro').write_text(json.dumps({'meta':{'version':1},'board':{'design_settings':{'rules':{'min_clearance':.2,'min_track_width':.2,'min_copper_edge_clearance':.4}}},'net_settings':gen.net_settings()},indent=2))
gen.pcb_board()
b=pcb.LoadBoard(str(OUT/'esp32-ecu.kicad_pcb'))
def place(ref,x,y,angle=0):
 f=b.FindFootprintByReference(ref);f.SetPosition(pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y)));f.SetOrientationDegrees(angle)
place('U3',20,48);place('U1',54,26);place('U18',62,27);place('C44',62,32)
for i,p in enumerate(connectors):place(p.ref,20+23*i,198)
# Large actuator plugs get their own perimeter space.
place('J1',18,23);place('J8',178,108,90);place('J9',194,65,90);place('J10',194,148,90)
place('J7',100,140)
# Pack by courtyard with a 0.8 mm assembly gap, retaining connector datums.
fixed={'U3','J1','J7','J8','J9','J10',*[p.ref for p in connectors], 'H1','H2','H3','H4'}
def bounds(f):
 items=[x.GetBoundingBox() for x in f.GraphicalItems() if x.GetLayer()==pcb.F_CrtYd]
 if not items:items=[x.GetBoundingBox() for x in f.Pads()]
 return (min(r.GetX() for r in items)/1e6,min(r.GetY() for r in items)/1e6,max(r.GetRight() for r in items)/1e6,max(r.GetBottom() for r in items)/1e6)
def intersects(a,c):return a[0]<c[2]+.8 and a[2]>c[0]-.8 and a[1]<c[3]+.8 and a[3]>c[1]-.8
occupied=[bounds(f) for f in b.GetFootprints() if f.GetReference() in fixed]
movable=[f for f in b.GetFootprints() if f.GetReference() not in fixed]
movable.sort(key=lambda f: -(bounds(f)[2]-bounds(f)[0])*(bounds(f)[3]-bounds(f)[1]))
for f in movable:
 x,y=f.GetPosition().x/1e6,f.GetPosition().y/1e6
 candidates=[(x+dx,y+dy) for dx in range(-35,36) for dy in range(-35,36)]
 candidates.sort(key=lambda v:(v[0]-x)**2+(v[1]-y)**2)
 for px,py in candidates:
  f.SetPosition(pcb.VECTOR2I(pcb.FromMM(px),pcb.FromMM(py)));bb=bounds(f)
  if bb[0]<16 or bb[1]<18 or bb[2]>204 or bb[3]>186:continue
  if any(intersects(bb,o) for o in occupied):continue
  occupied.append(bb);break
 else:raise RuntimeError('No assembly clearance: '+f.GetReference())
for f in b.GetFootprints():
 f.Reference().SetLayer(pcb.F_Fab);f.Reference().SetVisible(True)
for f in b.GetFootprints():
 if f.GetReference().startswith('H'):f.Reference().SetVisible(False)
for t in b.GetDrawings():
 if isinstance(t,pcb.PCB_TEXT):t.SetText(t.GetText().replace('A0','A1 HAND SOLDER'))
for zone in b.Zones():zone.SetPadConnection(pcb.ZONE_CONNECTION_THERMAL)
# Print friendly sensor identification above each plug.
for p in connectors:
 f=b.FindFootprintByReference(p.ref);pos=f.GetPosition();t=pcb.PCB_TEXT(b);t.SetText(p.value+'\n1:G 2:5V 3:SIG');t.SetPosition(pcb.VECTOR2I(pos.x+pcb.FromMM(2.5),pos.y-pcb.FromMM(6)));t.SetTextSize(pcb.VECTOR2I(pcb.FromMM(.8),pcb.FromMM(.8)));t.SetTextThickness(pcb.FromMM(.12));t.SetLayer(pcb.F_SilkS);b.Add(t)
pcb.SaveBoard(str(OUT/'esp32-ecu.kicad_pcb'),b)
with (OUT/'bom.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Reference','Value','MPN','Footprint','DNP','Note']);w.writerows([p.ref,p.value,p.mpn,p.footprint,p.dnp,p.note] for p in parts)
contract={'revision':'A1','status':'layout_in_progress_not_for_fabrication','gpio':gpio,'parts':[vars(p) for p in parts]};(OUT/'net_contract.json').write_text(json.dumps(contract,indent=2))
with (OUT/'connector-pinout.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Connector','Label','PCB pin','Net','Mating housing']);
 for p in parts:
  if p.ref.startswith('J'):
   mate='XHP-3' if 'XH_' in p.footprint else f'VHR-{len(p.pins)}N' if 'VH_' in p.footprint else '2.54mm service header'
   for n,net in p.pins.items():w.writerow([p.ref,p.value,n,net,mate])
print(f'A1 generated: {len(parts)} parts. Routing and checks required.')
