#!/usr/bin/env python3
"""Create a separate THT idle accessory placement/netlist draft, never A3/A4.

Run with /usr/bin/python3 (KiCad pcbnew). Copper is deliberately not released:
the actual valve, protection branch, eFuse routing and enclosure are unmeasured.
Use --replace-generated only after inspecting edits to this generated draft.
"""
import argparse,csv,json,shutil,sys,hashlib,re
from pathlib import Path
import pcbnew as pcb
from design import Part
import build_hardware as b

R=Path(__file__).resolve().parents[1]
OUT=R/'hardware/idle-accessory'
parts=[]
def part(ref,value,fp,pins,xy,names=None,types=None,mpn='',note=''):
 p=Part(ref,value,'ECU:'+fp,{str(k):v for k,v in pins.items()},{str(k):v for k,v in (names or {}).items()},{str(k):v for k,v in (types or {}).items()},'idle',xy,mpn=mpn,note=note);parts.append(p);return p

part('J1','CARRIER LOGIC ONLY','JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical',{1:'GPIO3',2:'RUN_5V',3:'+5V_LOGIC',4:'GND'},(20,22),{1:'GPIO3 / U3 pad13',2:'RUN_5V / TP6',3:'+5V',4:'GND'},{1:'output',2:'output',3:'power_out',4:'power_out'},'B4B-XH-A(LF)(SN)','Carrier take-offs require a reviewed harness; no native carrier connector exists')
part('J2','PROTECTED ACTUATOR SUPPLY','TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal',{1:'IAC_12V_PROTECTED',2:'GND'},(74,48),{1:'EXTERNAL FUSED SWITCHED +12V',2:'POWER RETURN'},{1:'power_out',2:'power_in'},'1715721','Fixed screw supply entry cannot accept J3 valve plug; 9–16V, externally fused <=2A load contract; reverse/transient protection is external; verify torque/strain relief')
part('J3','NC PWM VALVE','JST_VH_B2P-VH_1x02_P3.96mm_Vertical',{1:'IAC_12V_PROTECTED',2:'IAC_LS'},(76,19),{1:'VALVE +',2:'VALVE LOW SIDE'},mpn='B2P-VH(LF)(SN)',note='Two-wire continuous-duty NC energize-to-open only; verify polarity and R/L')
part('U1','UCC27524P','DIP-8_W7.62mm_LongPads',{1:'ENA',2:'INA',3:'GND',4:'GND',5:None,6:'+5V_LOGIC',7:'DRIVE_A',8:'GND'},(40,30),{1:'ENA',2:'INA',3:'GND',4:'INB',5:'OUTB_NC',6:'VDD',7:'OUTA',8:'ENB'},{1:'input',2:'input',3:'power_in',4:'input',5:'output',6:'power_in',7:'output',8:'input'},'UCC27524P.B','Direct solder PDIP8, no socket; input-independent VDD and UVLO; external EN pulldown mandatory')
part('Q1','VNP35N07-E','TO-220-3_Vertical',{1:'SWITCH_INPUT',2:'IAC_LS',3:'GND'},(65,40),{1:'INPUT',2:'DRAIN / LIVE TAB',3:'SOURCE'},{1:'input',2:'passive',3:'power_in'},'VNP35N07-E','TO220 metal tab is IAC_LS, insulate from case/mounting hardware; thermal/current tests pending')
part('D1','SB5H100-E3','D_DO-201AD_P15.24mm_Horizontal',{1:'IAC_12V_PROTECTED',2:'IAC_LS'},(65,28.5),{1:'K / BAND',2:'A'},mpn='SB5H100-E3/54',note='Axial DO201AD 100V 5A candidate; flyback cathode to valve positive, anode to low side')
rfp='R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical'
for ref,value,n1,n2,xy,note in [
 ('R1','1k','GPIO3','INA',(30,29),'GPIO input series'),('R2','2k2','GPIO3','GND',(23,34),'GPIO-side reset pulldown, not after R1'),
 ('R3','1k','RUN_5V','ENA',(35,20),'Hardware enable series'),('R4','4k7','ENA','GND',(35,26),'Mandatory ENA pulldown overrides driver internal pullup'),
 ('R5','10k','INA','GND',(33,37),'Local driver input pulldown'),('R6','220R','DRIVE_A','SWITCH_INPUT',(54,30),'Smart-switch input series'),
 ('R7','10k','SWITCH_INPUT','GND',(61,47),'Switch input pulldown')]:part(ref,value,rfp,{1:n1,2:n2},xy,note=note+'; exact leaded part/power/height procurement pending')
