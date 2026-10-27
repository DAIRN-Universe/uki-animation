"""Avian head, pear-shaped body, feather fan and short bird feet for v4.

All geometry is independent of the unchanged wing builder and wing materials.
"""
import math

import bmesh
import bpy
from mathutils import Vector


def mesh_part(api, name, vertices, faces, mat, bone):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return api.finish(obj, name, mat, bone)


def blade(api, name, start, end, width, thickness, normal, mat, bone):
    a, b = Vector(start), Vector(end)
    direction = (b-a).normalized()
    side = direction.cross(Vector(normal)).normalized()
    outward = side.cross(direction).normalized()
    vertices = [tuple(a)]
    for t,w in zip((.10,.25,.45,.65,.83,.94),(.60,1,.88,.60,.28,.08)):
        for j in range(8):
            angle = j*math.tau/8
            # Shallow convex vane, tapered shaft and a pointed end.
            p = a.lerp(b,t) + side*(width*w*math.cos(angle)) + outward*(.025*math.sin(math.pi*t)+thickness*w*(1+math.sin(angle)))
            vertices.append(tuple(p))
    vertices.append(tuple(b))
    faces = [(0, 1+j, 1+(j+1)%8) for j in range(8)]
    for row in range(5):
        for j in range(8):
            faces.append((1+row*8+j,1+row*8+(j+1)%8,1+(row+1)*8+(j+1)%8,1+(row+1)*8+j))
    faces += [(49,41+j,41+(j+1)%8) for j in range(8)]
    return mesh_part(api,name,vertices,faces,mat,bone)


def tube(api,name,points,radii,mat,bone):
    points = [Vector(p) for p in points]
    vertices=[]
    for k,center in enumerate(points):
        tangent=(points[min(k+1,len(points)-1)]-points[max(k-1,0)]).normalized()
        axis=tangent.cross(Vector((1,0,0)))
        if axis.length < .1:
            axis=tangent.cross(Vector((0,1,0)))
        axis.normalize()
        second=tangent.cross(axis).normalized()
        for j in range(10):
            angle=j*math.tau/10
            vertices.append(tuple(center+radii[k]*(axis*math.cos(angle)+second*math.sin(angle))))
    faces=[tuple(reversed(range(10)))]
    for row in range(len(points)-1):
        for j in range(10):
            faces.append((row*10+j,row*10+(j+1)%10,(row+1)*10+(j+1)%10,(row+1)*10+j))
    faces.append(tuple(range((len(points)-1)*10,len(points)*10)))
    return mesh_part(api,name,vertices,faces,mat,bone)


BODY_RINGS = [
    (.40,.12,.17,.08),(.50,.32,.28,.08),(.65,.50,.43,.06),
    (.88,.59,.48,.04),(1.12,.57,.46,.02),(1.35,.50,.40,0),
    (1.55,.41,.34,0),(1.72,.32,.27,0),(1.82,.18,.16,0),
]


def body_dimensions(z):
    z=max(BODY_RINGS[0][0],min(z,BODY_RINGS[-1][0]))
    for a,b in zip(BODY_RINGS,BODY_RINGS[1:]):
        if a[0] <= z <= b[0]:
            t=(z-a[0])/(b[0]-a[0])
            rx,ry,cy=[a[k]+(b[k]-a[k])*t for k in (1,2,3)]
            return rx,ry,cy
    raise ValueError(z)


def body_surface(z,x):
    rx,ry,cy=body_dimensions(z)
    return cy-ry*math.sqrt(max(.02,1-(x/rx)**2))


