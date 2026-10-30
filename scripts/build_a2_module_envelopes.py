"""FreeCAD Python. Conservative envelopes, not manufacturer detailed component CAD."""
import FreeCAD as A,Part
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'hardware/a2-through-hole/lib/models';O.mkdir(exist_ok=True);V=A.Vector
# KiCad model Y is opposite the board editor's Y. Z=0 is carrier top surface.
doc=A.newDocument('A2_Module_Envelopes')
esp=Part.makeBox(25.4,62.74,1.6,V(-1.27,-56.34,8.5))
esp=esp.fuse(Part.makeBox(18,19,2.8,V(2.43,-19,10.1)))
esp=esp.fuse(Part.makeBox(8,6,3,V(1.5,-56.34,10.1)))
esp=esp.fuse(Part.makeBox(8,6,3,V(13.5,-56.34,10.1)))
# Vertical regulator: body occupies the rectangle standing above its header.
buck=Part.makeBox(10.16,1.6,12.7,V(-1.27,-.8,2.5))
for name,shape in [('esp32-s3-devkitc-envelope',esp),('pololu-d36v6-envelope',buck)]:
 obj=doc.addObject('PartDesign::Feature',name.replace('-','_'));obj.Shape=shape;Part.export([obj],str(O/f'{name}.step'))
(O/'README.md').write_text('These are dimensioned assembly envelopes for the purchased modules. They are not manufacturer detailed CAD and do not establish connector fit. The ESP32 envelope includes the socketed mounting height; the actual 44-pad and 22.86 mm row datums are in the KiCad footprint. Radios are disabled; no antenna performance claim.\n')
print('Created assembly envelopes for the two purchased modules')
