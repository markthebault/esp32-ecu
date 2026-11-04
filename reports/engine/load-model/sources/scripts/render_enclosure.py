"""Blender background renderer for the actual exported enclosure meshes."""
import bpy,math
from pathlib import Path
from mathutils import Vector
R=Path(__file__).resolve().parents[1]
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def mat(name,color):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1);return m
shell=mat('Printed graphite polymer',(.12,.17,.22));board=mat('Board envelope reference',(.025,.22,.12))
for name,x in [('base',0),('lid',240)]:
 bpy.ops.wm.stl_import(filepath=str(R/'enclosure'/f'{name}.stl'));o=bpy.context.object;o.location.x=x;o.data.materials.append(shell)
bpy.ops.mesh.primitive_cube_add(size=1,location=(109,109,9.8));o=bpy.context.object;o.name='PCB envelope only';o.dimensions=(200,200,1.6);o.data.materials.append(board)
# Add component-height envelope markers only at the mounting holes, not fictional electronics.
bpy.ops.object.camera_add(location=(590,-620,610));cam=bpy.context.object;cam.rotation_euler=(Vector((225,105,10))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.clip_end=5000;cam.data.type='ORTHO';cam.data.ortho_scale=560;bpy.context.scene.camera=cam
for loc,power,size in [((100,-150,500),2200000,400),((400,300,450),1600000,300)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.shape='DISK';l.data.size=size
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32;scene.world.color=(.3,.3,.3);scene.render.resolution_x=1500;scene.render.resolution_y=850;scene.render.resolution_percentage=100;scene.render.film_transparent=True;scene.render.image_settings.file_format='PNG';scene.render.filepath=str(R/'enclosure/enclosure-3d.png');bpy.ops.wm.save_as_mainfile(filepath=str(R/'enclosure/enclosure.blend'));bpy.ops.render.render(write_still=True)
