#!/usr/bin/env python3
"""A2 through-hole carrier. KiCad Python required. Full build replaces A2 routing.
--metadata refreshes source sheets/BOM only and leaves routed copper untouched.
"""
import argparse,csv,json,math,shutil
from pathlib import Path
import pcbnew as pcb
from design import Part
import build_hardware as gen
R=Path(__file__).resolve().parents[1];O=R/'hardware/a2-through-hole';L=O/'lib';(L/'ecu.pretty').mkdir(parents=True,exist_ok=True)
seed=json.loads((R/'scripts/a2-seed.json').read_text())
parts=[Part(**d) for d in seed['parts'] if d['ref'] not in ['U18','C44']];by={p.ref:p for p in parts};gpio=seed['gpio']
RFP='Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'
CFP='Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm'
FILM='Capacitor_THT:C_Rect_L7.2mm_W5.0mm_P5.00mm'
DIP=lambda n:f'Package_DIP:DIP-{n}_W7.62mm_LongPads'
for p in parts:
 p.note=p.note.replace('A1','A2').replace('docs/hand-solder.md','docs/through-hole.md')
 if p.ref.startswith('R'):p.footprint=RFP
 if p.ref.startswith('C'):
  p.footprint=CFP
  if any(v in p.value for v in ['1u','10u','22u','47u']):p.footprint=FILM
  if '22u' in p.value or '47u' in p.value or '10u' in p.value:p.footprint='Capacitor_THT:CP_Radial_D8.0mm_P3.50mm'
 if p.value=='BAT85':p.footprint='Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal'
 if p.ref.startswith('TP'):p.footprint='TestPoint:TestPoint_THTPad_D2.5mm_Drill1.2mm'
 if p.ref.startswith('Q'):
  p.value=p.mpn='VNP35N07-E';p.footprint='Package_TO_SOT_THT:TO-220-3_Vertical'
  p.note='Protected low-side TO-220, INPUT / DRAIN / SOURCE. Tab is live drain. External branch fuses required; current/thermal/clamp targets need tests.'
for i in range(61,65):by['R'+str(i)].value='100k 1%';by['C'+str(i)].value='270n 5% FILM';by['C'+str(i)].footprint=FILM
for i in range(81,85):by['C'+str(i)].value='68n 5% FILM';by['C'+str(i)].footprint=FILM
for ref in ['U9','U10','U11','U16','U17']:
 p=by[ref];p.value=p.mpn='SN74HCT08N';p.footprint=DIP(14)
for ref in ['U12','U13','U14','U15']:
 p=by[ref];p.value=p.mpn='CD74HCT221E';p.footprint=DIP(16)
