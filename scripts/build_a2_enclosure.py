"""FreeCAD Python. A2-R2 PCB mounts and splash-resistant enclosure design.
The gasket is cut from sheet, not printed. No ingress rating is claimed.
"""
import FreeCAD as A,Part,MeshPart
import json,csv
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'enclosure/a2';O.mkdir(exist_ok=True);V=A.Vector
INSERT_BORE=4.0 # Nominal ruthex M3/M3S bore. Check the coupon with the actual printer/material.
PCB_HOLES=[(13,13),(205,13),(13,205),(205,205)]
LID_HOLES=[(4.5,4.5),(213.5,4.5),(4.5,213.5),(213.5,213.5),(109,4.5),(109,213.5),(4.5,109),(213.5,109)]
SEAL=[(15,3),(97,3),(104,12),(114,12),(121,3),(203,3),(215,15),(215,97),(206,104),(206,114),(215,121),(215,203),(203,215),(121,215),(114,206),(104,206),(97,215),(15,215),(3,203),(3,121),(12,114),(12,104),(3,97),(3,15)]
base=Part.Shape();base.read(str(R/'enclosure/base.step'))
# Retain the original 218 mm body; close all old front penetrations.
base=base.fuse(Part.makeBox(212,3,44,V(3,0,0)))
# Fill the four original PCB pilots, enlarge the supports and flare their roots.
for x,y in PCB_HOLES:
 base=base.fuse(Part.makeCylinder(5,8,V(x,y,1)))
 base=base.fuse(Part.makeCone(6,5,2,V(x,y,3)))
 # Blind bore leaves the complete 3 mm exterior floor untouched.
 base=base.cut(Part.makeCylinder(INSERT_BORE/2,4.9,V(x,y,4.1)))
# Eight lid fasteners, with their blind inserts entirely outboard of the seal.
for i,(x,y) in enumerate(LID_HOLES):
 if i<4:base=base.fuse(Part.makeCylinder(1.26,12,V(x,y,32))) # close old pilot
 else:base=base.fuse(Part.makeCylinder(4,44,V(x,y,0)))
 base=base.cut(Part.makeCylinder(INSERT_BORE/2,4.9,V(x,y,39.1)))
# A wider upper landing carries the gasket and distributes lid clamp pressure.
landing=Part.makeBox(218,218,5,V(0,0,39)).cut(Part.makeBox(206,206,6,V(6,6,39)))
for x,y,l,w in [(0,94,15,30),(203,94,15,30),(94,0,30,15),(94,203,30,15)]:landing=landing.fuse(Part.makeBox(l,w,5,V(x,y,39)))
for sx,sy in [(1,1),(-1,1),(1,-1),(-1,-1)]:
 pts=[(0,0),(22,0),(0,22),(0,0)]
 pts=[V(x if sx>0 else 218-x,y if sy>0 else 218-y,39) for x,y in pts]
 landing=landing.fuse(Part.Face(Part.makePolygon(pts)).extrude(V(0,0,5)))
base=base.fuse(landing)
# Recut insert bores through the new landing.
for x,y in LID_HOLES:base=base.cut(Part.makeCylinder(INSERT_BORE/2,4.9,V(x,y,39.1)))
# Rear cable entries: use gland panel washers and jacketed cables.
for x in [40,85,130,175]:base=base.cut(Part.makeCylinder(8.1,5,V(x,219,27),V(0,-1,0)))
# Keep the shield bond inside. There is no unsealed side stud penetration.
base=base.fuse(Part.makeBox(8,12,18,V(210,151,3)))
base=base.cut(Part.makeCylinder(INSERT_BORE/2,4.9,V(210,157,14),V(1,0,0)))
# Offset the closed centreline to obtain a continuous 3.4 mm wide groove.
wire=Part.makePolygon([V(x,y,0) for x,y in SEAL+[SEAL[0]]])
def ring(width):
 faces=[Part.Face(wire.makeOffset2D(d,join=2)) for d in [-width/2,width/2]]
 faces.sort(key=lambda f:f.Area);return faces[1].cut(faces[0])
