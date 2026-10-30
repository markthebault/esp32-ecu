"""FreeCAD: compact 120 mm PCB case with splash gasket and internal shield bonds."""
import FreeCAD as A,Part,MeshPart
import json,csv
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'enclosure/a3';O.mkdir(exist_ok=True);V=A.Vector
W,H=138,150;PCB=[(13,13),(125,13),(13,125),(125,125)];LID=[(4.5,4.5),(W-4.5,4.5),(4.5,H-4.5),(W-4.5,H-4.5),(W/2,4.5),(W/2,H-4.5),(4.5,H/2),(W-4.5,H/2)];GLANDS=[27,55,83,111]
SEAL=[(15,3),(57,3),(64,12),(74,12),(81,3),(W-15,3),(W-3,15),(W-3,63),(W-12,70),(W-12,80),(W-3,87),(W-3,H-15),(W-15,H-3),(81,H-3),(74,H-12),(64,H-12),(57,H-3),(15,H-3),(3,H-15),(3,87),(12,80),(12,70),(3,63),(3,15)]
base=Part.makeBox(W,H,44).cut(Part.makeBox(W-6,H-6,42,V(3,3,3)))
for x,y in PCB:
 base=base.fuse(Part.makeCylinder(5,6,V(x,y,3))).fuse(Part.makeCone(6,5,2,V(x,y,3)))
 base=base.cut(Part.makeCylinder(2,4.9,V(x,y,4.1)))
# Scallops clear the actual solder tails near the rear-right support.
TAIL_RELIEFS=json.loads((O/'solder-tail-reliefs.json').read_text())
for r in TAIL_RELIEFS:
 x,y=r['center_box_mm'];base=base.cut(Part.makeCylinder(r['radius_mm'],3.8,V(x,y,r['bottom_z_mm'])))
for x,y in LID:base=base.fuse(Part.makeCylinder(4,44,V(x,y,0)))
landing=Part.makeBox(W,H,5,V(0,0,39)).cut(Part.makeBox(W-12,H-12,6,V(6,6,39)))
PATCHES=[(0,H/2-15,15,30),(W-15,H/2-15,15,30),(W/2-15,0,30,15),(W/2-15,H-15,30,15)]
for x,y,l,w in PATCHES:landing=landing.fuse(Part.makeBox(l,w,5,V(x,y,39)))
for sx,sy in [(1,1),(-1,1),(1,-1),(-1,-1)]:
 pts=[V(x if sx>0 else W-x,y if sy>0 else H-y,39) for x,y in [(0,0),(22,0),(0,22),(0,0)]];landing=landing.fuse(Part.Face(Part.makePolygon(pts)).extrude(V(0,0,5)))
base=base.fuse(landing)
for x,y in LID:base=base.cut(Part.makeCylinder(2,4.9,V(x,y,39.1)))
for x in GLANDS:base=base.cut(Part.makeCylinder(8.1,5,V(x,H+1,27),V(0,-1,0)))
# Blind interior bond boss, above/behind the PCB corner; no exterior penetration.
BOND=(W-8,H-25,14);base=base.fuse(Part.makeBox(8,12,18,V(W-8,H-31,3))).cut(Part.makeCylinder(2,4.9,V(*BOND),V(1,0,0)))
wire=Part.makePolygon([V(x,y,0) for x,y in SEAL+[SEAL[0]]])
def ring(width):
 faces=[Part.Face(wire.makeOffset2D(d,join=2)) for d in [-width/2,width/2]];faces.sort(key=lambda f:f.Area);return faces[1].cut(faces[0])
groove=ring(3.4).extrude(V(0,0,1.5));groove.translate(V(0,0,42.5));base=base.cut(groove)
for x,y in PCB:base=base.cut(Part.makeCylinder(3.4,9,V(x,y,36)))
gasket=ring(3).extrude(V(0,0,2))
lid=Part.makeBox(W+4,H+4,3,V(-2,-2,0)).fuse(Part.makeBox(W+4,H+4,4,V(-2,-2,3)).cut(Part.makeBox(W+.8,H+.8,5,V(-.4,-.4,3))))
# Installed lid bond at W-10,H-25. Flip about H/2 for print orientation.
lid_bond=(W-10,25);lid=lid.fuse(Part.makeCylinder(3.5,5.5,V(*lid_bond,3))).cut(Part.makeCylinder(2,4.9,V(*lid_bond,3.6)))
for x,y in LID:lid=lid.cut(Part.makeCylinder(1.7,4,V(x,y,-.5)))
liner=Part.makeBox(W-10,H-10,34).cut(Part.makeBox(W-12,H-12,34,V(1,1,1)))
for x,y in PCB:liner=liner.cut(Part.makeCylinder(6.4,2,V(x-5,y-5,0)))
for x,y in LID:liner=liner.cut(Part.makeCylinder(4.6,36,V(x-5,y-5,-1)))
for x in GLANDS:liner=liner.cut(Part.makeCylinder(9,4,V(x-5,H-12,23.8),V(0,1,0)))
liner=liner.cut(Part.makeBox(10,14,19,V(W-14,H-37,-.2)))
faces=[Part.Face(wire.makeOffset2D(d,join=2)) for d in [-2.5,2.5]];faces.sort(key=lambda f:f.Area);cover_face=faces[0].common(Part.makePlane(W-15,H-15,V(7.5,7.5,0)))
for x,y,l,w in PATCHES:cover_face=cover_face.cut(Part.makePlane(l+4,w+4,V(x-2,y-2,0)))
for sx,sy in [(1,1),(-1,1),(1,-1),(-1,-1)]:
 pts=[V(x if sx>0 else W-x,y if sy>0 else H-y,0) for x,y in [(0,0),(24,0),(0,24),(0,0)]];cover_face=cover_face.cut(Part.Face(Part.makePolygon(pts)))