def torso(api):
    rings=[]
    for a,b in zip(BODY_RINGS,BODY_RINGS[1:]):
        rings.extend(tuple(x+(y-x)*t for x,y in zip(a,b)) for t in (0,.25,.5,.75))
    rings.append(BODY_RINGS[-1])
    vertices=[(0,.08,.37)]
    for z,rx,ry,cy in rings:
        for j in range(40):
            angle=j*math.tau/40
            vertices.append((rx*math.cos(angle),cy+ry*math.sin(angle),z))
    vertices.append((0,0,1.86))
    faces=[(0,1+j,1+(j+1)%40) for j in range(40)]
    for row in range(len(rings)-1):
        for j in range(40):
            faces.append((1+row*40+j,1+row*40+(j+1)%40,1+(row+1)*40+(j+1)%40,1+(row+1)*40+j))
    last=1+(len(rings)-1)*40
    faces += [(len(vertices)-1,last+j,last+(j+1)%40) for j in range(40)]
    core=mesh_part(api,'Avian pear torso',vertices,faces,'avian_brown','body')
    # Retain the previous joined mesh origin, so unchanged wings stay bit-identical.
    for v in core.data.vertices:
        v.co.z -= 1.08
    core.location.z=1.08
    core.data.materials.append(api.MATS['avian_cream'])
    for face in core.data.polygons:
        center=sum((core.data.vertices[i].co for i in face.vertices),Vector())/len(face.vertices)
        world=center+core.location
        if world.y < -.12 and abs(world.x) < .33 and .43 < world.z < 1.72:
            face.material_index=1
    # Fine overlapping feather bib follows the breast rather than a separate oval plate.
    for row,z in enumerate((1.67,1.47,1.27,1.07,.87,.67)):
        half_width=(.18,.26,.32,.34,.30,.22)[row]
        count=5 if row in (0,5) else 7
        for j in range(count):
            x=(j/(count-1)*2-1)*half_width
            tip_z=z-.23
            tip_x=x*.87
            blade(api,'Breast contour feather',(x,body_surface(z,x)-.012,z+.03),
                  (tip_x,body_surface(tip_z,tip_x)-.058,tip_z),.072,.004,(0,-1,0),
                  'avian_ivory' if (j+row)%3 else 'avian_cream','body')
    for row,z in enumerate((1.55,1.32,1.09,.86,.63)):
        for j in range(15):
            angle=(j+.5*(row%2))*math.pi/14
            rx,ry,cy=body_dimensions(z)
            ex,ey,ecy=body_dimensions(z-.27)
            start=(rx*math.cos(angle)*1.012,cy+ry*math.sin(angle)*1.012,z)
            end=(ex*math.cos(angle)*1.02,ecy+ey*math.sin(angle)*1.02,z-.27)
            blade(api,'Body contour feather',start,(end[0],end[1]+.035,end[2]),.085,.005,
                  (math.cos(angle),math.sin(angle),.1),
                  ('avian_brown','avian_copper','avian_tan')[(j+row)%3],'body')
    # Seven distinct tapered feathers, fanned behind the rump.
    for j in range(7):
        t=(j-3)/3
        start=(t*.075,.29,.95)
        end=(t*.29,.78-abs(t)*.14,.26+abs(t)*.08)
        tail=blade(api,f'Tail fan feather {j+1:02d}',start,end,.085,.012,(0,1,.15),
                   'avian_copper' if j%2 else 'avian_brown','body')
        ids=tail.data.attributes.new('avian_tail_id','INT','FACE')
        for item in ids.data:
            item.value=j+1
        api.line('Tail shaft',[(start[k]+(end[k]-start[k])*u for k in range(3))
                              for u in (.15,.45,.75,.94)],.003,'avian_tan','body')


def head_surface(x,z):
    return -.48*math.sqrt(max(.025,1-(x/.76)**2-((z-2.14)/.56)**2))


def facial_mask(api):
    outline=[(0,2.57),(-.15,2.65),(-.36,2.62),(-.55,2.51),(-.65,2.34),
             (-.64,2.14),(-.51,1.94),(-.28,1.78),(0,1.69),(.28,1.78),
             (.51,1.94),(.64,2.14),(.65,2.34),(.55,2.51),(.36,2.62),(.15,2.65)]
    # A single shallow curved heart-shaped disk, backed and closed at the rim.
    center=Vector((0,2.18))
    vertices=[]
    for back in (False,True):
        vertices.append((0,head_surface(0,2.18)-.024+(.035 if back else 0),2.18))
        for t in (.25,.50,.75,1):
            for ox,oz in outline:
                p=center.lerp(Vector((ox,oz)),t)
                vertices.append((p.x,head_surface(p.x,p.y)-.024+(.035 if back else 0),p.y))
    n=len(outline);layer=1+4*n;faces=[]
    for offset in (0,layer):
        faces += [(offset,offset+1+j,offset+1+(j+1)%n) for j in range(n)]
        for row in range(3):
            for j in range(n):
                faces.append((offset+1+row*n+j,offset+1+row*n+(j+1)%n,
                              offset+1+(row+1)*n+(j+1)%n,offset+1+(row+1)*n+j))
    for j in range(n):
        a=1+3*n+j;b=1+3*n+(j+1)%n
        faces.append((a,b,b+layer,a+layer))
    mesh_part(api,'Unified owl facial disk',vertices,faces,'avian_ivory','head')



def eye_patch(api,name,x,y,z,scale,mat):
    obj=api.oval(name,(x,y,z),scale,mat,'head')
    base=head_surface(x,z)
    for vertex in obj.data.vertices:
        vertex.co.y += head_surface(x+vertex.co.x,z+vertex.co.z)-base
    return obj


