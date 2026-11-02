"""Ordered image placements on authenticated model textures."""
import base64, copy, hashlib, io, math, re, zipfile
import xml.etree.ElementTree as ET
import numpy as np
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps
from . import dds, light_effects as engine, light_recovery, wotdata, uml_preview
from .common import title_name, write_json
from .preview3d_assets import Resources

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_LAYERS = 32
MAX_TOTAL_IMAGE_BYTES = 32 * 1024 * 1024

def create_stock_project(tank, folder):
    """建立只含元数据的载体；原版网格和贴图仍从所选客户端读取。"""
    parts = tank.split('/')
    if len(parts)!=2 or not all(re.fullmatch(r'[A-Za-z0-9_-]+',x) for x in parts):
        raise ValueError('请选择索引中的有效车型。')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    source=folder/'原版资源载体.wotmod'
    with zipfile.ZipFile(source,'x',zipfile.ZIP_STORED) as z:
        z.writestr('meta.xml','<root><id>local.wotworkbench.paint3d</id><version>1.0</version><name>3D paint</name></root>')
    return dict(schema=1, source=str(source), source_sha256=engine.digest(source),
                lights=[], nation=parts[0], vehicle=parts[1], recipe=copy.deepcopy(engine.DEFAULT_RECIPE),
                baseline_user_confirmed=False, source_kind='client_stock')

def project_from_package(tank, source):
    """只接受当前车型的涂装或关联的 UML 配置，拒绝灯效成品工程。"""
    nation,vehicle=tank.split('/')
    source=Path(source).resolve()
    with zipfile.ZipFile(source) as z:
        engine.check_archive(z)
        if light_recovery.manifests(z.namelist()):
            raise ValueError('暂不支持直接修改灯效成品包；请先完成三维贴图，再导入灯效制作器。')
        identities=set()
        for name in z.namelist():
            match=re.match(r'^res/vehicles/([^/]+)/([^/]+)/',name,re.I)
            if match:identities.add((match[1].casefold(),match[2].casefold()))
        uml=uml_preview.choose(z,nation,vehicle)
        if not uml and identities!={(nation.casefold(),vehicle.casefold())}:
            raise ValueError('请选择只包含当前所选车型的涂装包。')
        if uml:
            # The configured custom model is the editable resource identity;
            # keep the selected base vehicle separately for its descriptor.
            base_vehicle=vehicle
            sample=next(iter(uml['visuals'].values())).split('/')
            nation,vehicle=sample[2:4]
        else:base_vehicle=None
    return dict(schema=1,source=str(source),source_sha256=engine.digest(source),lights=[],
                nation=nation,vehicle=vehicle,recipe=copy.deepcopy(engine.DEFAULT_RECIPE),
                base_vehicle=base_vehicle,baseline_user_confirmed=False,source_kind='user_package')

def render_placement(original, decal, u, v, scale, angle):
    """The UV origin and rotation match the preview canvas; preserve base alpha."""
    width=max(1,round(original.width*scale))
    height=max(1,round(width*decal.height/decal.width))
    if width>original.width*2 or height>original.height*4:
        raise ValueError('图片过大，请缩小后再生成。')
    image=decal.resize((width,height),Image.Resampling.LANCZOS)
    if angle:image=image.rotate(-angle,expand=True,resample=Image.Resampling.BICUBIC)
    layer=Image.new('RGBA',original.size)
    x=round(u*original.width-image.width/2);y=round(v*original.height-image.height/2)
    layer.alpha_composite(image,dest=(x,y))
    result=Image.alpha_composite(original.convert('RGBA'),layer)
    result.putalpha(original.convert('RGBA').getchannel('A'))
    return result

def encode_preserve_alpha(image, reference):
    """Retain the original opacity at every mip, including original BC3 blocks."""
    info=dds.inspect(reference)
    if info.fourcc not in ('DXT1','DXT3','DXT5','BC7','RGBA8','BGRA8','BGRX8'):
        raise ValueError('该 AM 贴图格式不受支持：'+info.format_name)
    if info.fourcc in ('DXT3','DXT5'):
        # BC2/BC3 store opacity in the first eight bytes of each block;
        # keeping those bytes also preserves independently authored mip alpha.
        result=bytearray(dds.encode_like(image,reference))
        for offset in range(info.offset,len(result),16):
            result[offset:offset+8]=reference[offset:offset+8]
        result=bytes(result)
    elif info.fourcc=='DXT1':
        # BC1 combines colour and opacity in each block, so encode every mip
        # with that mip's own original 1-bit opacity mask.
        result=bytearray(reference[:info.offset]);mip=image.convert('RGBA')
        for (w,h,count),source in zip(info.sizes(),dds.decode_mips(reference)):
            if mip.size!=(w,h):mip=mip.resize((w,h),Image.Resampling.BOX)
            mip.putalpha(source.convert('RGBA').getchannel('A'))
            encoded=dds._encode_level(mip,'DXT1')
            if len(encoded)!=count:raise ValueError('DDS 编码器返回了错误的块长度。')
            result.extend(encoded)
        result=bytes(result)
    else:result=dds.encode_like(image,reference)
    dds.verify_matches(result,reference)
    for old,new in zip(dds.decode_mips(reference),dds.decode_mips(result)):
        if not np.array_equal(np.asarray(old.convert('RGBA'))[...,3],np.asarray(new.convert('RGBA'))[...,3]):
            raise ValueError('压缩后透明通道发生变化，已停止生成；该透明贴图无法无损保留透明度。')
    return result

