"""原始网格选区身份；仅记录，不写入游戏资源。"""
import re


def resolve(scene, batches):
    """Translate preview triangle numbers into original primitiveGroup indices.

    Scene metadata comes from the extraction step, not the browser. A selection
    remains bound to the input digest and the exact preview geometry. Each batch
    is (preview mesh index, list of zero-based triangle indices).
    """
    checksum = scene.get('source_sha256', '')
    if not re.fullmatch(r'[a-f0-9]{64}', checksum):
        raise ValueError('选区缺少有效的原包 SHA256')
    if not isinstance(batches, list) or not batches:
        raise ValueError('请先选择模型区域')
    meshes = scene.get('meshes', [])
    groups = {}
    for batch in batches:
        if not isinstance(batch, dict) or type(batch.get('mesh')) is not int:
            raise ValueError('选区网格编号无效')
        index = batch['mesh']
        if index < 0 or index >= len(meshes):
            raise ValueError('选区网格编号超出范围')
        m = meshes[index]
        source = m.get('source')
        ids = batch.get('triangles')
        if not source or not isinstance(ids, list) or not ids:
            raise ValueError('选区不含可追踪的三角面')
        mapping = source.get('triangle_ids', [])
        if len(mapping) != m.get('triangles'):
            raise ValueError('预览三角面与原始索引映射不一致')
        if any(type(i) is not int or i < 0 or i >= len(mapping) for i in ids):
            raise ValueError('选区三角面编号超出范围')
        key = (source['visual'], source['render_set'], source['geometry'], source['group'])
        row = groups.setdefault(key, dict(visual=key[0], render_set=key[1], geometry=key[2],
                                          group=key[3], texture=source.get('texture'), visual_sha256=source.get('visual_sha256'), primitives_sha256=source.get('primitives_sha256'), texture_sha256=source.get('texture_sha256'), triangles=set()))
        if row['texture'] != source.get('texture'):
            raise ValueError('同一网格引用了不同贴图')
        row['triangles'].update(mapping[i] for i in ids)
    return dict(schema=1, source_sha256=checksum,
                groups=[{**v, 'triangles': sorted(v['triangles'])} for _, v in sorted(groups.items())])