p=by['U6'];p.value=p.mpn='MCP3208-CI/P';p.footprint=DIP(16)
p=by['U7'];p.value=p.mpn='SN74HC14N';p.footprint=DIP(14)
p=by['U8'];p.value=p.mpn='MCP2562-E/P';p.footprint=DIP(8);p.names['8']='STBY';p.note='Standby by default. JP1 open; firmware listen-only. Not a silent normal-mode transceiver.'
p=by['U2'];p.value=p.mpn='LD1117V33';p.footprint='Package_TO_SOT_THT:TO-220-3_Vertical';p.note='3V3 regulator. 200mA continuous target pending thermal measurement. Use specified electrolytic ESR; no USB/carrier dual power.'
p=by['U4'];p.value=p.mpn='MAX1232EPA+';p.footprint=DIP(8)
p.pins={'1':'+5V','2':'+5V','3':'GND','4':'GND','5':None,'6':'SAFE_N','7':'WDI','8':'+5V'}
p.names={'1':'PBRST_N','2':'TD','3':'TOL','4':'GND','5':'RST_HIGH','6':'RESET_N_OD','7':'ST_N','8':'VCC'};p.types={'4':'power_in','5':'output','6':'open_collector','8':'power_in'}
p.note='5V monitor and watchdog: TD=VCC, 500..2000ms watchdog (1.2s typical); reset active 250..1000ms. TTL ST accepts 3V3. Open-drain reset wired to 3V3 SAFE_N.'
by['C15'].pins={'1':'+5V','2':'GND'};by['R12'].value='10k'
p=by['U5'];p.value=p.mpn='MCP120-315DI/TO';p.footprint='Package_TO_SOT_THT:TO-92_Inline_Wide';p.pins={'1':'SAFE_N','2':'+3V3','3':'GND'};p.names={'1':'RESET_N_OD','2':'VDD','3':'VSS'};p.types={'1':'open_collector','2':'power_in','3':'power_in'};p.note='D bondout TO-92: RESET, VDD, VSS. Different bondout suffixes are not drop-in.'
p=by['D1'];p.value=p.mpn='1.5KE27CA';p.footprint='Diode_THT:D_DO-201AD_P5.08mm_Vertical_AnodeUp';p.note='Axial bidirectional TVS; 23.1V standoff and specified 37.5V pulse clamp. No load-dump qualification claim.'
p=by['D2'];p.value='SB5100';p.mpn='SB5100-B';p.footprint='Diode_THT:D_DO-201AD_P15.24mm_Horizontal';p.pins={'1':'VIN_PROT','2':'VBAT_FUSED'};p.names={'1':'K','2':'A'}
p=by['F2'];p.value='PTC 100mA radial';p.mpn='MF-R010';p.footprint='ECU:PTC_MF_R010';p.note='100mA hold rating at datasheet ambient; thermal derating and slow trip, not an electronic current limiter.'
p=by['C2'];p.value='47u 63V';p.footprint='Capacitor_THT:CP_Radial_D8.0mm_P3.50mm';p.pins={'1':'VIN_FILTERED','2':'GND'}
by['U1'].pins['2']='VIN_FILTERED'
p=by['D22'];p.value='P6KE24CA';p.mpn='P6KE24CA';p.footprint='Diode_THT:D_DO-15_P12.70mm_Horizontal';p.pins={'1':'CANH','2':'GND'};p.names={};p.note='Axial bidirectional CAN surge clamp; verify overshoot and capacitance on assembled bus.'
by['J7'].pins['4']='CHASSIS';by['J7'].value='CAN_H_L_G_SHIELD';by['J7'].mpn='B4B-XH-A(LF)(SN)';by['J7'].footprint='Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical'
def add(ref,value,fp,pins,page,mpn='',note='',dnp=False,names=None,types=None):
 p=Part(ref,value,fp,{str(k):v for k,v in pins.items()},names or {},types or {},page,(0,0),mpn=mpn,note=note,dnp=dnp);parts.append(p);by[ref]=p;return p
add('D23','P6KE24CA','Diode_THT:D_DO-15_P12.70mm_Horizontal',{1:'CANL',2:'GND'},'trigger_can','P6KE24CA')
add('L2','47uH input filter','Inductor_THT:L_Radial_D10.0mm_P5.00mm_Fastron_07P',{1:'VIN_PROT',2:'VIN_FILTERED'},'power','RLB0914-470KL','Radial choke, 5mm pitch. 1.56A datasheet current; check derating. Not the converter switching inductor.')
add('R150','1R 0.5W damping',RFP,{1:'VIN_FILTERED',2:'FILTER_DAMP'},'power',note='Series RC damping branch across converter input; verify input impedance/load-step stability.')
add('C45','47u 63V','Capacitor_THT:CP_Radial_D8.0mm_P3.50mm',{1:'FILTER_DAMP',2:'GND'},'power')
add('C46','100n 100V',CFP,{1:'VIN_FILTERED',2:'GND'},'power')
add('J19','POWER_RETURN','Connector_JST:JST_VH_B2P-VH_1x02_P3.96mm_Vertical',{1:'GND',2:'GND'},'outputs','B2P-VH(LF)(SN)','Both pins are actuator return. Two adequately sized parallel wires to engine ground star; never use sensor wires for injector return.')
add('J20','SHIELD_BOND','Connector_JST:JST_VH_B2P-VH_1x02_P3.96mm_Vertical',{1:'CHASSIS',2:'CHASSIS'},'core','B2P-VH(LF)(SN)','Shield/lining bond only. No normal load current. Short broad strap to enclosure conductive lining and designated chassis bond.')
add('C47','4.7n 100V',CFP,{1:'CHASSIS',2:'GND'},'core',note='RF coupling of shield and signal ground; not galvanic isolation.')
add('R151','1M',RFP,{1:'CHASSIS',2:'GND'},'core',note='Static bleed, not a protective earth bond.')
for i,sig in enumerate(['MAP','TPS','CLT','IAT','LAMBDA_WB','POSTCAT_BUF','CRANK_RAW','CAM_RAW']):
 add('C'+str(150+i),'100p C0G 100V' if i>=6 else '1n C0G 100V',CFP,{1:sig,2:'CHASSIS'},'analog' if i<6 else 'trigger_can',note='Cable-entry RF shunt to shield, before series input resistor. Validate edge delay and fault stress.')
