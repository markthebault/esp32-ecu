"""Assembly envelopes for missing VH/PTC models, not detailed mating CAD."""
import FreeCAD as A,Part
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'hardware/a3-compact/lib/models';V=A.Vector;doc=A.newDocument('A3_Connector_Envelopes')
for n in [2,4,5,8]:
 span=(n-1)*3.96
 body=Part.makeBox(span+3.9,6.8,2.5,V(-1.95,-4.8,0))
 body=body.fuse(Part.makeBox(span+1.5,1.7,10.9,V(-.75,2,0)))
 for i in range(n):body=body.fuse(Part.makeBox(1.14,1.14,13.5,V(i*3.96-.57,-.57,-3.5)))
 obj=doc.addObject('PartDesign::Feature','VH_'+str(n));obj.Shape=body;Part.export([obj],str(O/f'jst-vh-{n}-envelope.step'))
body=Part.makeBox(7.4,2.8,7.6,V(-1.2,-1.4,2.0))
for x in [0,5.08]:body=body.fuse(Part.makeCylinder(.3,5.5,V(x,0,-3.5)))
obj=doc.addObject('PartDesign::Feature','PTC');obj.Shape=body;Part.export([obj],str(O/'ptc-envelope.step'))
(O/'README.md').write_text('Purchased ESP32-S3 and Pololu modules, JST VH headers and PTC use simplified assembly envelopes. They are not manufacturer detailed CAD and do not establish connector mating fit. VH footprint datums and nominal envelope derive from the JST VH standard header drawing: https://www.jst-mfg.com/product/pdf/eng/eVH.pdf . The actual BOM and native pads remain the construction authority. The four DNP sensor pull-ups are intentionally absent. Service Wi-Fi requires physical verification with the lid open; no antenna or EMC performance is claimed.\n')
print('Missing connector/PTC assembly envelopes generated')
