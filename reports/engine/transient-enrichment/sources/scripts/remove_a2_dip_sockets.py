"""Replace A2 DIP socket footprints with bare-IC long-pad footprints.
Refuse any pad geometry change; preserve copper, nets, part UUIDs and positions.
Run with KiCad Python after refreshing A2 metadata. Safe to run again.
"""
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];O=R/'hardware/a2-through-hole';path=O/'esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path));old=[];changed=[]
def pads(f):return {pad.GetNumber():pad for pad in f.Pads() if pad.GetNumber()}
def geometry(f):
 return {n:(pad.GetPosition().x,pad.GetPosition().y,pad.GetSize().x,pad.GetSize().y,pad.GetDrillSize().x,pad.GetDrillSize().y,pad.GetShape(),pad.GetAttribute(),pad.GetLayerSet().FmtHex(),pad.GetOrientationDegrees()) for n,pad in pads(f).items()}
for f in list(b.GetFootprints()):
 stem=str(f.GetFPID().GetLibItemName())
 if not stem.startswith('DIP-') or '_Socket_LongPads' not in stem:continue
 name=stem.replace('_Socket_LongPads','_LongPads')
 oldlib=O/'lib/ecu.pretty'
 if not (oldlib/(stem+'.kicad_mod')).exists():oldlib=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Package_DIP.pretty')
 original=p.FootprintLoad(str(oldlib),stem);replacement=p.FootprintLoad(str(O/'lib/ecu.pretty'),name)
 if geometry(original)!=geometry(replacement):raise RuntimeError('Pad geometry differs: '+stem)
 replacement.SetReference(f.GetReference());replacement.SetValue(f.GetValue());replacement.SetFPID(p.LIB_ID('ECU',name));replacement.SetPath(f.GetPath());replacement.SetUuid(f.m_Uuid);replacement.SetAttributes(f.GetAttributes());replacement.SetOrientationDegrees(f.GetOrientationDegrees());replacement.SetPosition(f.GetPosition())
 for key in ['MPN','DesignNote']:
  replacement.SetField(key,f.GetField(key).GetText());replacement.GetField(key).SetVisible(False);replacement.GetField(key).SetLayer(p.F_Fab)
 replacement.Value().SetVisible(False);replacement.Reference().SetLayer(p.F_Fab);replacement.Reference().SetVisible(True);replacement.Reference().SetPosition(f.Reference().GetPosition());replacement.Reference().SetTextSize(f.Reference().GetTextSize());replacement.Reference().SetTextThickness(f.Reference().GetTextThickness())
 previous=pads(f)
 for n,pad in pads(replacement).items():
  q=previous[n]
  assert pad.GetPosition()==q.GetPosition(),(f.GetReference(),n,'pad moved')
  pad.SetNet(q.GetNet());pad.SetUuid(q.m_Uuid)
 b.Add(replacement);old.append(f);changed.append(f.GetReference())
for f in old:b.Remove(f)
p.SaveBoard(str(path),b)
print('Direct-solder DIP footprints:',', '.join(sorted(changed)) if changed else 'already updated')