def head(api):
    api.oval('Broad avian head',(0,0,2.14),(.76,.48,.56),'avian_brown','head')
    for row in range(8):
        latitude=.22+row*.28
        for j in range(24):
            phi=(j+.5*(row%2))*math.tau/24
            if math.sin(phi)<-.20 and latitude>.40:
                continue
            def point(lat):
                return (.77*math.sin(lat)*math.cos(phi),.49*math.sin(lat)*math.sin(phi),2.14+.57*math.cos(lat))
            tip=point(min(2.68,latitude+.36))
            tip=(tip[0]*1.035,tip[1]*1.035,tip[2]-.012)
            blade(api,'Head contour feather',point(latitude),tip,
                  .075,.005,(math.cos(phi),math.sin(phi),.2),
                  ('avian_brown','avian_copper','avian_tan')[(j+row)%3],'head')
    facial_mask(api)
    for sign in (-1,1):
        x=sign*.29
        eye_patch(api,'Flush orbital rim',x,-.477,2.22,(.234,.012,.245),'eye_dark')
        eye_patch(api,'Amber iris',x,-.488,2.22,(.207,.008,.217),'avian_gold')
        eye_patch(api,'Blue inner iris',x,-.495,2.23,(.154,.006,.174),'eye_blue')
        eye_patch(api,'Pupil',x,-.501,2.24,(.107,.005,.145),'eye_dark')
        api.oval('Eye reflection',(x-.041,-.505,2.30),(.034,.006,.038),'white','head')
        api.oval('Eye small reflection',(x+.033,-.511,2.23),(.012,.005,.014),'white','head')
        blade(api,'Feathered brow',(sign*.08,-.49,2.46),(sign*.52,-.397,2.48),
              .055,.008,(0,-1,0),'avian_cream','head')
        for j in range(3):
            blade(api,'Pointed ear plume',(sign*(.40+j*.06),-.01,2.57),
                  (sign*(.44+j*.095),-.025,3.045-j*.085),.105,.020,(0,-1,0),
                  ('avian_blue','avian_teal','avian_blue')[j],'head')
        api.line('Ear gold motif',[(sign*(.48+.065*math.sin(t*4.8)),-.055,2.64+t*.32)
                                  for t in [i/24 for i in range(25)]],.016,'avian_gold','head')
    # A hooked, tapered bill replaces the spherical nose-like volume.
    tube(api,'Hooked upper bill',[(0,-.49,2.105),(0,-.56,2.065),(0,-.625,1.995),
                                 (0,-.635,1.94),(0,-.604,1.89)],
         [.053,.080,.057,.028,.0015],'avian_gold','head')
    api.line('Bill split',[(-.055,-.602,1.985),(0,-.659,1.965),(.055,-.602,1.985)],
             .0025,'avian_claw','head')


def feet(api):
    for sign,side in ((-1,'L'),(1,'R')):
        x=sign*.26;bone='foot.'+side
        api.oval('Feathered upper leg',(x,.025,.43),(.125,.13,.15),'avian_cream','body')
        for j in range(4):
            dx=(j-1.5)*.045
            blade(api,'Leg coverts',(x+dx,-.085,.46),(x+dx*.9,-.11,.27),
                  .039,.009,(0,-1,0),'avian_ivory','body')
        tube(api,'Short avian tarsus',[(x,.055,.30),(x,.035,.23),(x,-.025,.145)],
             [.037,.030,.034],'avian_gold',bone)
        for z in (.18,.215,.25):
            api.line('Tarsus scale',[(x-.024,-.008,z),(x,-.022,z-.004),(x+.024,-.008,z)],
                     .0028,'avian_scale',bone)
        for j in range(3):
            tx=x+(j-1)*.12;ty=-.285+abs(j-1)*.035
            tube(api,'Splayed front toe',[(x,-.025,.145),(x+(j-1)*.052,-.13,.12),(tx,ty,.095)],
                 [.034,.027,.020],'avian_gold',bone)
            for t in (.45,.72):
                cx=x+(tx-x)*t;cy=-.025+(ty+.025)*t
                api.line('Toe scale',[(cx-.019,cy,.143-t*.025),(cx,cy-.004,.147-t*.025),
                                      (cx+.019,cy,.143-t*.025)],.0025,'avian_scale',bone)
            tube(api,'Curved front claw',[(tx,ty-.005,.105),(tx,ty-.049,.103),
                                          (tx,ty-.087,.068),(tx,ty-.095,-.008)],
                 [.023,.020,.012,.001],'avian_claw',bone)
        tube(api,'Rear toe',[(x,.01,.145),(x,.10,.11),(x,.20,.095)],
             [.030,.023,.018],'avian_gold',bone)
        tube(api,'Rear claw',[(x,.19,.10),(x,.24,.087),(x,.275,-.008)],
             [.020,.014,.001],'avian_claw',bone)


def build_avian_body(api,rig):
    palette={'avian_brown':(.26,.090,.022),'avian_copper':(.43,.16,.039),
             'avian_tan':(.56,.25,.07),'avian_cream':(.91,.70,.40),
             'avian_ivory':(.98,.86,.62),'avian_gold':(.88,.43,.035),
             'avian_blue':(.012,.22,.43),'avian_teal':(.012,.38,.57),
             'avian_claw':(.065,.047,.035),'avian_scale':(.43,.20,.045),
             'eye_dark':(.004,.020,.055),'eye_blue':(.01,.21,.42)}
    for name,color in palette.items():
        api.material(name,color)
        node=api.MATS[name].node_tree.nodes.get('Principled BSDF')
        node.inputs['Roughness'].default_value=.20 if name.startswith('eye_') else .76
    torso(api)
    head(api)
    # Broader, lower owl head; rig and all wing coordinates remain unchanged.
    for obj in api.PARTS:
        if obj.vertex_groups.get('head') is not None:
            for vertex in obj.data.vertices:
                vertex.co.x *= 1.10
            obj.location.x *= 1.10
            obj.location.z -= .06
    feet(api)
