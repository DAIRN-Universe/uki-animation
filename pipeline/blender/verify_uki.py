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
from mathutils import Vector


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
    assert scene.get('book_opens_toward') == 'uki'
    assert scene.get('independent_wrist_twist') is False
    assert scene.get('book_rotation_locked') is True
    assert len(scene.timeline_markers) == 16
    assert all(image.packed_file for image in bpy.data.images if image.name.endswith('.png'))
    assert mesh.data.shape_keys is None
    assert len(mesh.data.materials) >= 10
    assert all(v.groups and abs(sum(g.weight for g in v.groups)-1) < 1e-6 for v in mesh.data.vertices)
    assert all(math.isfinite(c) for v in mesh.data.vertices for c in v.co)
    wing_preservation=None
    tail_count=None
    if cfg.get('body_model') == 'avian_pear':
        sys.path.insert(0,str(Path(__file__).resolve().parent))
        from verify_wing_preservation import wing_signature
        wing_preservation,_=wing_signature(mesh,rig)
        assert wing_preservation == cfg['wing_reference_signature'], 'Wings changed from v3'
        ids=mesh.data.attributes.get('avian_tail_id')
        assert ids is not None
        tail_ids={item.value for item in ids.data if item.value > 0}
        assert tail_ids == set(range(1,cfg['tail_feather_count']+1))
        tail_count=len(tail_ids)

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
    reader_facing = []
    opening_spine = []
    opening_angles = {}
    book_rotation = None
    max_book_rotation_delta = 0.
    previous_wrists = {}
    max_wrist_step = 0.
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
            wrist_bone = rig.pose.bones['wrist.'+side]
            assert Vector(wrist_bone.rotation_euler).length < 1e-6
            assert all(c.type != 'COPY_ROTATION' for c in wrist_bone.constraints)
            wrist_rotation = wrist_bone.matrix.to_quaternion()
            if side in previous_wrists:
                step = previous_wrists[side].rotation_difference(wrist_rotation).angle
                step = min(step,math.tau-step)
                max_wrist_step = max(max_wrist_step,step)
                assert step < math.pi/4, (frame,side,'Abrupt wing flip',step)
            previous_wrists[side] = wrist_rotation.copy()
            if segments == 2:
                folds = [rig.pose.bones[f'feathers{j}_tip.{side}'].rotation_euler.x for j in (1,2,3)]
                assert max(folds)-min(folds) < 1e-6
        for bone in rig.pose.bones:
            assert abs((bone.tail-bone.head).length-lengths[bone.name]) < 1e-4, (frame, bone.name)
        current_rotation = bpy.data.objects['BookRoot'].matrix_world.to_3x3()
        if book_rotation is None:
            book_rotation = current_rotation.copy()
        max_book_rotation_delta = max(max_book_rotation_delta, max(abs(current_rotation[i][j]-book_rotation[i][j]) for i in range(3) for j in range(3)))
        assert max_book_rotation_delta < 1e-6, 'The whole book rotates'
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
            root = bpy.data.objects['BookRoot']
            if phase['n'] in (5,6,7):
                opening_spine.append(root.matrix_world.translation.copy())
            if phase['n'] == 6:
                front = bpy.data.objects['CoverHinge.R'].matrix_world @ Vector((.45,0,.36))
                assert front.z > root.matrix_world.translation.z + .2, 'Cover opens down through the stand'
            if phase['n'] in (5,7):
                opening_angles[phase['n']] = [bpy.data.objects['CoverHinge.'+side].rotation_euler.z for side in ('L','R')]
            if phase['n'] in (7,9,10):
                head_matrix = (rig.matrix_world @ rig.pose.bones['head'].matrix
                               @ rig.data.bones['head'].matrix_local.inverted())
                eyes = head_matrix @ Vector(cfg.get('eye_reference',(0,-.6,2.25)))
                for sign,side in ((-1,'L'),(1,'R')):
                    hinge = bpy.data.objects['CoverHinge.'+side]
                    # Inner page surface is on +Y, opposite the decorated cover.
                    point = hinge.matrix_world @ Vector((sign*.235,.10,.36))
                    normal = (hinge.matrix_world.to_3x3() @ Vector((0,1,0))).normalized()
                    facing = normal.dot((eyes-point).normalized())
                    reader_facing.append(facing)
                    assert facing > .1, (frame, side, 'Pages face away from Uki', facing)
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
    spine_drift = max((p-opening_spine[0]).length for p in opening_spine)
    assert spine_drift < 1e-6, spine_drift
    cover_travel = [abs(b-a) for a,b in zip(opening_angles[5],opening_angles[7])]
    assert math.degrees(cover_travel[0]) < 45
    assert math.degrees(cover_travel[1]) > 120
    assert max_edge_delta < 1e-4, max_edge_delta
    assert max_book_step < .2, max_book_step
    return {'status': 'passed', 'blender': bpy.app.version_string,
            'frames_checked': scene.frame_end-scene.frame_start+1,
            'phases_checked': 16, 'finger_segments': segments, 'rigid_edges_checked': len(rigid_edges), 'max_ik_error': max_error,
            'max_mesh_edge_length_delta': max_edge_delta,
            'max_book_step_per_frame': max_book_step,
            'non_manifold_edges': boundary, 'degenerate_faces': degenerate,
            'source_hashes_unchanged': True,
            'tail_feather_count': tail_count,
            'wing_preservation_signature': wing_preservation,
            'pages_face_uki_min_dot': min(reader_facing),
            'spine_drift_during_opening': spine_drift,
            'max_book_rotation_matrix_delta': max_book_rotation_delta,
            'independent_wrist_twist': False,
            'max_inherited_wrist_step_degrees': math.degrees(max_wrist_step),
            'coupled_feather_groups': True,
            'cover_opening_degrees': [math.degrees(x) for x in cover_travel],
            'limits': 'Checks do not establish collision-free surfaces, artistic match, or production readiness.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = verify()
    args.report.write_text(json.dumps(result, indent=2)+'\n')
    print('UKI VALIDATION', json.dumps(result))