add('H5','M3 SHIELD LUG','MountingHole:MountingHole_3.2mm_M3_Pad',{1:'CHASSIS'},'core',note='Conductive plated lug, bolt and short broad braid to enclosure side stud; not a signal-ground mounting point.')
# Small source series resistors slow board-level SPI edges without loading sensor signals.
for ref,pin,net in [('R152','18','SPI_CLK'),('R153','17','SPI_MOSI')]:
 by['U3'].pins[pin]=net+'_MCU';add(ref,'47R',RFP,{1:net+'_MCU',2:net},'core')
# Retain non-radio operation. DIP circuitry and THT passives are the only user-soldered parts.
assert len(by)==len(parts)
gen.OUT=O;gen.LIB=L;gen.PARTS=parts;gen.GPIO=gpio;gen.EXTRA_POWER_FLAGS=["VIN_FILTERED"]
# Copy only the two purchased module footprints; all other footprints are stock THT.
for name in ['ESP32_S3_DevKitC_1_socket','Pololu_D36V6F5_vertical']:
 shutil.copyfile(R/'hardware/a1-hand-solder/lib/ecu.pretty'/f'{name}.kicad_mod',L/'ecu.pretty'/f'{name}.kicad_mod')
# Radial PTC custom footprint with conservative body clearance.
(L/'ecu.pretty/PTC_MF_R010.kicad_mod').write_text('''(footprint "PTC_MF_R010" (version 20241229) (generator "esp32_ecu") (layer "F.Cu") (attr through_hole)
(property "Reference" "F?" (at 2.54 -4) (layer "F.SilkS") (effects (font (size 1 1))))
(property "Value" "PTC" (at 2.54 4) (layer "F.Fab") (effects (font (size 1 1))))
(fp_rect (start -1.6 -2) (end 6.7 2) (stroke (width .15) (type default)) (fill none) (layer "F.SilkS"))
(fp_rect (start -2.2 -2.7) (end 7.3 2.7) (stroke (width .05) (type default)) (fill none) (layer "F.CrtYd"))
(pad "1" thru_hole circle (at 0 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask"))
(pad "2" thru_hole circle (at 5.08 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask")))''')
for p in parts:
 if p.footprint.startswith('ECU:'):continue
 group,stem=p.footprint.split(':');src=gen.STOCK/'footprints'/f'{group}.pretty'/f'{stem}.kicad_mod'
 if not src.exists():raise RuntimeError('Missing footprint '+str(src))
 shutil.copyfile(src,L/'ecu.pretty'/src.name)
gen.schematic()
for path in O.glob('*.kicad_sch'):path.write_text(path.read_text().replace('A0','A2 THROUGH HOLE'))
flags=[Part('#FLG0'+str(i),'PWR_FLAG','ECU:unused',{'1':net},{},{'1':'power_out'},'power',(0,0)) for i,net in enumerate(['GND','VIN_PROT','+5V','VIN_FILTERED'],1)]
(L/'ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "esp32_ecu") '+'\n'.join(gen.symbol(p)[0] for p in parts+flags if p.pins)+')')
for typ in ['sym','fp']:
 uri='lib/ecu.kicad_sym' if typ=='sym' else 'lib/ecu.pretty';(O/f'{typ}-lib-table').write_text(f'({typ}_lib_table (lib (name "ECU") (type "KiCad") (uri "${{KIPRJMOD}}/{uri}") (options "") (descr "A2")))')
with (O/'bom.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Reference','Value','MPN','Footprint','DNP','Assembly','Note'])
 for p in parts:w.writerow([p.ref,p.value,p.mpn,p.footprint,p.dnp,'Purchased assembled module' if p.ref in ['U1','U3'] else 'Through hole',p.note])
with (O/'connector-pinout.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Connector','Label','PCB pin','Net','Mating housing'])
 for p in parts:
  if p.ref.startswith('J'):
   mate=f'XHP-{len(p.pins)}' if 'XH_' in p.footprint else f'VHR-{len(p.pins)}N' if 'VH_' in p.footprint else '2.54mm service header'
   w.writerows([p.ref,p.value,n,net,mate] for n,net in p.pins.items())
