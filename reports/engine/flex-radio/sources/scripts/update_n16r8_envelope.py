#!/usr/bin/env python3
"""Record a provisional raised, inward 10mm antenna envelope, without rerouting."""
from pathlib import Path
import json, re, struct
R=Path(__file__).resolve().parents[1];O=R/'hardware/a4-n16r8'
c=json.loads((O/'net_contract.json').read_text());u=next(p for p in c['parts'] if p['ref']=='U3')
def end_block(s,start):
 depth=0;quoted=False;escape=False
 for i in range(start,len(s)):
  ch=s[i]
  if quoted:
   if escape:escape=False
   elif ch=='\\':escape=True
   elif ch=='"':quoted=False
  elif ch=='"':quoted=True
  elif ch=='(':depth+=1
  elif ch==')':
   depth-=1
   if depth==0:return i+1
 raise ValueError('Unclosed S-expression')
p=O/'esp32-ecu.kicad_pcb';s=p.read_text();start=s.index('(footprint "ECU:ESP32_S3_DevKitC_1_socket"');end=end_block(s,start);block=s[start:end]
# Same pad/routing datums. Only body/courtyard at antenna end and purchased model.
block=block.replace('(start -1.5 -7)','(start -1.5 -10)')
block=re.sub(r'\(property "MPN" "[^"]*"','(property "MPN" '+json.dumps(u['mpn']),block)
block=re.sub(r'\(property "DesignNote" "[^"]*"','(property "DesignNote" '+json.dumps(u['note']),block)
block=block.replace('esp32-s3-devkitc-envelope.step','esp32-s3-n16r8-provisional.stl')
s=s[:start]+block+s[end:];p.write_text(s)
p=O/'lib/ecu.pretty/ESP32_S3_DevKitC_1_socket.kicad_mod';s=p.read_text().replace('(start -1.5 -7)','(start -1.5 -10)').replace('esp32-s3-devkitc-envelope.step','esp32-s3-n16r8-provisional.stl');p.write_text(s)
# OpenSCAD source and an equivalent box-triangle STL. Not manufacturer CAD.
boxes=[(-1.27,-56.34,8.5,25.4,66.34,1.6),(2.43,-19,10.1,18,19,2.8),(1.5,-56.34,10.1,8,6,3),(13.5,-56.34,10.1,8,6,3)]
model=O/'lib/models';(model/'esp32-s3-n16r8-provisional.scad').write_text('// Provisional envelope. 22.86mm row spacing and 8.5mm socket stack unmeasured.\n'+'\n'.join(f'translate([{x},{y},{z}]) cube([{w},{h},{d}]);' for x,y,z,w,h,d in boxes)+'\n')
triangles=[]
for x,y,z,w,h,d in boxes:
 v=[(x,y,z),(x+w,y,z),(x+w,y+h,z),(x,y+h,z),(x,y,z+d),(x+w,y,z+d),(x+w,y+h,z+d),(x,y+h,z+d)]
 for a,b,cc,dd in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
  for i,j,k in [(a,b,cc),(a,cc,dd)]:triangles.append(struct.pack('<12fH',0,0,0,*v[i],*v[j],*v[k],0))
(model/'esp32-s3-n16r8-provisional.stl').write_bytes(b'PROVISIONAL N16R8 raised envelope; not a measured fit model'.ljust(80,b' ')+struct.pack('<I',len(triangles))+b''.join(triangles))
(O/'README.md').write_text((O/'README.md').read_text().replace('The placed module model still shows the earlier generic assembly envelope; it is not a fit-qualified model of the selected board.','The placed module model uses a new provisional raised envelope with the 10 mm inward extension; it is not a fit-qualified model of the selected board.').replace('The inherited rule area is an A3 provision;','The inherited rule area is an A3 provision;'))
for name in ['BOM.md']:
 p=O/name;s=p.read_text();warning='> PROVISIONAL: selected N16R8 module; socket spacing and antenna fit unmeasured. No A4 fabrication release. See README.md and ../../docs/espnow.md.\n\n'
 if not s.startswith('> PROVISIONAL'):p.write_text(warning+s)
print('Updated provisional N16R8 envelope only; no net or copper changes.')
