#!/usr/bin/env python3
"""Prepare/import routing for an explicit NEW A6 copy, never an old carrier.

Uses native RF rule areas unchanged. Placement also excludes the larger
provisional antenna envelope. No fabrication, physical or RF rating is inferred.
"""
import argparse,hashlib,json,re,shutil,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
import pcbnew as pcb
from kicad9_carrier_copy import chunks

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pads(board):return sorted((f.GetReference(),p.GetNumber(),p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y,p.GetDrillSize().x,p.GetDrillSize().y)for f in board.GetFootprints()for p in f.Pads()if p.GetNumber())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--board',type=Path,required=True);p.add_argument('--prepare',type=Path);p.add_argument('--import-session',type=Path);p.add_argument('--drc-cosmetics',type=Path);a=p.parse_args()
 if bool(a.prepare)==bool(a.import_session):p.error('Choose prepare or import')
 path=a.board.resolve();contract_path=path.parent/'net_contract.json';contract=json.loads(contract_path.read_text());assert contract['revision']=='A6-FLEX-RGB-HOLD'
 board=pcb.LoadBoard(str(path));assert not board.GetTracks(),'Do not overwrite routed work';original_pads=pads(board)
 if a.prepare:
  out=a.prepare.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copyfile(path,out/'before.kicad_pcb')
  netlist=out/'native.xml';subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(netlist),str(path.with_suffix('.kicad_sch'))],check=True)
  native={(n.attrib['ref'],n.attrib['pin']):net.attrib['name']for net in ET.parse(netlist).getroot().findall('./nets/net')for n in net.findall('node')}
  changes=[]
  for f in board.GetFootprints():
   row=next(r for r in contract['parts']if r['ref']==f.GetReference())
   for pad in f.Pads():
    pin=pad.GetNumber()
    if not pin:continue
    key=(f.GetReference(),pin)
    if key not in native:continue
    expected=native[key];declared=row['pins'][pin]
    if declared is not None:assert expected==declared,(key,expected,declared)
    if pad.GetNetname()!=expected:
     assert declared is None and expected.startswith('unconnected-'),(key,expected)
     if board.FindNet(expected)is None:board.Add(pcb.NETINFO_ITEM(board,expected))
     changes.append(dict(ref=key[0],pin=pin,old=pad.GetNetname(),new=expected));pad.SetNet(board.FindNet(expected))
  cosmetics=[]
  if a.drc_cosmetics:
   objects={d.m_Uuid.AsString():(None,d)for d in board.GetDrawings()}
   for f in board.GetFootprints():
    for item in f.GraphicalItems():objects[item.m_Uuid.AsString()]=(f.GetReference(),item)
   for violation in json.loads(a.drc_cosmetics.read_text())['violations']:
    assert violation['type']in ('silk_overlap','silk_over_copper'),'Do not clear noncosmetic violations'
    available=[(item['uuid'],*objects[item['uuid']])for item in violation['items']if item['uuid']in objects]
    if any(obj.GetLayer()!=pcb.F_SilkS for _,_,obj in available):continue
    available=[(uid,ref,obj)for uid,ref,obj in available if obj.GetLayer()==pcb.F_SilkS]
    if not available:continue
    # Preserve the ink as assembly information, instead of relaxing the DRC.
    available.sort(key=lambda q:0 if q[1]is None else 1 if hasattr(q[2],'GetText')else 2 if q[1].startswith(('D','C'))else 3)
    uid,ref,obj=available[0];obj.SetLayer(pcb.F_Fab);cosmetics.append(dict(uuid=uid,reference=ref,from_layer='F.SilkS',to_layer='F.Fab',reason=violation['type']))
  assert pads(board)==original_pads,'Cosmetic update moved pad geometry'
  pcb.SaveBoard(str(path),board)
  dsn=out/'a6.dsn';assert pcb.ExportSpecctraDSN(board,str(dsn));text=dsn.read_text();start,end,block=next(chunks(text,'class'));assert len(list(chunks(text,'class')))==1
  via=re.search(r'\(use_via ("[^"]+")',block)[1];netnames=sorted(n.GetNetname()for n in board.GetNetsByNetcode().values()if n.GetNetname())
  high={n for n in netnames if n in ('GND','VBAT_FUSED','VIN_PROT','VIN_FILTERED')or re.fullmatch(r'INJ[1-4]_LS',n)}
  supply={n for n in netnames if n in ('+5V','+3V3','SENSOR_5V','FLEX_12V','MAIN_LS','PUMP_LS','FAN_LS')}
  groups=[('Power',sorted(high),1000),('Supply',sorted(supply),500),('Logic',[n for n in netnames if n not in high|supply],250)]
  classes='\n'.join('(class '+name+' '+' '.join(json.dumps(n)for n in members)+f' (circuit (use_via {via})) (rule (width {width}) (clearance 200)))'for name,members,width in groups)
  dsn.write_text(text[:start]+classes+text[end:])
  (out/'routing-input.json').write_text(json.dumps(dict(board_sha256=sha(path),dsn_sha256=sha(dsn),native_netlist_sha256=sha(netlist),no_connect_name_normalization=changes,cosmetic_moves=cosmetics,route_classes=dict(Power_width_mm=1,Supply_width_mm=.5,Logic_width_mm=.25,clearance_mm=.2),RF_rule_areas='Unchanged native union from A5; no new placed component inside full provisional14..44/29..40 envelope',qualification=__doc__),indent=2)+'\n')
 else:
  transforms={f.GetReference():(f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees())for f in board.GetFootprints()};before_sha=sha(path)
  assert pcb.ImportSpecctraSES(board,str(a.import_session.resolve()))
  # SES quantizes placement coordinates. Restore the original exact integer
  # transforms; accept only sub-grid rounding, never real component movement.
  restored=[]
  for f in board.GetFootprints():
   original=transforms[f.GetReference()];current=(f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees());dx,dy=current[0]-original[0],current[1]-original[1];da=(current[2]-original[2]+180)%360-180
   assert max(abs(dx),abs(dy))<=100 and abs(da)<1e-6,('Unexpected SES placement change',f.GetReference(),original,current)
   if current!=original:restored.append(dict(ref=f.GetReference(),dx_nm=dx,dy_nm=dy,angle_delta_deg=da))
   f.SetPosition(pcb.VECTOR2I(original[0],original[1]));f.SetOrientationDegrees(original[2])
  assert pads(board)==original_pads,'Router moved footprint pad geometry'
  pcb.ZONE_FILLER(board).Fill(board.Zones());pcb.SaveBoard(str(path),board)
  contract['status']='ROUTED_NATIVE_DRAFT_AWAITING_CHECKS_NOT_FOR_FABRICATION';contract_path.write_text(json.dumps(contract,indent=2)+'\n')
  proof=path.parent/'routing-import.json';assert not proof.exists();proof.write_text(json.dumps(dict(input_board_sha256=before_sha,session_sha256=sha(a.import_session),exact_original_pad_geometry_restored=True,quantized_transforms_restored=restored,output_board_sha256=sha(path),track_via_objects=len(board.GetTracks()),manufacturing_release=False),indent=2)+'\n')
 print('A6 routing operation completed; native/physical gates remain')

if __name__=='__main__':main()
