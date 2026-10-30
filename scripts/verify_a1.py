"""Verify the routed A1 net/pad contract and its enclosure datums."""
import json
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];D=R/'hardware/a1-hand-solder';b=p.LoadBoard(str(D/'esp32-ecu.kicad_pcb'));c=json.loads((D/'net_contract.json').read_text());count=0
fps={f.GetReference():f for f in b.GetFootprints()}
for part in c['parts']:
 f=fps[part['ref']];assert str(f.GetFPID().GetLibItemName())==part['footprint'].split(':')[1],part['ref']
 actual={x.GetNumber():x.GetNetname() for x in f.Pads() if x.GetNumber()}
 expected={}
 for n,net in part['pins'].items():
  name=part['names'].get(n,'');expected[n]=net if net is not None else 'unconnected-('+part['ref']+'-'+(name+'-' if name else '')+'Pad'+n+')'
 assert actual==expected,(part['ref'],actual,expected)
 count+=len(actual)
box=json.loads((R/'enclosure/dimensions.json').read_text());o=box['board_origin_mm']
for i,(x,y) in enumerate(box['pcb_holes_mm'],1):
 f=fps['H'+str(i)];assert abs(f.GetPosition().x/1e6-10+o[0]-x)<1e-6;assert abs(f.GetPosition().y/1e6-10+o[1]-y)<1e-6
assert c['gpio']['ARM']==47
for report in ['drc','erc']:
 s=json.loads((R/f'reports/a1/{report}.json').read_text())
 if report=='drc':assert not s['violations'] and not s['unconnected_items'] and not s['schematic_parity']
 else:assert all(not sh.get('violations') for sh in s['sheets'])
result={'parts':len(fps),'pads_checked':count,'electrical_contract':'pass','pcb_mounting_datums':'pass','erc_violations':0,'drc_violations':0,'unconnected':0,'schematic_parity_issues':0,'physical_fit_tested':False,'vehicle_qualified':False}
(R/'reports/a1/validation-summary.json').write_text(json.dumps(result,indent=2));print(result)
