#!/usr/bin/env python3
"""Create a separate SW2-J4-DRAFT1 THT prototype. No carrier/archive edits.

Run with KiCad9 Python. Routing, ERC/DRC and physical qualification are separate.
"""
import argparse,csv,hashlib,json
from pathlib import Path
import pcbnew as pcb
import build_hardware as builder
from design import Part
from kicad9_carrier_copy import footprint_copy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/switch-inputs'
PARTS=[]
RFP='R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical'
CFP='C_Disc_D5.0mm_W2.5mm_P5.00mm'
def part(ref,value,fp,pins,xy,names=None,types=None,mpn='',note='',angle=0):
 PARTS.append(Part(ref,value,'ECU:'+fp,{str(k):v for k,v in pins.items()},
  {str(k):v for k,v in (names or {}).items()},{str(k):v for k,v in (types or {}).items()},
  'switches',xy,angle,mpn,note))

part('J1','INTERNAL J4 LINK','JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical',
 {1:'GND',2:'+3V3',3:'SDA_CARRIER',4:'SCL_CARRIER'},(21,23),
 {1:'GND',2:'3V3',3:'SDA GPIO41',4:'SCL GPIO42'},
 {1:'power_out',2:'power_out',3:'bidirectional',4:'bidirectional'},'B4B-XH-A(LF)(SN)',
 'Short internal harness only. Carrier J4 pin5 SAFE_N has NO wire/contact on this accessory. One explicit I2C owner; no other device at0x20.')
part('J2','DRY CONTACTS ONLY','JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical',
 {1:'SW0',2:'GND',3:'SW1',4:'GND'},(72,22),
 {1:'SW0',2:'RETURN0',3:'SW1',4:'RETURN1'},mpn='B4B-XH-A(LF)(SN)',
 note='Each low-current dry contact closes SW to its own return. No external supply, Hall/pulse or safety-interlock role. Open wire=open; short to return=closed. Use dry-circuit contacts.')
part('U1','MCP23008-E/P','DIP-18_W7.62mm_LongPads',
 {1:'SCL',2:'SDA',3:'GND',4:'GND',5:'GND',6:'RESET_N',7:None,8:None,9:'GND',
  10:'GP0',11:'GP1',12:'GP2',13:'GP3',14:'GP4',15:'GP5',16:'GP6',17:'GP7',18:'+3V3'},(45,27),
 {1:'SCL',2:'SDA',3:'A2',4:'A1',5:'A0',6:'RESET_N',7:'NC',8:'INT_NC',9:'VSS',
  10:'GP0',11:'GP1',12:'GP2',13:'GP3',14:'GP4',15:'GP5',16:'GP6',17:'GP7 OUTPUT ONLY',18:'VDD'},
 {1:'input',2:'bidirectional',3:'input',4:'input',5:'input',6:'input',8:'open_collector',9:'power_in',
  10:'input',11:'input',12:'input',13:'input',14:'input',15:'input',16:'input',17:'output',18:'power_in'},
 'MCP23008-E/P','Direct solder PDIP18, no socket. Address0x20. DS20001919I pinout; GP7 output only. Marker is behavior/readback, not unique identity.')
part('U2','MCP121-300E/TO','TO-92_Inline_Wide',{1:'RESET_N',2:'+3V3',3:'GND'},(24,47),
 {1:'RESET_N OPEN DRAIN',2:'VDD',3:'VSS'},{1:'open_collector',2:'power_in',3:'power_in'},
 'MCP121-300E/TO','Prototype supervisor. Open-drain10k pullup. Trip2.857..3.003V; release80..180ms under specified conditions. Leakage max, hysteresis over temperature, rail ramps and actual loaded RESET levels remain characterization holds.')
for channel,xy in [(0,(73,35)),(1,(73,52))]:
 part('Q'+str(channel+1),'2N3904BU','TO-92_Inline_Wide',
  {1:'GND',2:f'BASE{channel}',3:f'COL{channel}'},xy,
  {1:'EMITTER',2:'BASE',3:'COLLECTOR'},mpn='2N3904BU',
  note='onsemi E-B-C bondout only, manually formed2.54mm leads. Open contact drives low; closed reads high. Sub-mA saturation/cutoff, temperature and power-off injection need physical characterization.')
