"""Correct two stale SMD dielectric labels to match existing A3 electrolytic footprints."""
import json
from pathlib import Path
import pcbnew as p
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact';contract=O/'net_contract.json';c=json.loads(contract.read_text());b=p.LoadBoard(str(O/'esp32-ecu.kicad_pcb'))
for part in c['parts']:
 if part['ref'] not in ['C5','C6']:continue
 assert part['footprint']=='Capacitor_THT:CP_Radial_D8.0mm_P3.50mm'
 part['value']='22u 16V electrolytic';part['note']='Radial electrolytic on the 5V rail; select exact series and verify rail stability/ripple over temperature.'
 f=b.FindFootprintByReference(part['ref']);f.SetValue(part['value']);f.SetField('DesignNote',part['note']);f.GetField('DesignNote').SetVisible(False);f.GetField('DesignNote').SetLayer(p.F_Fab)
contract.write_text(json.dumps(c,indent=2));p.SaveBoard(str(O/'esp32-ecu.kicad_pcb'),b)
# Cached defaults are regenerated separately; update these two placed symbol fields.
sch=O/'power.kicad_sch';s=sch.read_text()
for part in [d for d in c['parts'] if d['ref'] in ['C5','C6']]:
 start=s.index('(property "Reference" "'+part['ref']+'"');end=s.index('(instances ',start);block=s[start:end]
 import re
 block=re.sub(r'\(property "Value" "[^"]*"','(property "Value" "'+part['value']+'"',block)
 block=re.sub(r'\(property "DesignNote" "[^"]*"','(property "DesignNote" "'+part['note']+'"',block)
 s=s[:start]+block+s[end:]
sch.write_text(s)
print('Corrected C5/C6 metadata only; values, nets, footprint geometry and routing preserved')
