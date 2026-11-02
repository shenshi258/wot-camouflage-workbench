"""Read-only vehicle preview assets. This module never writes game resources."""
import argparse
import copy
import hashlib
import io
import json
import math
import os
import shutil
import re
import struct
import time
import threading
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from . import light_assets as mesh, light_effects as engine, light_recipe as recipe, light_select, uml_preview, dds

SCHEMA = 10
PARTS = ('chassis','hull','turret','gun')


def write_json(path,data):
    path=Path(path);temporary=path.with_name(path.name+'.tmp_%d_%d'%(os.getpid(),threading.get_ident()))
    temporary.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    temporary.replace(path)


class Resources:
    """Input skin overrides base-client files; unrelated installed mods are excluded."""
    def __init__(self,source,client):
        self.source=zipfile.ZipFile(source);self.source_names={n.casefold():n for n in self.source.namelist()}
        self.client=Path(client) if client else None;self.opened={};self.index={};self.missing=set()
        self.packages=[]
        if self.client:
            paths=ET.parse(self.client/'paths.xml').getroot()
            self.packages=[self.client/n.text.strip() for n in paths.findall('.//Package') if n.text]
            self.packages.sort(key=lambda p:(0 if p.name=='scripts.pkg' else 1 if 'vehicle' in p.name else 2))

    def read(self,name):
        name=name.replace('\\','/').strip()
        if name.startswith('/') or ':' in name or '..' in name.split('/'):
            raise ValueError('资源引用必须是游戏内相对路径')
        key=name.casefold()
        if key.startswith('res/'):key=key[4:];name=name[4:]
        source=self.source_names.get('res/'+key)
        if source:return self.source.read(source)
        if self.client:
            loose=self.client/'res'/name
            if loose.is_file() and loose.resolve().is_relative_to((self.client/'res').resolve()):return loose.read_bytes()
        if key in self.index:
            archive,entry=self.index[key];return self.opened[archive].read(entry)
        if key in self.missing:raise FileNotFoundError(name)
        while self.packages:
            path=self.packages.pop(0)
            if not path.is_file():continue
            z=zipfile.ZipFile(path);self.opened[str(path)]=z
            for n in z.namelist():self.index.setdefault(n.casefold(),(str(path),n))
            if key in self.index:
                archive,entry=self.index[key];return self.opened[archive].read(entry)
        self.missing.add(key);raise FileNotFoundError(name)

    def close(self):
        self.source.close()
        for archive in self.opened.values():archive.close()


def save_snapshot(project,path):
    """Copy metadata plus authenticated, already extracted arrays, not a second skin."""
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    public=engine.public_project(project);arrays={}
    for light in project['lights']:
        if not light.get('supported'):continue
        for name in ('_vertices','_indices','_anchor_matrix'):
            arrays[light['id']+name]=light[name]
    np.savez(path/'geometry.npz',**arrays)
    write_json(path/'project.json',public)


def load_snapshot(path):
    path=Path(path);project=json.loads((path/'project.json').read_text(encoding='utf-8'))
    with np.load(path/'geometry.npz',allow_pickle=False) as arrays:
        for light in project['lights']:
            if light.get('supported'):
                for name in ('_vertices','_indices','_anchor_matrix'):light[name]=arrays[light['id']+name].copy()
    return project


def vector(text,default=(0,0,0)):
    if not text:return list(default)
    result=list(map(float,text.split()))
    if len(result)!=3 or not all(math.isfinite(x) for x in result):raise ValueError('部件装配坐标无效')
    return result