def _validate_layer(project,body,payload):
    """Validate every layer independently, including its vehicle-local texture."""
    try:
        index=payload['mesh'];u=float(payload['u']);v=float(payload['v']);scale=float(payload['scale']);angle=float(payload['angle'])
        if type(index) is not int or index<0 or index>=len(body['meshes']):raise ValueError('所选模型无效。')
        if not all(math.isfinite(x) for x in (u,v,scale,angle)) or not(0<=u<=1 and 0<=v<=1 and .01<=scale<=1 and -180<=angle<=180):
            raise ValueError('图片位置、大小或角度无效。')
        encoded=payload['image']
        if not isinstance(encoded,str) or len(encoded)>MAX_IMAGE_BYTES*4//3+8:raise ValueError('图片超过 8 MB。')
        raw_image=base64.b64decode(encoded,validate=True)
        if not raw_image or len(raw_image)>MAX_IMAGE_BYTES:raise ValueError('图片超过 8 MB。')
    except (KeyError,TypeError,OverflowError,ValueError) as error:
        raise ValueError('图片或位置参数无效：'+str(error)) from error
    item=body['meshes'][index];ref=item.get('source') or {}
    texture=str(ref.get('texture') or '').strip().replace('\\','/').removeprefix('res/')
    prefix=('vehicles/'+project['nation']+'/'+project['vehicle']+'/').casefold()
    if not texture.casefold().startswith(prefix) or not texture.casefold().endswith('_am.dds'):
        raise ValueError('该位置不是本车可编辑的 AM 贴图；请点击其他表面。')
    return dict(mesh=index,u=u,v=v,scale=scale,angle=angle,raw_image=raw_image,texture=texture,ref=ref)


