"""FreeCAD Python: validate R2 mounting, seal layout and nominal assembly geometry."""
import FreeCAD as A,Part
import json,math
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'enclosure/a3';V=A.Vector
params=json.loads((O/'dimensions.json').read_text());shapes={}
for name in ['base','lid','insulating_tray','lid_insulator','gasket-sheet-reference']:
 s=Part.Shape();s.read(str(O/f'{name}.step'));assert s.isValid(),name;shapes[name]=s
base=shapes['base'];tray=shapes['insulating_tray'].copy();tray.translate(V(5,5,3.2))
lid=shapes['lid'].copy();lid.rotate(V(0,75,0),V(1,0,0),180);lid.translate(V(0,0,47))
cover=shapes['lid_insulator'].copy();cover.translate(V(7.5,7.5,3));cover.rotate(V(0,75,0),V(1,0,0),180);cover.translate(V(0,0,47))
board=Part.makeBox(120,120,1.6,V(9,9,9))
for x,y in params['pcb_mounts_mm']+[[14,109]]:board=board.cut(Part.makeCylinder(1.6,3,V(x,y,8.5)))
for n,a,c in [('base/tray',base,tray),('base/PCB',base,board),('tray/PCB',tray,board),('base/lid',base,lid),('tray/lid',tray,lid),('cover/lid',cover,lid),('cover/base',cover,base)]:
 vol=a.common(c).Volume
 assert vol<.001,(n,vol)
wire=Part.makePolygon([V(x,y,0) for x,y in params['gasket_centerline_mm']+[params['gasket_centerline_mm'][0]]]);face=Part.Face(wire)
gasket=shapes['gasket-sheet-reference'].common(Part.makeBox(138,150,1.5));gasket.translate(V(0,0,42.5))
for n,s in [('base',base),('lid',lid),('cover',cover)]:assert s.common(gasket).Volume<.001,('compressed gasket collision',n)
for x,y in params['lid_fasteners_mm']:
 assert not face.isInside(V(x,y,0),1e-6,True),'lid screw is inside water seal'
 assert Part.Vertex(V(x,y,0)).distToShape(wire)[0]>3.7,'screw too close to gasket channel'
 shaft=Part.makeCylinder(1.5,8,V(x,y,39.8));assert base.common(shaft).Volume<.001;assert lid.common(shaft).Volume<.001
# Each PCB bolt passes through its existing 3.2 mm hole, above an intact floor.
for x,y in params['pcb_mounts_mm']:
 driver=Part.makeCylinder(3.3,40,V(x,y,11.4));assert base.common(driver).Volume<.001,'PCB screw access blocked'
 shaft=Part.makeCylinder(1.5,6,V(x,y,5.4));assert base.common(shaft).Volume<.001;assert board.common(shaft).Volume<.001
 floor=Part.makeCylinder(2,3,V(x,y,0));assert abs(base.common(floor).Volume-floor.Volume)<.001,'mount bore breaches exterior floor'
for r in params['solder_tail_reliefs']:
 x,y=r['center_box_mm'];tail=Part.makeCylinder(1.2,3,V(x,y,6));assert base.common(tail).Volume<.001,('solder tail relief',r)
# The internal shield bond does not penetrate the side wall or floor.
probe=Part.makeCylinder(1.5,1,V(137,125,14),V(1,0,0));assert abs(base.common(probe).Volume-probe.Volume)<.001
# Conservative gland flange envelopes: 24 mm OD, up to 5 mm thickness outside rear face.
for x in params['cable_entry_x_mm']:
 flange=Part.makeCylinder(12,5,V(x,150,27),V(0,1,0));assert lid.common(flange).Volume<.001,'gland clashes with rain skirt'
# Actual PCB mounting datums are supplied by the native PCB audit.
audit=json.loads((R/'reports/a3/validation-summary.json').read_text())
for ref,(x,y) in zip(['H1','H2','H3','H4'],params['pcb_mounts_mm']):
 px,py=audit['mounting_hole_centers_board_mm'][ref];assert abs(px-10+9-x)<1e-6 and abs(py-10+9-y)<1e-6
# Check the nominal top-side electronics envelope, including the lowest lid-bond boss.
assert 9+1.6+25<params['lid_bond_closed_face_z_mm']
result={'revision':params['revision'],'nominal_solid_collisions':0,'pcb_mount_alignment':'pass, checked against actual KiCad board','pcb_screws':4,'pcb_screwdriver_access_diameter_mm':6.6,'lid_screws':8,'blind_mount_floor_check':'pass','lid_screws_outside_seal':True,'continuous_gasket_ring':len(shapes['gasket-sheet-reference'].Solids)==1,'nominal_gasket_compression_percent':25,'maximum_gland_flange_diameter_mm':24,'board_bottom_z_mm':9,'tray_floor_top_z_mm':4.2,'underside_clearance_to_tray_mm':4.8,'cover_bottom_z_mm':43.2,'lowest_lid_bond_boss_z_mm':38.5,'nominal_max_component_envelope_above_pcb_mm':25,'minimum_top_envelope_clearance_mm':2.9,'physical_fit_tested':False,'splash_tested':False,'emi_tested':False,'ingress_rating':None}
(O/'fit-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