groove=ring(3.4).extrude(V(0,0,1.5));groove.translate(V(0,0,42.5));base=base.cut(groove)
# Open screwdriver/washer access above each PCB mount without cutting the seal.
for x,y in PCB_HOLES:base=base.cut(Part.makeCylinder(3.4,9,V(x,y,36)))
gasket=ring(3.0).extrude(V(0,0,2.0)) # reference geometry only; cut 2 mm gasket sheet
# Lid outside face is on the print bed. Its down-facing rain skirt prints upward.
lid=Part.makeBox(222,222,3,V(-2,-2,0))
skirt=Part.makeBox(222,222,4,V(-2,-2,3)).cut(Part.makeBox(218.8,218.8,5,V(-.4,-.4,3)))
lid=lid.fuse(skirt)
# Blind internal boss bonds the removable lid lining to the base lining.
lid=lid.fuse(Part.makeCylinder(3.5,5.5,V(208,61,3)))
lid=lid.cut(Part.makeCylinder(INSERT_BORE/2,4.9,V(208,61,3.6)))
for x,y in LID_HOLES:lid=lid.cut(Part.makeCylinder(1.7,4,V(x,y,-.5)))
# The dielectric tray clears all supports and the new internal shield-bond boss.
liner=Part.makeBox(208,208,34).cut(Part.makeBox(206,206,34,V(1,1,1)))
for x,y in PCB_HOLES:liner=liner.cut(Part.makeCylinder(6.4,2,V(x-5,y-5,0)))
for i,(x,y) in enumerate(LID_HOLES):liner=liner.cut(Part.makeCylinder(5.2 if i<4 else 4.6,36,V(x-5,y-5,-1)))
for x in [40,85,130,175]:liner=liner.cut(Part.makeCylinder(9,4,V(x-5,206,23.8),V(0,1,0)))
liner=liner.cut(Part.makeBox(10,14,19,V(204,145,-.2)))
# The cover must stay inside the water-seal detours, clear of the gasket.
inner_faces=[Part.Face(wire.makeOffset2D(d,join=2)) for d in [-2.5,2.5]]
inner_faces.sort(key=lambda f:f.Area)
lid_cover_face=inner_faces[0].common(Part.makePlane(203,203,V(7.5,7.5,0)))
# Clear the upper landing patches and the internal lid-bond boss.
for x,y,l,w in [(0,93,17,32),(201,93,17,32),(93,0,32,17),(93,201,32,17)]:lid_cover_face=lid_cover_face.cut(Part.makePlane(l,w,V(x,y,0)))
for sx,sy in [(1,1),(-1,1),(1,-1),(-1,-1)]:
 pts=[V(x if sx>0 else 218-x,y if sy>0 else 218-y,0) for x,y in [(0,0),(24,0),(0,24),(0,0)]]
 lid_cover_face=lid_cover_face.cut(Part.Face(Part.makePolygon(pts)))
lid_cover_face=lid_cover_face.cut(Part.Face(Part.Wire(Part.makeCircle(4,V(208,157,0)))))
lid_liner=lid_cover_face.extrude(V(0,0,.8));lid_liner.translate(V(-7.5,-7.5,0));lid_liner.rotate(V(0,101.5,.4),V(1,0,0),180)
# Small first-print coupon: left-to-right nominal 4.0 / 4.1 / 4.2 mm bores.
coupon=Part.makeBox(30,12,7)
for x,d in [(5,4.0),(15,4.1),(25,4.2)]:coupon=coupon.cut(Part.makeCylinder(d/2,4.9,V(x,6,2.1)))
doc=A.newDocument('ECU_A2_R2_Splash_Enclosure');result={}
for name,shape in [('base',base),('lid',lid),('insulating_tray',liner),('lid_insulator',lid_liner),('insert_fit_coupon',coupon)]:
 shape=shape.removeSplitter();assert shape.isValid() and len(shape.Solids)==1,name
 obj=doc.addObject('PartDesign::Feature',name);obj.Shape=shape
 Part.export([obj],str(O/f'{name}.step'))
 m=MeshPart.meshFromShape(Shape=shape,LinearDeflection=.06,AngularDeflection=.12,Relative=False);assert m.isSolid(),name;m.write(str(O/f'{name}.stl'))
 result[name]={'valid_solid':True,'closed_mesh':True,'size_mm':[shape.BoundBox.XLength,shape.BoundBox.YLength,shape.BoundBox.ZLength]}
obj=doc.addObject('PartDesign::Feature','Gasket_SHEET_REFERENCE_DO_NOT_PRINT');obj.Shape=gasket;Part.export([obj],str(O/'gasket-sheet-reference.step'))
(R/'.cache/a2').mkdir(parents=True,exist_ok=True)
MeshPart.meshFromShape(Shape=gasket,LinearDeflection=.06,AngularDeflection=.12,Relative=False).write(str(R/'.cache/a2/gasket-preview.stl'))
doc.recompute();doc.saveAs(str(O/'ecu-a2-enclosure.FCStd'))
# Gasket: one-piece cutting template, 1:1 millimetres, with no screw holes.
def svg(name,w,h,body):
 (O/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}"><g fill="none" stroke="black" stroke-width="0.15">'+body+'</g></svg>')