def assembly(resources,vehicle,visuals,warnings,uml=None):
    result={part:[0.,0.,0.] for part in PARTS}
    mapping={'french':'france','chinese':'china','czech':'czech','swedish':'sweden','polish':'poland',
             'italian':'italy','japanese':'japan','german':'germany','american':'usa','british':'uk','russian':'ussr'}
    nation=next(iter(visuals.values())).split('/')[2]
    definition='scripts/item_defs/vehicles/%s/%s.xml'%(mapping.get(nation,nation),vehicle)
    try:
        root=engine.xml(resources.read(definition))
        chassis=next(iter(root.find('chassis')))
        result['hull']=vector(chassis.findtext('hullPosition'))
        result['turret']=vector(root.findtext('hull/turretPositions/turret'))
        turrets=root.find('turrets0');turret=next(iter(turrets))
        result['gun']=vector(turret.findtext('gunPosition'))
        # Prefer the descriptor module whose model matches the selected visual.
        for module in root.find('chassis'):
            model=(module.findtext('models/undamaged') or '').strip().casefold()
            if model and 'res/'+model.replace('.model','.visual_processed')==visuals.get('chassis','').casefold():
                result['hull']=vector(module.findtext('hullPosition'));break
        for module in turrets:
            model=(module.findtext('models/undamaged') or '').strip().casefold()
            if model and 'res/'+model.replace('.model','.visual_processed')==visuals.get('turret','').casefold():
                result['gun']=vector(module.findtext('gunPosition'));break
    except (FileNotFoundError,ValueError,TypeError,StopIteration) as error:
        warnings.append('车型装配定义未完整读取，当前仅供检查部件：'+str(error))
    # UML models can have custom vehicle names that have no client descriptor.
    # Their own attachment nodes and profile position take precedence.
    if uml:
        if uml.get('hull_position'):
            result['hull']=vector(uml['hull_position'])
        if 'hull' in visuals:
            matrices,_=mesh.node_matrices(engine.xml(resources.read(visuals['hull'])))
            if 'HP_turretJoint' in matrices:result['turret']=matrices['HP_turretJoint'][3,:3].tolist()
            else:warnings.append('UML 车体未找到炮塔挂点；炮塔位置需核对。')
    # Native visual joint is a useful exact reference for a modified turret.
    if 'turret' in visuals:
        matrices,_=mesh.node_matrices(engine.xml(resources.read(visuals['turret'])))
        if 'HP_gunJoint' in matrices:result['gun']=matrices['HP_gunJoint'][3,:3].tolist()
    return result


def part_visuals(resources,project,warnings,uml=None):
    candidates={p:[] for p in PARTS}
    for name in resources.source.namelist():
        if '/normal/lod0/' not in name.lower() or not name.lower().endswith('.visual_processed'):continue
        part=Path(name).stem.lower().split('_')[0]
        if part in candidates:candidates[part].append(name)
    visuals=dict(uml['visuals']) if uml else {}
    preferred={x.get('source_visual',x['visual']) for x in project['lights'] if x.get('selected')}
    for part,names in candidates.items():
        if names and part not in visuals:
            visuals[part]=sorted(names,key=lambda n:(n not in preferred,'_skins' in n,n.casefold()))[0]
            if len(names)>1:warnings.append('%s 有多套部件，当前显示 %s。'%(part,Path(visuals[part]).name))
    # Texture-only skins can use the matching stock models from the selected client.
    if project.get('nation') and project.get('vehicle') and resources.client:
        prefix=('vehicles/'+project['nation']+'/'+project['vehicle']+'/normal/lod0/').casefold()
        found={}
        for package in resources.packages:
            if not package.is_file():continue
            with zipfile.ZipFile(package) as z:
                for name in z.namelist():
                    if name.casefold().startswith(prefix) and name.casefold().endswith('.visual_processed'):
                        part=Path(name).stem.lower().split('_')[0]
                        if part in PARTS:found.setdefault(part,[]).append('res/'+name)
        for part in PARTS:
            if part not in visuals and found.get(part):
                visuals[part]=sorted(found[part],key=str.casefold)[0]
                warnings.append(part+' 使用客户端原版模型；多型号或外观需要在游戏中核对。')
    for part in PARTS:
        if part not in visuals:warnings.append('输入包及客户端均未找到 %s 的 normal/lod0 模型。'%part)
    if not visuals:raise ValueError('输入包或客户端中没有可预览的 normal/lod0 整车部件。')
    return visuals


def transformed(vertices,skin,nodes,matrices):
    positions=np.c_[vertices[:,:3],np.ones(len(vertices))]
    result=vertices.copy()
    if not skin:
        matrix=matrices[nodes[0]]
        result[:,:3]=(positions@matrix)[:,:3]
        result[:,3:6]=vertices[:,3:6]@np.linalg.inv(matrix[:3,:3]).T
    else:
        skin=np.asarray(skin,dtype=int)
        bones=skin[:,:3]//3;weights=np.c_[skin[:,3:5],255-skin[:,3]-skin[:,4]]/255
        if (skin[:,:3]%3).any() or (weights<0).any():raise ValueError('预览蒙皮索引或权重无效')
        result[:,:6]=0
        for index in np.unique(bones):
            if index>=len(nodes):raise ValueError('预览蒙皮引用不存在的骨骼')
            weight=(weights*(bones==index)).sum(1)
            if not weight.any():continue
            matrix=matrices[nodes[index]]
            result[:,:3]+=(positions@matrix)[:,:3]*weight[:,None]
            result[:,3:6]+=(vertices[:,3:6]@np.linalg.inv(matrix[:3,:3]).T)*weight[:,None]
    result[:,3:6]/=np.maximum(np.linalg.norm(result[:,3:6],axis=1)[:,None],1e-12)
    if not np.isfinite(result).all():raise ValueError('预览网格包含非有限坐标')
    return result