def build(project, client, body, payload, output_dir, title):
    """Compose saved layers in order, then encode each affected texture once."""
    if engine.digest(project['source'])!=project['source_sha256'] or body.get('source_sha256')!=project['source_sha256']:
        raise ValueError('输入包或预览已改变，请重新打开三维贴图。')
    if not isinstance(payload,dict):raise ValueError('贴图参数无效。')
    layers=payload.get('layers',[payload])
    if not isinstance(layers,list) or not 1<=len(layers)<=MAX_LAYERS:
        raise ValueError('一次可保存 1～32 张图片。')
    edits=[];total=0
    for value in layers:
        if not isinstance(value,dict):raise ValueError('贴图层参数无效。')
        edit=_validate_layer(project,body,value);total+=len(edit['raw_image'])
        if total>MAX_TOTAL_IMAGE_BYTES:raise ValueError('图片总大小不能超过 32 MB。')
        edits.append(edit)
    resources=Resources(project['source'],client)
    groups=0;group_issues=[];targets={};target_pixels=0;checked_models={}
    try:
        for edit in edits:
            key=edit['texture'].casefold()
            if key not in targets:
                raw=resources.read(edit['texture']);info=dds.inspect(raw)
                if max(info.width,info.height)>8192:raise ValueError('贴图尺寸超过 8192，暂不能处理。')
                target_pixels+=info.width*info.height
                if target_pixels>64000000:raise ValueError('所编辑贴图的总像素过大，请分次处理。')
                original=dds.decode(raw)
                targets[key]=dict(texture=edit['texture'],raw=raw,original=original,result=original.copy())
            target=targets[key]
            if not edit['ref'].get('texture_sha256') or hashlib.sha256(target['raw']).hexdigest()!=edit['ref']['texture_sha256']:
                raise ValueError('原贴图与预览不一致，请重新打开。')
            ref=edit['ref'];visual=ref.get('visual')
            if not isinstance(visual,str):raise ValueError('预览缺少原模型信息。')
            primitive=visual.replace('.visual_processed','.primitives_processed')
            for name,hash_key in ((visual,'visual_sha256'),(primitive,'primitives_sha256')):
                if name not in checked_models:checked_models[name]=hashlib.sha256(resources.read(name)).hexdigest()
                if not ref.get(hash_key) or checked_models[name]!=ref[hash_key]:raise ValueError('原模型或网格与预览不一致，请重新打开。')
            try:
                with Image.open(io.BytesIO(edit['raw_image'])) as im:
                    if im.format not in ('PNG','JPEG','WEBP') or im.width*im.height>25000000:
                        raise ValueError('请选择不超过 2500 万像素的 PNG、JPG 或 WebP 图片。')
                    decal=ImageOps.exif_transpose(im).convert('RGBA')
            except (OSError,Image.DecompressionBombError) as error:raise ValueError('图片无法读取。') from error
            target['result']=render_placement(target['result'],decal,edit['u'],edit['v'],edit['scale'],edit['angle'])
        # Geometry is not edited here. Record problems already present in all
        # displayed vehicle parts separately from the new texture validation.
        for body_visual in set(body.get('visuals',{}).values()):
            prim=body_visual.replace('.visual_processed','.primitives_processed')
            count,issues=engine.visual_group_audit(resources,body_visual,{prim.lower():prim})
            groups+=count
            group_issues.extend(dict(resource=body_visual,location=where,issue=message,preexisting=True) for where,message in issues)
    finally:resources.close()
    changed={}
    for key,item in targets.items():
        before=np.asarray(item['original']);after=np.asarray(item['result'])
        if not np.any(np.any(before[...,:3]!=after[...,:3],axis=2)&(before[...,3]>0)):continue
        data=encode_preserve_alpha(item['result'],item['raw'])
        if data!=item['raw']:changed[key]=dict(item,data=data)
    if not changed:raise ValueError('图片没有覆盖可见区域或压缩后没有变化，请调整位置或大小。')
    out=Path(output_dir)/(title_name(title)+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True,exist_ok=False)
    target=out/(title_name(title)+'_三维贴图_待实测.wotmod');staged=target.with_suffix('.wotmod.building')
    with zipfile.ZipFile(project['source']) as z:
        engine.check_archive(z);names={n.casefold():n for n in z.namelist()}
    replacements={};additions={}
    for item in changed.values():
        name='res/'+item['texture'];existing=names.get(name.casefold())
        (replacements if existing else additions)[existing or name]=item['data']
    engine.write_game_archive(project['source'],staged,replacements,additions)
    engine.check_game_zip(staged)
    with zipfile.ZipFile(project['source']) as before,zipfile.ZipFile(staged) as after:
        engine.check_archive(after)
        for name,data in {**replacements,**additions}.items():
            if after.read(name)!=data:raise ValueError('最终包贴图与生成结果不一致。')
        for entry in before.infolist():
            if entry.filename in replacements:continue
            written=after.getinfo(entry.filename)
            if (entry.CRC,entry.file_size)!=(written.CRC,written.file_size):raise ValueError('非目标资源发生变化。')
    for item in changed.values():dds.verify_matches(item['data'],item['raw'])
    root=engine.resolve_client_root(client)
    version=ET.parse(root/'version.xml').getroot()
    report=dict(artifact=dict(path=str(target),sha256=engine.digest(staged),bytes=staged.stat().st_size),
        baseline=dict(kind=project['source_kind'],path=project['source'] if project['source_kind']=='user_package' else str(root),
                      sha256=project['source_sha256'] if project['source_kind']=='user_package' else None,status='unconfirmed',agent_observed=False),
        environment=dict(root=str(root),version=wotdata.game_version(root),client_version=version.findtext('version','').strip(),realm=version.findtext('meta/realm','').strip(),paths_xml_sha256=engine.digest(root/'paths.xml')),
        texture=edits[0]['texture'],source_texture_sha256=hashlib.sha256(targets[edits[0]['texture'].casefold()]['raw']).hexdigest(),
        image_sha256=hashlib.sha256(edits[0]['raw_image']).hexdigest(),position=[edits[0]['u'],edits[0]['v']],scale=edits[0]['scale'],angle=edits[0]['angle'],
        layers=[dict(mesh=e['mesh'],texture=e['texture'],position=[e['u'],e['v']],scale=e['scale'],angle=e['angle'],image_sha256=hashlib.sha256(e['raw_image']).hexdigest()) for e in edits],
        textures=[dict(path=e['texture'],format=dds.inspect(e['raw']).format_name,source_sha256=hashlib.sha256(e['raw']).hexdigest(),sha256=hashlib.sha256(e['data']).hexdigest()) for e in changed.values()],
        file_validation=dict(status='passed',zip_crc=True,zip_stored=True,dds_structure='passed',other_entries_unchanged=True),
        offline_validation=dict(status='partial',groups_checked=groups,preexisting_group_issues=group_issues,vehicle_dependency_check='not_tested',game_shader_execution='not_tested'),
        in_game_tested=False,whole_vehicle_loading=dict(status='not_tested'),
        limitations=['预览为近似渲染；同一贴图共享 UV 的其他位置也会受影响。','只覆盖本次编辑的 AM 贴图；其他 LOD、外观、mip 和压缩效果需检查。','游戏内整车加载与实际视觉效果未实测。'])
    write_json(out/'验证记录.json',report)
    for i,item in enumerate(changed.values()):item['result'].save(out/('贴图预览.png' if i==0 else '贴图预览_%d.png'%(i+1)))
    staged.rename(target)
    return target,report
