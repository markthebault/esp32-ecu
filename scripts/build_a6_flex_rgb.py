#!/usr/bin/env python3
"""Create a new120mm A6 flex/RGB native draft, preserving the A5 source.

KiCad9 Python required. Never flashes or exports manufacturing files. A fresh
output is mandatory; routing/native checks and physical qualification are separate.
"""
import argparse,csv,hashlib,json,re,shutil
from dataclasses import asdict,fields
from pathlib import Path
import pcbnew as pcb
import build_hardware as builder
from build_a5_idle_interface import place
from design import Part
from kicad9_carrier_copy import chunks,footprint_copy
from route_a5_idle_interface import geometry
from pack_a6 import pack
from place_a6_back import place_back

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'hardware/a5-idle-interface'
FRONT=ROOT/'hardware/flex-input/frontend.json'
LED=ROOT/'hardware/flex-input/status-led.json'
RFP='R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical'
CFP='C_Disc_D5.0mm_W2.5mm_P5.00mm'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def resistance_code(v):
 for exponent in range(7):
  digits=v/(10**exponent)
  if 100<=digits<1000 and digits==int(digits):return str(int(digits))+str(exponent)
 raise ValueError(v)

def convert(row,page):
 ref=row['ref'];names={};types={}
 if 'mounting'in row:fp=row['mounting']['footprint']
 elif ref.startswith('R'):fp=RFP
 elif ref=='C163':fp='CP_Radial_D8.0mm_P3.50mm';names={'1':'PLUS','2':'MINUS'}
 elif ref.startswith('C'):fp=CFP
 elif ref.startswith('D'):fp='D_DO-35_SOD27_P3.81mm_Vertical_AnodeUp';names={'1':'K BAND','2':'A'}
 elif ref.startswith('Q'):fp='TO-92_Inline_Wide';names={'1':'EMITTER','2':'BASE','3':'COLLECTOR'}
 elif ref=='F3':fp='PTC_MF_R010'
 elif ref=='J22':fp='JST_VH_B3P-VH_1x03_P3.96mm_Vertical';names={'1':'RETURN','2':'SENSOR9..18V HOLD','3':'FREQUENCY LOW PULSE'}
 elif ref=='J23':fp='JST_PH_B5B-PH-K_1x05_P2.00mm_Vertical';names={'1':'COMMON ANODE LIMITED5V','2':'RED CATHODE','3':'GREEN CATHODE','4':'BLUE CATHODE','5':'NC_NO_CONTACT'}
 elif ref=='U18':
  fp='DIP-8_W7.62mm_LongPads';names={'1':'OUT1 OC','2':'IN1-','3':'IN1+','4':'GND','5':'IN2+','6':'IN2-','7':'OUT2_NC','8':'VCC'}
  types={'1':'open_collector','2':'input','3':'input','4':'power_in','5':'input','6':'input','7':'open_collector','8':'power_in'}
 elif ref=='U19':
  fp='DIP-18_W7.62mm_LongPads';names={'1':'SCL','2':'SDA','3':'A2','4':'A1','5':'A0','6':'RESET_N','7':'NC','8':'INT_NC','9':'VSS','18':'VDD',**{str(n+10):'GP'+str(n)for n in range(8)}}
  types={'1':'input','2':'bidirectional','3':'input','4':'input','5':'input','6':'input','8':'open_collector','9':'power_in','18':'power_in',**{str(n+10):'output'for n in range(8)}}
 elif ref=='U20':fp='TO-92_Inline_Wide';names={'1':'RESET_N OC','2':'VDD','3':'VSS'};types={'1':'open_collector','2':'power_in','3':'power_in'}
 else:raise ValueError(ref)
 mpn=row.get('mpn','')
 if ref.startswith('R'):mpn=('MRS16000C'if'0.4W'in row['value']else'MRS25000C')+resistance_code(row['ohm'])+'FCT00'
 note=row.get('note','')+' A6 conditional development draft, no fabrication/physical qualification.'
 if ref.startswith('R'):note+=' Candidate '+('MRS16'if'0.4W'in row['value']else'MRS25')+' order code; availability, TCR/derating, formed body and thermal acceptance pending.'
 if ref=='R179':note+=' Use the declared mounting side and footprint; physical forming, heat and fit acceptance pending.'
 return Part(ref,row['value'],'ECU:'+fp,row['pins'],names,types,page,(0,0),mpn=mpn,note=note)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'hardware/a6-flex-rgb');p.add_argument('--footprint-input',type=Path,required=True);p.add_argument('--repack',action='store_true',help='Rearrange the new copy and require complete new routing; original A5 is unchanged');p.add_argument('--packing-attempts',type=int,default=32);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise SystemExit('Choose a new output directory; existing designs are never regenerated in place')
 source_hashes={str(x.relative_to(ROOT)):sha(x)for x in SOURCE.rglob('*')if x.is_file()and x.suffix!='.kicad_prl'}
 shutil.copytree(SOURCE,out,ignore=shutil.ignore_patterns('*.kicad_prl','*.lck','*~'))
 contract=json.loads((SOURCE/'net_contract.json').read_text());front=json.loads(FRONT.read_text());led=json.loads(LED.read_text())
 back_refs={r['ref']for r in led['parts']if r.get('mounting',{}).get('side')=='B.Cu'}
 assert not back_refs or a.repack,'Current back-mounted profile requires complete new routing with--repack'
 contract.update(revision='A6-FLEX-RGB-HOLD',status='NATIVE_UNROUTED_DRAFT_NOT_FOR_FABRICATION',manufacturing_release=False,physical_fit_tested=False)
 assert front['existing_part_changes']=={'U3':{'32':'FLEX'}}
 module=next(x for x in contract['parts']if x['ref']=='U3');assert module['pins']['32']is None;module['pins']['32']='FLEX';module['types']['32']='input'
 module['note']+=' A6 GPIO38 only receives protected flex candidate; oldGPIO38 RMT/LED builds incompatible. Use compact_n16r8_flex_dev only; engine outputs inhibited.'
 names={f.name for f in fields(Part)};parts=[Part(**{k:v for k,v in r.items()if k in names})for r in contract['parts']]
 added=[convert(r,'flex')for r in front['parts']]+[convert(r,'status_led')for r in led['parts']]
 assert len({p.ref for p in parts+added})==len(parts+added)
 provenance={}
 for stem,record in json.loads((a.footprint_input/'provenance.json').read_text()).items():
  path=a.footprint_input/(stem+'.kicad_mod');assert sha(path)==record['sha256'];data,removed=footprint_copy(path.read_bytes());target=out/'lib/ecu.pretty'/(stem+'.kicad_mod');target.write_bytes(data)
  provenance[stem]={**record,'copy_sha256':sha(target),'omitted_metadata':removed}
 for stem in ('DIP-18_W7.62mm_LongPads',):
  path=ROOT/'hardware/switch-inputs/lib/ecu.pretty'/(stem+'.kicad_mod');target=out/'lib/ecu.pretty'/path.name;shutil.copyfile(path,target)
  provenance[stem]=dict(source=str(path.relative_to(ROOT)),source_sha256=sha(path),copy_sha256=sha(target))
 for ref in sorted(r['ref']for r in led['parts']if'mounting'in r):
  row=next(r for r in led['parts']if r['ref']==ref);stem=row['mounting']['footprint'];path=ROOT/'hardware/flex-input/footprints'/(stem+'.kicad_mod');target=out/'lib/ecu.pretty'/path.name;assert not target.exists();shutil.copyfile(path,target)
  provenance[stem]=dict(source=str(path.relative_to(ROOT)),source_sha256=sha(path),copy_sha256=sha(target),physical_fit_qualified=False)
 board_file=out/'esp32-ecu.kicad_pcb';board=pcb.LoadBoard(str(board_file));before=sorted(geometry(t)for t in board.GetTracks())
 original_board=board
 if a.repack:
  # Removing every native track in one Python process invalidates this Linux
  # SWIG iterator. Strip only the new copy's balanced copper expressions, then
  # load a fresh native board; the source file and its footprint geometry stay.
  text=board_file.read_text();removed=0
  for kind in ('segment','via'):
   blocks=list(chunks(text,kind));removed+=len(blocks)
   for start,end,_ in reversed(blocks):text=text[:start]+text[end:]
  assert removed==len(before)
  board_file.write_text(text);board=pcb.LoadBoard(str(board_file));assert not board.GetTracks()
 desired={f.GetReference():(f.GetPosition().x/1e6,f.GetPosition().y/1e6)for f in board.GetFootprints()}
 for t in board.GetTracks():t.SetLocked(True)
 for item in parts+added:
  for pin,net in item.pins.items():
   name=net if net is not None else builder.nc_net(item,pin)
   if board.FindNet(name) is None:board.Add(pcb.NETINFO_ITEM(board,name))
 contract['gpio']['FLEX']=38
 module_fp=next(f for f in board.GetFootprints()if f.GetReference()=='U3');module_pad=next(p for p in module_fp.Pads()if p.GetNumber()=='32');module_pad.SetNet(board.FindNet('FLEX'));module_pad.SetPinType('input')
 # Big packages/connectors first; put bypasses near their actual power pads.
 priority=['U18','U19','U20','J22','J23','F3','Q8','Q9','Q10','C160','C161','C162','C163']
 added.sort(key=lambda p:(priority.index(p.ref)if p.ref in priority else 100,int(re.search(r'\d+',p.ref)[0])))
 locations={};defaults={'U18':(46,61),'U19':(53,56),'U20':(57,57),'J22':(55,15),'J23':(79,15),'F3':(53,27),'Q8':(68,45),'Q9':(73,45),'Q10':(78,45)}
 for item in added:
  fp=pcb.FootprintLoad(str(out/'lib/ecu.pretty'),item.footprint.split(':')[1]);assert fp is not None,item.ref
  fp.SetReference(item.ref);fp.SetValue(item.value);fp.SetFPID(pcb.LIB_ID('ECU',item.footprint.split(':')[1]));fp.SetPath(pcb.KIID_PATH('/'+builder.uid('root')+'/'+builder.uid(item.page)+'/'+builder.uid(item.ref)))
  fp.Reference().SetLayer(pcb.F_Fab);fp.Reference().SetTextSize(pcb.VECTOR2I(pcb.FromMM(.8),pcb.FromMM(.8)));fp.Value().SetVisible(False)
  for pin in fp.Pads():
   n=pin.GetNumber()
   if n:
    assert n in item.pins,(item.ref,n);net=item.pins[n];pin.SetNet(board.FindNet(net if net is not None else builder.nc_net(item,n)))
  preferred=defaults.get(item.ref,(47,62)if item.page=='flex'else(66,50))
  bypass={'C160':('U18','8'),'C161':('U19','18'),'C162':('U20','2'),'C163':('U19','18')}
  if item.ref in bypass and not a.repack:
   ref,n=bypass[item.ref];owner=next(f for f in board.GetFootprints()if f.GetReference()==ref);pin=next(p for p in owner.Pads()if p.GetNumber()==n);preferred=(pin.GetPosition().x/1e6,pin.GetPosition().y/1e6-4)
  if a.repack:
   board.Add(fp)
   if item.ref in back_refs:fp.Flip(fp.GetPosition(),False)
   xy,angle=[0,0],0;desired[item.ref]=preferred
  else:xy,angle=place(board,fp,preferred)
  locations[item.ref]=dict(xy_mm=xy,angle_deg=angle);print(item.ref,xy,angle,flush=True)
  row=asdict(item);row.update(placed_xy_mm=xy,placed_angle_deg=angle);contract['parts'].append(row);parts.append(item)
 packing=None
 if a.repack:
  pcb.SaveBoard(str(board_file),board)
  packing=pack(board,{p.ref:p for p in parts if p.ref not in back_refs},desired,attempts=a.packing_attempts,problem_path=out/'packing-input.json',exclude=back_refs);locations=packing['positions'];assert not board.GetTracks()
  for ref in sorted(back_refs):
   fp=next(f for f in board.GetFootprints()if f.GetReference()==ref);jack=next(f for f in board.GetFootprints()if f.GetReference()=='J23');preferred=[jack.GetPosition().x/1e6,jack.GetPosition().y/1e6];xy,angle,check=place_back(board,fp,preferred,already_added=True);locations[ref]=dict(xy_mm=xy,angle_deg=angle,side='B.Cu',back_check=check)
  for row in contract['parts']:row.update(placed_xy_mm=locations[row['ref']]['xy_mm'],placed_angle_deg=locations[row['ref']]['angle_deg'],placed_side='B.Cu'if row['ref']in back_refs else'F.Cu')
 else:assert sorted(geometry(t)for t in board.GetTracks())==before
 for text in board.GetDrawings():
  if isinstance(text,pcb.PCB_TEXT):text.SetText(text.GetText().replace('A5-IDLE HOLD','A6-FLEX-RGB HOLD'))
 pcb.ZONE_FILLER(board).Fill(board.Zones());pcb.SaveBoard(str(board_file),board)
 builder.OUT,builder.LIB,builder.PARTS=out,out/'lib',parts
 builder.NOTES={'core':'A6 HOLD. GPIO38 flex input; legacy GPIO38 LED/RMT incompatible. Pluggable N16R8 geometry/eFuse, CPU timing and physical IO unqualified. Engine outputs inhibited.',
  'flex':'A6 FLEX INPUT CANDIDATE. Circuit equivalents and captured software checks only; sensor supply/pinout/protection/timing unqualified. No sensor connection/fabrication release.',
  'status_led':'A6 MCP0x21 advisory RGB. HighGP0/1/2 selects red/green/blue. GP3..7 NC outputs low. Retained green does not prove live CPU/light output; optics/reset/partial power unqualified.'}
 for page in ('core','flex','status_led'):builder.write_sheet(page)
 flags=[b for _,_,b in chunks((SOURCE/'lib/ecu.kicad_sym').read_text(),'symbol')if re.match(r'\(symbol "#FLG\d+"',b)]
 (out/'lib/ecu.kicad_sym').write_text('(kicad_symbol_lib (version 20231120) (generator "esp32_ecu_a6")\n'+'\n'.join([builder.symbol(p)[0]for p in parts if p.pins]+flags)+')')
 root=(out/'esp32-ecu.kicad_sch').read_text();at=root.index('(sheet_instances')
 sheets=[]
 for page,x,number in (('flex',139.7,9),('status_led',254.0,10)):
  y=193.04;sheets.append(f'(sheet (at {x} {y}) (size 96.52 45.72) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {builder.uid(page)}) (property "Sheetname" "{page}" (at {x} {y-2.54} 0) {builder.effects(1)}) (property "Sheetfile" "{page}.kicad_sch" (at {x} {y+48.26} 0) {builder.effects(1)}) (instances (project "esp32-ecu" (path "/{builder.uid("root")}" (page "{number}")))))\n')
 (out/'esp32-ecu.kicad_sch').write_text(root[:at]+''.join(sheets)+root[at:])
 for path in out.glob('*.kicad_sch'):path.write_text(path.read_text().replace('A5 IDLE INTERFACE HOLD','A6 FLEX RGB HOLD').replace('ESP32 ECU A0 /','ESP32 ECU A6 /').replace('A0 BENCH','A6 HOLD'))
 contract['flex_input']=dict(contract=front['contract'],source_sha256=sha(FRONT),gpio=38,connector='J22',sensor_supply_qualified=False,physical_output_enabled=False)
 contract['status_led']=dict(contract=led['contract'],source_sha256=sha(LED),address=33,connector='J23',optics_qualified=False)
 (out/'net_contract.json').write_text(json.dumps(contract,indent=2)+'\n');(out/'new-footprints.json').write_text(json.dumps(provenance,indent=2)+'\n')
 with(out/'bom.csv').open('w',newline='')as stream:
  w=csv.writer(stream,lineterminator='\n');w.writerow(['Reference','Value','MPN','Footprint','DNP','Assembly','Note'])
  for r in contract['parts']:w.writerow([r['ref'],r['value'],r['mpn'],r['footprint'],r.get('dnp',False),'Purchased module'if r['ref']in ('U1','U3')else'Direct-solder THT',r['note']])
 (out/'source-provenance.json').write_text(json.dumps(dict(source_revision='A5-IDLE-INTERFACE-HOLD',source_sha256=source_hashes,input_contracts={str(FRONT.relative_to(ROOT)):sha(FRONT),str(LED.relative_to(ROOT)):sha(LED)},original_carrier_unchanged=True,original_copper_objects=before,old_copper_locked=not a.repack,old_copper_geometry_retained=not a.repack,complete_new_routing_required=a.repack,new_connections_unrouted=True,placements=locations,packing=packing,qualification='Native draft only. No fabrication, sensor/power qualification, module/case fit, RF, target/HIL or physical engine operation.'),indent=2)+'\n')
 assert all(sha(ROOT/name)==digest for name,digest in source_hashes.items())
 print('Created A6 native draft with',len(added),'new PCB parts; new links need routing/ERC/DRC/parity. No fabrication release.')

if __name__=='__main__':main()