def extract_rigid_lights(project, selection, offset=0.002, client=None):
    """Build rigid overlay records from authenticated original triangles.

    Existing vehicle geometry stays intact; unsupported multi-bone selections
    fail instead of flattening their deformation.
    """
    import hashlib
    import zipfile
    from pathlib import Path
    import numpy as np
    from . import light_effects as engine, light_assets as mesh
    if engine.digest(project['source']) != project['source_sha256'] or selection.get('source_sha256') != project['source_sha256']:
        raise ValueError('输入包或选区哈希不匹配，请重新导入并框选。')
    records = []
    from .preview3d_assets import Resources
    resources=Resources(project['source'],client)
    try:
      with zipfile.ZipFile(project['source']) as archive:
          engine.check_archive(archive)
          names = {n.casefold(): n for n in archive.namelist()}
          for group in selection['groups']:
              path = group['visual']
              if '/normal/lod0/' not in path.casefold():
                  raise ValueError('选区模型不在输入包内或不是 normal/lod0。')
              fields = path.replace('\\','/').split('/')
              if len(fields) < 7 or fields[:2] != ['res', 'vehicles']:
                  raise ValueError('无法识别选区的车型。')
              part = Path(path).stem.lower().split('_')[0]
              if part not in ('chassis','hull','turret','gun'):
                  raise ValueError('选区不是受支持的车辆部件。')
              raw_visual=resources.read(path);prim=path.replace('.visual_processed','.primitives_processed');raw_primitives=resources.read(prim)
              if group.get('visual_sha256') and hashlib.sha256(raw_visual).hexdigest()!=group['visual_sha256']:raise ValueError('原模型已变化，请重新框选。')
              if group.get('primitives_sha256') and hashlib.sha256(raw_primitives).hexdigest()!=group['primitives_sha256']:raise ValueError('原网格已变化，请重新框选。')
              visual=engine.xml(raw_visual);matrices,parents=mesh.node_matrices(visual)
              sections=mesh.sections(raw_primitives)
              try:
                  rs=visual.findall('renderSet')[group['render_set']]
                  geo=rs.findall('geometry')[group['geometry']]
                  pg=geo.findall('primitiveGroup')[group['group']]
                  vertices,skin=mesh.vertex_data(sections[geo.findtext('vertices').strip()])
                  indices,_=engine.read_indices(sections,geo,pg)
                  chosen=group['triangles']
                  if not chosen or any(type(i) is not int or i<0 or i>=len(indices) for i in chosen):
                      raise ValueError('三角面超出原始网格范围。')
                  ids=indices[chosen]
                  if ids.min()<0 or ids.max()>=len(vertices):raise ValueError('选区顶点索引无效。')
                  nodes=[n.text.strip() for n in rs.findall('node')]
                  anchor,kind,transform=engine.attachment(vertices,skin,ids,nodes,matrices,parents,part)
                  vi,inverse=np.unique(ids,return_inverse=True);points=vertices[vi].copy()
                  points[:,:3]=(np.c_[points[:,:3],np.ones(len(points))]@transform)[:,:3]
                  points[:,3:6]=points[:,3:6]@np.linalg.inv(transform[:3,:3]).T
                  points[:,3:6]/=np.maximum(np.linalg.norm(points[:,3:6],axis=1)[:,None],1e-12)
                  points[:,:3]+=points[:,3:6]*offset
                  matrix=matrices[anchor] if kind=='node' else np.eye(4)
                  preview=(np.c_[points[:,:3],np.ones(len(points))]@matrix)[:,:3]
              except (IndexError,KeyError,TypeError) as error:
                  raise ValueError('选区与原始网格不匹配，请重新框选。') from error
              identity=hashlib.sha256((path+str(group['render_set'])+str(group['geometry'])+str(group['group'])+str(chosen)).encode()).hexdigest()[:16]
              records.append(dict(id='area_'+identity,vehicle=fields[3],nation=fields[2],part=part,visual=path,
                  primitives=prim,render_set=group['render_set'],geometry=group['geometry'],group=group['group'],
                  material='框选附加灯面',source_triangle_ids=chosen,texture='res/__area_white__.dds',
                  triangles=len(chosen),supported=True,selected=True,anchor=anchor,anchor_kind=kind,
                  transform=transform.tolist(),_vertices=points,_indices=inverse.reshape(-1,3),_anchor_matrix=matrix,
                  _preview=preview,bounds=[preview.min(0).tolist(),preview.max(0).tolist()],overlay_body=True))
    finally:
        resources.close()
    if not records:raise ValueError('选区为空。')
    return records