paths=[]
for w in ring(3).Wires:
 points=w.discretize(Deflection=.01);paths.append('<path d="M '+' L '.join(f'{v.x:.4f} {v.y:.4f}' for v in points)+' Z"/>')
svg('gasket-cut-template.svg',218,218,''.join(paths))
# Lining stays below the gasket land. Trim at the support reliefs, never across the water seal.
outline='<path d="M8 0 H204 L212 8 V204 L204 212 H8 L0 204 V8 Z"/>'
holes=''.join(f'<circle cx="{x-3}" cy="{y-3}" r="6.5"/>' for x,y in PCB_HOLES)
holes+=''.join(f'<circle cx="{x-3}" cy="{y-3}" r="{5.0 if i<4 else 4.5}"/>' for i,(x,y) in enumerate(LID_HOLES))
svg('shield-floor-template.svg',212,212,outline+holes+'<rect x="207" y="147" width="5" height="14"/>')
foil_paths=[]
for w in lid_cover_face.Wires:
 points=w.discretize(Deflection=.01);foil_paths.append('<path d="M '+' L '.join(f'{v.x:.4f} {218-v.y:.4f}' for v in points)+' Z"/>')
svg('shield-lid-template.svg',218,218,''.join(foil_paths))
svg('shield-rear-template.svg',212,35,'<rect x="0" y="0" width="212" height="35"/>'+''.join(f'<circle cx="{x-3}" cy="24" r="8.3"/>' for x in [40,85,130,175]))
svg('shield-wall-template.svg',212,35,'<rect x="0" y="0" width="212" height="35"/>')
for name in ['shield-front-template.svg','shield-bond-wall-template.svg']:
 if (O/name).exists():(O/name).unlink()
hardware=[
 [4,'M3 x 6 mm pan-head screws','PCB mounts, with 0.8 mm nylon washers'],
 [4,'M3 nylon washers, 0.8 mm thick, about 6 mm OD','Insulate PCB screw heads'],
 [8,'M3 x 8 mm pan-head screws','Lid; use the specified washers'],
 [8,'M3 flat washers, 0.8 mm thick','Lid clamping'],
 [14,'ruthex RX-M3Sx4.0 short heat-set inserts','4 PCB + 8 lid + 2 internal shield bonds; 4.0 mm nominal bore'],
 [2,'M3 x 5 mm screws with ring terminals/star washers','Internal base and lid lining bonds; no wall penetrations, allow at least 1 mm terminal/washer stack'],
 [1,'M3 x 6 mm bolt, nut and ring terminal','PCB shield lug H5; check underside nut clearance'],
 [1,'2.0 mm soft closed-cell silicone gasket sheet','Cut one continuous 3 mm wide ring using template; nominal 25% compression'],
 [4,'M16 cable glands or gasketed blanking plugs','Match jacket OD and use panel sealing washers; no loose wires through single-hole glands']]
with (O/'hardware.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['Quantity','Item','Use']);w.writerows(hardware)
params={'revision':'A2-R2','pcb_mounts_mm':PCB_HOLES,'pcb_boss_diameter_mm':10,'pcb_support_height_above_floor_mm':6,'pcb_support_top_z_mm':9,'pcb_insert_bore_depth_mm':4.9,'pcb_insert_bore_bottom_z_mm':4.1,'insert_bore_diameter_mm':INSERT_BORE,'insert_length_mm':4,'insert_recess_below_support_mm':.4,'lid_fasteners_mm':LID_HOLES,'lid_insert_bore_bottom_z_mm':39.1,'internal_shield_bond_mm':[210,157,14],'internal_shield_bond_axis':[1,0,0],'internal_lid_bond_xy_mm':[208,157],'lid_bond_closed_face_z_mm':38.5,'gasket_centerline_mm':SEAL,'gasket_width_mm':3,'gasket_free_thickness_mm':2,'gasket_groove_width_mm':3.4,'gasket_groove_depth_mm':1.5,'nominal_gasket_compression_percent':25,'cable_entry_center_height_mm':27,'maximum_gland_flange_diameter_mm':24,'assembled_outer_mm':[222,222,47],'base_outer_mm':[218,218,44],'tray_installation_origin_mm':[5,5,3.2],'board_origin_mm':[9,9,9],'exterior_screw_holes_into_electronics':0,'physical_fit_tested':False,'splash_tested':False,'ingress_rating':None}
(O/'dimensions.json').write_text(json.dumps(params,indent=2));(O/'validation.json').write_text(json.dumps({'parts':result,**params,'shield_material_required':'conductive lining and internal bonds, separate from water gasket','emi_tested':False},indent=2))
print('Generated A2-R2: four PCB insert mounts, eight lid screws, continuous gasket groove and rain skirt')