part('C1','100nF','C_Disc_D5.0mm_W2.5mm_P5.00mm',{1:'+5V_LOGIC',2:'GND'},(51,37),note='Local VDD decoupling; leaded ceramic 10V+; exact part/fit pending')
part('C2','1uF','C_Rect_L7.2mm_W5.0mm_P5.00mm',{1:'+5V_LOGIC',2:'GND'},(41,45),note='Local VDD decoupling; leaded nonpolar film 10V+ candidate envelope; exact part/fit pending')
for i,xy in enumerate(((14,14),(86,14),(14,56),(86,56)),1):part('H'+str(i),'M3 MOUNT','MountingHole_3.2mm_M3',{},xy,note='Screw mounted accessory; case location/stand-offs/clearance not finalized')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replace-generated',action='store_true');a=p.parse_args()
 if OUT.exists() and any(OUT.iterdir()) and not a.replace_generated:raise SystemExit('Draft exists; inspect git diff before explicit --replace-generated')
 lib=OUT/'lib';footprints=lib/'ecu.pretty';footprints.mkdir(parents=True,exist_ok=True)
 footprint_sources={}
 for item in parts:
  stem=item.footprint.split(':')[1];src=R/'hardware/a4-n16r8/lib/ecu.pretty'/(stem+'.kicad_mod')
  if item.ref=='J2':
   entry=OUT/'terminal-source.json';origin=json.loads(entry.read_text());src=footprints/(stem+'.kicad_mod');data=src.read_bytes()
   assert hashlib.sha256(data).hexdigest()==origin['sha256']
   footprint_sources[stem]=origin;continue
  data=src.read_bytes();adapted=data.replace(b'(version 20260206)',b'(version 20241229)').replace(b'\t(duplicate_pad_numbers_are_jumpers no)\n',b'')
  adapted=re.sub(rb'\n\t\(point\n(?:\t\t[^\n]*\n)*\t\)',b'',adapted)
  # Archived libraries came from KiCad10 on the Mac. These ordinary THT
  # footprints use the common syntax; only this new copy's format declaration
  # is adapted, then the native9 loader must accept it. Old files stay intact.
  (footprints/src.name).write_bytes(adapted)
  footprint_sources[stem]=dict(source=str(src.relative_to(R)),sha256=hashlib.sha256(data).hexdigest(),new_copy_sha256=hashlib.sha256(adapted).hexdigest(),adaptation='format declaration20260206 to20241229; drop explicit false duplicate-pad jumper metadata; omit KiCad10 construction point metadata; pad/copper/courtyard geometry unchanged; accepted by native KiCad9 loader')
 shutil.copy2(R/'hardware/a4-n16r8/lib/NOTICE.md',lib/'NOTICE.md')
 with (lib/'NOTICE.md').open('a') as f:f.write('\nAccessory copies adapt KiCad10 format declarations, false duplicate-pad metadata and construction points for KiCad9. Pad/copper/courtyard geometry is retained; hashes are in ../footprint-provenance.json. The Phoenix terminal comes from the pinned official commit in ../terminal-source.json. Archived A3/A4 sources are unchanged. Referenced3D paths are not a verified assembly.\n')
 b.OUT=OUT;b.LIB=lib;b.PARTS=parts;b.NOTES={'idle':'IDLE ACCESSORY DRAFT / NOT FOR FABRICATION. GPIO3 JTAG strap requires actual eFuse routing read, no burns. External protected fused actuator power. Hardware RUN_5V disables drive. No physical validation.'}
 b.write_sheet('idle')
 sheet=OUT/'idle.kicad_sch';s=sheet.read_text().replace('ESP32 ECU A0 / idle','ESP32 ECU idle accessory / placement draft').replace('2026-10-30','2026-11-04').replace('A0 BENCH','IAC-DRAFT1')
 # Standalone root path rather than a child of the archived ECU A0 project.
 s=s.replace('/'+b.uid('root')+'/'+b.uid('idle'),'/'+b.uid('idle'));s=s[:-1]+'(sheet_instances (path "/" (page "1"))))';sheet.write_text(s)
 (lib/'ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "esp32_ecu_idle")\n'+'\n'.join(b.symbol(x)[0] for x in parts if x.pins)+')')
 (OUT/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "ECU") (type "KiCad") (uri "${KIPRJMOD}/lib/ecu.pretty") (options "") (descr "Vendored THT footprints")))')
 (OUT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "ECU") (type "KiCad") (uri "${KIPRJMOD}/lib/ecu.kicad_sym") (options "") (descr "Explicit accessory pin contracts")))')
 board=pcb.BOARD();board.SetCopperLayerCount(2);board.GetDesignSettings().SetBoardThickness(pcb.FromMM(1.6))
 nets={}
 for net in sorted({v if v is not None else b.nc_net(x,k) for x in parts for k,v in x.pins.items()}):
  n=pcb.NETINFO_ITEM(board,net);board.Add(n);nets[net]=n
 for item in parts:
  fp=pcb.FootprintLoad(str(footprints),item.footprint.split(':')[1]);assert fp is not None,item.footprint
  fp.SetReference(item.ref);fp.SetValue(item.value);fp.SetFPID(pcb.LIB_ID('ECU',item.footprint.split(':')[1]));fp.SetPath(pcb.KIID_PATH('/'+b.uid('idle')+'/'+b.uid(item.ref)))
  fp.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(x) for x in item.xy)));fp.Value().SetVisible(False)
  fp.Reference().SetTextSize(pcb.VECTOR2I(pcb.FromMM(.9),pcb.FromMM(.9)));fp.Reference().SetTextThickness(pcb.FromMM(.15))
  if item.ref.startswith('H'):fp.SetAttributes(fp.GetAttributes()|pcb.FP_BOARD_ONLY);fp.Reference().SetVisible(False)
  for pad in fp.Pads():
   num=pad.GetNumber()
   if not num:continue
   assert num in item.pins
   pad.SetNet(nets[item.pins[num] if item.pins[num] is not None else b.nc_net(item,num)])
  board.Add(fp)
 for a,z in [((10,10),(90,10)),((90,10),(90,60)),((90,60),(10,60)),((10,60),(10,10))]:
  e=pcb.PCB_SHAPE();e.SetShape(pcb.SHAPE_T_SEGMENT);e.SetStart(pcb.VECTOR2I(*(pcb.FromMM(x) for x in a)));e.SetEnd(pcb.VECTOR2I(*(pcb.FromMM(x) for x in z)));e.SetLayer(pcb.Edge_Cuts);e.SetWidth(pcb.FromMM(.05));board.Add(e)
 for label,xy in [('IAC DRAFT1 / UNROUTED / NO FAB',(50,12)),('NC VALVE / <=2A / EXTERNAL FUSE',(50,58))]:
  t=pcb.PCB_TEXT(board);t.SetText(label);t.SetPosition(pcb.VECTOR2I(*(pcb.FromMM(x) for x in xy)));t.SetTextSize(pcb.VECTOR2I(pcb.FromMM(1),pcb.FromMM(1)));t.SetTextThickness(pcb.FromMM(.15));t.SetLayer(pcb.F_SilkS);board.Add(t)
 pcb.SaveBoard(str(OUT/'idle.kicad_pcb'),board)
 project={'meta':{'filename':'idle.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':.3,'min_track_width':.3,'min_copper_edge_clearance':.5}}}}
 (OUT/'idle.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
 manifest=dict(revision='IAC-DRAFT1',status='unrouted_placement_and_netlist_draft_not_for_fabrication',board_mm=[80,50],layers=2,mounting='4x M3, 3.2mm holes, 72x42mm centres',physical_default=False,gpio=3,u3_socket_pad13='NC in archived A4 carrier, requires separate take-off',parts=[dict(reference=x.ref,value=x.value,footprint=x.footprint,mpn=x.mpn,pins=x.pins,pin_names=x.names,note=x.note) for x in parts])
 (OUT/'net_contract.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (OUT/'footprint-provenance.json').write_text(json.dumps(footprint_sources,indent=2)+'\n')
 with (OUT/'bom.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['Reference','Value','MPN candidate','Footprint','Qualification / procurement']);w.writerows((x.ref,x.value,x.mpn,x.footprint,x.note) for x in parts)
 print('Wrote separate 80x50mm through-hole accessory placement/netlist draft; copper and fit are pending')

if __name__=='__main__':main()
