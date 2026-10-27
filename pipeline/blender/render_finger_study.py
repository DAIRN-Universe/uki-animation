"""Render an A/B study from the SAME articulated mesh, plus a curl clip.

blender -b model.blend -t 4 --python-exit-code 1 \
  --python pipeline/blender/render_finger_study.py -- --output output/finger-study
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def aim(camera, point):
    camera.rotation_euler = (Vector(point)-camera.location).to_track_quat('-Z','Y').to_euler()


def distances(rig):
    """Nearest cover/page distances, not a collision-free-grasp assertion."""
    dg = bpy.context.evaluated_depsgraph_get()
    verts, faces = [], []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or not obj.name.startswith(('Cover.', 'Page block.', 'TurningPage')):
            continue
        evaluated = obj.evaluated_get(dg)
        data = evaluated.to_mesh()
        try:
            offset = len(verts)
            verts += [obj.matrix_world @ v.co for v in data.vertices]
            faces += [tuple(offset+i for i in f.vertices) for f in data.polygons]
        finally:
            evaluated.to_mesh_clear()
    bvh = BVHTree.FromPolygons(verts, faces)
    result = {}
    for side in ('L','R'):
        for j in range(3):
            bone = rig.pose.bones[f'feathers{j+1}_tip.{side}']
            point = rig.matrix_world @ bone.tail
            nearest, normal, index, distance = bvh.find_nearest(point)
            result[f'{j+1}.{side}'] = round(distance,6)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    out = args.output.resolve()
    repo = Path(__file__).resolve().parents[2]
    if out.exists() or not (out.is_relative_to(repo/'output') or out.is_relative_to(repo/'.local-assets')):
        raise RuntimeError('Choose a new ignored output directory')
    out.mkdir(parents=True)
    scene = bpy.context.scene
    assert scene.get('finger_segments') == 2
    rig = bpy.data.objects['UkiRig']
    scene.frame_set(73)
    bpy.context.view_layer.update()
    # Freeze the book interaction, then vary only the finger joints for A/B.
    for obj in scene.objects:
        if obj.animation_data:
            obj.animation_data.action = None
    camera = scene.camera
    camera.location = (-1.9,-3.2,1.7)
    camera.data.ortho_scale = 1.65
    aim(camera,(-.22,-.64,1.12))
    scene.render.resolution_x,scene.render.resolution_y = 800,640
    fingers = [b for b in rig.pose.bones if b.name.startswith('feathers')]
    original = {b.name: b.rotation_euler.copy() for b in fingers}
    metrics = {}
    for label,amount in [('straight',0),('curled',1)]:
        for b in fingers:
            b.rotation_euler = original[b.name]
            b.rotation_euler.x *= amount
        bpy.context.view_layer.update()
        metrics[label] = distances(rig)
        scene.render.filepath = str(out/f'fingers_{label}.png')
        bpy.ops.render.render(write_still=True)
    # Repeatable close-up of the articulation, holding the book/root still.
    scene.frame_start,scene.frame_end = 1,49
    for frame in range(1,50):
        t = (frame-1)/48
        amount = math.sin(math.pi*t)**2
        for b in fingers:
            b.rotation_euler = original[b.name]
            b.rotation_euler.x *= amount
            b.keyframe_insert(data_path='rotation_euler',frame=frame)
    for fc in rig.animation_data.action.fcurves:
        for p in fc.keyframe_points:
            p.interpolation = 'LINEAR'
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.render_aa = '8'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_cavity = True
    scene.render.resolution_x,scene.render.resolution_y = 640,480
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.filepath = str(out/'finger_curl.mp4')
    bpy.ops.render.render(animation=True)
    report = {'purpose':'Same mesh, same book pose, straight vs curled finger chains',
              'nearest_surface_distances':metrics,
              'limits':'Distances alone do not establish contact, normal alignment, penetration, or a page grip.'}
    (out/'finger-study.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