contract={'revision':'A2','status':'unrouted_not_for_fabrication','gpio':gpio,'parts':[vars(p) for p in parts]}
parser=argparse.ArgumentParser();parser.add_argument('--metadata',action='store_true');args=parser.parse_args()
if args.metadata:
 old=json.loads((O/'net_contract.json').read_text());contract['status']=old['status'];(O/'net_contract.json').write_text(json.dumps(contract,indent=2));print('A2 source metadata refreshed, routed board preserved');raise SystemExit
(O/'net_contract.json').write_text(json.dumps(contract,indent=2))
project={'meta':{'version':1},'board':{'design_settings':{'rules':{'min_clearance':.2,'min_track_width':.2,'min_copper_edge_clearance':.4,'min_through_hole_diameter':.3}}},'net_settings':gen.net_settings()}
(O/'esp32-ecu.kicad_pro').write_text(json.dumps(project,indent=2))
b=pcb.BOARD();b.SetCopperLayerCount(4);b.SetLayerType(pcb.In1_Cu,pcb.LT_POWER);b.GetDesignSettings().SetBoardThickness(pcb.FromMM(1.6))
nets={}
for net in sorted({net if net is not None else gen.nc_net(p,n) for p in parts for n,net in p.pins.items()}):
 n=pcb.NETINFO_ITEM(b,net);b.Add(n);nets[net]=n
fps={}
def pos(ref,x,y,a=0):
 f=fps[ref];f.SetPosition(pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y)));f.SetOrientationDegrees(a)
for p in parts:
 f=pcb.FootprintLoad(str(L/'ecu.pretty'),p.footprint.split(':')[1]);f.SetReference(p.ref);f.SetValue(p.value);f.SetFPID(pcb.LIB_ID('ECU',p.footprint.split(':')[1]));f.SetPath(pcb.KIID_PATH(f'/{gen.uid("root")}/{gen.uid(p.page)}/{gen.uid(p.ref)}'))
 for key,val in [('MPN',p.mpn),('DesignNote',p.note)]:f.SetField(key,val);f.GetField(key).SetVisible(False);f.GetField(key).SetLayer(pcb.F_Fab)
 if p.dnp:f.SetAttributes(f.GetAttributes()|pcb.FP_DNP)
 if p.ref.startswith('TP'):f.SetAttributes(f.GetAttributes() & ~pcb.FP_EXCLUDE_FROM_BOM)
 if p.ref.startswith('H') and not p.pins:f.SetAttributes(f.GetAttributes()|pcb.FP_BOARD_ONLY)
 if p.ref=='H5':f.SetAttributes(f.GetAttributes() & ~pcb.FP_BOARD_ONLY & ~pcb.FP_EXCLUDE_FROM_BOM)
 f.Value().SetVisible(False);f.Reference().SetLayer(pcb.F_Fab);f.Reference().SetVisible(not p.ref.startswith('H'));f.Reference().SetTextSize(pcb.VECTOR2I(pcb.FromMM(1),pcb.FromMM(1)))
 b.Add(f);fps[p.ref]=f
 actual=set()
 for pad in f.Pads():
  n=pad.GetNumber()
  if not n:continue
  actual.add(n);assert n in p.pins,(p.ref,n)
  pad.SetNet(nets[p.pins[n] if p.pins[n] is not None else gen.nc_net(p,n)])
 assert actual==set(p.pins),(p.ref,actual,set(p.pins))
# Fixed connector datums, separated sensor/Hall and actuator placement regions.
fixed={}
def fix(ref,x,y,a=0):pos(ref,x,y,a);fixed[ref]=True
fix('U3',20,46);fix('J1',18,23);fix('J19',180,18);fix('J20',72,18)
fix('H5',202,158);fix('J9',199,48,90);fix('J10',199,95,90);fix('J8',170,123)
fix('U8',70,108);fix('J7',73,131)
for ref,x,y,a in [('D1',18,32,0),('D2',44,27,180),('C1',48,50,0),('L2',54,36,0),('C2',68,36,0),('U1',66,48,0),('C46',60,43,0),('C45',82,36,0),('R150',80,48,0),('U2',62,64,0),('C9',74,66,0),('C5',84,62,0),('C6',56,76,0)]:fix(ref,x,y,a)
for i in range(8):fix('J'+str(11+i),20+23*i,198)
for ref,xy in zip(['H1','H2','H3','H4'],[(14,14),(206,14),(14,206),(206,206)]):fix(ref,*xy)
for i in range(1,5):fix('Q'+str(i),126+(i-1)*18,28)
for i in range(5,8):fix('Q'+str(i),132+(i-5)*21,109)
for i in range(6):
 x=18+23*i
 fix('R'+str(20+2*i),x,183);fix('R'+str(21+2*i),x,175);fix('C'+str(20+i),x+3,169)
 fix('D'+str(100+10*i),x,162);fix('D'+str(101+10*i),x+10,162);fix('C'+str(150+i),x+10,191)
