#!/usr/bin/env python3
"""FreeCAD Python: PYTHONPATH=<FreeCAD>/lib <FreeCAD>/bin/python scripts/build_enclosure.py"""
import json,math
from pathlib import Path
import FreeCAD as A,Part,MeshPart
from pathlib import Path
import json,math
R=Path(__file__).resolve().parents[1];O=R/'enclosure';O.mkdir(exist_ok=True)
# Board datums measured from A1 Edge.Cuts, connectors are internal.
p={'outer_mm':218,'wall_mm':3,'floor_mm':3,'base_height_mm':44,'lid_mm':3,'board_origin_mm':[9,9], 'pcb_mm':[200,200,1.6], 'standoff_height_mm':6,'pcb_holes_mm':[[13,13],[205,13],[13,205],[205,205]], 'lid_screws_mm':[[4.5,4.5],[213.5,4.5],[4.5,213.5],[213.5,213.5]],'cable_hole_diameter_mm':16.2,'cable_hole_x_mm':[40,85,130,175],'cable_hole_z_mm':30,'fit_clearance_mm':.3}
V=A.Vector
base=Part.makeBox(218,218,44).cut(Part.makeBox(212,212,42,V(3,3,3)))
for x,y in p['pcb_holes_mm']:
 base=base.fuse(Part.makeCylinder(3.5,6,V(x,y,3)))
 base=base.cut(Part.makeCylinder(1.25,8,V(x,y,1)))
for x,y in p['lid_screws_mm']:
 base=base.fuse(Part.makeCylinder(4.5,44,V(x,y,0)))
 base=base.cut(Part.makeCylinder(1.25,12,V(x,y,32)))
for x in p['cable_hole_x_mm']:
 base=base.cut(Part.makeCylinder(8.1,5,V(x,-1,30),V(0,1,0)))
# Printed bridge above each opening has two 3.2 mm zip tie holes.
for x in p['cable_hole_x_mm']:
 for dx in [-12,12]:base=base.cut(Part.makeCylinder(1.6,5,V(x+dx,-1,30),V(0,1,0)))
# Lid is exported with outside face on the bed, locating lip faces up.
lid=Part.makeBox(218,218,3)
# Segmented locating lip avoids the corner posts, 0.3 mm gap to inner wall.
for x,y,l,w in [(12,3.3,194,1.5),(12,213.2,194,1.5),(3.3,12,1.5,194),(213.2,12,1.5,194)]:lid=lid.fuse(Part.makeBox(l,w,2,V(x,y,3)))
for x,y in p['lid_screws_mm']:
 lid=lid.cut(Part.makeCylinder(1.7,5,V(x,y,0)))
 # Pan head fasteners with washers, no countersink splitting thin lid.
# Split lid option for small printers: tongue free butt joint, join with printed bridge plates.
plug=Part.makeCylinder(7.8,3).fuse(Part.makeCylinder(10,1.5,V(0,0,3)))
doc=A.newDocument('ECU_A1_Enclosure')
results={}
for name,shape in [('base',base.removeSplitter()),('lid',lid.removeSplitter()),('cable_blank',plug.removeSplitter())]:
 if not shape.isValid() or len(shape.Solids)!=1:raise RuntimeError(name+' is not a valid single solid')
 obj=doc.addObject('PartDesign::Feature',name);obj.Shape=shape
 Part.export([obj],str(O/f'{name}.step'))
 mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=.08,AngularDeflection=.15,Relative=False)
 mesh.write(str(O/f'{name}.stl'))
 results[name]={'valid_solid':True,'volume_mm3':shape.Volume,'size_mm':[shape.BoundBox.XLength,shape.BoundBox.YLength,shape.BoundBox.ZLength],'mesh_closed':mesh.isSolid()}
 if not mesh.isSolid():raise RuntimeError(name+' mesh not closed')
doc.recompute();doc.saveAs(str(O/'ecu-a1-enclosure.FCStd'))
(O/'dimensions.json').write_text(json.dumps(p,indent=2));(O/'validation.json').write_text(json.dumps({'parts':results,'physical_fit_tested':False,'waterproof':False,'printer_bed_minimum_mm':[218,218]},indent=2))
print(json.dumps(results,indent=2))
