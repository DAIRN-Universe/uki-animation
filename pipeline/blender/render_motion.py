"""Render a small review clip from a saved character scene (no .blend mutation)."""
import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def render_motion(out):
    scene = bpy.context.scene
    camera = scene.camera
    camera.location = (1.8,-8,3.2)
    camera.data.ortho_scale = 4.5
    camera.rotation_euler = (Vector((0,-.15,1.45))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.render_aa = '8'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.render.resolution_x,scene.render.resolution_y = 640,480
    # Keep the authored 24 FPS timing: review every third frame at 8 FPS.
    scene.frame_step = 3
    scene.render.fps = 8
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.filepath = str(out)
    bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    repo = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    if out.exists() or not (out.is_relative_to(repo/'output') or out.is_relative_to(repo/'.local-assets')):
        raise RuntimeError('Choose a new ignored movie path')
    out.parent.mkdir(parents=True,exist_ok=True)
    render_motion(out)
