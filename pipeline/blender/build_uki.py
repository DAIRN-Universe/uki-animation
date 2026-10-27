"""Blender 4.0+: reproducible single-mesh Uki prototype, rig and book study.

blender -b --factory-startup -t 4 --python pipeline/blender/build_uki.py -- \
    --output .local-assets/characters/uki/model/v1 --render
No source images are edited; only new output directories are accepted.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

REPO = Path(__file__).resolve().parents[2]
CFG = json.loads(Path(__file__).with_name('uki_character.json').read_text())
PARTS = []
MATS = {}
ARTICULATED = False


def material(name, color, metal=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    node = m.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value = (*color, 1)
    node.inputs['Metallic'].default_value = metal
    node.inputs['Roughness'].default_value = 0.42
    MATS[name] = m


def finish(obj, name, mat, bone=None):
    obj.name = name
    obj.data.materials.append(MATS[mat])
    for p in obj.data.polygons:
        p.use_smooth = True
    if bone:
        group = obj.vertex_groups.new(name=bone)
        group.add(list(range(len(obj.data.vertices))), 1, 'REPLACE')
        PARTS.append(obj)
    return obj


def oval(name, center, scale, mat, bone=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=center)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mat, bone)


def feather(name, start, end, width, depth, mat, bone):
    """Closed tapered volume; rigid weight preserves feather length in all poses."""
    a, b = Vector(start), Vector(end)
    direction = (b-a).normalized()
    side = direction.cross(Vector((0, -1, 0)))
    if side.length < .01:
        side = direction.cross(Vector((1, 0, 0)))
    side.normalize()
    normal = direction.cross(side).normalized()
    verts = [tuple(a)]
    for t in (.12, .3, .5, .7, .88):
        w = math.sin(math.pi*t)**.7
        for j in range(8):
            angle = j*math.tau/8
            p = a.lerp(b, t)+side*(width*w*math.cos(angle))+normal*(depth*w*math.sin(angle))
            verts.append(tuple(p))
    verts.append(tuple(b))
    faces = [(0, 1+(j+1)%8, 1+j) for j in range(8)]
    for row in range(4):
        for j in range(8):
            p = 1+row*8+j
            q = 1+row*8+(j+1)%8
            faces.append((p, q, q+8, p+8))
    faces += [(41, 33+j, 33+(j+1)%8) for j in range(8)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat, bone)


def line(name, points, radius, mat, bone):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    curve.use_fill_caps = True
    spline = curve.splines.new('POLY')
    spline.points.add(len(points)-1)
    for p, xyz in zip(spline.points, points):
        p.co = (*xyz, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    # Curve conversion duplicates cap rings; weld only this ornament/toe.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.select_set(False)
    return finish(obj, name, mat, bone)


def cube(name, center, scale, mat, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(MATS[mat])
    bevel = obj.modifiers.new('Soft edges', 'BEVEL')
    bevel.width = .018
    bevel.segments = 2
    if parent:
        obj.parent = parent
    return obj


def empty(name, parent=None, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_type = 'PLAIN_AXES'
    obj.empty_display_size = .12
    obj.parent = parent
    obj.location = location
    return obj


def skeleton():
    arm = bpy.data.armatures.new('UkiSkeleton')
    rig = bpy.data.objects.new('UkiRig', arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')

    def bone(name, head, tail, parent=None, connected=False):
        b = arm.edit_bones.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = arm.edit_bones[parent]
            b.use_connect = connected
        return b

    bone('root', (0, 0, 0), (0, 0, .25))
    bone('body', (0, 0, .65), (0, 0, 1.65), 'root')
    bone('head', (0, 0, 1.65), (0, 0, 2.3), 'body')
    for sign, side in ((-1, 'L'), (1, 'R')):
        bone('foot.'+side, (sign*.26, 0, .3), (sign*.26, -.24, .12), 'root')
        bone('upper.'+side, (sign*.46, 0, 1.62), (sign*.78, -.05, 1.12), 'body')
        bone('forearm.'+side, (sign*.78, -.05, 1.12), (sign*.72, -.12, .55), 'upper.'+side, True)
        bone('wrist.'+side, (sign*.72, -.12, .55), (sign*.69, -.15, .35), 'forearm.'+side, True)
        for j in range(3):
            x = sign*(.58+j*.14)
            start = Vector((x, -.16, .52))
            end = Vector((x+sign*.08, -.18, .2))
            if ARTICULATED:
                points = [start.lerp(end, t) for t in (0, .55, 1)]
                names = [f'feathers{j+1}.{side}', f'feathers{j+1}_tip.{side}']
                for k, name in enumerate(names):
                    bone(name, points[k], points[k+1], 'wrist.'+side if k == 0 else names[k-1], k > 0)
            else:
                bone(f'feathers{j+1}.{side}', start, end, 'wrist.'+side)
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.show_in_front = True
    arm.display_type = 'OCTAHEDRAL'
    for b in rig.pose.bones:
        b.rotation_mode = 'XYZ'
    rig.select_set(False)
    return rig


def bird(rig):
    oval('Body', (0, 0, 1.08), (.53, .43, .67), 'brown', 'body')
    oval('Breast', (0, -.25, 1.12), (.37, .18, .55), 'cream', 'body')
    oval('Head', (0, 0, 2.16), (.70, .49, .62), 'brown', 'head')
    # Overlapping, closed feather islands around the brown head/back.
    for row in range(5):
        z = 2.56-row*.19
        latitude = (z-2.16)/.65
        radius = math.sqrt(max(.15, 1-latitude**2))
        for j in range(18):
            angle = (j+row*.5)*math.tau/18
            x, y = .66*radius*math.cos(angle), .42*radius*math.sin(angle)
            if y < -.16:
                continue
            feather('Head plumage', (x, y, z+.06), (x*1.08, y*1.09, z-.23), .10, .04,
                    ['brown', 'copper', 'tan'][(j+row)%3], 'head')
    for row in range(4):
        for j in range(11):
            angle = j*math.pi/10
            x, y = .48*math.cos(angle), .34*math.sin(angle)
            z = 1.47-row*.23
            feather('Back plumage', (x, y, z), (x*.94, y*1.1, z-.32), .11, .04,
                    ['copper', 'brown', 'tan'][(row+j)%3], 'body')
    for j in range(5):
        x = (j-2)*.09
        feather('Tail', (x, .25, .9), (x*1.3, .53, .27), .105, .045, 'copper', 'body')
    for row in range(4):
        for j in range(5):
            x = (j-2)*.115
            z = 1.47-row*.2
            feather('Breast feather', (x, -.37, z), (x*.95, -.41, z-.25), .085, .025,
                    'cream' if (j+row)%2 else 'ivory', 'body')
    feather('Forehead mask', (0, -.38, 2.73), (0, -.50, 2.10), .14, .085, 'ivory', 'head')
    feather('Chin mask', (0, -.38, 2.06), (0, -.35, 1.66), .23, .10, 'ivory', 'head')
    for sign in (-1, 1):
        x = sign*.31
        oval('Face disk', (x, -.36, 2.15), (.345, .16, .40), 'ivory', 'head')
        for j in range(7):
            a = j*math.pi/6
            feather('Face fringe', (x+sign*.18*math.sin(a), -.40, 2.44-.48*j/6),
                    (x+sign*(.28+.02*math.sin(a)), -.40, 2.40-.53*j/6), .065, .026, 'cream', 'head')
        oval('Eye outline', (x, -.509, 2.21), (.235, .06, .264), 'navy', 'head')
        oval('Iris gold', (x, -.557, 2.21), (.204, .044, .23), 'gold', 'head')
        oval('Iris blue', (x, -.594, 2.23), (.159, .027, .187), 'blue', 'head')
        oval('Pupil', (x, -.615, 2.25), (.113, .022, .15), 'navy', 'head')
        oval('Eye glint', (x-.045, -.638, 2.32), (.041, .012, .045), 'white', 'head')
        oval('Eye small glint', (x+.038, -.638, 2.23), (.017, .009, .019), 'white', 'head')
        feather('Brow blue', (sign*.10, -.49, 2.48), (sign*.51, -.47, 2.47), .055, .027, 'navy', 'head')
        for j in range(3):
            feather('Blue ear tuft', (sign*(.41+j*.05), -.03, 2.57),
                    (sign*(.43+j*.11), -.015, 3.08-j*.08), .12, .065,
                    ['blue', 'teal', 'navy'][j], 'head')
        points = [(sign*(.48+.07*math.sin(t*3.5)), -.105, 2.65+t*.37) for t in [i/20 for i in range(21)]]
        line('Ear gold inlay', points, .021, 'gold', 'head')
        # Three forward toes and one rear toe per foot; no wing claws.
        side = 'R' if sign == 1 else 'L'
        bone = 'foot.'+side
        oval('Ankle', (sign*.26, 0, .32), (.10, .10, .17), 'gold', bone)
        oval('Foot', (sign*.26, -.09, .17), (.17, .17, .075), 'gold', bone)
        for j in range(3):
            tx = sign*.26+(j-1)*.12
            line('Forward toe', [(sign*.26, -.08, .18), (tx, -.26, .12), (tx, -.35, .10)], .042, 'gold', bone)
            feather('Toe claw', (tx, -.33, .12), (tx, -.43, .045), .045, .035, 'claw', bone)
        line('Rear toe', [(sign*.26, .02, .17), (sign*.26, .20, .10)], .037, 'gold', bone)
        feather('Rear claw', (sign*.26, .18, .12), (sign*.26, .29, .06), .035, .028, 'claw', bone)
        # Shoulder and forearm volumes plus three independent feather groups.
        feather('Wing upper', (sign*.47, -.015, 1.67), (sign*.79, -.08, 1.06), .20, .14, 'blue', 'upper.'+side)
        feather('Wing forearm', (sign*.78, -.06, 1.16), (sign*.72, -.13, .49), .17, .105, 'teal', 'forearm.'+side)
        for j in range(3):
            if ARTICULATED:
                names = [f'feathers{j+1}.{side}', f'feathers{j+1}_tip.{side}']
                for k, name in enumerate(names):
                    bone_data = rig.data.bones[name]
                    head, tail = bone_data.head_local, bone_data.tail_local
                    # Rounded hidden joint; short external feathers overlap at hinges.
                    oval('Finger joint', head, (.043, .037, .043), 'teal', name)
                    for layer in range(2):
                        shift = Vector((sign*(layer-.5)*.045, -.035-layer*.012, 0))
                        feather('Articulated finger feather', head+shift+Vector((0,0,.025)),
                                tail+shift+Vector((0,0,-.035)), .055-layer*.008, .024,
                                'blue' if layer == 0 else 'teal', name)
                finger_skin(rig, names)
            else:
                for k in range(3):
                    x = sign*(.55+j*.13+k*.025)
                    feather('Flight feather', (x, -.18, .58-k*.035),
                            (x+sign*(.03+j*.02), -.20, .12+k*.045), .082, .033,
                            ['blue', 'teal', 'copper'][k], f'feathers{j+1}.{side}')
        for j in range(4):
            feather('Wing covert', (sign*(.46+j*.045), -.15, 1.55-j*.11),
                    (sign*(.62+j*.055), -.19, 1.19-j*.12), .095, .04,
                    ['teal', 'blue'][j%2], 'upper.'+side)
        points = [(sign*(.54+.09*math.sin(t*5.5)), -.195, 1.51-t*.38) for t in [i/30 for i in range(31)]]
        line('Wing gold inlay', points, .026, 'gold', 'upper.'+side)
    feather('Beak', (0, -.51, 2.09), (0, -.70, 1.87), .115, .095, 'gold', 'head')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in PARTS:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = PARTS[0]
    bpy.ops.object.join()
    mesh = bpy.context.object
    mesh.name = 'UkiMesh'
    mod = mesh.modifiers.new('Uki skin', 'ARMATURE')
    mod.object = rig
    mesh.parent = rig
    mesh.select_set(False)
    return mesh


def finger_skin(rig, names):
    """Closed flexible core with blended weights; external feathers stay rigid."""
    start = rig.data.bones[names[0]].head_local
    end = rig.data.bones[names[-1]].tail_local
    direction = (end-start).normalized()
    side = direction.cross(Vector((0,1,0))).normalized()
    normal = direction.cross(side).normalized()
    ts = [0, .15, .35, .45, .50, .55, .60, .65, .75, .9, 1]
    verts, weights = [], []
    for t in ts:
        center = start.lerp(end,t)
        if t <= .45:
            weight = (1,0)
        elif t < .65:
            u = (t-.45)/.20
            weight = (1-u,u)
        else:
            weight = (0,1)
        for j in range(8):
            a = j*math.tau/8
            verts.append(tuple(center+side*(.032*math.cos(a))+normal*(.027*math.sin(a))))
            weights.append(weight)
    faces = [tuple(reversed(range(8)))]
    for row in range(len(ts)-1):
        for j in range(8):
            faces.append((row*8+j,row*8+(j+1)%8,(row+1)*8+(j+1)%8,(row+1)*8+j))
    faces.append(tuple(range((len(ts)-1)*8,len(ts)*8)))
    data = bpy.data.meshes.new('Finger flexible core')
    data.from_pydata(verts,[],faces)
    data.update()
    obj = bpy.data.objects.new('Finger flexible core',data)
    bpy.context.collection.objects.link(obj)
    finish(obj,obj.name,'teal')
    for k,name in enumerate(names):
        group = obj.vertex_groups.new(name=name)
        for i,w in enumerate(weights):
            if w[k] > 0:
                group.add([i],w[k],'REPLACE')
    PARTS.append(obj)


def book():
    root = empty('BookRoot')
    hinges, anchors = {}, {}
    cube('Spine', (0, 0, .36), (.075, .09, .76), 'leather', root)
    for sign, side in ((-1, 'L'), (1, 'R')):
        h = empty('CoverHinge.'+side, root, (sign*.025, 0, 0))
        hinges[side] = h
        cube('Cover.'+side, (sign*.235, 0, .36), (.47, .045, .76), 'leather', h)
        cube('Gold border.'+side, (sign*.235, -.028, .36), (.40, .012, .68), 'gold', h)
        cube('Leather panel.'+side, (sign*.235, -.037, .36), (.36, .012, .64), 'leather', h)
        for j in range(6):
            cube('Page block.'+side+str(j), (sign*.235, .012+j*.003, .36), (.43, .008, .69), 'paper', h)
        # Mid-edge contact markers are explicit, inspectable book children.
        anchors[side] = empty('Grip.'+side, h, (sign*.45, -.06, .35))
    page_hinge = empty('PageHinge', root)
    # Author clarification: static pages only; no page-turn mechanism.
    return root, hinges, anchors, page_hinge


def aim(obj, point):
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def scene_setup():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 24
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 3
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.fps = CFG['fps']
    scene.world.color = (.16, .16, .16)
    scene.view_settings.view_transform = 'Standard'
    cube('Stage', (0, 0, -.06), (200, 200, .1), 'stage')
    for name, loc, energy, size in [('Key', (-3, -4, 7), 800, 5), ('Fill', (4, -2, 4), 500, 4), ('Rim', (1, 3, 6), 900, 3)]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.shape, data.size = energy, 'DISK', size
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = loc
        aim(obj, (0, 0, 1.5))
    data = bpy.data.cameras.new('ReviewCamera')
    camera = bpy.data.objects.new('ReviewCamera', data)
    bpy.context.collection.objects.link(camera)
    data.type, data.ortho_scale = 'ORTHO', 3.65
    camera.location = (0, -7, 2.0)
    aim(camera, (0, 0, 1.56))
    scene.camera = camera
    return camera


def setup_ik(rig):
    targets = {}
    for sign, side in ((-1, 'L'), (1, 'R')):
        target = empty('CTRL_wrist.'+side)
        target.location = (sign*.72, -.12, .55)
        target.rotation_mode = 'XYZ'
        targets[side] = target
        ik = rig.pose.bones['forearm.'+side].constraints.new('IK')
        ik.name, ik.target, ik.chain_count, ik.use_stretch = 'Wing reach', target, 2, False
        # Wrist inherits the wing chain; no independent object-twisting controller.
        for name in ('upper.', 'forearm.'):
            rig.pose.bones[name+side].ik_stretch = 0
    if ARTICULATED:
        for side in ('L','R'):
            for j in range(3):
                for suffix in ('_tip',):
                    finger = rig.pose.bones[f'feathers{j+1}{suffix}.{side}']
                    limit = finger.constraints.new('LIMIT_ROTATION')
                    limit.owner_space = 'LOCAL'
                    limit.use_limit_x = True
                    limit.min_x, limit.max_x = 0, 1.4
                tip = empty(f'ContactTip{j+1}.{side}')
                c = tip.constraints.new('COPY_LOCATION')
                c.target, c.subtarget, c.head_tail = rig, f'feathers{j+1}_tip.{side}', 1
    return targets


def set_key(obj, path, value, frame):
    setattr(obj, path, value)
    obj.keyframe_insert(data_path=path, frame=frame)


def animate(rig, root, hinges, anchors, page, targets):
    phases, spacing = CFG['phases'], CFG['phase_spacing']
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 1+(len(phases)-1)*spacing
    for p in phases:
        label = p['label'] if p['n'] != 10 else 'HOLD (reference: TURN PAGE)'
        scene.timeline_markers.new(f"{p['n']:02d} {label}", frame=1+(p['n']-1)*spacing)
    # Bake every frame. Book and contact targets share the same smooth transforms.
    for frame in range(scene.frame_start, scene.frame_end+1):
        u = (frame-1)/spacing
        i = min(int(u), len(phases)-2)
        t = u-i
        t = t*t*(3-2*t)
        a, b = phases[i:i+2]
        def val(key):
            av, bv = a[key], b[key]
            if a['n'] == 10 and key == 'grip':
                # Return whole wings to the open covers before closing starts.
                reach = min(1, t/.35)
                return [reach,reach]
            if a['n'] == 10 and key == 'open':
                close = max(0,(t-.35)/.65)
                return 1-close*close*(3-2*close)
            if isinstance(av, list):
                return [x+(y-x)*t for x, y in zip(av, bv)]
            return av+(bv-av)*t
        scene.frame_set(frame)
        # Book coordinates describe the spine base. Opening never recentres it.
        rotation = (Matrix.Rotation(math.radians(val('reading_pitch')), 4, 'X')
                    @ Matrix.Rotation(math.radians(val('yaw')), 4, 'Z')
                    @ Matrix.Rotation(math.radians(val('tilt')), 4, 'Y'))
        set_key(root, 'location', val('book'), frame)
        set_key(rig.pose.bones['body'], 'location', (val('body_x'), val('body_z'), 0), frame)
        set_key(rig.pose.bones['body'], 'rotation_euler', (0, math.radians(val('body_yaw')), 0), frame)
        set_key(root, 'rotation_euler', rotation.to_euler('XYZ', root.rotation_euler), frame)
        # Rear cover stays near its held pose; the front cover swings around the spine.
        for side, closed, travel in (('L', -88, 0), ('R', 88, -180)):
            angle = math.radians(closed + travel*val('open'))
            set_key(hinges[side], 'rotation_euler', (0, 0, angle), frame)
        # Reference phase 10 is retained as a numbered hold; page turn excluded by author.
        head = rig.pose.bones['head']
        set_key(head, 'rotation_euler', (math.radians(val('head_pitch')), math.radians(-val('head')), 0), frame)
        bpy.context.view_layer.update()
        for j, (sign, side) in enumerate(((-1, 'L'), (1, 'R'))):
            grip = val('grip')[j]
            neutral = Vector((sign*(.72+.82*val('spread')), -.12, .55+1.08*val('spread')))
            neutral = rig.matrix_world @ rig.pose.bones['body'].matrix @ rig.data.bones['body'].matrix_local.inverted() @ neutral
            contact = anchors[side].matrix_world.translation
            target = targets[side]
            position = neutral.lerp(contact, grip)
            set_key(target, 'location', position, frame)
            # Object rotation is not driven by feather fingers or an independent wrist.
            for k in range(3):
                fan = rig.pose.bones[f'feathers{k+1}.{side}']
                set_key(fan, 'rotation_euler', (grip*.15, 0, sign*(k-1)*(.13*grip+.24*val('spread'))), frame)
                if ARTICULATED:
                    digit = rig.pose.bones[f'feathers{k+1}_tip.{side}']
                    set_key(digit,'rotation_euler',(.55*grip,0,0),frame)
    # Avoid Bezier overshoot in baked transforms and contact locations.
    for action in bpy.data.actions:
        for fc in action.fcurves:
            for point in fc.keyframe_points:
                point.interpolation = 'LINEAR'
    scene.frame_set(1)


def audit(mesh, rig, anchors, targets, out):
    scene = bpy.context.scene
    lengths = {b.name: b.length for b in rig.data.bones}
    phase_results = []
    original = (len(mesh.data.vertices), len(mesh.data.polygons))
    max_error = 0
    errors = []
    for frame in range(scene.frame_start, scene.frame_end+1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for side in ('L', 'R'):
            wrist = rig.matrix_world @ rig.pose.bones['forearm.'+side].tail
            error = (wrist-targets[side].matrix_world.translation).length
            max_error = max(max_error, error)
            if error > .001:
                errors.append({'frame': frame, 'wing': side, 'ik_error': round(error, 5)})
        for bone in rig.pose.bones:
            actual = (bone.tail-bone.head).length
            if abs(actual-lengths[bone.name]) > 1e-4:
                raise RuntimeError('Bone length changed: '+bone.name)
        if (frame-1) % CFG['phase_spacing'] == 0:
            p = CFG['phases'][(frame-1)//CFG['phase_spacing']]
            contacts = {}
            for j, side in enumerate(('L', 'R')):
                if p['grip'][j] == 1:
                    wrist = rig.matrix_world @ rig.pose.bones['forearm.'+side].tail
                    contacts[side] = round((wrist-anchors[side].matrix_world.translation).length, 5)
            phase_results.append({'phase': p['n'], 'frame': frame, 'label': p['label'], 'grip_errors': contacts})
    # A single stable mesh is used throughout. Components are rigid weighted islands.
    weights_ok = all(v.groups and abs(sum(g.weight for g in v.groups)-1) < 1e-6 for v in mesh.data.vertices)
    report = {'blender': bpy.app.version_string, 'method': 'manual procedural reference-based prototype; no AI export',
              'mesh': {'vertices': original[0], 'faces': original[1], 'single_mesh': True, 'finger_segments': 2 if ARTICULATED else 1,
                       'normalized_weights': weights_ok, 'materials': len(mesh.data.materials)},
              'bones': len(rig.data.bones), 'frames_checked': scene.frame_end,
              'bone_lengths_constant': True, 'max_ik_error': max_error,
              'unreachable_samples': errors, 'phases': phase_results,
              'limits': ['Rigid feathers with flexible finger cores' if ARTICULATED else 'Rigid islands; no production skin deformation',
                         'Geometric contact markers are not collision or feather-surface contact',
                         'Silhouette/style require author review; not an approved character',
                         'No eyelids, facial animation, or full collision solver',
                         'Page turning excluded by author; reference phase 10 is a hold']}
    (out/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print('UKI AUDIT', json.dumps({k: report[k] for k in ('bones', 'frames_checked', 'max_ik_error')}))
    return report


def main():
    global ARTICULATED
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--animate', action='store_true')
    parser.add_argument('--articulated-fingers', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if CFG.get('book_rotation_locked') and len({(p['yaw'],p['tilt'],p['reading_pitch']) for p in CFG['phases']}) != 1:
        raise RuntimeError('Book orientation must remain constant; use wing motion to open the cover')
    ARTICULATED = args.articulated_fingers
    out = args.output.resolve()
    blend_name = 'uki_character_' + CFG['version'].split('-')[0] + '.blend'
    if out.exists():
        raise RuntimeError('Output exists; choose a new version directory')
    if not (out.is_relative_to(REPO/'.local-assets') or out.is_relative_to(REPO/'output')):
        raise RuntimeError('Output must be under ignored .local-assets/ or output/')
    for name, digest in CFG['references'].items():
        path = REPO/'.local-assets'/name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Reference hash mismatch: '+name)
    out.mkdir(parents=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for name, color in {'brown':(.30,.105,.026), 'copper':(.52,.21,.055), 'tan':(.66,.32,.10),
                        'cream':(.93,.70,.35), 'ivory':(1,.88,.62), 'navy':(.006,.025,.065),
                        'blue':(.012,.22,.43), 'teal':(.012,.38,.57), 'gold':(1,.57,.06),
                        'white':(1,1,1), 'claw':(.10,.07,.065), 'leather':(.20,.055,.012),
                        'paper':(.91,.79,.52), 'stage':(.075,.10,.13)}.items():
        material(name, color, .08 if name == 'gold' else 0)
    rig = skeleton()
    mesh = bird(rig)
    root, hinges, anchors, page = book()
    # Supports are staging proxies, not new episode scenery.
    for x in (-1.1, 1.15):
        for j in range(3):
            cube('Stack proxy', (x, -.3, .12+j*.21), (.85, .65, .20), 'leather')
    cube('Reading support', (.23, -.73, .85), (1.18, .82, .10), 'leather')
    for x in (-.23,.69):
        for y in (-1.03,-.43):
            cube('Reading stand leg', (x,y,.42), (.065,.065,.84), 'leather')
    camera = scene_setup()
    targets = setup_ik(rig)
    animate(rig, root, hinges, anchors, page, targets)
    report = audit(mesh, rig, anchors, targets, out)
    if report['max_ik_error'] > .001:
        raise RuntimeError('IK checks failed; inspect audit.json before rendering')
    scene = bpy.context.scene
    # Save a neutral library pose; animation remains a single reusable Action per object.
    for obj in (root, *hinges.values(), page, *targets.values(), rig):
        if obj.animation_data:
            obj.animation_data.action.name = 'Uki_BookStudy_' + obj.name
            obj['action_name'] = obj.animation_data.action.name
    scene.frame_set(scene.frame_end)
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    # Pack reference images for offline visual review, keeping source files unchanged.
    for name in CFG['references']:
        if name.endswith('.png'):
            img = bpy.data.images.load(str(REPO/'.local-assets'/name), check_existing=True)
            img.pack()
            img.filepath = bpy.path.relpath(str(REPO/'.local-assets'/name), start=str(out))
    scene['finger_segments'] = 2 if ARTICULATED else 1
    scene['page_turn_enabled'] = False
    scene['book_opens_toward'] = 'uki'
    scene['book_opening_revision'] = 3
    scene['independent_wrist_twist'] = False
    scene['book_rotation_locked'] = True
    scene['book_support'] = 'reading_stand'
    scene['prototype_status'] = 'Needs author review; see audit.json and repository report'
    scene['source_issue'] = 'DAIRN-Universe/uki-animation#17'
    bpy.ops.wm.save_as_mainfile(filepath=str(out/blend_name))
    if args.render:
        # Hide staging/book for four consistent character-only controls.
        staging = [o for o in scene.objects if o.type == 'MESH' and o != mesh and o.name != 'Stage']
        for obj in staging:
            obj.hide_render = True
        # Rest controls are temporary for reference renders; saved rig keeps the study.
        for obj in (rig, *targets.values()):
            if obj.animation_data:
                obj.animation_data.action = None
        rig.pose.bones['head'].rotation_euler = (0, 0, 0)
        rig.pose.bones['body'].location = (0, 0, 0)
        rig.pose.bones['body'].rotation_euler = (0, 0, 0)
        for sign, side in ((-1, 'L'), (1, 'R')):
            targets[side].location = (sign*.72, -.12, .55)
            targets[side].rotation_euler = rig.data.bones['wrist.'+side].matrix_local.to_euler()
            for k in range(3):
                rig.pose.bones[f'feathers{k+1}.{side}'].rotation_euler = (0, 0, 0)
                if ARTICULATED:
                    for suffix in ('_tip',):
                        rig.pose.bones[f'feathers{k+1}{suffix}.{side}'].rotation_euler = (0,0,0)
        for name, loc in [('front',(0,-7,1.56)), ('three_quarter',(5,-5,1.56)), ('profile',(7,0,1.56)), ('back',(0,7,1.56)), ('profile_head_front',(7,0,1.56))]:
            rig.pose.bones['head'].rotation_euler.y = math.pi/2 if name == 'profile_head_front' else 0
            camera.location = loc
            aim(camera, (0, 0, 1.56))
            scene.render.filepath = str(out/(name+'.png'))
            bpy.ops.render.render(write_still=True)
        # Reload saved model so controls and staging are restored exactly.
        bpy.ops.wm.open_mainfile(filepath=str(out/blend_name))
        scene = bpy.context.scene
        camera = scene.camera
        camera.location = (1.8, -8, 3.2)
        camera.data.ortho_scale = 4.5
        aim(camera, (0, -.15, 1.45))
        for p in CFG['phases']:
            scene.frame_set(1+(p['n']-1)*CFG['phase_spacing'])
            scene.render.filepath = str(out/f"phase_{p['n']:02d}.png")
            bpy.ops.render.render(write_still=True)
        if args.animate:
            sys.path.insert(0,str(Path(__file__).resolve().parent))
            from render_motion import render_motion
            render_motion(out/'motion.mp4')
    print('UKI OUTPUT', out)


if __name__ == '__main__':
    main()