for i in range(2):
 x=156+23*i;fix('R'+str(40+2*i),x,183);fix('C'+str(30+i),x+2,176)
 fix('D'+str(200+10*i),x,169);fix('D'+str(201+10*i),x+10,169);fix('C'+str(156+i),x+10,191)
# Reserve the antenna-end of the purchased module; no copper, tracks or parts in this area.
# Radios remain disabled. Conductive enclosure intentionally precludes RF use.
def bounds(f):
 items=[i.GetBoundingBox() for i in f.GraphicalItems() if i.GetLayer()==pcb.F_CrtYd]
 if not items:items=[i.GetBoundingBox() for i in f.Pads()]
 return tuple(v/1e6 for v in [min(i.GetX() for i in items),min(i.GetY() for i in items),max(i.GetRight() for i in items),max(i.GetBottom() for i in items)])
def overlap(a,c,gap=1.0):return a[0]<c[2]+gap and a[2]>c[0]-gap and a[1]<c[3]+gap and a[3]>c[1]-gap
occupied=[bounds(fps[r]) for r in fixed]
for i,a in enumerate(occupied):
 for c in occupied[i+1:]:
  if overlap(a,c,.2):raise RuntimeError('Fixed placement overlap '+str((a,c)))
def region(p):
 if p.ref in ['U4','U5','U9']:return (47,35,114,106)
 if p.page=='power':return (18,18,114,105)
 if p.page=='core':return (18,18,119,141)
 if p.page=='analog':return (18,132,151,158)
 if p.page=='trigger_can':return (52,98,198,163)
 return (108,35,192,155)
movable=[p for p in parts if p.ref not in fixed]
decouplers={'C10':('U2','2'),'C15':('U4','8'),'C16':('U5','2'),'C28':('U6','16'),'C32':('U7','14'),'C33':('U8','3'),'C34':('U8','5'),'C35':('U9','14'),'C36':('U10','14'),'C37':('U11','14'),'C38':('U12','16'),'C39':('U13','16'),'C40':('U14','16'),'C41':('U15','16'),'C42':('U16','14'),'C43':('U17','14')}
movable.sort(key=lambda p: (0 if p.ref.startswith('U') else 1 if p.ref in decouplers else 2,-(bounds(fps[p.ref])[2]-bounds(fps[p.ref])[0])*(bounds(fps[p.ref])[3]-bounds(fps[p.ref])[1])))
for p in movable:
 f=fps[p.ref];x0,y0,x1,y1=region(p);desired=((x0+x1)/2,(y0+y1)/2)
 if p.ref=='U6':desired=(75,140)
 if p.ref=='U7':desired=(162,146)
 if p.ref in decouplers:
  ic,pin=decouplers[p.ref];pad=next(pad for pad in fps[ic].Pads() if pad.GetNumber()==pin);desired=(pad.GetPosition().x/1e6,pad.GetPosition().y/1e6)
  x0,y0,x1,y1=16,20,196,158
 candidates=[(x,y,a) for a in [0,90] for x in range(x0,x1,2) for y in range(y0,y1,2)]
 candidates.sort(key=lambda v:(v[0]-desired[0])**2+(v[1]-desired[1])**2+(.1 if v[2] else 0))
 for x,y,a in candidates:
  pos(p.ref,x,y,a);bb=bounds(f)
  if bb[0]<x0 or bb[1]<y0 or bb[2]>x1 or bb[3]>y1:continue
  if any(overlap(bb,c) for c in occupied):continue
  occupied.append(bb);break
 else:raise RuntimeError('No placement room for '+p.ref)
