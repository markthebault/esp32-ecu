"""A3 six-layer stack: F / GND / signal / signal / GND / B."""
from pathlib import Path
import json,re,csv
import pcbnew as p
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact';path=O/'esp32-ecu.kicad_pcb';b=p.LoadBoard(str(path));b.SetCopperLayerCount(6);b.SetLayerType(p.In1_Cu,p.LT_POWER);b.SetLayerType(p.In4_Cu,p.LT_POWER)
if not any(z.GetLayer()==p.In4_Cu for z in b.Zones()):
 z=p.ZONE(b);z.SetLayer(p.In4_Cu);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(p.FromMM(.25));z.SetPadConnection(p.ZONE_CONNECTION_THERMAL);z.SetThermalReliefGap(p.FromMM(.25));z.SetThermalReliefSpokeWidth(p.FromMM(.5));z.Outline().NewOutline()
 for x,y in [(10.5,10.5),(129.5,10.5),(129.5,129.5),(10.5,129.5)]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
 b.Add(z)
c=json.loads((O/'net_contract.json').read_text());c['copper_layers']=6;c['stack']='F.Cu / In1.Cu GND / In2.Cu signal / In3.Cu signal / In4.Cu GND / B.Cu';c['board_size_mm']=[120,120]
f=b.FindFootprintByReference('J20');name='JST_VH_B2P_SHIELD_Compact';f.SetFPID(p.LIB_ID('ECU',name));p.FootprintSave(str(O/'lib/ecu.pretty'),f)
for d in c['parts']:
 if d['ref']=='J20':d['footprint']='ECU:'+name
for sch in O.glob('*.kicad_sch'):
 s=sch.read_text()
 # Change J20's instance and its embedded symbol default without changing J19.
 start=s.find('(property "Reference" "J20"')
 if start>=0:
  end=s.find('(instances ',start);block=s[start:end];block=re.sub(r'ECU:JST_VH_B2P-VH_1x02_P3.96mm_Vertical','ECU:'+name,block);s=s[:start]+block+s[end:]
 sch.write_text(s)
p.SaveBoard(str(path),b);(O/'net_contract.json').write_text(json.dumps(c,indent=2))
with (O/'bom.csv').open('w') as out:
 w=csv.writer(out);w.writerow(['Reference','Value','MPN','Footprint','DNP','Assembly','Note'])
 for d in c['parts']:w.writerow([d['ref'],d['value'],d['mpn'],d['footprint'],d['dnp'],'Purchased assembled module' if d['ref'] in ['U1','U3'] else 'Through hole',d['note']])
print('A3 six-layer stack installed, two ground planes')
