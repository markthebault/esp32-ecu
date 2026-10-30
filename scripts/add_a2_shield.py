"""Add the separately bonded shield lug and local CHASSIS region to A2."""
from pathlib import Path
import json,pcbnew as p
import build_hardware as g
R=Path(__file__).resolve().parents[1];O=R/'hardware/a2-through-hole';path=O/'esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path))
if not any(f.GetReference()=='H5' for f in b.GetFootprints()):
 f=p.FootprintLoad(str(O/'lib/ecu.pretty'),'MountingHole_3.2mm_M3_Pad');f.SetReference('H5');f.SetField('MPN','');f.GetField('MPN').SetVisible(False);f.GetField('MPN').SetLayer(p.F_Fab);f.SetValue('M3 SHIELD LUG');f.Value().SetVisible(False);f.Reference().SetVisible(False);f.SetFPID(p.LIB_ID('ECU','MountingHole_3.2mm_M3_Pad'));f.SetAttributes(f.GetAttributes() & ~p.FP_BOARD_ONLY & ~p.FP_EXCLUDE_FROM_BOM);f.SetPath(p.KIID_PATH(f'/{g.uid("root")}/{g.uid("core")}/{g.uid("H5")}'));f.SetPosition(p.VECTOR2I(p.FromMM(202),p.FromMM(158)));b.Add(f)
 for pad in f.Pads():
  if pad.GetNumber():pad.SetNet(b.FindNet('CHASSIS'))
if not any(z.GetNetname()=='CHASSIS' for z in b.Zones()):
 z=p.ZONE(b);z.SetLayer(p.B_Cu);z.SetNet(b.FindNet('CHASSIS'));z.SetLocalClearance(p.FromMM(.5));z.SetPadConnection(p.ZONE_CONNECTION_THERMAL);z.SetThermalReliefGap(p.FromMM(.3));z.SetThermalReliefSpokeWidth(p.FromMM(.5));z.Outline().NewOutline()
 for x,y in [(12,187),(198,187),(198,145),(208,145),(208,208),(12,208)]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
 b.Add(z)
note=next(d['note'] for d in json.loads((O/'net_contract.json').read_text())['parts'] if d['ref']=='H5')
for f in b.GetFootprints():
 if f.GetReference()=='H5':f.SetField('DesignNote',note);f.GetField('DesignNote').SetVisible(False);f.GetField('DesignNote').SetLayer(p.F_Fab)
p.SaveBoard(str(path),b)