for a,c in [((10,10),(210,10)),((210,10),(210,210)),((210,210),(10,210)),((10,210),(10,10))]:
 s=pcb.PCB_SHAPE();s.SetShape(pcb.SHAPE_T_SEGMENT);s.SetStart(pcb.VECTOR2I(pcb.FromMM(a[0]),pcb.FromMM(a[1])));s.SetEnd(pcb.VECTOR2I(pcb.FromMM(c[0]),pcb.FromMM(c[1])));s.SetLayer(pcb.Edge_Cuts);s.SetWidth(pcb.FromMM(.05));b.Add(s)
z=pcb.ZONE(b);z.SetLayer(pcb.In1_Cu);z.SetNet(nets['GND']);z.SetLocalClearance(pcb.FromMM(.3));z.SetPadConnection(pcb.ZONE_CONNECTION_THERMAL);z.SetThermalReliefGap(pcb.FromMM(.3));z.SetThermalReliefSpokeWidth(pcb.FromMM(.5));z.Outline().NewOutline()
for x,y in [(10.5,10.5),(209.5,10.5),(209.5,209.5),(10.5,209.5)]:z.Outline().Append(pcb.FromMM(x),pcb.FromMM(y))
b.Add(z)
# Local chassis copper at the sensor bank provides a short RF return to H5.
z=pcb.ZONE(b);z.SetLayer(pcb.B_Cu);z.SetNet(nets['CHASSIS']);z.SetLocalClearance(pcb.FromMM(.5));z.SetPadConnection(pcb.ZONE_CONNECTION_THERMAL);z.SetThermalReliefGap(pcb.FromMM(.3));z.SetThermalReliefSpokeWidth(pcb.FromMM(.5));z.Outline().NewOutline()
for x,y in [(12,187),(198,187),(198,145),(208,145),(208,208),(12,208)]:z.Outline().Append(pcb.FromMM(x),pcb.FromMM(y))
b.Add(z)
# Preserve a copper keepout under the module PCB antenna, bounded outside pin rows.
k=pcb.ZONE(b);k.SetIsRuleArea(True);layers=pcb.LSET.AllCuMask();k.SetLayerSet(layers);k.SetDoNotAllowTracks(True);k.SetDoNotAllowVias(True);k.SetDoNotAllowZoneFills(True);k.Outline().NewOutline()
for x,y in [(18,36),(45,36),(45,43),(18,43)]:k.Outline().Append(pcb.FromMM(x),pcb.FromMM(y))
b.Add(k)
# Decoupling capacitors are placed by the packing stage; verify and refine their loop lengths before release.
def label(t,x,y,size=.85):
 s=pcb.PCB_TEXT(b);s.SetText(t);s.SetPosition(pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y)));s.SetTextSize(pcb.VECTOR2I(pcb.FromMM(size),pcb.FromMM(size)));s.SetTextThickness(pcb.FromMM(.12));s.SetLayer(pcb.F_SilkS);b.Add(s)
for i in range(8):label(by['J'+str(11+i)].value+'\n1:G 2:5V 3:S',22.5+23*i,205,.8)
label('A2 THROUGH HOLE / SOCKETED ESP32-S3',104,15,1.1)
# Short wide injector source return to a dedicated engine-ground connector.
def ground_track(a,c):
 t=pcb.PCB_TRACK(b);t.SetStart(pcb.VECTOR2I(pcb.FromMM(a[0]),pcb.FromMM(a[1])));t.SetEnd(pcb.VECTOR2I(pcb.FromMM(c[0]),pcb.FromMM(c[1])));t.SetWidth(pcb.FromMM(2.5));t.SetLayer(pcb.F_Cu);t.SetNet(nets['GND']);b.Add(t)
ground_track((131.08,18),(185.08,18))
for i in range(4):ground_track((131.08+18*i,28),(131.08+18*i,18))
# Write actual placements to manifest; source xy is not a placement authority.
for p in parts:
 f=fps[p.ref];contract['parts'][next(i for i,d in enumerate(contract['parts']) if d['ref']==p.ref)]['placed_xy_mm']=[f.GetPosition().x/1e6,f.GetPosition().y/1e6]
pcb.SaveBoard(str(O/'esp32-ecu.kicad_pcb'),b);(O/'net_contract.json').write_text(json.dumps(contract,indent=2))
print('Generated A2:',len(parts),'through-hole parts/modules; routing and review required')