for ref,a,k,xy in [('D1','+3V3','BIAS0',(58.5,26)),('D2','+3V3','BIAS1',(58.5,56)),
 ('D3','GND','BASE0',(62.5,21)),('D4','GND','BASE1',(62.5,52))]:
 part(ref,'1N4148-TAP','D_DO-35_SOD27_P3.81mm_Vertical_AnodeUp',{1:k,2:a},xy,
  {1:'K BAND',2:'A'},mpn='1N4148-TAP',note='Feed diode or reverse-BE clamp; NOT a guarantee of zero backfeed. Band/cathode is pad1; verify purchased part and assembly.')
resistors=[
 ('R1',2200,'BIAS0','SW0',(65,26)),('R2',2200,'BIAS1','SW1',(65,56)),
 ('R3',4990,'SW0','MID0',(65,32)),('R4',4990,'MID0','BASE0',(65,37.5)),
 ('R5',4990,'SW1','MID1',(65,61.5)),('R6',4990,'MID1','BASE1',(72,65)),
 ('R7',100000,'BASE0','GND',(74,29)),('R8',100000,'BASE1','GND',(74,46.5)),
 ('R9',4700,'+3V3','COL0',(81,35)),('R10',4700,'+3V3','COL1',(81,52)),
 ('R11',1000,'COL0','GP0',(63,42)),('R12',1000,'COL1','GP1',(63,47.5)),
 ('R13',10000,'GP2','GND',(56,30)),('R14',10000,'GP3','+3V3',(56,35.5)),
 ('R15',10000,'GP4','GND',(56,41)),('R16',10000,'GP5','+3V3',(56,46.5)),
 ('R17',1000,'GP7','GP6',(56,22.5)),('R18',100000,'GP6','GND',(56,52)),
 ('R19',10000,'RESET_N','+3V3',(32,47)),('R20',1000,'+3V3','GND',(21,41)),
 ('R21',100,'SDA_CARRIER','SDA',(34,22)),('R22',100,'SCL_CARRIER','SCL',(34,28))]
def resistance_code(value):
 for exponent in range(7):
  digits=value/(10**exponent)
  if 100<=digits<1000 and digits==int(digits):return str(int(digits))+str(exponent)
 raise ValueError(value)
for ref,value,a,b,xy in resistors:
 part(ref,f'{value}R 1% 0.6W',RFP,{1:a,2:b},xy,mpn='MRS25000C'+resistance_code(value)+'FCT00',
  note='Vishay MRS25 ordering-code candidate, availability/packing unverified. P70=0.6W with film-temperature limits; upright body may be6.5mm tall. Fault/rail thermal and actual formed-lead fit unqualified.'+
  (' Mandatory local bleeder, not proof of zero backfeed.' if ref=='R20' else ''))
for ref,value,net,xy,angle in [('C1','100nF 50V','+3V3',(52.62,23),180),('C2','100nF 50V','+3V3',(24,52),0),
 ('C3','10nF 50V','COL0',(74,42),0),('C4','10nF 50V','COL1',(74,59),0)]:
 part(ref,value,CFP,{1:net,2:'GND'},xy,angle=angle,
  note='Leaded ceramic candidate: P5mm, body<=D5/W2.5mm envelope. Exact part and bias/temp/assembly fit pending; no SMD. Collector RC is filtering, not continuity detection.')
part('C5','10uF 16V','CP_Radial_D8.0mm_P3.50mm',{1:'+3V3',2:'GND'},(21,35),
 {1:'PLUS',2:'MINUS'},note='Leaded radial local bulk. Exact D8/P3.5 part, leakage/ESR/temperature and physical fit pending.')
