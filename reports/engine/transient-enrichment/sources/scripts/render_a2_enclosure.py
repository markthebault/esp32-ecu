"""Blender render of the R2 printed geometry; metallic inserts are envelopes."""
import bpy
from pathlib import Path
from mathutils import Vector
import json
R=Path(__file__).resolve().parents[1];O=R/'enclosure/a2';d=json.loads((O/'dimensions.json').read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def material(name,color):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1);return m
shell=material('Printed case',(.12,.17,.22));dielectric=material('Dielectric covers',(.55,.61,.66));brass=material('Insert envelope',(.62,.39,.08));seal=material('Compressed sheet gasket',(.03,.43,.7))
def load(path,loc,mat,scale=(1,1,1)):
 bpy.ops.wm.stl_import(filepath=str(path));o=bpy.context.object;o.location=loc;o.scale=scale;o.data.materials.append(mat);return o
load(O/'base.stl',(0,0,0),shell);load(O/'insulating_tray.stl',(5,5,3.2),dielectric)
load(O/'lid.stl',(240,0,0),shell);load(O/'lid_insulator.stl',(247.5,7.5,3),dielectric)
load(R/'.cache/a2/gasket-preview.stl',(0,0,42.5),seal,(1,1,.75))
# Visible top collars locate the installed brass inserts without fictional screw threads.
for points,z in [(d['pcb_mounts_mm'],8.6),(d['lid_fasteners_mm'],43.6)]:
 for x,y in points:
  bpy.ops.mesh.primitive_torus_add(major_radius=1.7,minor_radius=.3,major_segments=32,minor_segments=8,location=(x,y,z));bpy.context.object.data.materials.append(brass)
bpy.ops.mesh.primitive_torus_add(major_radius=1.7,minor_radius=.3,major_segments=32,minor_segments=8,location=(210.4,157,14),rotation=(0,1.5707963268,0));bpy.context.object.data.materials.append(brass)
bpy.ops.mesh.primitive_torus_add(major_radius=1.7,minor_radius=.3,major_segments=32,minor_segments=8,location=(448,61,8.1));bpy.context.object.data.materials.append(brass)
bpy.ops.object.camera_add(location=(540,650,890));cam=bpy.context.object;cam.rotation_euler=(Vector((225,109,14))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.clip_end=5000;cam.data.type='ORTHO';cam.data.ortho_scale=555;bpy.context.scene.camera=cam
for loc,power,size in [((100,450,700),3200000,450),((450,-100,600),2100000,350)]:
 bpy.ops.object.light_add(type='AREA',location=loc);bpy.context.object.data.energy=power;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=size
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=40;scene.world.color=(.3,.3,.3);scene.render.resolution_x=1500;scene.render.resolution_y=950;scene.render.resolution_percentage=100;scene.render.film_transparent=True;scene.render.image_settings.file_format='PNG';scene.render.filepath=str(O/'enclosure-3d.png');bpy.ops.wm.save_as_mainfile(filepath=str(O/'enclosure.blend'));bpy.ops.render.render(write_still=True)

# Direct top view exposes all four PCB mounts for assembly.
cam.location=(109,109,600);cam.rotation_euler=(Vector((109,109,0))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=236;scene.render.resolution_x=1200;scene.render.resolution_y=1200;scene.render.filepath=str(O/'pcb-mounts-top.png');bpy.ops.render.render(write_still=True)