def resolve_material(resources,material):
    if material is None:return ET.Element('material')
    result=material
    for _ in range(8):
        external=(result.text or '').strip()
        if not external.endswith('.mfm'):return result
        result=engine.xml(resources.read(external))
    raise ValueError('材质引用层级过深')


class AssetWriter:
    def __init__(self,folder,resources,warnings):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.resources=resources;self.warnings=warnings;self.textures={};self.texture_hashes={};self.meshes=[];self.counter=0

    def texture(self,path,neutral=False):
        if not path:return None
        path=path.strip()
        key=(path.casefold(),neutral)
        if key in self.textures:return self.textures[key]
        try:
            raw=self.resources.read(path)
            self.texture_hashes[key]=hashlib.sha256(raw).hexdigest()
            if neutral:raw=engine.neutral_texture(raw)
            image=dds.decode(raw) if raw[84:88]==b'DX10' else Image.open(io.BytesIO(raw)).convert('RGBA')
            image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
            filename='texture_'+hashlib.sha256((path+str(neutral)).encode()).hexdigest()[:16]+'.png'
            image.save(self.folder/filename,optimize=False)
            self.textures[key]=filename;return filename
        except (FileNotFoundError,OSError,ValueError) as error:
            self.warnings.append('贴图未显示：%s（%s）'%(path,error));self.textures[key]=None;return None

    def geometry(self,vertices,indices,**info):
        indices=np.asarray(indices,dtype=int).reshape(-1)
        if not len(indices):return
        used,inverse=np.unique(indices,return_inverse=True)
        if used.min()<0 or used.max()>=len(vertices):raise ValueError('预览索引越界')
        data=np.asarray(vertices[used],dtype='<f4')
        self.counter+=1;name='mesh_%04d'%self.counter
        data.tofile(self.folder/(name+'.bin'));np.asarray(inverse,dtype='<u4').tofile(self.folder/(name+'.idx'))
        self.meshes.append(dict(vertex=name+'.bin',index=name+'.idx',stride=data.shape[1],vertices=len(data),
                                triangles=len(indices)//3,**info))


def make_body(project,client,folder,log=lambda _:None):
    source=Path(project['source'])
    if engine.digest(source)!=project['source_sha256']:raise ValueError('输入包已改变，请重新提取后预览。')
    warnings=[];resources=Resources(source,client);writer=AssetWriter(folder,resources,warnings);pitch_supported=True
    try:
        nations={x.get('nation') for x in project['lights'] if x.get('nation')}
        project_nation=project.get('nation') or (next(iter(nations)) if len(nations)==1 else None)
        light_vehicles={x.get('vehicle') for x in project['lights'] if x.get('vehicle')}
        project_vehicle=project.get('vehicle') or (next(iter(light_vehicles)) if len(light_vehicles)==1 else None)
        uml=uml_preview.choose(resources.source,project_nation,project_vehicle) if project_nation and project_vehicle else None
        visuals=part_visuals(resources,project,warnings,uml)
        vehicles={x['vehicle'] for x in project['lights']}
        if not vehicles and project.get('vehicle'):vehicles={project['vehicle']}
        if len(vehicles)!=1:raise ValueError('三维预览一次只支持一辆车。')
        vehicle=project.get('base_vehicle') or next(iter(vehicles))
        if uml and not project.get('base_vehicle'):
            bases={base for nation,base in uml['bases'] if nation==project_nation.casefold()}
            if len(bases)==1:vehicle=next(iter(bases))
        offsets=assembly(resources,vehicle,visuals,warnings,uml)
        if uml:
            warnings.append('按 UML 配置及模型挂点装配；预览不代表游戏内效果。')
            if uml['enabled'] in ('false','0'):warnings.append('此 UML 配置当前标记为禁用；预览不会更改该设置。')
        unsupported=sum(not x.get('supported',False) for x in project['lights'])
        if unsupported:warnings.append('%d 块灯面需专门适配，保留原材质显示，不参与动态编辑。'%unsupported)
        supported={}
        for light in project['lights']:
            if light.get('supported'):
                key=(light['visual'],light['render_set'],light['geometry'],light['group'])
                supported.setdefault(key,set()).update(light['source_triangle_ids'])
        for part,path in visuals.items():
            log('读取'+part+'模型与贴图…')
            raw_visual=resources.read(path);raw_primitives=resources.read(path.replace('.visual_processed','.primitives_processed'))
            visual=engine.xml(raw_visual);matrices,parents=mesh.node_matrices(visual)
            sections=mesh.sections(raw_primitives)
            visual_sha=hashlib.sha256(raw_visual).hexdigest();primitives_sha=hashlib.sha256(raw_primitives).hexdigest()
            decoded={}
            for ri,rs in enumerate(visual.findall('renderSet')):
                nodes=[n.text.strip() for n in rs.findall('node')]
                for gi,geo in enumerate(rs.findall('geometry')):
                    try:
                        vertex_name=geo.findtext('vertices').strip();cache=(vertex_name,tuple(nodes))
                        if cache not in decoded:
                            vertices,skin=mesh.vertex_data(sections[vertex_name])
                            decoded[cache]=transformed(vertices,skin,nodes,matrices)
                        vertices=decoded[cache]
                        for pi,pg in enumerate(geo.findall('primitiveGroup')):
                            indices,_=engine.read_indices(sections,geo,pg)
                            removed=supported.get((path,ri,gi,pi),set())
                            source_triangles=[i for i in range(len(indices)) if i not in removed]
                            if removed:indices=indices[source_triangles]
                            if not len(indices):continue
                            material=resolve_material(resources,pg.find('material'))
                            props={p.text.strip():list(p)[0].text for p in material.findall('property') if p.text and len(p)}
                            shader=(material.findtext('fx') or '').strip().lower()
                            glow='glow' in shader
                            volume=shader.endswith('/volumetric_effect.fx')
                            if volume:
                                warning='体积光使用透明贴图近似显示，动态效果需在游戏内核对。'
                                if warning not in warnings:warnings.append(warning)
                            def in_gun_branch(name):
                                seen=set()
                                while name and name not in seen:
                                    if name=='Gun':return True
                                    seen.add(name);name=parents.get(name)
                                return False
                            branches={in_gun_branch(n) for n in nodes} if part=='gun' else {True}
                            if len(branches)>1:
                                pitch_supported=False
                                warnings.append('炮管含混合静态/倾角骨骼，当前仅显示原始姿态，暂不启用炮管俯仰。')
                            writer.geometry(vertices,indices,part=part,kind='body',inclined=part!='gun' or all(in_gun_branch(n) for n in nodes),
                                            texture=writer.texture(props.get('diffuseMap') or props.get('albedoMap')),
                                            emissive=glow,volume=volume,glowDestBlend=(props.get('destBlend') or '').strip(),
                                            alphaTest=float(props.get('alphaReference',0) or 0)/255 if (props.get('alphaTestEnable') or '').strip().lower()=='true' else 0,
                                            material=(material.findtext('identifier') or '车体').strip(),
                                            source=dict(visual=path, render_set=ri, geometry=gi, group=pi,
                                                        visual_sha256=visual_sha, primitives_sha256=primitives_sha, triangle_ids=source_triangles,
                                                        texture=props.get('diffuseMap') or props.get('albedoMap'),
                                                        texture_sha256=writer.texture_hashes.get(((props.get('diffuseMap') or props.get('albedoMap') or '').strip().casefold(),False))))
                    except (ValueError,KeyError,IndexError,struct.error) as error:
                        warnings.append('%s 的网格 %d/%d 未显示：%s'%(part,ri,gi,error))
        if not writer.meshes:raise ValueError('没有读取到可显示的车体网格。')
        data=dict(schema=SCHEMA,vehicle=next(iter(vehicles)),offsets=offsets,visuals=visuals,
                  pitchSupported=pitch_supported,
                  meshes=writer.meshes,warnings=warnings,source_sha256=project['source_sha256'],
                  triangles=sum(m['triangles'] for m in writer.meshes),material_note='基础贴图近似预览；不执行游戏原生材质')
        write_json(Path(folder)/'scene.json',data);return data
    finally:resources.close()


def evaluate_track(frames,times):
    start=np.array([float(f.findtext('startTime')) for f in frames])
    values=np.array([list(map(float,f.findtext('value').split())) for f in frames])
    incoming=np.array([list(map(float,f.findtext('inTangent').split())) for f in frames])
    outgoing=np.array([list(map(float,f.findtext('outTangent').split())) for f in frames])
    at=np.clip(np.searchsorted(start,times,side='right')-1,0,len(start)-2)
    dt=start[at+1]-start[at];u=(times-start[at])/dt
    return ((2*u**3-3*u*u+1)[:,None]*values[at]+(u**3-2*u*u+u)[:,None]*dt[:,None]*outgoing[at]
            +(-2*u**3+3*u*u)[:,None]*values[at+1]+(u**3-u*u)[:,None]*dt[:,None]*incoming[at+1])


def lamp_plan(project,visuals):
    """Exact export splitting and phase names; extra columns preserve pick identities."""
    selected=[x for x in project['lights'] if x.get('supported') and x.get('selected') and visuals.get(x['part'])==x.get('source_visual',x['visual'])]
    emitted,_=engine.deduplicate_variant_lights(selected,project['recipe'])
    models=engine.render_groups(emitted)
    face_map={x['id']:i for i,x in enumerate(project['lights'])}
    result=[]
    for mi,(((source,anchor,kind,texture), ids),lights) in enumerate(models):
        cfg=recipe.validate_config(engine.model_recipe(lights) or project['recipe'])
        parts=[];indices=[];offset=0
        for light in lights:
            parts.append(np.c_[light['_vertices'],np.full(len(light['_vertices']),face_map[light['id']])])
            indices.extend((light['_indices']+offset).tolist());offset+=len(light['_vertices'])
        vertices=np.concatenate(parts);indices=np.asarray(indices)
        wheel=lights[0]['part']=='chassis' and re.fullmatch(r'(?:W|WD)_[LR]\d+',anchor) is not None
        split=mesh.split_for_direction(vertices,indices,cfg['direction'],lights[0]['_anchor_matrix'],wheel)
        related=np.concatenate([x['_preview'] if '_preview' in x else (np.c_[x['_vertices'][:,:3],np.ones(len(x['_vertices']))]@x['_anchor_matrix'])[:,:3] for x in selected if x['visual']==source])
        center=(related.min(0)+related.max(0))/2
        for bi,(vs,ix,z) in enumerate(split):
            point=mesh.flow_phase_point(vs,z,cfg['direction'],lights[0]['_anchor_matrix'],wheel)
            identifier='light_%03d_band_%02d'%(mi,bi)
            phase=recipe.spatial_offset(point,center,cfg,identifier)
            # Bake only the independent lamp's anchor, leaving the source geometry intact.
            vs=transformed(vs,[],[anchor],{anchor:lights[0]['_anchor_matrix']})
            result.append(dict(vertices=vs,indices=ix,config=cfg,phase=phase,identifier=identifier,
                               part=lights[0]['part'],texture=texture,model_key=((source,anchor,kind,texture),ids),point=point,center=center))
    return result


def make_lamps(project,client,body,folder,log=lambda _:None,cache=None):
    # Deselected recovered rigs remain active in the exported baseline. Preview
    # them with their authenticated original recipe, ignoring current drafts.
    if project.get('recovery'):
        project=dict(project,lights=[dict(x,selected=True,配方=x['recovered_recipe'])
                                    if x.get('recovered_model') and not x.get('selected') else x
                                    for x in project['lights']])
    resources=Resources(project['source'],client);warnings=[];writer=AssetWriter(folder,resources,warnings)
    try:
        relevant=[x for x in project['lights'] if x.get('supported') and body['visuals'].get(x['part'])==x.get('source_visual',x['visual'])]
        active=[x for x in relevant if x.get('selected')]
        emitted,_=engine.deduplicate_variant_lights(active,project['recipe'])
        groups=engine.render_groups(emitted)
        # Group membership is part of geometry identity; changing only colour
        # or brightness within an unchanged group can reuse its mesh buffers.
        shape=[(key,(lights[0].get('配方') or project['recipe'])['流水方向']) for key,lights in groups]
        shape.append(tuple((x['id'],bool(x.get('selected'))) for x in relevant))
        key=hashlib.sha256(json.dumps(shape,ensure_ascii=False).encode()).hexdigest()
        reuse=cache is not None and cache.get('key')==key
        if reuse:
            configs={key:recipe.validate_config(engine.model_recipe(lights) or project['recipe']) for key,lights in groups}
            bands=[]
            for original in cache['bands']:
                band=dict(original);cfg=configs[band['model_key']];band['config']=cfg
                band['phase']=recipe.spatial_offset(band['point'],band['center'],cfg,band['identifier']);bands.append(band)
        else:bands=lamp_plan(project,body['visuals'])
        selected={x['id'] for x in project['lights'] if x.get('selected')}
        width=max([min(4096,max(128,math.ceil(b['config']['period']/min(b['config']['step'],b['config']['breath'])*64))) for b in bands] or [128])
        if len(bands)>4096 or width*max(1,len(bands))>4194304:
            raise ValueError('当前灯效超出三维预览的显存预算，请减少灯面或缩短循环；二维预览与导出仍可使用。')
        curve_keys=[]
        for band in bands:
            cfg=band['config'];normalized={k:v for k,v in cfg.items() if k not in ('raw','peak','palette')}
            normalized['palette']=[[round(c/cfg['peak'],12) for c in rgb] for rgb in cfg['palette']]
            curve_keys.append((band['identifier'],band['phase'],normalized))
        animation_key=hashlib.sha256((key+json.dumps(curve_keys,sort_keys=True)).encode()).hexdigest()
        reuse_animation=cache is not None and cache.get('animation_key')==animation_key
        revision=int(Path(folder).name.rsplit('_',1)[-1]) if re.fullmatch(r'lamps_\d+',Path(folder).name) else 0
        lut=None if reuse_animation else np.ones((max(1,len(bands)),width,4),dtype='<f4')
        tracks=[]
        # One material draw per part/texture. Band ID is a vertex attribute, not a material.
        batches={}
        for index,band in enumerate(bands):
            cfg=band['config']
            if not reuse_animation:
                times=np.linspace(0,cfg['period'],width)
                frames=recipe.colour_track(band['identifier'],band['phase'],cfg).findall('frame')
                lut[index]=evaluate_track(frames,times)
            gain=cfg['peak']/cache['animation_base_peaks'][index] if reuse_animation else 1.
            tracks.append(dict(period=cfg['period'],breath=cfg['breath'],low=cfg['low'],nativePulse=cfg['mode']=='流水呼吸' and recipe.has_dimming(cfg),gain=gain))
            if not reuse:
                vs=np.c_[band['vertices'],np.full(len(band['vertices']),index)]
                batch=batches.setdefault((band['part'],band['texture']),[]);batch.append((vs,np.asarray(band['indices']).reshape(-1)))
        for (part,texture),batch in batches.items():
            arrays=[];indices=[];offset=0
            for vs,ix in batch:arrays.append(vs);indices.extend((ix+offset).tolist());offset+=len(vs)
            writer.geometry(np.concatenate(arrays),indices,part=part,kind='lamp',texture=writer.texture(texture,True),emissive=True)
        # Unselected extracted lamps keep their source colour and remain pickable.
        unselected_batches={}
        for light in ([] if reuse else project['lights']):
            if not light.get('supported') or light['id'] in selected or body['visuals'].get(light['part'])!=light.get('source_visual',light['visual']):continue
            anchor=light['anchor'];vs=transformed(light['_vertices'],[],[anchor],{anchor:light['_anchor_matrix']})
            face_id=next(i for i,x in enumerate(project['lights']) if x['id']==light['id'])
            unselected_batches.setdefault((light['part'],light['texture']),[]).append(
                (np.c_[vs,np.full(len(vs),face_id),np.full(len(vs),-1)],light['_indices'].reshape(-1)))
        for (part,texture),batch in unselected_batches.items():
            arrays=[];indices=[];offset=0
            for vs,ix in batch:arrays.append(vs);indices.extend((ix+offset).tolist());offset+=len(vs)
            writer.geometry(np.concatenate(arrays),indices,part=part,kind='unselected',texture=writer.texture(texture),emissive=True)
        if not reuse_animation:lut.tofile(Path(folder)/'animation.bin')
        if reuse:
            geometry=cache['meshes'];mesh_revision=cache['revision'];warnings=cache['warnings']
        else:
            geometry=writer.meshes;mesh_revision=revision
            if cache is not None:cache.update(key=key,bands=bands,meshes=geometry,revision=mesh_revision,warnings=warnings)
        animation_revision=cache['animation_revision'] if reuse_animation else revision
        if cache is not None and not reuse_animation:
            cache.update(animation_key=animation_key,animation_revision=revision,animation_base_peaks=[b['config']['peak'] for b in bands])
        data=dict(schema=SCHEMA,meshes=geometry,tracks=tracks,lutWidth=width,lutHeight=max(1,len(bands)),geometryKey=key,meshRevision=mesh_revision,
                  animationKey=animation_key,animationRevision=animation_revision,
                  faceIds=[x['id'] for x in project['lights']],warnings=warnings,
                  bands=[dict(identifier=b['identifier'],phase=b['phase']) for b in bands])
        write_json(Path(folder)/'scene.json',data);return data
    finally:resources.close()


def apply_state(project,state):
    project=copy.copy(project);project['recipe']=state['recipe'];recipe.validate_config(project['recipe'])
    lights=[]
    by_id={x['id']:x for x in state['lights']}
    for original in project['lights']:
        light=dict(original);edit=by_id.get(light['id'],{})
        light['selected']=bool(edit.get('selected',False)) and light.get('supported',False)
        light.pop('配方',None)
        if edit.get('recipe') is not None:recipe.validate_config(edit['recipe']);light['配方']=edit['recipe']
        lights.append(light)
    project['lights']=lights;return project


def worker(session):
    session=Path(session);request=json.loads((session/'request.json').read_text(encoding='utf-8'))
    project=load_snapshot(session);client=request.get('client');generation=-1;lamp_cache={}
    def log(message):write_json(session/'progress.json',dict(message=message))
    try:
        if engine.digest(project['source'])!=project['source_sha256']:
            raise ValueError('输入包已改变，请重新提取后预览。')
        source_stat=Path(project['source']).stat();source_stamp=(source_stat.st_size,source_stat.st_mtime_ns)
        stamp=[]
        if client:
            root=Path(client)
            stamp=[engine.digest(root/'version.xml'),engine.digest(root/'paths.xml')]
            stamp.extend((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted((root/'res/packages').glob('*.pkg')))
        identity=[project.get('nation'),project.get('vehicle'),project.get('base_vehicle')]
        key=hashlib.sha256((project['source_sha256']+str(client)+str(SCHEMA)+json.dumps(stamp)+json.dumps(identity)+json.dumps([(x['id'],x.get('supported')) for x in project['lights']])).encode()).hexdigest()[:24]
        base=Path(request['cache'])/key
        if not (base/'scene.json').exists():body=make_body(project,client,base,log)
        else:body=json.loads((base/'scene.json').read_text(encoding='utf-8'))
        write_json(session/'body.json',dict(folder=str(base),scene=body))
        log('整车已加载，正在准备灯面…')
        while not (session/'stop').exists():
            try:state=json.loads((session/'state.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):time.sleep(.1);continue
            current=state['revision']
            if current==generation:time.sleep(.1);continue
            folder=session/('lamps_%d'%current)
            try:
                source_stat=Path(project['source']).stat()
                if (source_stat.st_size,source_stat.st_mtime_ns)!=source_stamp:
                    raise ValueError('预览期间输入包发生变化，请重新提取。')
                updated=apply_state(project,state)
                started=time.perf_counter();lamps=make_lamps(updated,client,body,folder,log,lamp_cache)
                write_json(session/'ready.json',dict(revision=current,folder=str(folder),scene=lamps,prepare_seconds=time.perf_counter()-started))
                log('三维灯效已更新')
            except Exception as error:
                write_json(session/'error.json',dict(revision=current,message=str(error)))
            generation=current
            for old in session.glob('lamps_*'):
                # Prune only this session's own obsolete generations. Keep the
                # geometry generation still referenced by the current animation.
                if (old.is_dir() and old.name not in ('lamps_%s'%lamp_cache.get('revision'),'lamps_%s'%lamp_cache.get('animation_revision'))
                        and re.fullmatch(r'lamps_\d+',old.name) and int(old.name[6:])<current-3
                        and time.time()-old.stat().st_mtime>30 and old.resolve().is_relative_to(session.resolve())):
                    shutil.rmtree(old)
    except Exception as error:write_json(session/'error.json',dict(revision=-1,message=str(error)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('session');worker(parser.parse_args().session)
