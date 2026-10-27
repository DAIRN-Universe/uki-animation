"""Independent Blender checks against a reopened generated .blend.

blender -b path/to/uki_character_v1.blend -t 4 --python \
  pipeline/blender/verify_uki.py -- --report output/uki-validation.json
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy


def verify():
    cfg = json.loads(Path(__file__).with_name('uki_character.json').read_text())
    repo = Path(__file__).resolve().parents[2]
    for path, digest in cfg['references'].items():
        assert hashlib.sha256((repo/'.local-assets'/path).read_bytes()).hexdigest() == digest, path
    scene = bpy.context.scene
    rig, mesh = bpy.data.objects['UkiRig'], bpy.data.objects['UkiMesh']
    assert len([m for m in mesh.modifiers if m.type == 'ARMATURE' and m.object == rig]) == 1
    segments = scene.get('finger_segments', 1)
    assert len(rig.data.bones) == (23 if segments == 2 else 17)
    assert scene.render.fps == cfg['fps']
    assert scene.get('page_turn_enabled') is False
    assert len(scene.timeline_markers) == 16
    assert all(image.packed_file for image in bpy.data.images if image.name.endswith('.png'))
    assert mesh.data.shape_keys is None
    assert len(mesh.data.materials) >= 10
    assert all(v.groups and abs(sum(g.weight for g in v.groups)-1) < 1e-6 for v in mesh.data.vertices)
    assert all(math.isfinite(c) for v in mesh.data.vertices for c in v.co)
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    boundary = sum(not e.is_manifold for e in bm.edges)
    degenerate = sum(f.calc_area() < 1e-10 for f in bm.faces)
    bm.free()
    assert boundary == 0, f'Non-manifold edges: {boundary}'
    assert degenerate == 0, f'Degenerate faces: {degenerate}'
    lengths = {b.name: b.length for b in rig.data.bones}
    rigid_edges = {e.index for e in mesh.data.edges
                   if len(mesh.data.vertices[e.vertices[0]].groups) == 1
                   and len(mesh.data.vertices[e.vertices[1]].groups) == 1
                   and mesh.data.vertices[e.vertices[0]].groups[0].group == mesh.data.vertices[e.vertices[1]].groups[0].group}
    base_edges = [(mesh.data.vertices[e.vertices[0]].co-mesh.data.vertices[e.vertices[1]].co).length for e in mesh.data.edges]
    max_error, max_edge_delta, max_book_step = 0., 0., 0.
    last_book = None
    for frame in range(scene.frame_start, scene.frame_end+1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for side in ('L', 'R'):
            bone = rig.pose.bones['forearm.'+side]
            target = bpy.data.objects['CTRL_wrist.'+side]
            error = (rig.matrix_world @ bone.tail-target.matrix_world.translation).length
            max_error = max(max_error, error)
            assert error < .001, (frame, side, error)
            assert not bone.constraints['Wing reach'].use_stretch
        for bone in rig.pose.bones:
            assert abs((bone.tail-bone.head).length-lengths[bone.name]) < 1e-4, (frame, bone.name)
        book_pos = bpy.data.objects['BookRoot'].matrix_world.translation.copy()
        if last_book is not None:
            max_book_step = max(max_book_step, (book_pos-last_book).length)
        last_book = book_pos
        if (frame-1) % cfg['phase_spacing'] == 0:
            phase = cfg['phases'][(frame-1)//cfg['phase_spacing']]
            for j, side in enumerate(('L', 'R')):
                if phase['grip'][j] == 1:
                    wrist = rig.matrix_world @ rig.pose.bones['forearm.'+side].tail
                    assert (wrist-bpy.data.objects['Grip.'+side].matrix_world.translation).length < .001
            dg = bpy.context.evaluated_depsgraph_get()
            evaluated = mesh.evaluated_get(dg)
            data = evaluated.to_mesh()
            try:
                assert len(data.vertices) == len(mesh.data.vertices)
                assert len(data.polygons) == len(mesh.data.polygons)
                for edge, base in zip(data.edges, base_edges):
                    if edge.index not in rigid_edges:
                        continue
                    current = (data.vertices[edge.vertices[0]].co-data.vertices[edge.vertices[1]].co).length
                    max_edge_delta = max(max_edge_delta, abs(current-base))
            finally:
                evaluated.to_mesh_clear()
    assert max_edge_delta < 1e-4, max_edge_delta
    assert max_book_step < .2, max_book_step
    return {'status': 'passed', 'blender': bpy.app.version_string,
            'frames_checked': scene.frame_end-scene.frame_start+1,
            'phases_checked': 16, 'finger_segments': segments, 'rigid_edges_checked': len(rigid_edges), 'max_ik_error': max_error,
            'max_mesh_edge_length_delta': max_edge_delta,
            'max_book_step_per_frame': max_book_step,
            'non_manifold_edges': boundary, 'degenerate_faces': degenerate,
            'source_hashes_unchanged': True,
            'limits': 'Checks do not establish collision-free surfaces, artistic match, or production readiness.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = verify()
    args.report.write_text(json.dumps(result, indent=2)+'\n')
    print('UKI VALIDATION', json.dumps(result))
