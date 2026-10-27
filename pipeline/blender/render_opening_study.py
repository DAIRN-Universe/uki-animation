"""Side inspection of spine, cover and wrist motion; 2x slow motion.

blender -b model.blend -t 4 --python-exit-code 1 \
  --python pipeline/blender/render_opening_study.py -- --output output/opening-new
"""
import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stills-only',action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    out = args.output.resolve()
    repo = Path(__file__).resolve().parents[2]
    if out.exists() or not (out.is_relative_to(repo/'output') or out.is_relative_to(repo/'.local-assets')):
        raise RuntimeError('Choose a new ignored output directory')
    out.mkdir(parents=True)
    scene = bpy.context.scene
    assert scene.get('book_opens_toward') == 'uki'
    camera = scene.camera
    camera.location = (4,-.6,2.1)
    camera.data.ortho_scale = 3.5
    camera.rotation_euler = (Vector((0,-.35,1.5))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x,scene.render.resolution_y = 640,640
    for label,frame in [('closed',49),('opening',61),('open',73)]:
        scene.frame_set(frame)
        scene.render.filepath = str(out/f'opening_side_{label}.png')
        bpy.ops.render.render(write_still=True)
    if args.stills_only:
        return
    scene.frame_start,scene.frame_end,scene.frame_step = 49,73,1
    scene.render.fps = 12
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.render_aa = '8'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_cavity = True
    scene.render.resolution_x,scene.render.resolution_y = 640,480
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.filepath = str(out/'opening_side.mp4')
    bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    main()
