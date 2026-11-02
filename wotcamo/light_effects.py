"""Select existing glow surfaces from a WOT skin and build isolated native lights.

The extracted project is one .wotlights archive. Unsupported deforming meshes are
reported, never flattened. Inputs are preserved and outputs always start not_tested.
"""
import copy
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import struct
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from .common import ROOT, title_name, write_json
from . import light_assets as mesh, light_recipe, light_select, dds

DEFAULT_RECIPE = {'颜色': [{'名称': '蓝', 'RGB': [.03, .22, 1]}, {'名称': '粉', 'RGB': [1, .1, .46]},
                       {'名称': '黄', 'RGB': [1, .75, .04]}], '每色秒数': 2, '呼吸周期秒数': 2,
                  '峰值倍率': 2, '暗相系数': .08, '流水方向': '向车头', '每米延迟秒数': .65,
                  # Write the mode explicitly. A recipe without 效果模式 silently
                  # falls back to 流水呼吸, which is exactly the "everything breathes
                  # whatever I set" report from v2.1.0.
                  '效果模式': '流水呼吸', '亮灯比例': .3}
GLOW_EFFECTS = frozenset(('shaders/std_effects/glow.fx', 'shaders/std_effects/glow_skinned.fx'))


def native_pulse_values(config):
    """Native Pulse values written into the material for this recipe.

    Measured against the client's emissive_playground Pulse branches: the ramp
    period is 4 / speed seconds, so speed == 0 freezes it and the material stays
    flat in that probe. Non-breathing modes also write both dark-floor fields
    as 1.0. These are export parameters, not proof of visible engine output on
    an arbitrary client or of successful material sequence binding.
    """
    if config['mode'] == '流水呼吸' and light_recipe.has_dimming(config):
        return 4 / config['breath'], config['low']
    return 0., 1.


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def xml(data):
    if data[:4] == struct.pack('<I', 0x62a14e45):
        path = ROOT / 'tools/wot_toolkit/common/XmlUnpacker.py'
        spec = importlib.util.spec_from_file_location('light_xml_unpacker', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.XmlUnpacker().read(io.BytesIO(data))
    return ET.fromstring(data)


def check_archive(z):
    names = z.namelist()
    if len(names) != len(set(n.casefold() for n in names)):
        raise ValueError('包内有大小写重复资源，请先处理重复条目')
    for name in names:
        normalized = name.replace('\\', '/')
        if normalized.startswith('/') or '..' in normalized.split('/') or ':' in normalized:
            raise ValueError('包中存在不安全资源路径')
    if z.testzip() is not None:
        raise ValueError('压缩包 CRC 校验失败')


def check_game_zip(path):
    """Validate local headers too: a normal central directory can hide ZIP64 locals."""
    checked = 0
    with zipfile.ZipFile(path) as z, Path(path).open('rb') as stream:
        for entry in z.infolist():
            stream.seek(entry.header_offset)
            header = struct.unpack('<I5H3I2H', stream.read(30))
            if header[0] != 0x04034b50:
                raise ValueError('安装包本地文件头损坏：' + entry.filename)
            stream.read(header[-2]); extra = stream.read(header[-1])
            at = 0; tags = set()
            while at + 4 <= len(extra):
                tag, size = struct.unpack_from('<HH', extra, at)
                tags.add(tag); at += 4 + size
            if header[1] >= 45 or header[7] == 0xffffffff or header[8] == 0xffffffff or 1 in tags:
                raise ValueError('安装包包含 ZIP64 本地文件头，请使用普通 ZIP 重新打包：' + entry.filename)
            if header[3] != zipfile.ZIP_STORED or entry.compress_type != zipfile.ZIP_STORED:
                raise ValueError('安装包必须使用无压缩储存格式：' + entry.filename)
            if (header[7], header[8]) != (entry.compress_size, entry.file_size):
                raise ValueError('安装包本地文件头与目录的大小不一致：' + entry.filename)
            checked += 1
    return dict(format='ZIP32_STORED', local_headers_checked=checked, zip64=False)


def write_game_archive(source, target, changes=None, added=None, excluded=None, added_files=None):
    changes = changes or {}; added = added or {}
    excluded = set(excluded or ())
    added_files = added_files or {}
    # Do not reuse ZipInfo.extra/extract_version from ZIP64 input packages.
    # Set known sizes before streaming, so Python never needs forced ZIP64.
    with zipfile.ZipFile(source) as original:
        original_entries = [x for x in original.infolist() if x.filename not in excluded]
        final_names = [x.filename.casefold() for x in original_entries] + [n.casefold() for n in added] + [n.casefold() for n in added_files]
        if len(final_names) != len(set(final_names)):
            raise ValueError('输出资源存在重复路径，已停止打包')
        estimate = sum(len(changes[x.filename]) if x.filename in changes else x.file_size for x in original_entries)
        estimate += sum(map(len, added.values()))
        estimate += sum(Path(p).stat().st_size for p in added_files.values())
        estimate += sum(98 + 2 * len(x.filename.encode('utf-8')) for x in original_entries)
        estimate += sum(98 + 2 * len(x.encode('utf-8')) for x in added)
        estimate += sum(98 + 2 * len(x.encode('utf-8')) for x in added_files)
        if estimate >= zipfile.ZIP64_LIMIT or len(final_names) >= 65535:
            raise ValueError('资源超过普通 ZIP 打包容量；可取消“嵌入可恢复工程”后重试，或精简资源。不会自动生成 ZIP64 安装包。')
        with zipfile.ZipFile(target, 'x', zipfile.ZIP_STORED, allowZip64=False) as dest:
            for entry in original.infolist():
                if entry.filename in excluded:
                    continue
                info = zipfile.ZipInfo(entry.filename, entry.date_time)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = entry.create_system; info.external_attr = entry.external_attr
                info.file_size = entry.file_size
                if entry.filename in changes:
                    dest.writestr(info, changes[entry.filename])
                else:
                    with original.open(entry) as a, dest.open(info, 'w') as b:
                        shutil.copyfileobj(a, b)
            for name, data in added.items():
                dest.writestr(name, data)
            for name, path in added_files.items():
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_STORED
                info.file_size = Path(path).stat().st_size
                with Path(path).open('rb') as a, dest.open(info, 'w') as b:
                    shutil.copyfileobj(a, b)
    return check_game_zip(target)


def input_package(source, work):
    source = Path(source).resolve()
    if source.suffix.lower() == '.wotmod':
        return source
    with zipfile.ZipFile(source) as z:
        matches = [x for x in z.infolist() if x.filename.lower().endswith('.wotmod') and not x.is_dir()]
        if len(matches) != 1:
            raise ValueError('ZIP 中需恰好包含一个 .wotmod；多个包时请先选出要处理的包')
        work.mkdir(parents=True, exist_ok=True)
        dest = work / '输入涂装.wotmod'
        with z.open(matches[0]) as a, dest.open('xb') as b:
            shutil.copyfileobj(a, b)
    return dest


def read_indices(sections, geo, pg):
    data = sections[geo.findtext('primitive').strip()]
    count, groups = struct.unpack_from('<II', data, 64)
    size = 4 if data[:64].rstrip(b'\0') == b'list32' else 2
    group = int(pg.text.strip())
    if not 0 <= group < groups:
        raise ValueError('primitiveGroup 超出索引分组范围')
    start, triangles, first, vertices = struct.unpack_from('<4I', data, 72 + count * size + group * 16)
    if start + triangles * 3 > count:
        raise ValueError('索引范围超过缓冲区')
    ids = np.array(struct.unpack_from('<' + ('I' if size == 4 else 'H') * (triangles * 3), data, 72 + start * size))
    return ids.reshape(-1, 3), (first, vertices)


def components(vertices, indices):
    # Weld positions only for connectivity; original UV seams remain in export.
    used = np.unique(indices)
    _, welded = np.unique(np.round(vertices[used, :3], 5), axis=0, return_inverse=True)
    lookup = dict(zip(used, welded))
    parent = list(range(int(welded.max()) + 1))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for tri in indices:
        a = find(lookup[tri[0]])
        for i in tri[1:]:
            parent[find(lookup[i])] = a
    groups = {}
    for i, tri in enumerate(indices):
        groups.setdefault(find(lookup[tri[0]]), []).append(i)
    return list(groups.values())


def attachment(vertices, skin, indices, nodes, matrices, parents, part):
    if not nodes or any(n not in matrices for n in nodes):
        raise ValueError('找不到模型挂点或变换')
    if skin:
        bones = set()
        for vi in np.unique(indices):
            a, b, c, wa, wb = skin[int(vi)]
            if wa + wb > 255:
                raise ValueError('蒙皮权重无效')
            for bone, weight in zip((a, b, c), (wa, wb, 255 - wa - wb)):
                if weight:
                    if bone % 3:
                        raise ValueError('不支持的骨骼索引格式')
                    bones.add(bone // 3)
        if len(bones) != 1:
            raise ValueError('多骨骼变形灯面，需专门适配，不能自动静态化')
        bone = nodes[next(iter(bones))]
        anchor = parents[bone]
        if not anchor or anchor not in matrices:
            raise ValueError('无法确认蒙皮的运动父节点')
        if part == 'gun':
            ancestor = anchor; seen = set()
            while ancestor is not None and ancestor not in seen and ancestor != 'Gun':
                seen.add(ancestor); ancestor = parents.get(ancestor)
            if ancestor != 'Gun':
                raise ValueError('炮管骨骼不在 Gun 倾角分支下，需核对客户端动画')
        transform = matrices[bone] @ np.linalg.inv(matrices[anchor])
        kind = 'node'
    else:
        if len(nodes) != 1:
            raise ValueError('非蒙皮网格包含多个节点')
        if part not in ('hull', 'turret', 'gun', 'chassis'):
            raise ValueError('无法识别车辆部件别名')
        if part == 'gun':
            if 'Gun' not in matrices:
                raise ValueError('缺少 Gun 倾角节点')
            anchor, kind = 'Gun', 'node'
            transform = matrices[nodes[0]] @ np.linalg.inv(matrices['Gun'])
        else:
            anchor, kind, transform = part, 'part', matrices[nodes[0]]
    return anchor, kind, transform


def scan(source, work=None, log=lambda x: None, _remaining_only=False, _embedded_depth=0, allow_body=False):
    (ROOT / '.cache').mkdir(exist_ok=True)
    work = Path(work or tempfile.mkdtemp(prefix='lights_', dir=ROOT / '.cache'))
    package = input_package(source, work)
    log('检查输入包，并识别发光材质和连通灯面……')
    catalog = []; issues = []; glow_groups=0; body_vehicles=set(); vehicle_paths=set()
    with zipfile.ZipFile(package) as z:
        check_archive(z)
        lookup = {n.lower(): n for n in z.namelist()}
        for name in z.namelist():
            m=re.match(r'res/vehicles/([^/]+)/([^/]+)/.+',name,re.I)
            if m and not name.endswith('/'):vehicle_paths.add((m[1],m[2]))
        from . import light_recovery
        if not _remaining_only and light_recovery.manifests(z.namelist()):
            try:
                manifest_names = light_recovery.manifests(z.namelist())
                if len(manifest_names) == 1:
                    from . import light_embedded
                    data = light_recovery.read_manifest(z, manifest_names[0])
                    restored = light_embedded.restore(z, manifest_names[0], data, work, log, _embedded_depth)
                    if restored is not None:
                        return restored
                return light_recovery.recover(package, work, log)
            except (KeyError, TypeError, IndexError, StopIteration, ValueError, zipfile.BadZipFile) as error:
                raise ValueError('成品包恢复未完成：%s\n原成品包未修改；可改用原 .wotlights 工程。' % error) from error
        for path in z.namelist():
            match = re.match(r'res/vehicles/([^/]+)/([^/]+)/(.+)\.visual_processed$', path, re.I)
            if not match:
                continue
            part = Path(path).stem.lower().split('_')[0]
            if part in ('hull','turret','gun','chassis') and '/normal/lod0/' in path.lower():
                body_vehicles.add(match[2])
            try:
                visual = xml(z.read(path)); matrices, parents = mesh.node_matrices(visual)
                prim_path = lookup[path.replace('.visual_processed', '.primitives_processed').lower()]
                sections = mesh.sections(z.read(prim_path))
            except Exception as error:
                issues.append({'resource': path, 'issue': str(error)}); continue
            for ri, rs in enumerate(visual.findall('renderSet')):
                for gi, geo in enumerate(rs.findall('geometry')):
                    for pi, pg in enumerate(geo.findall('primitiveGroup')):
                        mat = pg.find('material')
                        if mat is None or (mat.findtext('fx') or '').strip().lower() not in GLOW_EFFECTS:
                            continue
                        glow_groups+=1
                        key = '%s|%d|%d|%d' % (path, ri, gi, pi)
                        base = dict(vehicle=match[2], nation=match[1], part=part, visual=path, primitives=prim_path,
                                    render_set=ri, geometry=gi, group=pi, material=mat.findtext('identifier', '').strip())
                        try:
                            vertices, skin = mesh.vertex_data(sections[geo.findtext('vertices').strip()])
                            ids, (first, count) = read_indices(sections, geo, pg)
                            if not len(ids) or ids.min() < 0 or ids.max() >= len(vertices):
                                raise ValueError('灯面索引无效')
                            if ids.min() < first or ids.max() >= first + count:
                                raise ValueError('灯面分组顶点范围异常')
                            texture = next(p.findtext('Texture').strip() for p in mat.findall('property') if p.text.strip() == 'diffuseMap')
                            texture_path = lookup[('res/' + texture).lower()]
                            dds.inspect(z.read(texture_path))
                            nodes = [n.text.strip() for n in rs.findall('node')]
                            for ci, subset in enumerate(components(vertices, ids)):
                                selected = ids[subset]
                                vi, inverse = np.unique(selected, return_inverse=True)
                                rec = dict(base, id=hashlib.sha1(key.encode()).hexdigest()[:12] + '_%03d' % ci,
                                           component=ci, source_triangle_ids=subset, texture=texture_path,
                                           triangles=len(subset), supported=True, reason='', selected=False)
                                try:
                                    if len(geo.findall('primitiveGroup')) != 1:
                                        raise ValueError('灯面共用多材质索引缓冲，需专门拆分')
                                    if z.read(texture_path)[84:88] != b'DXT5':
                                        raise ValueError('自动变色目前仅支持 DXT5/BC3 灯光贴图')
                                    if '/normal/lod0/' not in path.lower():
                                        raise ValueError('自动构建仅支持 normal/lod0；其他 LOD 或外观变体需专门适配')
                                    anchor, kind, transform = attachment(vertices, skin, selected, nodes, matrices, parents, part)
                                    rec.update(anchor=anchor, anchor_kind=kind, transform=transform.tolist())
                                    points = vertices[vi].copy()
                                    points[:, :3] = (np.c_[points[:, :3], np.ones(len(points))] @ transform)[:, :3]
                                    points[:, 3:6] = points[:, 3:6] @ np.linalg.inv(transform[:3, :3]).T
                                    points[:, 3:6] /= np.maximum(np.linalg.norm(points[:, 3:6], axis=1)[:, None], 1e-12)
                                    rec['_vertices'] = points
                                    rec['_indices'] = inverse.reshape(-1, 3)
                                    rec['_anchor_matrix'] = matrices[anchor] if kind=='node' else np.eye(4)
                                except (ValueError, IndexError, np.linalg.LinAlgError) as error:
                                    rec.update(supported=False, reason=str(error), anchor='—')
                                if rec['supported']:
                                    preview = rec['_vertices'][:,:3]
                                    rec['_preview'] = (np.c_[preview,np.ones(len(preview))] @ rec['_anchor_matrix'])[:,:3]
                                else:
                                    preview = vertices[vi,:3]
                                    rec['_preview'] = (np.c_[preview,np.ones(len(preview))] @ matrices[nodes[0]])[:,:3]
                                rec['bounds'] = [rec['_preview'].min(0).tolist(), rec['_preview'].max(0).tolist()]
                                catalog.append(rec)
                        except Exception as error:
                            issues.append(dict(base, issue=str(error)))
    if not catalog and allow_body and len(vehicle_paths)==1:
        nation,vehicle=next(iter(vehicle_paths))
        return dict(schema=1, source=str(package), source_sha256=digest(package), lights=[], vehicle=vehicle, nation=nation, scan_issues=issues, recipe=copy.deepcopy(DEFAULT_RECIPE), baseline_user_confirmed=False)
    if not catalog and not _remaining_only:
        if glow_groups:
            details=['%s（%s）：%s'%(Path(x.get('visual',x.get('resource','未知资源'))).name,x.get('material','发光材质'),x['issue']) for x in issues[:3]]
            raise ValueError('已找到 %d 组发光材质，但灯面读取失败。\n%s%s\n原始涂装未改动。'%(glow_groups,'\n'.join(details),'\n其余 %d 项问题已省略。'%(len(issues)-3) if len(issues)>3 else ''))
        raise ValueError('没有找到可提取的 glow 灯面。普通 PBS 车漆不自动当作灯光；详情：' + str(issues[:3]))
    result = dict(schema=1, source=str(package), source_sha256=digest(package), lights=catalog,
                  scan_issues=issues, recipe=copy.deepcopy(DEFAULT_RECIPE), baseline_user_confirmed=False)
    if len(vehicle_paths)==1:
        result['nation'],result['vehicle']=next(iter(vehicle_paths))
    log('识别 %d 块灯面，其中 %d 块可自动制作。' % (len(catalog), sum(c['supported'] for c in catalog)))
    return result


def public_project(project):
    return {**{k: v for k, v in project.items() if k != 'lights' and not k.startswith('_')},
            'lights': [{k: v for k, v in x.items() if not k.startswith('_')} for x in project['lights']]}


def override_recipe(light):
    """A face override, or None when it follows the vehicle recipe."""
    value = light.get('配方')
    return value if isinstance(value, dict) else None


def model_recipe(lights):
    """Return the one recipe shared by a light model, or None for the global one.

    A model becomes a single .model/.seq pair, so mixing recipes inside one model
    cannot be honoured; refuse it instead of silently picking a winner.
    """
    values = [override_recipe(light) for light in lights]
    first = json.dumps(values[0], sort_keys=True, ensure_ascii=False)
    for other in values[1:]:
        if json.dumps(other, sort_keys=True, ensure_ascii=False) != first:
            raise ValueError('同一独立灯模型内的灯面配方不一致，请先按模型整体套选再一起设置')
    return values[0]


def model_recipes(selected):
    """Validate callers that explicitly require a single recipe per attachment."""
    groups = {}
    for light in selected:
        groups.setdefault(light_select.model_key(light), []).append(light)
    return {key: model_recipe(lights) for key, lights in groups.items()}


def render_groups(lights):
    """Split an attachment by effective override; IDs keep cache keys stable."""
    groups = {}
    for light in lights:
        signature = json.dumps(override_recipe(light), sort_keys=True, ensure_ascii=False)
        groups.setdefault((light_select.model_key(light), signature), []).append(light)
    return [((base, tuple(x['id'] for x in faces)), faces) for (base, _), faces in groups.items()]


def variant_geometry_key(light):
    """Fingerprint a face in its attachment frame across normal/skin variants."""
    geometry=np.asarray(light['_vertices'][light['_indices']],dtype='<f4').tobytes()
    base=re.sub(r'/_skins/[^/]+/', '/', light['visual'], flags=re.I).casefold()
    return (base,light['anchor'],light['anchor_kind'],light['texture'].casefold(),hashlib.sha256(geometry).hexdigest())


def variant_aliases(lights):
    """Map exactly overlapping variant faces so their settings stay consistent."""
    groups={}
    for light in lights:
        if light.get('supported'):
            groups.setdefault(variant_geometry_key(light),[]).append(light)
    aliases={}
    for members in groups.values():
        if len({x['visual'].casefold() for x in members})>1:
            for light in members:
                aliases[light['id']]={x['id'] for x in members if x['id']!=light['id']}
    return aliases


def deduplicate_variant_lights(lights, global_recipe):
    """Collapse exact surface aliases across normal and _skins variants only.

    Both visuals are still stripped of their selected original faces. A single
    independent copy follows their shared anchor instead of mixing two phases.
    Different frames, textures, triangles or effective recipes remain separate.
    """
    unique, aliases, seen, geometry_recipes = [], [], {}, {}
    for light in lights:
        cfg=light_recipe.validate_config(override_recipe(light) or global_recipe)
        effective={k:v for k,v in cfg.items() if k!='raw'}
        geometry_key=variant_geometry_key(light)
        signature=json.dumps(effective,sort_keys=True)
        earlier=geometry_recipes.get(geometry_key)
        if earlier and earlier[0].casefold()!=light['visual'].casefold() and earlier[1]!=signature:
            raise ValueError('重复外观中的同一灯面设置了不同配方，请将对应灯面设为相同效果，避免重叠。')
        geometry_recipes.setdefault(geometry_key,(light['visual'],signature))
        key=geometry_key+(signature,)
        first=seen.get(key)
        if first is not None and first['visual'].casefold()!=light['visual'].casefold():
            aliases.append(dict(id=light['id'],representative=first['id'],source=light['visual'],
                                representative_source=first['visual'],anchor=light['anchor']))
        else:
            unique.append(light);seen.setdefault(key,light)
    return unique,aliases


def remove_selected_faces(visual, sections, selections):
    """Stop drawing selected old lamps, without a black-texture placeholder.

    Resolve all positions before removal so renderSet indexes cannot shift.
    The original skeleton and unrelated geometry/materials are left intact.
    """
    targets={}
    for ri,gi,pi in selections:
        rs=visual.findall('renderSet')[ri];geo=rs.findall('geometry')[gi]
        targets[(ri,gi,pi)]=(rs,geo,geo.findall('primitiveGroup')[pi])
    changed=False;coverage=[]
    for (ri,gi,pi),selected in selections.items():
        rs,geo,pg=targets[(ri,gi,pi)]
        if len(geo.findall('primitiveGroup'))!=1:
            raise ValueError('所选灯面与其他材质共用索引缓冲，请先拆分该 geometry')
        ids,_=read_indices(sections,geo,pg)
        if not selected or min(selected)<0 or max(selected)>=len(ids):
            raise ValueError('所选灯面三角形范围无效')
        keep=[i for i in range(len(ids)) if i not in selected]
        if keep:
            verts,_=mesh.vertex_data(sections[geo.findtext('vertices').strip()])
            if len(verts)>=65536:raise ValueError('原灯面顶点超过 16 位索引范围，需专门适配')
            name='light_maker_%d_%d.indices'%(ri,gi)
            sections[name]=mesh.make_ib(ids[keep],len(verts))
            geo.find('primitive').text=name;pg.text='0';changed=True
        else:
            rs.remove(geo)
            if not rs.findall('geometry'):visual.remove(rs)
        coverage.append(dict(render_set=ri,geometry=gi,selected_triangles=len(selected),
                             retained_triangles=len(keep),suppression='index_filter' if keep else 'geometry_removed'))
    return changed,coverage


def geometry_digest(light):
    h = hashlib.sha256()
    for name, dtype in (('_vertices', '<f8'), ('_indices', '<i8')):
        array = np.ascontiguousarray(light[name], dtype=dtype)
        h.update(json.dumps(array.shape).encode()); h.update(array.tobytes())
    return h.hexdigest()


def save_project(project, destination, compress_source=False, autosave_ui=None):
    destination = Path(destination)
    if any(x.get('overlay_body') for x in project['lights']):
        raise ValueError('框选灯面尚不支持工程恢复，不能保存为可恢复工程。')
    if destination.exists():
        raise ValueError('工程文件已存在，请使用新名称以保留旧版本')
    if digest(project['source']) != project['source_sha256']:
        raise ValueError('输入包已变化，请重新扫描')
    for light in project['lights']:
        recipe = override_recipe(light)
        if recipe is not None:
            light_recipe.validate_config(recipe)
    arrays = {}
    for light in project['lights']:
        if light['supported']:
            arrays[light['id'] + '_vertices'] = light['_vertices']
            arrays[light['id'] + '_indices'] = light['_indices']
    data = io.BytesIO(); np.savez_compressed(data, **arrays)
    saved = public_project(project)
    saved['geometry_sha256'] = {x['id']: geometry_digest(x) for x in project['lights'] if x['supported']}
    # A completed extension is published only after the new archive passes CRC
    # and source-hash checks; a failed save removes its own temporary file.
    fd,temporary=tempfile.mkstemp(prefix=destination.name+'.',suffix='.building',dir=destination.parent)
    os.close(fd);temporary=Path(temporary)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
            z.write(project['source'], 'source.wotmod', compress_type=zipfile.ZIP_DEFLATED if compress_source else zipfile.ZIP_STORED, compresslevel=3 if compress_source else None)
            z.writestr('project.json', json.dumps(saved, ensure_ascii=False, indent=2))
            z.writestr('extracted_lights.npz', data.getvalue())
            if autosave_ui is not None:
                z.writestr('autosave_ui.json', json.dumps(autosave_ui, ensure_ascii=False))
        with zipfile.ZipFile(temporary) as z:
            if z.testzip() is not None:raise ValueError('工程文件校验失败')
        if digest(project['source']) != project['source_sha256']:
            raise ValueError('输入包在保存期间发生变化，请重新扫描')
        if os.name=='nt':
            os.rename(temporary,destination)  # Windows rename refuses an existing destination.
        else:
            os.link(temporary,destination)  # Atomic no-overwrite on supported POSIX filesystems.
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def load_project(path, work, log=lambda x: None, require_complete=False, _embedded_depth=0):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        required = {'source.wotmod', 'project.json', 'extracted_lights.npz'}
        if len(names) != len(set(names)) or set(names) not in (required, required | {'autosave_ui.json'}):
            raise ValueError('不是此制作器保存的灯光工程')
        autosave_ui = json.loads(z.read('autosave_ui.json')) if 'autosave_ui.json' in names else None
        if autosave_ui is not None and not isinstance(autosave_ui, dict):
            raise ValueError('自动保存的表单数据无效')
        saved = json.loads(z.read('project.json'))
        if saved.get('schema') != 1:
            raise ValueError('不支持的灯光工程版本')
        light_recipe.validate_config(saved['recipe'])
        source = work / '输入涂装.wotmod'
        with z.open('source.wotmod') as a, source.open('xb') as b:
            shutil.copyfileobj(a, b)
    if digest(source) != saved['source_sha256']:
        raise ValueError('工程输入包哈希不匹配')
    # Re-derive all geometry from the authenticated source instead of trusting saved paths/transforms.
    project = scan(source, work, log, _embedded_depth=_embedded_depth, allow_body=autosave_ui is not None)
    if require_complete or autosave_ui is not None:
        if project['source_sha256'] != saved['source_sha256']:
            raise ValueError('内嵌工程输入发生额外嵌套还原，无法保证原始输入一致')
        saved_ids = [x['id'] for x in saved['lights']]
        current_ids = {x['id'] for x in project['lights']}
        if len(saved_ids) != len(set(saved_ids)) or set(saved_ids) != current_ids:
            raise ValueError('内嵌工程灯面分组与当前读取结果不一致，无法保证完整恢复')
        expected = saved.get('geometry_sha256', {})
        actual = {x['id']: geometry_digest(x) for x in project['lights'] if x['supported']}
        if expected != actual:
            raise ValueError('内嵌工程灯面几何校验不一致，无法保证完整恢复')
    selected = {x['id'] for x in saved['lights'] if x.get('selected')}
    saved_recipes = {x['id']: x['配方'] for x in saved['lights'] if isinstance(x.get('配方'), dict)}
    for light in project['lights']:
        light['selected'] = light['supported'] and light['id'] in selected
        if light['id'] in saved_recipes:
            light_recipe.validate_config(saved_recipes[light['id']])
            light['配方'] = copy.deepcopy(saved_recipes[light['id']])
    project['recipe'] = saved['recipe']
    project['baseline_user_confirmed'] = bool(saved.get('baseline_user_confirmed', False))
    project['embed_recoverable'] = bool(saved.get('embed_recoverable', True))
    if isinstance(saved.get('embedded_restore'), dict):
        project['embedded_restore'] = copy.deepcopy(saved['embedded_restore'])
    if autosave_ui is not None:
        project['_autosave_ui'] = autosave_ui
    return project


def resolve_client_root(selected):
    value = str(selected).strip().strip('"')
    if not value:
        raise ValueError('请先选择游戏客户端目录（包含 version.xml 和 paths.xml 的文件夹）。')
    path = Path(value).expanduser().resolve()
    if path.is_file():
        path = path.parent
    # Accept a game subdirectory, including mods/res_mods and its version folder.
    for candidate in (path, *path.parents):
        if (candidate / 'version.xml').is_file() and (candidate / 'paths.xml').is_file():
            return candidate
    raise ValueError('没有找到游戏客户端根目录。请选择同时包含 version.xml 和 paths.xml 的游戏文件夹，例如 World_of_Tanks_ASIA；也可以选择其 mods 或 res_mods 子目录，由制作器自动识别上级目录。')


def client_info(root):
    root = resolve_client_root(root)
    version = ET.parse(root / 'version.xml').getroot()
    paths = ET.parse(root / 'paths.xml').getroot()
    shader_package = root / 'res/packages/shaders.pkg'
    if not shader_package.is_file():
        raise ValueError('已识别客户端目录，但缺少 res/packages/shaders.pkg，请检查游戏资源是否完整：' + str(root))
    with zipfile.ZipFile(shader_package) as z:
        for branch in ('10', '11'):
            with zipfile.ZipFile(io.BytesIO(z.read('shaders/custom/emissive_playground.' + branch + '.dx11.fxo'))) as f:
                effect = f.read('effect'); metadata = effect[:effect.index(b'ARISDX11')]
                if b"('Pulse', 2)" not in metadata:
                    raise ValueError('客户端原生 Pulse 枚举不匹配，不能套用本模板')
    dll = root / 'win64/python27.dll'
    if not dll.exists():
        raise ValueError('此制作器目前需要客户端 win64/python27.dll 编译脚本')
    return dict(root=str(root), version=version.findtext('version', '').strip(), realm=version.findtext('meta/realm', '').strip(),
                paths_xml_sha256=digest(root / 'paths.xml'), resource_paths=[n.text.strip() for n in paths.findall('.//Path')])


def compile27(source, target, client):
    """Compile in an isolated helper: two Python runtimes must not share this process."""
    import subprocess, sys
    source, target = Path(source).resolve(), Path(target).resolve()
    dll = Path(client).resolve() / 'win64/python27.dll'
    if not dll.is_file():
        raise ValueError('客户端缺少 win64/python27.dll，无法编译游戏脚本。')
    raw = source.read_bytes()
    try: raw.decode('ascii')
    except UnicodeDecodeError as error:
        raise ValueError('游戏脚本包含非 ASCII 字符，无法使用当前精简 Python 2 编译器。') from error
    helper = r"""
import ctypes, sys
library = ctypes.PyDLL(sys.argv[1])
ctypes.c_int.in_dll(library, 'Py_NoSiteFlag').value = 1
library.Py_Initialize()
library.PyRun_SimpleString.argtypes = [ctypes.c_char_p]
source, target = sys.argv[2:]
script = ("import marshal\nsrc=open(u%s,'rb').read()\n" % ascii(source) +
          "src=src.split('\\n',1)[1] if src.startswith('# -*- coding: utf-8 -*-') else src\n" +
          "code=compile(src,'light_runtime.py','exec')\n" +
          "open(u%s,'wb').write('\\x03\\xf3\\x0d\\x0a\\x00\\x00\\x00\\x00'+marshal.dumps(code))\n" % ascii(target))
if library.PyRun_SimpleString(script.encode('ascii')):
    sys.stderr.write('Python 2 编译失败；请检查上方错误或客户端 Python 2 运行库。\n')
    sys.exit(1)
"""
    try:
        result = subprocess.run([sys.executable, '-c', helper, str(dll), str(source), str(target)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                                encoding='utf-8', errors='replace',
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('无法启动游戏脚本编译助手：' + str(error)) from error
    if result.returncode or not target.is_file():
        detail = result.stdout.strip()[-2000:] or ('退出码 %s' % result.returncode)
        raise ValueError('游戏脚本编译失败，请检查客户端 Python 2 运行库：' + detail)
    if target.read_bytes()[:4] != b'\x03\xf3\x0d\x0a':
        raise ValueError('生成的脚本不是 Python 2.7 格式')


def neutral_texture(raw):
    # Keep BC3 alpha blocks, mip chain and interpolation indices exactly intact.
    if raw[84:88] == b'DXT5':
        out = bytearray(raw)
        a = np.frombuffer(raw, dtype=np.uint8, offset=128).reshape(-1, 16)
        b = np.frombuffer(out, dtype=np.uint8, offset=128).reshape(-1, 16)
        for start in (8, 10):
            packed = a[:, start].astype(np.uint16) | (a[:, start + 1].astype(np.uint16) << 8)
            maximum = np.maximum.reduce(((packed >> 11) / 31, ((packed >> 5) & 63) / 63, (packed & 31) / 31))
            five = np.rint(maximum * 31).astype(np.uint16); six = np.rint(maximum * 63).astype(np.uint16)
            value = (five << 11) | (six << 5) | five
            b[:, start] = value & 255; b[:, start + 1] = value >> 8
        return bytes(out)
    raise ValueError('自动变色目前仅支持 DXT5/BC3 灯光贴图；其他格式需适配以保留透明度')


def build(project, client, output_dir, title='自定义灯效', log=lambda x: None, embed_recoverable=None):
    if embed_recoverable is None:
        embed_recoverable = bool(project.get('embed_recoverable', True))
    if any(x.get('overlay_body') for x in project.get('lights', [])) and embed_recoverable:
        raise ValueError('框选车体灯面暂不支持嵌入可恢复工程，请关闭该选项。')
    selected = [x for x in project['lights'] if x.get('selected')]
    if not selected or any(not x['supported'] for x in selected):
        raise ValueError('请选择至少一块可自动制作的灯面')
    vehicles = {x['vehicle'] for x in selected}
    if len(vehicles) != 1:
        raise ValueError('一次只能制作一辆车的灯效')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]+', next(iter(vehicles))):
        raise ValueError('车型标识包含非标准字符')
    if digest(project['source']) != project['source_sha256']:
        raise ValueError('原包已改变，请重新提取')
    from . import light_recovery
    retained, excluded = light_recovery.retained(project, selected)
    environment = client_info(client)
    client = environment['root']
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out = Path(output_dir) / (title_name(title) + '_' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / '光效配方.json', project['recipe'])
    default_config = light_recipe.read_config(out / '光效配方.json')
    token = hashlib.sha256((project['source_sha256'] + json.dumps(sorted(x['id'] for x in selected))).encode()).hexdigest()[:12]
    prefix = 'particles/light_maker_' + token + '/'
    changes = {}; added = {'res/' + prefix + 'phase_white.dds': mesh.dds(True)}
    rigs = []; bands_report = []; areas = []; coverage = []; per_model_recipes = {}; model_faces = {}
    breathing = []
    group_selections = {}
    for light in selected:
        if light.get('recovered_model') or light.get('overlay_body'):
            continue
        key = (light['visual'], light['render_set'], light['geometry'], light['group'])
        group_selections.setdefault(key, set()).update(light['source_triangle_ids'])
    emitted,aliases=deduplicate_variant_lights(selected,project['recipe'])
    if aliases:log('合并 %d 块外观重复灯面，避免相同位置叠加两套不同相位。'%len(aliases))
    models = render_groups(emitted)
    log('导出独立灯面，保留未选灯面和原车材质……')
    with zipfile.ZipFile(project['source']) as original:
        lookup = {n.lower(): n for n in original.namelist()}
        for visual_path in sorted({x['visual'] for x in selected if not x.get('recovered_model') and not x.get('overlay_body')}):
            visual = xml(original.read(visual_path))
            prim_path = lookup[visual_path.replace('.visual_processed', '.primitives_processed').lower()]
            sections = mesh.sections(original.read(prim_path))
            selections={(ri,gi,pi):triangles for (path,ri,gi,pi),triangles in group_selections.items() if path==visual_path}
            changed_indices,removed=remove_selected_faces(visual,sections,selections)
            coverage.extend(dict(source=visual_path,**row) for row in removed)
            changes[visual_path] = mesh.xml(visual)
            if changed_indices:changes[prim_path] = mesh.packed_sections(sections)
        for mi, (((source_path, anchor, kind, texture), _), lights) in enumerate(models):
            name = 'light_%03d' % mi; base = prefix + name
            model_faces[name]=[x['id'] for x in lights]
            recipe = model_recipe(lights)
            # render_groups has already split differing per-face recipes; each
            # exported model still receives exactly one sequence and recipe.
            config = light_recipe.validate_config(recipe) if recipe else default_config
            per_model_recipes[name] = recipe
            parts = []; all_indices = []; offset = 0
            for light in lights:
                parts.append(light['_vertices']); all_indices.extend((light['_indices'] + offset).tolist()); offset += len(light['_vertices'])
            vertices = np.concatenate(parts); ids = np.asarray(all_indices, dtype=int)
            wheel = lights[0]['part']=='chassis' and re.fullmatch(r'(?:W|WD)_[LR]\d+',anchor) is not None
            split = mesh.split_for_direction(vertices,ids,config['direction'],lights[0]['_anchor_matrix'],wheel)
            related = [x['_preview'] for x in selected if x['visual']==source_path]
            preview_points = np.concatenate(related)
            radial_center = (preview_points.min(0) + preview_points.max(0)) / 2
            neutral = prefix + 'emission_' + hashlib.sha1(texture.encode()).hexdigest()[:10] + '.dds'
            if 'res/' + neutral not in added:
                added['res/' + neutral] = mesh.dds(True) if all(x.get('overlay_body') for x in lights) else neutral_texture(original.read(texture))
            seq = ET.fromstring(mesh.sequence(base + '.model')); seq.find('duration').text = format(config['period'],'.12g')
            light_object = seq.findall('sequenceObject')[1]
            native_speed, offset_black = native_pulse_values(config)
            brightness_low, brightness_high = light_recipe.brightness_bounds(config)
            effect = None; packed = {}; total_area = 0; all_vertices = []
            for bi, (vs, ix, center) in enumerate(split):
                if len(vs) >= 65536:
                    raise ValueError('单段灯面顶点过多，需细分')
                mat_name = name + '_band_%02d' % bi; section_prefix = 'band%02d_' % bi
                packed.update({section_prefix + k: v for k, v in mesh.sections(mesh.primitives(vs, ix)).items()})
                ev = ET.fromstring(mesh.effect_visual(mat_name, neutral, vs, len(ix)//3, prefix, config['peak']))
                rs = ev.find('renderSet'); geo = rs.find('geometry')
                geo.find('vertices').text = section_prefix + 'vertices'; geo.find('primitive').text = section_prefix + 'indices'
                for prop in rs.iter('property'):
                    if prop.text.strip() == 'speed': prop.find('Float').text = str(native_speed)
                    if prop.text.strip() in ('g_offsetBlack', 'g_offsetBlackFwd'): prop.find('Float').text = str(offset_black)
                if effect is None: effect = ev
                else: effect.insert(1 + len(effect.findall('renderSet')), rs)
                # Selection coordinates are part/bone-local; this produces per-part flow, not a seamless vehicle projection.
                phase_point = mesh.flow_phase_point(vs,center,config['direction'],lights[0]['_anchor_matrix'],wheel)
                phase_z = float(phase_point[2])
                phase = light_recipe.spatial_offset(phase_point,radial_center,config,mat_name)
                light_object.append(light_recipe.colour_track(mat_name, phase, config))
                bands_report.append(dict(model=name,material=mat_name,z=phase_z,point=phase_point.tolist(),radial_center=radial_center.tolist(),offset_seconds=phase,triangles=len(ix)//3,vertices=len(vs)))
                total_area += mesh.area(vs,ix); all_vertices.append(vs)
            source_area = mesh.area(vertices,ids)
            if abs(source_area-total_area) > max(1e-6,source_area*1e-5):
                raise ValueError('分段灯面面积校验失败')
            points = np.concatenate(all_vertices)
            for key,value in zip(('min','max'),mesh.render_bounds(points)): effect.find('boundingBox/'+key).text=' '.join(map(str,value))
            effect.find('geometrySize').text=str(sum(len(v)*24+len(i)*2 for v,i,c in split))
            model=ET.Element('root');ET.SubElement(model,'nodelessVisual').text=base
            added['res/'+base+'.model']=mesh.xml(model);added['res/'+base+'.visual_processed']=mesh.xml(effect)
            added['res/'+base+'.primitives_processed']=mesh.packed_sections(packed);added['res/'+base+'.seq']=mesh.xml(seq)
            rigs.append(dict(id=name,part=lights[0]['part'],anchor=anchor,anchor_kind=kind,sequence=base+'.seq'))
            areas.append(dict(model=name,source_area=source_area,output_area=total_area,source=lights[0].get('source_visual',source_path)))
            breathing.append(dict(model=name, source='独立配方' if recipe else '全局配方', mode=config['mode'],
                                  dimming_enabled=light_recipe.has_dimming(config),
                                  breath_seconds=config['breath'], period_seconds=config['period'],
                                  native_speed=native_speed, offset_black=offset_black,
                                  brightness_min=round(brightness_low,4), brightness_max=round(brightness_high,4),
                                  breathes=(brightness_high-brightness_low)>1e-4))
        runtime=(ROOT/'wotcamo/light_runtime.py.txt').read_text(encoding='utf-8')
        for index, entry in enumerate(retained):
            rig = dict(entry['rig'], id='retained_%03d' % index)
            rigs.append(rig)
            model_faces[rig['id']]=[entry['light_id']]
            areas.append(dict(entry['area'], model=rig['id']))
            bands_report.extend(dict(b, model=rig['id']) for b in entry['bands'])
            per_model_recipes[rig['id']] = entry['recipe']
            # Deselected recovered models keep the finished package's own assets,
            # so their breathing is whatever that package shipped, not this recipe.
            kept = light_recipe.validate_config(entry['recipe'])
            kept_low, kept_high = light_recipe.brightness_bounds(kept)
            breathing.append(dict(model=rig['id'], source='成品保留(未勾选)', mode=kept['mode'],
                                  dimming_enabled=light_recipe.has_dimming(kept),
                                  breath_seconds=kept['breath'], period_seconds=kept['period'],
                                  native_speed=native_pulse_values(kept)[0],
                                  offset_black=native_pulse_values(kept)[1],
                                  brightness_min=round(kept_low,4), brightness_max=round(kept_high,4),
                                  breathes=(kept_high-kept_low)>1e-4))
        runtime=runtime.replace('RIGS = []','RIGS = '+repr(rigs)).replace('__VEHICLE_TYPE__',next(iter(vehicles)))
        engineering=out/'工程记录';engineering.mkdir()
        script=engineering/'运行脚本.py';script.write_text(runtime,encoding='utf-8');compiled=engineering/'运行脚本.pyc';compile27(script,compiled,client)
        runtime_path='res/scripts/client/gui/mods/mod_light_maker_'+token+'.pyc'
        added[runtime_path]=compiled.read_bytes()
        manifest=dict(models=rigs,bands=bands_report,areas=areas,selected_ids=[x['id'] for x in selected],source_sha256=project['source_sha256'],recipe=project['recipe'],scope='selected rigid body overlays; original vehicle geometry retained' if any(x.get('overlay_body') for x in selected) else 'selected rigid existing glow components; independent native models',coverage=coverage)
        manifest['runtime_scripts']=[runtime_path]
        manifest['model_faces']=model_faces
        if aliases:manifest['deduplicated_lights']=aliases
        overrides={name: recipe for name, recipe in per_model_recipes.items() if recipe}
        if overrides:
            manifest['per_model_recipes']=overrides
            write_json(out/'光效配方_分模型.json',overrides)
        added_files = {}
        if embed_recoverable:
            from . import light_embedded
            log('压缩并嵌入可恢复工程，保留原始输入、灯面分组和已应用配方……')
            backup = engineering / light_embedded.FILENAME
            save_project(dict(project, embed_recoverable=True), backup, compress_source=True)
            backup_path = 'res/' + prefix + light_embedded.FILENAME
            manifest['embedded_project'] = dict(schema=1, path=backup_path,
                                                 sha256=digest(backup), bytes=backup.stat().st_size)
            added_files[backup_path] = backup
        added['res/'+prefix+'manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
        target=out/(title_name(title)+'_待实测.wotmod')
        # Publish an installable extension only after the final-byte audit and
        # its validation record both succeed. Keep failed intermediates for diagnosis.
        staged=target.with_suffix(target.suffix+'.building')
        write_game_archive(project['source'], staged, changes, added, excluded, added_files)
    log('核对最终包的网格分组、依赖和修改范围……')
    audit=audit_package(staged,project['source'],set(changes),client,excluded=excluded)
    report=dict(artifact=dict(path=str(target),sha256=digest(staged),bytes=staged.stat().st_size),environment=environment,
                baseline=dict(path=project['source'],sha256=project['source_sha256'],status='user_confirmed_working' if project.get('baseline_user_confirmed') else 'unconfirmed',agent_observed=False),
                recipe=project['recipe'],selected_components=len(selected),independent_models=len(rigs),file_validation=audit,
                recipes=dict(vehicle=project['recipe'],per_model={name: recipe for name, recipe in per_model_recipes.items() if recipe},
                             note='独立配方按灯模型生效：该模型的颜色、时间与亮度与全局配方互不影响。'),
                offline_validation=dict(status='partial',geometry_surface_area='passed',native_mode_enum='passed',native_shader_execution='not_tested',runtime_api_simulation='not_tested'),
                in_game_tested=False,whole_vehicle_loading=dict(status='not_tested'),
                limitations=['Actual client loading, material sequence binding, visible effect, joint motion, scope hide/restore and LOD need game tests.', 'Only existing supported glow.fx lights on normal/lod0; no automatic new lamps or multi-bone deforming export.', 'Spatial colour bands are local to each part; not seamless whole-vehicle flow.'])
    if any(x.get('overlay_body') for x in selected):
        report['limitations'][1]='Selected rigid body triangles only; original vehicle faces retained; unsupported multi-bone deformation is rejected.'
    if project.get('recovery'):
        report['recovery']=dict(input_kind='maker_finished_package', retained_models=len(retained),
                                removed_old_runtime_and_manifest=sorted(excluded),
                                original_source_sha256=project['recovery'].get('original_source_sha256'),
                                note=project['recovery']['note'])
    report['embedded_project'] = dict(enabled=bool(embed_recoverable), **({k:v for k,v in manifest['embedded_project'].items()} if embed_recoverable else {}))
    dimming=[row for row in breathing if row['breathes']]
    report['breathing_audit']=dict(
        models=breathing, dimming_models=[row['model'] for row in dimming],
        native_pulse_models=[row['model'] for row in breathing if row['native_speed']],
        summary='%d/%d 个灯模型的配方启用非恒定明暗倍率；其中 %d 个使用原生 Pulse，%d 个使用颜色序列。'
                % (len(dimming), len(breathing), sum(1 for row in dimming if row['native_speed']), sum(1 for row in dimming if not row['native_speed'])),
        note='brightness_min/max 仅为配方明暗倍率的计算范围，并非最终像素亮度。min=max 仅表示没有倍率起伏；换色、贴图、混合和游戏渲染仍可能改变观感亮度。保留模型按记录的配方估算，未重新执行其材质。')
    if project.get('recovery') and retained:
        report['breathing_audit']['retained_note']='%d 个未勾选的成品恢复模型沿用原包资源，配方改动不会影响它们的亮度。' % len(retained)
    write_json(out/'验证记录.json',report)
    (out/'使用说明.txt').write_text('此包为待实测版本。退出游戏后，仅启用一个同款完整涂装包。请检查整车加载、换色、呼吸、车轮/炮管随动、开镜退镜、切车及远近距离。\n遇到闪退停用本包，恢复已知正常的原版。没有进行自动安装。\n'
        + report['breathing_audit']['summary'] + '\n' + report['breathing_audit']['note'] + '\n'
        + json.dumps(report['file_validation'],ensure_ascii=False,indent=2),encoding='utf-8')
    staged.rename(target)
    return target,report


def visual_group_audit(archive, name, names):
    errors=[]; checked=0
    try:
        tree=xml(archive.read(name))
        ss=mesh.sections(archive.read(names[name.replace('.visual_processed','.primitives_processed').lower()]))
    except Exception as error:
        return 0,[("file",str(error))]
    for gi,geo in enumerate(tree.findall('.//geometry')):
        location='geometry[%s|%s]'%((geo.findtext('vertices') or '').strip(),(geo.findtext('primitive') or '').strip())
        try:
            vb=ss[geo.findtext('vertices').strip()]
            nv=struct.unpack_from('<I',vb,132 if vb.startswith(b'BPVT') else 64)[0]
        except Exception as error:
            errors.append((location,str(error)));continue
        for pi,pg in enumerate(geo.findall('primitiveGroup')):
            try:
                ids,(first,count)=read_indices(ss,geo,pg)
                if first+count>nv or (len(ids) and (ids.min()<first or ids.max()>=first+count)):
                    raise ValueError('顶点分组范围异常')
                checked+=1
            except Exception as error:
                errors.append((location+'/group%d'%pi,str(error)))
    return checked,errors


def audit_package(target, original_path, changed, client, excluded=None):
    issues=[];groups=0;dependencies=set();missing=[]
    archive_format=check_game_zip(target)
    with zipfile.ZipFile(original_path) as original,zipfile.ZipFile(target) as z:
        check_archive(z);names={n.lower():n for n in z.namelist()}
        original_names={n.lower():n for n in original.namelist()}
        for n in original.namelist():
            if n in (excluded or ()):
                continue
            if n not in changed:
                a,b=original.getinfo(n),z.getinfo(n)
                if (a.CRC,a.file_size)!=(b.CRC,b.file_size):raise ValueError('非目标原始资源发生变化')
        for n in z.namelist():
            if z.getinfo(n).compress_type!=0:raise ValueError('输出包含压缩条目')
            if not n.endswith(('.visual_processed','.model','.seq')):continue
            tree=xml(z.read(n))
            if n.endswith('.model'):
                for key in ('nodelessVisual','nodefullVisual'):
                    text=tree.findtext(key)
                    if text:dependencies.update([text.strip()+'.visual_processed',text.strip()+'.primitives_processed'])
            if n.endswith('.seq'):
                dependencies.update((x.text or '').strip() for x in tree.findall('.//resource') if x.text)
            if not n.endswith('.visual_processed'):continue
            dependencies.update((x.text or '').strip() for x in tree.findall('.//Texture') if x.text)
            for fx in tree.findall('.//fx'):
                if fx.text:
                    dependencies.update(fx.text.strip()[:-3]+'.'+b+'.dx11.fxo' for b in ('10','11'))
            count,errors=visual_group_audit(z,n,names);groups+=count
            if errors:
                old_errors=visual_group_audit(original,n,original_names)[1] if n in original.namelist() else []
                if set(errors)-set(old_errors):raise ValueError('输出引入新的网格问题：'+n+' '+str(set(errors)-set(old_errors)))
                issues.extend(dict(resource=n,location=loc,issue=err,preexisting=True) for loc,err in errors)
        from . import light_recovery, light_embedded
        embedded_checks = [light_embedded.audit(z, n, light_recovery.read_manifest(z, n))
                           for n in light_recovery.manifests(z.namelist())]
        unresolved={x.lower() for x in dependencies if 'res/'+x.lower() not in names}
    root=Path(client);paths=ET.parse(root/'paths.xml').getroot()
    for node in paths.findall('.//Package'):
        p=root/node.text.strip()
        if not p.exists():continue
        with zipfile.ZipFile(p) as z:unresolved.difference_update(n.lower() for n in z.namelist())
        if not unresolved:break
    unresolved={x for x in unresolved if not (root/'res'/x).exists()}
    return dict(status='completed_with_issues' if issues or unresolved else 'passed',zip_crc=True,stored_only=True,archive_format=archive_format,
                unchanged_resources_checked_by_crc_and_size=True,removed_resources=sorted(excluded or ()),embedded_projects=embedded_checks,groups_checked=groups,issues=issues,missing_dependencies=sorted(unresolved))