for n,xy in enumerate([(14,14),(86,14),(14,66),(86,66)],1):
 part('H'+str(n),'M3 INSULATED MOUNT','MountingHole_3.2mm_M3',{},xy,note='Unplated3.2mm. Insulating spacers; separate80x60mm accessory fit/clearance unmeasured.')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--replace-generated',action='store_true');args=parser.parse_args()
 if (OUT/'switches.kicad_pcb').exists() and not args.replace_generated:raise SystemExit('Draft exists; inspect before --replace-generated.')
 lib=OUT/'lib';fps=lib/'ecu.pretty';fps.mkdir(parents=True,exist_ok=True);origins={}
 for name in sorted({p.footprint.split(':')[1] for p in PARTS}):
  if name=='DIP-18_W7.62mm_LongPads':
   source=ROOT/'.cache/engine/switch-inputs/reference'/f'{name}.kicad_mod'
   origin=json.loads((source.parent/'dip18-source.json').read_text())
  else:
   source=ROOT/'hardware/a4-n16r8/lib/ecu.pretty'/f'{name}.kicad_mod';origin={'source':str(source.relative_to(ROOT))}
  original=source.read_bytes();data,omitted=footprint_copy(original);(fps/f'{name}.kicad_mod').write_bytes(data)
  origins[name]={**origin,'source_sha256':hashlib.sha256(original).hexdigest(),'copy_sha256':hashlib.sha256(data).hexdigest(),'omitted_metadata':omitted}
 (lib/'NOTICE.md').write_text('Footprints are copied from the project’s existing KiCad library copies, except DIP18 from the pinned official KiCad GitHub archive. Source/copy hashes and the DIP18 commit/URL are in ../footprint-provenance.json. See https://www.kicad.org/libraries/license/ for the KiCad library license and exception. Unsupported KiCad10 false-jumper/construction metadata is omitted for Linux KiCad9; pad/copper/courtyard geometry is retained. Referenced3D models are not verified assemblies. Symbols are generated by scripts/build_hardware.py and exact manufacturer pin maps remain a physical procurement/assembly check. No original carrier/library source is modified.\n')
 builder.OUT,builder.LIB,builder.PARTS=OUT,lib,PARTS
 builder.NOTES={'switches':'SW2-J4-DRAFT1 / HOLD / NO FABRICATION. Inhibited bench prototype. J4 pin5 SAFE_N has NO connection. Two-wire contacts cannot prove continuity. Electrical, power/reset, supply/thermal, timing and enclosure tests open.'}
 builder.write_sheet('switches');sheet=OUT/'switches.kicad_sch'
 text=sheet.read_text().replace('ESP32 ECU A0 / switches','Protected switch accessory SW2-J4-DRAFT1').replace('2026-10-30','2026-11-04').replace('A0 BENCH','SW2-J4-DRAFT1')
 text=text.replace('/'+builder.uid('root')+'/'+builder.uid('switches'),'/'+builder.uid('switches'))
 sheet.write_text(text[:-1]+'(sheet_instances (path "/" (page "1"))))')
 (lib/'ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "esp32_ecu_sw2")\n'+'\n'.join(builder.symbol(p)[0] for p in PARTS if p.pins)+')')
 for kind in ('fp','sym'):
  uri='${KIPRJMOD}/lib/'+('ecu.pretty' if kind=='fp' else 'ecu.kicad_sym')
  (OUT/(kind+'-lib-table')).write_text(f'({kind}_lib_table (version7) (lib (name "ECU") (type "KiCad") (uri "{uri}") (options "") (descr "Leaded prototype copies")))'.replace('(version7)','(version 7)'))
 board=pcb.BOARD();board.SetCopperLayerCount(2);board.GetDesignSettings().SetBoardThickness(pcb.FromMM(1.6));nets={}
 for net in sorted({v if v is not None else builder.nc_net(p,k) for p in PARTS for k,v in p.pins.items()}):nets[net]=pcb.NETINFO_ITEM(board,net);board.Add(nets[net])
 for p in PARTS:
  fp=pcb.FootprintLoad(str(fps),p.footprint.split(':')[1]);assert fp is not None,p.footprint
  fp.SetReference(p.ref);fp.SetValue(p.value);fp.SetFPID(pcb.LIB_ID('ECU',p.footprint.split(':')[1]));fp.SetPath(pcb.KIID_PATH('/'+builder.uid('switches')+'/'+builder.uid(p.ref)))
  fp.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in p.xy)));fp.SetOrientationDegrees(p.angle);board.Add(fp)
  fp.Reference().SetLayer(pcb.F_Fab);fp.Value().SetVisible(False)
  if p.ref.startswith('H'):fp.SetAttributes(fp.GetAttributes()|pcb.FP_BOARD_ONLY)
  for pad in fp.Pads():
   key=pad.GetNumber()
   if key:assert key in p.pins;pad.SetNet(nets[p.pins[key] if p.pins[key] is not None else builder.nc_net(p,key)])
 for a,b in [((10,10),(90,10)),((90,10),(90,70)),((90,70),(10,70)),((10,70),(10,10))]:
  line=pcb.PCB_SHAPE();line.SetShape(pcb.SHAPE_T_SEGMENT);line.SetStart(pcb.VECTOR2I(*(pcb.FromMM(v) for v in a)));line.SetEnd(pcb.VECTOR2I(*(pcb.FromMM(v) for v in b)));line.SetLayer(pcb.Edge_Cuts);line.SetWidth(pcb.FromMM(.05));board.Add(line)
 for value,xy in [('SW2-J4-DRAFT1 / HOLD',(50,12)),('J4 PIN5 NO WIRE',(32,66)),('CLOSED = HIGH',(63,68))]:
  text=pcb.PCB_TEXT(board);text.SetText(value);text.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(v) for v in xy)));text.SetTextSize(pcb.VECTOR2I(pcb.FromMM(1),pcb.FromMM(1)));text.SetTextThickness(pcb.FromMM(.15));text.SetLayer(pcb.F_SilkS);board.Add(text)
 pcb.SaveBoard(str(OUT/'switches.kicad_pcb'),board)
 (OUT/'switches.kicad_pro').write_text(json.dumps({'meta':{'filename':'switches.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':.3,'min_track_width':.3,'min_copper_edge_clearance':.5}}}},indent=2)+'\n')
 contract=dict(revision='SW2-J4-DRAFT1',status='PLACEMENT_NETLIST_HOLD_NOT_FOR_FABRICATION',board_mm=[80,60],copper_layers=2,physical_qualification=False,
  carrier_harness={'carrier':'J4','pins':{'1':'GND','2':'+3V3','3':'SDA_CARRIER','4':'SCL_CARRIER'},'pin5':'SAFE_N: no wire/contact; NOT an accessory signal'},
  acquisition={'address':32,'bus_hz':100000,'marker_mask':60,'marker_value':40,'loopback':['GP7','GP6'],'raw_high':'closed contact','wire_continuity_detection':False},
  supply={'rail':'+3V3','additional_headroom_measured':False,'carrier_200mA_target':'total provisional thermal target, not accessory headroom','simultaneous_carrier_and_module_USB_power':False},
  parts=[dict(reference=p.ref,value=p.value,footprint=p.footprint,pins=p.pins,pin_names=p.names,pin_types=p.types,mpn=p.mpn,note=p.note,placed_xy_mm=p.xy,placed_angle_deg=p.angle,fitted=not p.ref.startswith('H'))for p in PARTS])
 (OUT/'net_contract.json').write_text(json.dumps(contract,indent=2)+'\n');(OUT/'footprint-provenance.json').write_text(json.dumps(origins,indent=2)+'\n')
 with (OUT/'bom.csv').open('w',newline='')as f:
  w=csv.writer(f,lineterminator='\n');w.writerow(['Reference','Value','MPN candidate','Footprint','Qualification / procurement']);w.writerows((p.ref,p.value,p.mpn,p.footprint,p.note)for p in PARTS)
 print(json.dumps({'created':'SW2-J4-DRAFT1','footprints':len(PARTS),'board_mm':[80,60],'physical_qualification':False}))
if __name__=='__main__':main()