def paint_texture(project, selection, body, folder, image_path, client, output_dir, title,
                  center_x=0.5, center_y=0.5, scale=1.0, baseline=False):
    """Apply an image within selected UV triangles; preserve other DDS blocks.

    Only one vehicle-local texture is supported. Shared or ambiguous UV islands
    in the displayed model are rejected. Game appearance remains untested.
    """
    from pathlib import Path
    from datetime import datetime
    import io, json, zipfile
    import numpy as np
    from PIL import Image, ImageDraw, ImageChops, ImageFilter
    from . import light_effects as engine, dds, wotdata
    from .common import title_name, write_json
    from .preview3d_assets import Resources
    if engine.digest(project['source']) != project['source_sha256'] or selection.get('source_sha256') != project['source_sha256'] or body.get('source_sha256') != project['source_sha256']:
        raise ValueError('输入包、预览或选区的哈希不一致，请重新导入。')
    if not 0<=center_x<=1 or not 0<=center_y<=1 or not 0.05<=scale<=4:
        raise ValueError('位置须为 0～1，缩放须为 0.05～4。')
    texture_names={str(g.get('texture') or '').strip().replace('\\','/').removeprefix('res/') for g in selection['groups']}
    if len(texture_names)!=1 or not next(iter(texture_names)):
        raise ValueError('一次只能选择使用同一张贴图的面。')
    texture=next(iter(texture_names))
    first=selection['groups'][0]['visual'].split('/')
    vehicle_prefix=('vehicles/'+first[2]+'/'+first[3]+'/').casefold()
    if not texture.casefold().startswith(vehicle_prefix) or not texture.casefold().endswith('_am.dds'):
        raise ValueError('仅支持该车自身的 AM 贴图；共享履带和其他材质不可直接修改。')
    import hashlib
    resources=Resources(project['source'],client)
    try:
        raw=resources.read(texture)
        texture_sha=hashlib.sha256(raw).hexdigest()
        checked=set()
        for item in body['meshes']:
            ref=item.get('source') or {}; current=str(ref.get('texture') or '').strip().replace('\\','/').removeprefix('res/')
            if current.casefold()!=texture.casefold():continue
            if ref.get('texture_sha256') and ref['texture_sha256']!=texture_sha:raise ValueError('原贴图已变化，请重新打开预览。')
            visual=ref.get('visual');primitive=visual.replace('.visual_processed','.primitives_processed') if visual else ''
            if (visual,primitive) in checked:continue
            if not visual or (ref.get('visual_sha256') and hashlib.sha256(resources.read(visual)).hexdigest()!=ref['visual_sha256']):raise ValueError('原模型已变化，请重新打开预览。')
            if ref.get('primitives_sha256') and hashlib.sha256(resources.read(primitive)).hexdigest()!=ref['primitives_sha256']:raise ValueError('原网格已变化，请重新打开预览。')
            checked.add((visual,primitive))
    finally:resources.close()
    info=dds.inspect(raw);original=dds.decode(raw)
    selected=Image.new('L',original.size);other=Image.new('L',original.size)
    chosen={(g['visual'],g['render_set'],g['geometry'],g['group']):set(g['triangles']) for g in selection['groups']}
    hits=0;uv_points=[]
    for item in body['meshes']:
        source=item.get('source') or {}
        current=str(source.get('texture') or '').strip().replace('\\','/').removeprefix('res/')
        if current.casefold()!=texture.casefold():continue
        vertices=np.fromfile(Path(folder)/item['vertex'],dtype='<f4').reshape(-1,item['stride'])
        indices=np.fromfile(Path(folder)/item['index'],dtype='<u4').reshape(-1,3)
        mapping=source.get('triangle_ids',[])
        if len(mapping)!=len(indices):raise ValueError('预览网格与原始选区不一致。')
        key=(source.get('visual'),source.get('render_set'),source.get('geometry'),source.get('group'))
        wanted=chosen.get(key,set())
        for n,tri in enumerate(indices):
            uv=vertices[tri,6:8]
            if not np.isfinite(uv).all() or (uv<0).any() or (uv>1).any():
                raise ValueError('贴图使用重复或超出 0～1 的 UV，暂不能安全局部修改。')
            points=[(float(u)*(info.width-1),float(v)*(info.height-1)) for u,v in uv]
            if mapping[n] in wanted:
                ImageDraw.Draw(selected).polygon(points,fill=255);uv_points.extend(points);hits+=1
            else:ImageDraw.Draw(other).polygon(points,fill=255)
    if hits!=sum(len(g['triangles']) for g in selection['groups']):raise ValueError('选区未完整映射到预览贴图。')
    if not selected.getbbox():raise ValueError('选区 UV 没有有效面积。')
    # Erode shared triangle borders before comparing; interior UV overlap means
    # an unselected surface samples the same texels and cannot be isolated.
    if ImageChops.multiply(selected.filter(ImageFilter.MinFilter(3)),other.filter(ImageFilter.MinFilter(3))).getbbox():
        raise ValueError('未选区域与选区共用 UV，直接改贴图会同时改变其他表面；请另选区域或使用模型材质拆分。')
    with Image.open(image_path) as im:decal=im.convert('RGBA')
    bounds=selected.getbbox(); width=max(1,round((bounds[2]-bounds[0])*scale));height=max(1,round(width*decal.height/decal.width))
    if width>info.width*4 or height>info.height*4:raise ValueError('贴图尺寸过大，请降低缩放。')
    decal=decal.resize((width,height),Image.Resampling.LANCZOS)
    layer=Image.new('RGBA',original.size);x=round(bounds[0]+center_x*(bounds[2]-bounds[0])-width/2);y=round(bounds[1]+center_y*(bounds[3]-bounds[1])-height/2);layer.paste(decal,(x,y))
    mask=ImageChops.multiply(layer.getchannel('A'),selected);rgb=Image.composite(layer.convert('RGB'),original.convert('RGB'),mask);rgb.putalpha(original.getchannel('A'))
    encoded=dds.encode_like(rgb,raw);result=bytearray(raw);pos=info.offset;changed_blocks=0
    for w,h,n in info.sizes():
        mip=mask.resize((w,h),Image.Resampling.BOX);arr=np.asarray(mip);cols=(w+3)//4
        if not info.block:
            original_pixels=np.frombuffer(result,dtype=np.uint8,count=n,offset=pos).reshape(h,w,4)
            new_pixels=np.frombuffer(encoded,dtype=np.uint8,count=n,offset=pos).reshape(h,w,4)
            selected_pixels=arr>0;original_pixels[selected_pixels]=new_pixels[selected_pixels]
            changed_blocks+=int(selected_pixels.sum());del original_pixels,new_pixels
            pos+=n;continue
        for by in range((h+3)//4):
            for bx in range(cols):
                if np.any(arr[by*4:min(h,by*4+4),bx*4:min(w,bx*4+4)]):
                    start=pos+(by*cols+bx)*info.block;result[start:start+info.block]=encoded[start:start+info.block];changed_blocks+=1
        pos+=n
    if not changed_blocks:raise ValueError('图片没有覆盖选区。')
    out=Path(output_dir)/(title_name(title)+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));out.mkdir(parents=True,exist_ok=False)
    name='res/'+texture
    with zipfile.ZipFile(project['source']) as z:
        engine.check_archive(z);existing=next((n for n in z.namelist() if n.casefold()==name.casefold()),None)
    target=out/(title_name(title)+'_贴图_待实测.wotmod');staged=target.with_suffix('.wotmod.building')
    engine.write_game_archive(project['source'],staged,{existing:bytes(result)} if existing else {}, {} if existing else {name:bytes(result)})
    with zipfile.ZipFile(project['source']) as before, zipfile.ZipFile(staged) as after:
        engine.check_archive(after)
        output_name=existing or name
        encoded_final=after.read(output_name)
        if encoded_final!=bytes(result):raise ValueError('最终包中的贴图与生成结果不一致。')
        dds.verify_matches(encoded_final,raw)
        for entry in before.infolist():
            if entry.filename==existing:continue
            written=after.getinfo(entry.filename)
            if (entry.CRC,entry.file_size)!=(written.CRC,written.file_size):raise ValueError('非目标资源发生变化。')
    report=dict(artifact=dict(path=str(target),sha256=engine.digest(staged),bytes=staged.stat().st_size),
        baseline=dict(path=project['source'],sha256=project['source_sha256'],status='user_confirmed_working' if baseline else 'unconfirmed',agent_observed=False),
        environment=dict(root=str(engine.resolve_client_root(client)),version=wotdata.game_version(client)),
        selection=selection,texture=texture,position=[center_x,center_y],scale=scale,changed_blocks=changed_blocks,
        file_validation=dict(status='passed',zip_crc=True,dds_structure='passed'),whole_vehicle_loading=dict(status='not_tested'),
        limitations=['选区之外共享 UV、压缩块与 mip 边缘可能受到影响；未覆盖所有 LOD 和其他外观。','整车加载和实际贴图效果未游戏实测。'])
    write_json(out/'验证记录.json',report);rgb.save(out/'贴图预览.png');staged.rename(target)
    return target,report
