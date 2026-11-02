"""Import RGBA animations and share the authored atlas/quad/timing with export."""
import copy, hashlib, io, json, math, re, struct, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageChops
from .common import ROOT, title_name
from . import light_assets as mesh, light_effects as engine

MAX_FRAMES=128
MAX_BYTES=128*1024*1024
MAX_PIXELS=4096*4096
DEFAULTS=dict(fps=24.,width=1.25,brightness=1.,x=-1.82,y=0.,z=0.,part='hull',plane='side',angle=0.,mirror=False,blend='add',placement='plane',lift=.006,uv_scale=1.,uv_scale_x=1.,uv_scale_y=1.,u_offset=0.,v_offset=0.,crop_left=0.,crop_right=0.,crop_top=0.,crop_bottom=0.)
# Each corner can be pulled on its own, in fractions of the current half size.
# Normalized offsets keep a pulled shape proportional when length/width change.
WARPS=tuple('warp_%s_%s'%(corner,axis) for corner in ('tl','tr','br','bl') for axis in ('x','y','z'))
DEFAULTS.update({key:0. for key in WARPS})
DEFAULTS.update(tint_color='#FFFFFF',tint_strength=0.)
# A 8x8 grid bends around a pulled corner instead of only skewing two triangles.
PLANE_SEGMENTS=8
MANIFEST=re.compile(r'res/particles/ae_import_([0-9a-f]{12})/manifest\.json')
PACKAGE_CONFLICT_NOTE='同一车型只启用一份涂装或 AE 特效包；更换效果前停用旧包，避免资源覆盖。当前不支持叠加安装多个独立 AE 包。'

def config(value):
    c=dict(DEFAULTS);c.update(value)
    for k,lo,hi in [('tint_strength',0,100),('fps',1,60),('width',.01,20),('brightness',.01,10),('x',-30,30),('y',-30,30),('z',-30,30),('angle',-180,180),('lift',.001,.1),('uv_scale',.05,8),('uv_scale_x',.05,8),('uv_scale_y',.05,8),('u_offset',-2,2),('v_offset',-2,2)]+[(key,0,99) for key in ('crop_left','crop_right','crop_top','crop_bottom')]+[(key,-2.,2.) for key in WARPS]:
        if isinstance(c[k],bool):raise ValueError('参数必须是数值：'+k)
        c[k]=float(c[k])
        if not math.isfinite(c[k]) or not lo<=c[k]<=hi:raise ValueError('参数超出范围：'+k)
    if c['part'] not in ('hull','turret','gun'):raise ValueError('请选择车体、炮塔或炮管挂点。')
    if c['plane'] not in ('auto','side','front','top'):raise ValueError('特效朝向无效。')
    if c['placement'] not in ('plane','surface','surface_glow'):raise ValueError('请选择独立平面、贴面播放或贴面发光。')
    if c['blend'] not in ('add','alpha'):raise ValueError('透明混合方式无效。')
    if type(c['mirror']) is not bool:raise ValueError('双侧设置无效。')
    if not isinstance(c['tint_color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',c['tint_color']):raise ValueError('颜色请填写 #RRGGBB，例如 #FF80C8。')
    c['tint_color']=c['tint_color'].upper()
    if c['crop_left']+c['crop_right']>=100 or c['crop_top']+c['crop_bottom']>=100:raise ValueError('相对两边的裁剪合计必须小于 100%。')
    # A crossed/folded footprint cannot map the animation without reversing it.
    if c['placement']=='plane':
        left,right,top,bottom=c['crop_left']/100,1-c['crop_right']/100,c['crop_top']/100,1-c['crop_bottom']/100
        points=np.array([[(u-.5)*2+c['warp_'+key+'_x'],(.5-v)*2+c['warp_'+key+'_y']] for key,u,v in (('tl',left,top),('tr',right,top),('br',right,bottom),('bl',left,bottom))])
        edges=np.roll(points,-1,axis=0)-points
        crosses=edges[:,0]*np.roll(edges,-1,axis=0)[:,1]-edges[:,1]*np.roll(edges,-1,axis=0)[:,0]
        if np.any(crosses>=-1e-6):raise ValueError('四角已交叉或折叠，请把角点拉回，保持四边形不交叉。')
    return {k:c[k] for k in DEFAULTS}


def colorize_rgba(image,values):
    """Recolour straight RGB while preserving every alpha byte.

    Peak-channel detail supplies highlights and shading. Interpolate towards
    the selected hue instead of multiplying away missing source channels. Both
    preview and export use these baked pixels; brightness remains independent.
    """
    c=config(values);image=image.convert('RGBA')
    if c['tint_strength']==0:return image.copy()
    r,g,b,alpha=image.split();peak=ImageChops.lighter(ImageChops.lighter(r,g),b)
    channels=[]
    for offset in (1,3,5):
        scale=int(c['tint_color'][offset:offset+2],16)/255
        channels.append(peak.point([round(level*scale) for level in range(256)]))
    tinted=Image.merge('RGB',channels)
    blended=Image.blend(image.convert('RGB'),tinted,c['tint_strength']/100)
    return Image.merge('RGBA',(*blended.split(),alpha))


def colorized_clip(clip,values,folder):
    """Cache a recoloured copy; editable projects/presets retain source RGB."""
    c=config(values)
    if c['tint_strength']==0:return clip
    validate_clip(clip)
    key=hashlib.sha256((clip['atlas_sha256']+c['tint_color']+format(c['tint_strength'],'.12g')).encode()).hexdigest()
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);target=folder/('tint_'+key+'.png')
    if not target.exists():
        with Image.open(clip['atlas']) as image:
            result=colorize_rgba(image,c)
            temporary=target.with_suffix('.tmp.png');result.save(temporary);temporary.replace(target)
    return dict(clip,atlas=str(target.resolve()),atlas_sha256=engine.digest(target))

