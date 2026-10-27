"""Compare v4 wings against the actual v3 .blend without exporting mesh data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy

PREFIXES=('upper.','forearm.','wrist.','feathers')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def wing_signature(mesh,rig):
    names={g.index:g.name for g in mesh.vertex_groups}
    selected=[v.index for v in mesh.data.vertices if any(names[g.group].startswith(PREFIXES) for g in v.groups)]
    remap={old:new for new,old in enumerate(selected)}
    vertices=[]
    for i in selected:
        v=mesh.data.vertices[i]
        point=mesh.matrix_local @ v.co
        vertices.append(([round(c,6) for c in point],sorted((names[g.group],round(g.weight,7)) for g in v.groups)))
    faces=[];used=set()
    for p in mesh.data.polygons:
        if all(i in remap for i in p.vertices):
            material=mesh.data.materials[p.material_index]
            used.add(material.name)
            indices=[remap[i] for i in p.vertices]
            first=indices.index(min(indices))
            indices=indices[first:]+indices[:first]
            faces.append((indices,material.name,p.use_smooth))
    materials={}
    for name in sorted(used):
        mat=bpy.data.materials[name]
        node=mat.node_tree.nodes.get('Principled BSDF')
        materials[name]={'color':list(mat.diffuse_color),'base_color':list(node.inputs['Base Color'].default_value),
                         'roughness':node.inputs['Roughness'].default_value,'metallic':node.inputs['Metallic'].default_value}
    bones={}
    for b in rig.data.bones:
        if b.name.startswith(PREFIXES) or b.name in ('root','body'):
            bones[b.name]={'matrix':[[round(c,7) for c in row] for row in b.matrix_local],
                           'parent':b.parent.name if b.parent else None,'connected':b.use_connect}
    animations={}
    for obj in (rig,bpy.data.objects['CTRL_wrist.L'],bpy.data.objects['CTRL_wrist.R']):
        action=obj.animation_data.action
        curves=[]
        for fc in action.fcurves:
            if obj == rig and fc.data_path.startswith('pose.bones['):
                name=fc.data_path.split('"')[1]
                if name not in ('root','body') and not name.startswith(PREFIXES):
                    continue
            curves.append((fc.data_path,fc.array_index,
                           [(round(k.co.x,6),round(k.co.y,7),k.interpolation) for k in fc.keyframe_points]))
        animations[obj.name]=sorted(curves)
    return {'geometry_sha256':digest({'vertices':vertices,'faces':sorted(faces)}),
            'rig_sha256':digest(bones),'materials_sha256':digest(materials),
            'animation_sha256':digest(animations),
            'vertices':len(selected),'faces':len(faces)}, selected


def pose_points(mesh,selected):
    evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data=evaluated.to_mesh()
    try:
        return [tuple(mesh.matrix_world @ data.vertices[i].co) for i in selected]
    finally:
        evaluated.to_mesh_clear()


def compare(baseline,candidate):
    bpy.ops.wm.open_mainfile(filepath=str(baseline))
    base,indices=wing_signature(bpy.data.objects['UkiMesh'],bpy.data.objects['UkiRig'])
    frames=range(1,bpy.context.scene.frame_end+1,12)
    poses={}
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        poses[frame]=pose_points(bpy.data.objects['UkiMesh'],indices)
    bpy.ops.wm.open_mainfile(filepath=str(candidate))
    current,indices=wing_signature(bpy.data.objects['UkiMesh'],bpy.data.objects['UkiRig'])
    assert current==base, {'baseline':base,'candidate':current}
    maximum=0.
    for frame,old in poses.items():
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        new=pose_points(bpy.data.objects['UkiMesh'],indices)
        for a,b in zip(old,new):
            maximum=max(maximum,sum((x-y)**2 for x,y in zip(a,b))**.5)
    assert maximum<1e-6,maximum
    return {'status':'passed','reference':'v3-wing-supported','signature':current,
            'poses_checked':len(poses),'max_evaluated_vertex_delta':maximum,
            'scope':'Wing geometry, weights, materials, bind bones and evaluated animation retained.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result=compare(args.baseline.resolve(),args.candidate.resolve())
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('UKI WINGS',json.dumps(result))