cover_face=cover_face.cut(Part.Face(Part.Wire(Part.makeCircle(4,V(W-10,H-25,0)))))
cover=cover_face.extrude(V(0,0,.8));cover.translate(V(-7.5,-7.5,0));cover.rotate(V(0,(H-15)/2,.4),V(1,0,0),180)
coupon=Part.makeBox(30,12,7)
for x,d in [(5,4),(15,4.1),(25,4.2)]:coupon=coupon.cut(Part.makeCylinder(d/2,4.9,V(x,6,2.1)))
doc=A.newDocument('ECU_A3_Compact_Splash_Enclosure');result={}
for name,shape in [('base',base),('lid',lid),('insulating_tray',liner),('lid_insulator',cover),('insert_fit_coupon',coupon)]:
 shape=shape.removeSplitter();assert shape.isValid() and len(shape.Solids)==1,name
 obj=doc.addObject('PartDesign::Feature',name);obj.Shape=shape;Part.export([obj],str(O/f'{name}.step'))
 # Mesh the exported STEP so shared-edge tolerances match the exchange artifact.
 exchanged=Part.Shape();exchanged.read(str(O/f'{name}.step'))
 mesh=MeshPart.meshFromShape(Shape=exchanged,LinearDeflection=.06,AngularDeflection=.08,Relative=False);assert mesh.isSolid(),name;mesh.write(str(O/f'{name}.stl'))
 result[name]={'valid_solid':True,'closed_mesh':True,'size_mm':[shape.BoundBox.XLength,shape.BoundBox.YLength,shape.BoundBox.ZLength]}
obj=doc.addObject('PartDesign::Feature','Gasket_SHEET_REFERENCE_DO_NOT_PRINT');obj.Shape=gasket;Part.export([obj],str(O/'gasket-sheet-reference.step'))
(R/'.cache/a3').mkdir(parents=True,exist_ok=True);MeshPart.meshFromShape(Shape=gasket,LinearDeflection=.06,AngularDeflection=.08,Relative=False).write(str(R/'.cache/a3/gasket-preview.stl'))
doc.recompute();doc.saveAs(str(O/'ecu-a3-enclosure.FCStd'))
def svg(name,w,h,body):(O/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}"><g fill="none" stroke="black" stroke-width="0.15">'+body+'</g></svg>')
def paths(shape,flip=False):return ''.join('<path d="M '+' L '.join(f'{v.x:.4f} {H-v.y if flip else v.y:.4f}' for v in w.discretize(Deflection=.01))+' Z"/>' for w in shape.Wires)
svg('gasket-cut-template.svg',W,H,paths(ring(3)));svg('shield-lid-template.svg',W,H,paths(cover_face,True))
outline=f'<rect x="0" y="0" width="{W-6}" height="{H-6}"/>';holes=''.join(f'<circle cx="{x-3}" cy="{y-3}" r="6.5"/>' for x,y in PCB)+''.join(f'<circle cx="{x-3}" cy="{y-3}" r="4.7"/>' for x,y in LID)
svg('shield-floor-template.svg',W-6,H-6,outline+holes+f'<rect x="{W-11}" y="{H-34}" width="8" height="14"/>')
svg('shield-rear-template.svg',W-6,35,f'<rect x="0" y="0" width="{W-6}" height="35"/>'+''.join(f'<circle cx="{x-3}" cy="24" r="8.3"/>' for x in GLANDS))
svg('shield-side-template.svg',H-6,35,f'<rect x="0" y="0" width="{H-6}" height="35"/>')
shutil_source=R/'enclosure/a2/hardware.csv';(O/'hardware.csv').write_bytes(shutil_source.read_bytes())
params={'revision':'A3-120','pcb_mounts_mm':PCB,'pcb_boss_diameter_mm':10,'solder_tail_reliefs':TAIL_RELIEFS,'maximum_solder_tail_length_mm':3,'pcb_support_height_above_floor_mm':6,'pcb_support_top_z_mm':9,'pcb_insert_bore_depth_mm':4.9,'pcb_insert_bore_bottom_z_mm':4.1,'insert_bore_diameter_mm':4,'insert_length_mm':4,'insert_recess_below_support_mm':.4,'lid_fasteners_mm':LID,'lid_insert_bore_bottom_z_mm':39.1,'internal_shield_bond_mm':BOND,'internal_shield_bond_axis':[1,0,0],'internal_lid_bond_xy_mm':[W-10,H-25],'lid_bond_closed_face_z_mm':38.5,'gasket_centerline_mm':SEAL,'gasket_width_mm':3,'gasket_free_thickness_mm':2,'gasket_groove_width_mm':3.4,'gasket_groove_depth_mm':1.5,'nominal_gasket_compression_percent':25,'cable_entry_center_height_mm':27,'cable_entry_x_mm':GLANDS,'maximum_gland_flange_diameter_mm':24,'assembled_outer_mm':[W+4,H+4,47],'base_outer_mm':[W,H,44],'tray_installation_origin_mm':[5,5,3.2],'board_origin_mm':[9,9,9],'pcb_size_mm':[120,120],'exterior_screw_holes_into_electronics':0,'physical_fit_tested':False,'splash_tested':False,'ingress_rating':None}
(O/'dimensions.json').write_text(json.dumps(params,indent=2));(O/'validation.json').write_text(json.dumps({'parts':result,**params,'emi_tested':False},indent=2));print('A3 enclosure CAD and closed meshes generated')