def read_rgba(path):
    p=Path(path)
    if p.stat().st_size>16*1024*1024:raise ValueError('单张 PNG 不能超过 16 MB。')
    with Image.open(p) as im:
        if im.format!='PNG' or max(im.size)>4096 or im.width*im.height>MAX_PIXELS:raise ValueError('请选择不超过 4096×4096 像素的 PNG。')
        if 'A' not in im.getbands() and 'transparency' not in im.info:raise ValueError('PNG 没有透明通道，请从 AE 导出 RGB＋Alpha。')
        return im.convert('RGBA')

def natural(path):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',Path(path).name)]

def pack_frames(frames,destination,premultiplied=False):
    if not 1<=len(frames)<=MAX_FRAMES:raise ValueError('一次导入 1～128 帧；请缩短片段或降低导出帧率。')
    if len({im.size for im in frames})!=1:raise ValueError('序列帧尺寸必须一致。')
    w,h=frames[0].size
    if not any(im.getchannel('A').getextrema()[0]<255 for im in frames):raise ValueError('素材完全不透明，请导出透明背景。')
    if not any(im.getchannel('A').getextrema()[1]>0 for im in frames):raise ValueError('所有帧均完全透明，无法制作可见特效。')
    # Bound upload size independently of AE render dimensions; preserve aspect.
    ratio=min(1,512/max(w,h));cw,ch=max(1,round(w*ratio)),max(1,round(h*ratio))
    while True:
        cols=min(len(frames),max(1,4096//(cw+4)))
        rows=math.ceil(len(frames)/cols)
        if rows*(ch+4)<=4096:break
        cw=max(1,round(cw*.9));ch=max(1,round(ch*.9))
    aw=1<<math.ceil(math.log2(cols*(cw+4)));ah=1<<math.ceil(math.log2(rows*(ch+4)))
    atlas=Image.new('RGBA',(aw,ah));rects=[]
    for i,frame in enumerate(frames):
        if premultiplied:
            a=np.asarray(frame,dtype=np.float32)/255;alpha=a[:,:,3:]
            a[:,:,:3]=np.divide(a[:,:,:3],alpha,out=np.zeros_like(a[:,:,:3]),where=alpha>0)
            frame=Image.fromarray(np.uint8(np.clip(a,0,1)*255),'RGBA')
        frame=frame.resize((cw,ch),Image.Resampling.LANCZOS)
        x=(i%cols)*(cw+4)+2;y=(i//cols)*(ch+4)+2
        atlas.paste(frame,(x,y));rects.append([(x+.5)/aw,(y+.5)/ah,(x+cw-.5)/aw,(y+ch-.5)/ah])
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True);atlas.save(path)
    return dict(schema=1,atlas=str(path.resolve()),atlas_sha256=engine.digest(path),size=[aw,ah],frame_size=[w,h],packed_frame_size=[cw,ch],rects=rects,frames=len(frames),alpha='straight')

def import_sequence(paths,destination,premultiplied=False):
    paths=sorted([Path(p) for p in paths],key=natural)
    if not 1<=len(paths)<=MAX_FRAMES:raise ValueError('请选择 1～128 张 PNG 序列帧。')
    if sum(p.stat().st_size for p in paths)>MAX_BYTES:raise ValueError('序列帧合计不能超过 128 MB。')
    # Decode/resize incrementally, keeping total decoded memory bounded.
    size=None;frames=[]
    for p in paths:
        im=read_rgba(p)
        if size is None:size=im.size
        if im.size!=size:raise ValueError('序列帧尺寸必须一致。')
        im.thumbnail((512,512),Image.Resampling.LANCZOS);frames.append(im)
    result=pack_frames(frames,destination,premultiplied)
    result['frame_size']=list(size);result['order']=[p.name for p in paths]
    return result

def import_sheet(path,cols,rows,count,destination,premultiplied=False):
    if any(type(x) is not int or x<1 for x in (cols,rows,count)) or count>min(cols*rows,MAX_FRAMES):raise ValueError('图集行列数或有效帧数无效（最多 128 帧）。')
    im=read_rgba(path)
    if im.width%cols or im.height%rows:raise ValueError('PNG 宽高必须能被图集列数、行数整除。')
    w,h=im.width//cols,im.height//rows
    return pack_frames([im.crop((i%cols*w,i//cols*h,(i%cols+1)*w,(i//cols+1)*h)) for i in range(count)],destination,premultiplied)

def validate_clip(clip):
    if clip.get('schema')!=1 or type(clip.get('frames')) is not int or not 1<=clip['frames']<=MAX_FRAMES:raise ValueError('动画清单无效。')
    p=Path(clip['atlas'])
    if engine.digest(p)!=clip['atlas_sha256']:raise ValueError('特效图集已被改动，请重新导入。')
    with Image.open(p) as im:
        if im.size!=tuple(clip['size']) or im.mode!='RGBA' or max(im.size)>4096:raise ValueError('图集尺寸或透明格式不匹配。')
    if len(clip['rects'])!=clip['frames']:raise ValueError('图集帧数不匹配。')
    for rect in clip['rects']:
        if len(rect)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in rect):raise ValueError('图集帧范围无效。')
        if not 0<=rect[0]<rect[2]<=1 or not 0<=rect[1]<rect[3]<=1:raise ValueError('图集帧超出边界。')
    if len(clip['frame_size'])!=2 or not all(type(x) is int and 0<x<=4096 for x in clip['frame_size']):raise ValueError('动画宽高无效。')
    return clip

def plane_point(horizontal,vertical,plane):
    return [0.,vertical,-horizontal] if plane in ('auto','side') else [horizontal,vertical,0.] if plane=='front' else [horizontal,0.,-vertical]

def plane_normal(plane):
    return [1.,0.,0.] if plane in ('auto','side') else [0.,0.,1.] if plane=='front' else [0.,1.,0.]

def plane_corners(clip,c):
    """Corner positions in the unrotated plane's own axes, plus their crop UVs.

    The source aspect establishes the neutral size. Each authored axis then
    scales independently, and only the requested corner takes its own pull,
    so neither the two directions nor the four corners re-link each other.
    """
    c=config(c)
    base_width=c['width'];w=base_width*c['uv_scale_x']
    h=base_width*clip['frame_size'][1]/clip['frame_size'][0]*c['uv_scale_y']
    half_w,half_h=w*.5,h*.5
    left,right,top,bottom=c['crop_left']/100,1-c['crop_right']/100,c['crop_top']/100,1-c['crop_bottom']/100
    corners=[]
    for key,u,v in (('tl',left,top),('tr',right,top),('br',right,bottom),('bl',left,bottom)):
        corners.append(((u-.5)*w+c['warp_'+key+'_x']*half_w,(.5-v)*h+c['warp_'+key+'_y']*half_h,u,v))
    return corners,w,h

def plane_weights(segments=PLANE_SEGMENTS):
    """Bilinear weights per grid vertex, shared by preview handles and export."""
    segments=max(1,int(segments));out=[]
    for j in range(segments+1):
        t=j/segments
        for i in range(segments+1):
            s=i/segments
            out.append([(1-s)*(1-t),s*(1-t),s*t,(1-s)*t])
    return out

def plane_frames(clip,c):
    """Warped corner positions in geometry space, for direct on-screen dragging."""
    c=config(c);corners,w,h=plane_corners(clip,c)
    angle=math.radians(c['angle']);cs,sn=math.cos(angle),math.sin(angle)
    points=[]
    for key,(horizontal,vertical,_,_) in zip(('tl','tr','br','bl'),corners):
        xx=cs*horizontal-sn*vertical;yy=sn*horizontal+cs*vertical
        points.append((np.array(plane_point(xx,yy,c['plane']))+np.array(plane_normal(c['plane']))*c['warp_'+key+'_z']*min(w,h)*.5).tolist())
    return points,[w,h]

def plane_mesh(clip,c,rect,segments=PLANE_SEGMENTS):
    """Trimmed plane footprint with independently pulled corners.

    UVs follow the crop rectangle bilinearly, so trimming hides the requested
    edges without stretching what is left. Extra segments let one pulled corner
    bend the surface instead of only skewing two triangles.
    """
    c=config(c);segments=max(1,int(segments))
    corners,w,h=plane_corners(clip,c)
    angle=math.radians(c['angle']);cs,sn=math.cos(angle),math.sin(angle)
    normal=plane_normal(c['plane']);rows=[]
    for j in range(segments+1):
        t=j/segments
        for i in range(segments+1):
            s=i/segments
            weights=((1-s)*(1-t),s*(1-t),s*t,(1-s)*t)
            horizontal=sum(k*corner[0] for k,corner in zip(weights,corners))
            vertical=sum(k*corner[1] for k,corner in zip(weights,corners))
            u=sum(k*corner[2] for k,corner in zip(weights,corners))
            v=sum(k*corner[3] for k,corner in zip(weights,corners))
            xx=cs*horizontal-sn*vertical;yy=sn*horizontal+cs*vertical
            depth=sum(k*c['warp_'+corner+'_z'] for k,corner in zip(weights,('tl','tr','br','bl')))*min(w,h)*.5
            point=(np.array(plane_point(xx,yy,c['plane']))+np.array(normal)*depth).tolist()
            rows.append(point+normal+[rect[0]+u*(rect[2]-rect[0]),rect[1]+v*(rect[3]-rect[1])])
    indices=[]
    for j in range(segments):
        for i in range(segments):
            a=j*(segments+1)+i;b=a+1;down=a+segments+1;across=down+1
            indices.extend((a,b,across,a,across,down))
    vertices=np.array(rows,dtype=float)
    if any(c['warp_'+corner+'_z'] for corner in ('tl','tr','br','bl')):
        normals=np.zeros((len(vertices),3))
        for tri in np.asarray(indices).reshape(-1,3):
            a,b,d=vertices[tri,:3];n=np.cross(b-a,d-a)
            if np.dot(n,normal)<0:n=-n
            normals[tri]+=n
        lengths=np.linalg.norm(normals,axis=1)
        vertices[:,3:6]=normals/np.maximum(lengths[:,None],1e-15)
    return vertices,indices


def reflect_plane_geometry(vertices,indices):
    """Reflect one independent plane in its part's local X axis, including winding."""
    mirrored=np.asarray(vertices).copy();mirrored[:,0]*=-1;mirrored[:,3]*=-1
    triangles=np.asarray(indices).reshape(-1,3)
    return mirrored,triangles[:,[0,2,1]].reshape(-1).tolist()


def new_plane_config(clip,values,effect=None):
    """Start a fresh animated plane at the current overlay's bind-space centre.

    Preserve the loaded animation, playback and blend. Surface clipping and a
    previously pulled shape never leak into a newly created plane.
    """
    c=config(values)
    if c['placement']=='plane':
        # The live form may be ahead of the asynchronous preview snapshot.
        # Keep its pose and independent sizes; only reset the rectangle shape.
        out=dict(c)
        for key in ('uv_scale','u_offset','v_offset','crop_left','crop_right','crop_top','crop_bottom')+WARPS:out[key]=DEFAULTS[key]
        return config(out)
    out=dict(c,placement='plane',angle=0.)
    for key in ('uv_scale','uv_scale_x','uv_scale_y','u_offset','v_offset','crop_left','crop_right','crop_top','crop_bottom')+WARPS:out[key]=DEFAULTS[key]
    if effect and effect.get('vertices'):
        vertices=np.asarray(effect['vertices'])[:,:3]
        # Mirrored surface preview appends reflected triangles after the
        # original side. Fit the new plane to that original side only.
        if effect.get('config',{}).get('placement')!='plane':
            count=effect.get('original_vertex_count')
            if isinstance(count,int) and 0<count<=len(vertices):vertices=vertices[:count]
            # If the original selection already spans both sides, the first
            # source triangle identifies which side provides the plane bounds.
            if c['mirror'] and vertices[:,0].min() < -1e-5 and vertices[:,0].max() > 1e-5:
                side=-1 if vertices[:3,0].mean()<0 else 1
                selected=vertices[vertices[:,0]*side>=-1e-5]
                if len(selected)>=3:vertices=selected
        low=vertices.min(0);high=vertices.max(0);center=(low+high)*.5
        center+=np.array(effect.get('positions',[[0,0,0]])[0])
        axis=int(np.argmin(high-low));out['plane']=('side','top','front')[axis]
        horizontal,vertical=(2,1) if axis==0 else (0,2) if axis==1 else (0,1)
        out['width']=min(20.,max(.01,float(high[horizontal]-low[horizontal])))
        out['uv_scale_y']=min(8.,max(.05,float(high[vertical]-low[vertical])/(out['width']*clip['frame_size'][1]/clip['frame_size'][0])))
        out.update(zip(('x','y','z'),center.tolist()));out['part']=effect.get('part',c['part'])
        # Avoid z-fighting at the original surface without moving vehicle nodes.
        key=('x','y','z')[axis];out[key]+= .006 if center[axis]>=0 else -.006
    elif out['plane']=='auto':out['plane']='side'
    return config(out)

def quad(clip,c,rect):
    """Four-corner form kept for callers that only need the historical corners."""
    vertices,_=plane_mesh(clip,c,rect,1)
    return vertices[[0,1,3,2]]

def positions(c):
    c=config(c);out=[[c['x'],c['y'],c['z']]]
    if c['placement']!='plane':return [[0.,0.,0.]]
    if c['mirror'] and abs(c['x'])>1e-6:out.append([-c['x'],c['y'],c['z']])
    return out

def validate_bilateral_placement(c):
    """A centre-line plane cannot yield two distinct mirrored positions."""
    c=config(c)
    if c['placement']=='plane' and c['mirror'] and abs(c['x'])<=1e-6:
        raise ValueError('已勾选左右双侧，但平面的横向位置在中线，两个平面会重合。请将横向位置移向车体一侧，或取消双侧显示。')
    return c

def frame_keys(index,count,fps):
    if count==1:return [(0.,1.),(1/fps,1.)]
    dt=1/fps;end=count/fps;eps=min(1e-5,dt/10000)
    if index==0:return [(0.,1.),(dt-eps,1.),(dt,0.),(end-eps,0.),(end,1.)]
    # Divide both boundaries by FPS so the last stop is exactly the duration.
    # Multiplying by dt may leave a one-ULP gap and serialize duplicate times.
    start=index/fps;stop=(index+1)/fps
    frames=[(0.,0.),(start-eps,0.),(start,1.),(stop-eps,1.),(stop,0.)]
    if index<count-1:frames.append((end,0.))
    return frames

def write_track(obj,name,frames):
    tr=ET.SubElement(obj,'track');ET.SubElement(tr,'name').text=name;ET.SubElement(tr,'type').text='vector3'
    for t,value in frames:
        frame=ET.SubElement(tr,'frame')
        for k,v in [('startTime',format(t,'.12g')),('value',' '.join(map(str,value))),('inTangent','0 0 0'),('outTangent','0 0 0'),('tangentMode','0')]:ET.SubElement(frame,k).text=v

def sequence(prefix,clip,c,position,frame_tag='frame_'):
    root=ET.Element('root');ET.SubElement(root,'duration').text=format(clip['frames']/c['fps'],'.12g')
    obj=ET.SubElement(root,'sequenceObject')
    for k,v in [('name','Root'),('type','model'),('resource','')]:ET.SubElement(obj,k).text=v
    for i in range(clip['frames']):
        obj=ET.SubElement(root,'sequenceObject')
        for k,v in [('name','AE_Frame_%03d'%i),('type','model'),('resource',prefix+frame_tag+'%03d.model'%i),('castsShadow','false')]:ET.SubElement(obj,k).text=v
        write_track(obj,'position',[(0.,position)])
        write_track(obj,'rotationEuler',[(0.,[0,0,0])])
        write_track(obj,'scale',[(t,[s,s,s]) for t,s in frame_keys(i,clip['frames'],c['fps'])])
    ET.SubElement(root,'events');return mesh.xml(root)

def dds(image):
    # No atlas mipmaps: each frame is isolated by a gutter and half-texel inset.
    # Global mip generation would blend adjacent animation cells at distance.
    w,h=image.size;header=[124,0x100F,h,w,w*4,0,1]+[0]*11
    header += [32,0x41,0,32,0xff0000,0xff00,0xff,0xff000000,0x1000,0,0,0,0]
    return b'DDS '+struct.pack('<31I',*header)+image.tobytes('raw','BGRA')

def source_project(source,work):
    source=engine.input_package(source,work)
    with zipfile.ZipFile(source) as z:
        engine.check_archive(z)
        ids=set()
        for n in z.namelist():
            match=re.match(r'^res/vehicles/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/',n)
            if match:ids.add((match[1],match[2]))
        if len(ids)!=1:raise ValueError('请选择包含单一车型模型或贴图的涂装包。')
        nation,vehicle=next(iter(ids))
    return dict(schema=1,source=str(source),source_sha256=engine.digest(source),lights=[],nation=nation,vehicle=vehicle,recipe=copy.deepcopy(engine.DEFAULT_RECIPE),source_kind='user_package')

def _clip_polygon(poly,axis,bound,above):
    """Clip in local image UV space before atlas remapping; never sample a neighbour frame."""
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da=(a[axis]-bound)*(1 if above else -1);db=(b[axis]-bound)*(1 if above else -1)
        if da>=0:result.append(a)
        if (da>=0)!=(db>=0):result.append(a+(b-a)*(da/(da-db)))
    return result

def surface_geometry(project,c,client):
    """Re-derive an overlay from authenticated original faces, preserving its native joint.

    We copy selected triangles, with an explicit opt-in for a mirrored overlay.
    Own UVs and a normal offset affect only this new overlay; vehicle indices,
    materials, UVs, bones and shared nodes stay intact.
    Multi-joint/deforming selections are refused by the existing rigid extractor.
    """
    from . import area_selection
    selection=project.get('ae_selection')
    if not selection:raise ValueError('请在三维预览中点选或框选承载面，再点击“使用选区”。')
    count=sum(len(g.get('triangles',[])) for g in selection.get('groups',[]))
    if not 0<count<=5000:raise ValueError('一次选择 1～5000 个三角面；请缩小选区。')
    records=area_selection.extract_rigid_lights(project,selection,offset=0.,client=client)
    identities={(r['part'],r['anchor'],r['anchor_kind']) for r in records}
    if len(identities)!=1:raise ValueError('一次只能选同一运动挂点的表面，不能跨车体、炮塔或不同活动骨骼。')
    part,anchor,kind=next(iter(identities));arrays=[];indices=[];offset=0
    matrix=np.asarray(records[0]['_anchor_matrix'])
    for r in records:
        if not np.allclose(matrix,r['_anchor_matrix']):raise ValueError('选区挂点空间不一致，请重新选择。')
        arrays.append(r['_vertices']);indices.extend((r['_indices']+offset).reshape(-1).tolist());offset+=len(r['_vertices'])
    vertices=np.concatenate(arrays).copy();indices=np.asarray(indices).reshape(-1,3)
    # Projection is computed in the part's bind space, before its joint moves.
    projected=(np.c_[vertices[:,:3],np.ones(len(vertices))]@matrix)[:,:3]
    plane=c['plane']
    if plane=='auto':
        ranges=np.ptp(projected,axis=0);axis=int(np.argmin(ranges));plane=('side','top','front')[axis]
    uv=projected[:,[2,1]]*[-1,-1] if plane=='side' else projected[:,[0,1]]*[1,-1] if plane=='front' else projected[:,[0,2]]
    low=uv.min(0);extent=np.ptp(uv,axis=0)
    if np.min(extent)<1e-7:raise ValueError('当前映射方向没有有效面积，请选自动贴合或切换映射方向。')
    uv=(uv-low)/extent
    origin=np.array([.5,.5])
    snap=project.get('ae_surface_origin')
    if snap:
        # Validate the clicked bind-space point against authenticated selected
        # triangles. Browser/world poses never become a vehicle-node transform.
        point=np.asarray(snap.get('point'),dtype=float)
        if snap.get('source_sha256')!=project['source_sha256'] or point.shape!=(3,) or not np.isfinite(point).all():raise ValueError('装甲吸附点不属于当前涂装，请重新吸附。')
        tri=projected[indices];ab=tri[:,1]-tri[:,0];ac=tri[:,2]-tri[:,0];ap=point-tri[:,0]
        aa=(ab*ab).sum(1);bb=(ab*ac).sum(1);cc=(ac*ac).sum(1);den=aa*cc-bb*bb
        normal=np.cross(ab,ac);length=np.linalg.norm(normal,axis=1)
        safe=np.where(np.abs(den)>1e-20,den,1.)
        u=(cc*(ap*ab).sum(1)-bb*(ap*ac).sum(1))/safe;v=(aa*(ap*ac).sum(1)-bb*(ap*ab).sum(1))/safe
        distance=np.abs((ap*normal).sum(1))/np.maximum(length,1e-20)
        if not np.any((length>1e-10)&(distance<.004)&(u>=-1e-4)&(v>=-1e-4)&(u+v<=1.0001)):raise ValueError('吸附点已离开承载面，请重新吸附或清除选区。')
        center=point[[2,1]]*[-1,-1] if plane=='side' else point[[0,1]]*[1,-1] if plane=='front' else point[[0,2]]
        origin=(center-low)/extent
    theta=math.radians(c['angle']);rotation=np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
    # UV V points down, unlike the plane's world-up axis. Invert the mapping
    # rotation so the same direction button turns both modes the same way.
    uv=((uv-origin-[c['u_offset'],c['v_offset']])@rotation.T)/(c['uv_scale']*np.array([c['uv_scale_x'],c['uv_scale_y']]))+.5
    vertices[:,6:8]=uv
    # 1 mm separates ordinary playback from the paint; glow has an explicit lift.
    distance=.001 if c['placement']=='surface' else c['lift']
    vertices[:,:3]+=vertices[:,3:6]*distance
    output=[]
    for triangle in indices:
        poly=list(vertices[triangle])
        # Crop in per-frame UV space before atlas remapping. This trims actual
        # overlay triangles and cannot bleed into a neighbouring atlas frame.
        for axis,bound,above in [(6,c['crop_left']/100,True),(6,1-c['crop_right']/100,False),(7,c['crop_top']/100,True),(7,1-c['crop_bottom']/100,False)]:
            if poly:poly=_clip_polygon(poly,axis,bound,above)
        for i in range(1,len(poly)-1):
            tri=np.array([poly[0],poly[i],poly[i+1]])
            if np.linalg.norm(np.cross(tri[1,:3]-tri[0,:3],tri[2,:3]-tri[0,:3]))>1e-12:output.extend(tri)
    if not output:raise ValueError('素材已移出选中表面，请减小素材偏移或恢复缩放。')
    vertices=np.asarray(output);vertices[:,3:6]/=np.maximum(np.linalg.norm(vertices[:,3:6],axis=1)[:,None],1e-12)
    indices=list(range(len(vertices)));mirrored=0
    if c['mirror']:vertices,indices,mirrored=mirror_surface(vertices,indices,matrix)
    if len(vertices)>65535:raise ValueError('裁剪或双侧镜像后的网格过大，请减少所选面。')
    return dict(vertices=vertices,indices=indices,part=part,anchor=anchor,anchor_kind=kind,matrix=matrix,selected_triangles=count,mirrored_triangles=mirrored)


def mirror_surface(vertices,indices,matrix):
    """Reflect the new overlay about part-bind X=0, leaving the original intact.

    Reflection belongs to the overlay, never the vehicle mount. Positions and
    normals reflect in the same space, and winding reverses. Keep frame UVs and
    timing unchanged so both sides play the same authored animation. Triangles
    already present in the selection are not emitted twice.
    """
    vertices=np.asarray(vertices);matrix=np.asarray(matrix);indices=np.asarray(indices).reshape(-1,3)
    reflection=np.eye(4);reflection[0,0]=-1
    transform=matrix@reflection@np.linalg.inv(matrix)
    copied=vertices.copy();copied[:,:3]=(np.c_[vertices[:,:3],np.ones(len(vertices))]@transform)[:,:3]
    copied[:,3:6]=vertices[:,3:6]@np.linalg.inv(transform[:3,:3]).T
    copied[:,3:6]/=np.maximum(np.linalg.norm(copied[:,3:6],axis=1)[:,None],1e-12)
    def key(points):return tuple(sorted(tuple(int(x) for x in row) for row in np.rint(points*100000)))
    present={key(vertices[tri,:3]) for tri in indices};extra=[]
    bind=(np.c_[vertices[:,:3],np.ones(len(vertices))]@matrix)[:,:3]
    for tri in indices:
        # A triangle crossing the centre plane is already on both sides.
        xs=bind[tri,0]
        if xs.min() < -1e-5 and xs.max() > 1e-5:continue
        new=copied[tri[[0,2,1]]];identity=key(new[:,:3])
        if identity not in present:extra.extend(new);present.add(identity)
    if not extra:return vertices,indices.reshape(-1).tolist(),0
    extra=np.asarray(extra);start=len(vertices)
    return np.concatenate([vertices,extra]),indices.reshape(-1).tolist()+list(range(start,start+len(extra))),len(extra)//3

def geometry_plan(project,clip,c,client):
    if c['placement']=='plane':
        vertices,indices=plane_mesh(clip,c,[0,0,1,1])
        return dict(vertices=vertices,indices=indices,part=c['part'],anchor='Gun' if c['part']=='gun' else c['part'],anchor_kind='node' if c['part']=='gun' else 'part',matrix=np.eye(4))
    return surface_geometry(project,c,client)

def atlas_vertices(vertices,rect):
    out=vertices.copy();out[:,6]=rect[0]+out[:,6]*(rect[2]-rect[0]);out[:,7]=rect[1]+out[:,7]*(rect[3]-rect[1]);return out

def preview_data(clip,c,project=None,client=None):
    validate_clip(clip);c=config(c)
    waiting=c['placement']!='plane' and not (project or {}).get('ae_selection')
    plan=None if waiting else geometry_plan(project,clip,c,client)
    vertices=plan['vertices'].copy() if plan else np.zeros((0,8))
    if plan:vertices[:,:3]=(np.c_[vertices[:,:3],np.ones(len(vertices))]@plan['matrix'])[:,:3]
    corners,size=plane_frames(clip,c) if (plan is not None and c['placement']=='plane') else ([],[])
    original_count=len(vertices)-3*plan.get('mirrored_triangles',0) if plan else 0
    return dict(config=c,rects=clip['rects'],frames=clip['frames'],fps=c['fps'],period=clip['frames']/c['fps'],positions=positions(c) if plan else [],vertices=atlas_vertices(vertices,clip['rects'][0]).tolist(),local_uv=vertices[:,6:8].tolist(),indices=plan['indices'] if plan else [],part=plan['part'] if plan else c['part'],awaiting_selection=waiting,atlas_sha256=clip['atlas_sha256'],blendSrc=5,blendDst=2 if c['blend']=='add' else 6,original_vertex_count=original_count,
                corners=corners,weights=plane_weights() if corners else [],base_size=size)

def save_project(path,project,clip,c):
    validate_clip(clip);c=config(c)
    if engine.digest(project['source'])!=project['source_sha256']:raise ValueError('输入涂装已改变。')
    metadata=dict(schema=1,config=c,clip={k:v for k,v in clip.items() if k!='atlas'},project=project)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('ae_project.json',json.dumps(metadata,ensure_ascii=False));z.write(clip['atlas'],'atlas.png');z.write(project['source'],'source.wotmod')

def load_project(path,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path) as z:
        if set(z.namelist())!={'ae_project.json','atlas.png','source.wotmod'} or len(z.namelist())!=3:raise ValueError('AE 工程清单无效。')
        if z.getinfo('ae_project.json').file_size>2*1024*1024 or z.getinfo('atlas.png').file_size>MAX_BYTES or z.getinfo('source.wotmod').file_size>2*1024**3:raise ValueError('工程大小超限。')
        data=json.loads(z.read('ae_project.json'))
        if data.get('schema')!=1:raise ValueError('AE 工程版本不支持。')
        c=config(data['config'])
        for name in ('atlas.png','source.wotmod'):
            with z.open(name) as inp,(folder/name).open('wb') as out:
                import shutil;shutil.copyfileobj(inp,out)
    project=source_project(folder/'source.wotmod',folder/'source')
    if project['source_sha256']!=data['project']['source_sha256']:raise ValueError('工程中的涂装哈希不匹配。')
    project['baseline_user_confirmed']=bool(data['project'].get('baseline_user_confirmed',False))
    if data['project'].get('ae_selection'):
        selection=data['project']['ae_selection']
        if selection.get('source_sha256')!=project['source_sha256']:raise ValueError('保存的承载面不属于此涂装。')
        project['ae_selection']=selection
        if data['project'].get('ae_surface_origin'):project['ae_surface_origin']=copy.deepcopy(data['project']['ae_surface_origin'])
    clip=dict(data['clip'],atlas=str(folder/'atlas.png'));validate_clip(clip)
    return project,clip,c

def build(project,clip,values,client,outdir,title):
    validate_clip(clip);c=validate_bilateral_placement(values);environment=engine.client_info(client)
    if not project.get('baseline_user_confirmed'):raise ValueError('请先确认原涂装在所选客户端正常。')
    if engine.digest(project['source'])!=project['source_sha256']:raise ValueError('输入涂装已改变，请重新选择。')
    clip=colorized_clip(clip,c,Path(outdir)/'颜色缓存')
    # Verify blend enumerations in this exact client before authoring resources.
    with zipfile.ZipFile(Path(client)/'res/packages/shaders.pkg') as z:
        for branch in ('10','11'):
            with zipfile.ZipFile(io.BytesIO(z.read('shaders/custom/emissive_playground.'+branch+'.dx11.fxo'))) as shader:
                meta=shader.read('effect')
                destination=b"('ONE', 2)" if c['blend']=='add' else b"('INVSRCALPHA', 6)"
                if b"('SRCALPHA', 5)" not in meta or destination not in meta:raise ValueError('当前客户端的材质混合枚举不匹配。')
    plan=geometry_plan(project,clip,c,client)
    token=hashlib.sha256((project['vehicle']+'ae-import').encode()).hexdigest()[:12]
    prefix='particles/ae_import_'+token+'/'
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    target=outdir/(title_name(title)+'_AE特效_待实测.wotmod')
    if target.exists():raise ValueError('已有同名产物，请更换名称，保留旧包。')
    added={};excluded=set()
    with zipfile.ZipFile(project['source']) as z:
        for n in z.namelist():
            match=MANIFEST.fullmatch(n)
            if match:
                own='res/particles/ae_import_'+match[1]+'/'
                excluded.update(x for x in z.namelist() if x.startswith(own))
                excluded.add('res/scripts/client/gui/mods/mod_ae_import_'+match[1]+'.pyc')
    atlas=Image.open(clip['atlas']).convert('RGBA');added['res/'+prefix+'atlas.dds']=dds(atlas)
    added['res/'+prefix+'atlas.png']=Path(clip['atlas']).read_bytes()
    added['res/'+prefix+'phase_white.dds']=mesh.dds(True)
    variants=[('frame_',plan['vertices'],plan['indices'])]
    if c['placement']=='plane' and len(positions(c))>1:
        mirrored,mirrored_indices=reflect_plane_geometry(plan['vertices'],plan['indices'])
        variants.append(('frame_mirror_',mirrored,mirrored_indices))
    for i,rect in enumerate(clip['rects']):
        for frame_tag,geometry,indices in variants:
            vertices=atlas_vertices(geometry,rect);base=prefix+frame_tag+'%03d'%i
            visual=ET.fromstring(mesh.effect_visual('ae_frame',prefix+'atlas.dds',vertices,len(indices)//3,prefix=prefix,tint=c['brightness']))
            for p in visual.findall('.//property'):
                if p.text.strip()=='srcBlend':p[0].text='5'
                if p.text.strip()=='destBlend':p[0].text='2' if c['blend']=='add' else '6'
                if p.text.strip()=='speed':p[0].text='0.0'
                if p.text.strip() in ('g_offsetBlack','g_offsetBlackFwd'):p[0].text='1.0'
            model=ET.Element('root');ET.SubElement(model,'nodelessVisual').text=base
            added['res/'+base+'.model']=mesh.xml(model);added['res/'+base+'.visual_processed']=mesh.xml(visual)
            added['res/'+base+'.primitives_processed']=mesh.primitives(vertices,indices)
    rigs=[]
    for i,position in enumerate(positions(c)):
        seq=prefix+'effect_%d.seq'%i;tag='frame_mirror_' if i==1 and len(variants)>1 else 'frame_'
        added['res/'+seq]=sequence(prefix,clip,c,position,tag)
        rigs.append(dict(id='ae_effect_%d'%i,part=plan['part'],anchor=plan['anchor'],anchor_kind=plan['anchor_kind'],sequence=seq))
    runtime=(Path(__file__).parent/'light_runtime.py.txt').read_text(encoding='utf-8').replace('RIGS = []','RIGS = '+repr(rigs)).replace('__VEHICLE_TYPE__',project['vehicle'])
    runtime=runtime.replace('CustomVehicle.LightMaker','CustomVehicle.AEImport')
    src=outdir/'AE挂载脚本.py';src.write_text(runtime,encoding='utf-8');compiled=outdir/'AE挂载脚本.pyc';engine.compile27(src,compiled,client)
    added['res/scripts/client/gui/mods/mod_ae_import_'+token+'.pyc']=compiled.read_bytes()
    manifest=dict(schema=1,kind='ae_import',config=c,clip={k:v for k,v in clip.items() if k not in ('atlas','order')},models=rigs,preview=preview_data(clip,c,project,client),source_sha256=project['source_sha256'],selection=project.get('ae_selection'))
    added['res/'+prefix+'manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    engine.write_game_archive(project['source'],target,added=added,excluded=excluded)
    audit=engine.audit_package(target,project['source'],{},client,excluded=excluded)
    # Final archive readback, every geometry and sequence, original bytes retained.
    with zipfile.ZipFile(target) as z,zipfile.ZipFile(project['source']) as old:
        for n in old.namelist():
            if n not in excluded:assert z.read(n)==old.read(n)
        for n,data in added.items():assert z.read(n)==data
        assert audit['missing_dependencies']==[]
    report=dict(artifact=dict(path=str(target),sha256=engine.digest(target),bytes=target.stat().st_size),client=environment,baseline=dict(status='user_confirmed',observer='user'),file_validation=audit,offline_validation=dict(status='partial',scope='Final-package asset readback; preview/export share atlas, UV, dimensions, frame timing, blend and placement. Native shader execution and in-game effect require validation for this hash.'),ae_effect=dict(frames=clip['frames'],fps=c['fps'],blendSrc=5,blendDst=2 if c['blend']=='add' else 6,geometry_frames=clip['frames']*len(variants),geometry_variants=len(variants),mirrored=c['mirror']),in_game_tested=False,whole_vehicle_loading=dict(status='not_tested',reason='New package; user game observation required'))
    (outdir/'验证记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (outdir/'使用说明.txt').write_text('本包为待实测版本，未自动安装。\n'+PACKAGE_CONFLICT_NOTE+'\n请检查整车加载、完整动画循环、随动、开镜隐藏/恢复、切车清理和 LOD。\n预览与导出共用贴图、尺寸、帧率及混合设置；游戏曝光、泛光和画质仍可能影响外观。\n最终包 SHA256：'+report['artifact']['sha256'],encoding='utf-8-sig')
    return target,report

def bundle_delivery(target,report,project,clip,c,include_project=True):
    """Compress the outer delivery ZIP; keep the inner game archive STORED.

    A hash check binds bundling to the completed .wotmod. Packaging never
    installs into a client, and it cannot turn offline checks into game passes.
    """
    target=Path(target)
    if engine.digest(target)!=report['artifact']['sha256']:raise ValueError('待打包产物已改变，请重新生成。')
    destination=target.with_suffix('.zip')
    if destination.exists():raise ValueError('交付 ZIP 已存在，请保留旧版并更换名称。')
    # The reusable preset is always included in the outer ZIP, independently
    # of the optional vehicle-specific .aefx. Never add it inside the game mod.
    from . import ae_presets
    metadata,payload=ae_presets.encode(target.stem[:60],'本次生成使用的素材、播放、缩放、裁剪与颜色参数；可跨车辆复用。',clip,c)
    preset=target.with_suffix('.aepreset');ae_presets.atomic_write(preset,payload)
    editable=None
    if include_project:
        editable=target.with_suffix('.aefx');save_project(editable,project,clip,c)
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as out:
        out.write(target,target.name)
        for name in ('验证记录.json','使用说明.txt'):out.write(target.parent/name,name)
        out.write(preset,preset.name)
        if editable:out.write(editable,editable.name)
    with zipfile.ZipFile(destination) as z:
        if z.testzip() is not None:raise ValueError('交付 ZIP 校验失败。')
        with z.open(target.name) as inp:
            if hashlib.file_digest(inp,'sha256').hexdigest()!=report['artifact']['sha256']:raise ValueError('ZIP 中的安装包哈希不一致。')
        if hashlib.sha256(z.read(preset.name)).hexdigest()!=engine.digest(preset):raise ValueError('ZIP 中的特效预设哈希不一致。')
    result=dict(path=str(destination),sha256=engine.digest(destination),bytes=destination.stat().st_size,editable_project=bool(editable),effect_preset=preset.name,effect_preset_sha256=engine.digest(preset),game_archive_sha256=report['artifact']['sha256'])
    (target.parent/'自动打包记录.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
