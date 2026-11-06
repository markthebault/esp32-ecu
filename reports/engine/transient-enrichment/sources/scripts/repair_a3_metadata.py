"""Synchronize compact footprint fields and remove the superseded source-bus path."""
import pcbnew as p,json,math
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact';path=O/'esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path));c=json.loads((O/'net_contract.json').read_text());fs={f.GetReference():f for f in b.GetFootprints()}
for d in c['parts']:
 d['note']=d['note'].replace('A2','A3').replace('docs/through-hole.md','docs/compact.md')
 f=fs[d['ref']]
 for key,val in [('MPN',d['mpn']),('DesignNote',d['note'])]:f.SetField(key,val);f.GetField(key).SetVisible(False);f.GetField(key).SetLayer(p.F_Fab)
for sch in list(O.glob('*.kicad_sch'))+[O/'lib/ecu.kicad_sym']:
 sch.write_text(sch.read_text().replace('A2','A3').replace('docs/through-hole.md','docs/compact.md'))
# Remove the initial bus before adding a clearance-checked revised bus.
for t in list(b.GetTracks()):
 if not isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND' and t.GetWidth()>=p.FromMM(2.5):b.Remove(t)
# Crowded outlines are kept on the assembly layer; pin-1 features and references remain available.
for f in fs.values():
 if f.GetReference()=='J20':
  for s in f.GraphicalItems():
   if s.GetLayer()==p.F_SilkS:s.SetLayer(p.F_Fab)
p.SaveBoard(str(path),b);(O/'net_contract.json').write_text(json.dumps(c,indent=2))
project=json.loads((O/'esp32-ecu.kicad_pro').read_text());project['board']['design_settings']['rules']['min_copper_edge_clearance']=.4;(O/'esp32-ecu.kicad_pro').write_text(json.dumps(project,indent=2))
