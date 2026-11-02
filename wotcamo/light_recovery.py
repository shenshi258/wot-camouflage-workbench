"""Recover maker-owned, manifested lights without executing bundled scripts.

The source remains the finished package. Rebuilds replace its one runtime and
manifest, keeping deselected independent rigs byte-for-byte as baseline assets.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from . import light_assets as mesh, light_recipe

MANIFEST = re.compile(r'res/particles/light_maker_([0-9a-f]{12})/manifest\.json', re.I)
SEQUENCE = re.compile(r'particles/light_maker_[0-9a-f]{12}/light_[0-9]+\.seq', re.I)
SCRIPT = re.compile(r'res/scripts/client/gui/mods/mod_light_maker_[0-9a-f]{12}\.pyc', re.I)
SCOPE = 'selected rigid existing glow components; independent native models'


def manifests(names):
    return [n for n in names if MANIFEST.fullmatch(n)]


def read_manifest(archive, name):
    if archive.getinfo(name).file_size > 16 * 1024 * 1024:
        raise ValueError('灯效恢复清单过大')
    data = json.loads(archive.read(name))
    if data.get('scope') != SCOPE or not isinstance(data.get('models'), list) or not data['models']:
        raise ValueError('此成品包的灯效清单格式不受支持，无法可靠恢复工程')
    light_recipe.validate_config(data['recipe'])
    return data


def recover(package, work, log):
    from . import light_effects as engine
    import zipfile
    log('识别制作器成品包，恢复独立灯模型、挂点和配方……')
    with zipfile.ZipFile(package) as archive:
        names = manifests(archive.namelist())
        if len(names) != 1:
            raise ValueError('成品包包含多份灯效清单，无法确认有效版本；请使用原工程')
        name = names[0]; data = read_manifest(archive, name)
        from . import light_embedded
        embedded = light_embedded.metadata(name, data)
        old_embedded = None
        if embedded is not None:
            entry = archive.getinfo(embedded['path'])
            if entry.file_size != embedded['bytes']:
                raise ValueError('旧内嵌工程大小不匹配')
            with archive.open(entry) as stream:
                if light_embedded.hash_stream(stream) != embedded['sha256']:
                    raise ValueError('旧内嵌工程哈希不匹配')
            old_embedded = embedded['path']
        lookup = {n.casefold(): n for n in archive.namelist()}
        def read(path):
            # Read only archive entries, never paths on the host filesystem.
            if path.startswith('/') or '\\' in path or ':' in path or '..' in path.split('/'):
                raise ValueError('灯效恢复资源路径无效')
            return archive.read(lookup[path.casefold()])
        scripts = data.get('runtime_scripts', [
            'res/scripts/client/gui/mods/mod_light_maker_' + MANIFEST.fullmatch(name)[1] + '.pyc'])
        if not isinstance(scripts, list) or not scripts or any(not isinstance(s, str) or not SCRIPT.fullmatch(s) for s in scripts):
            raise ValueError('成品包运行脚本记录无效')
        scripts = [lookup[s.casefold()] for s in scripts]
        # An additional maker runtime with no manifest may otherwise double-mount.
        if {n.casefold() for n in archive.namelist() if SCRIPT.fullmatch(n)} != {s.casefold() for s in scripts}:
            raise ValueError('检测到未记录的旧灯效脚本，请先清理重复版本或使用原工程')
        areas = {row['model']: row for row in data['areas']}
        if len(areas) != len(data['areas']):
            raise ValueError('灯效模型来源记录重复')
        recovered = []; entries = []; seen = set(); vehicles = set()
        for rig in data['models']:
            rid = rig['id']; sequence = rig['sequence']
            if not isinstance(rid, str) or rid in seen or not SEQUENCE.fullmatch(sequence):
                raise ValueError('灯效模型编号或序列路径无效')
            seen.add(rid)
            source_visual = areas[rid]['source']
            match = re.fullmatch(r'res/vehicles/([^/]+)/([A-Za-z][A-Za-z0-9_]+)/(?:_skins/[^/]+/)?normal/lod0/([^/]+)\.visual_processed', source_visual)
            if not match or rig['part'] not in ('chassis','hull','turret','gun') or Path(source_visual).stem.split('_')[0] != rig['part']:
                raise ValueError('灯效模型的原车部件记录不受支持：' + rid)
            vehicles.add(match[2])
            visual = engine.xml(read(source_visual)); matrices, parents = mesh.node_matrices(visual)
            anchor = rig['anchor']; kind = rig['anchor_kind']
            if kind == 'part' and anchor == rig['part'] and rig['part'] != 'gun':
                anchor_matrix = np.eye(4)
            elif kind == 'node' and anchor in matrices:
                anchor_matrix = matrices[anchor]
                if rig['part'] == 'gun':
                    current = anchor; visited = set()
                    while current is not None and current != 'Gun' and current not in visited:
                        visited.add(current); current = parents.get(current)
                    if current != 'Gun':
                        raise ValueError('炮管灯挂点不在 Gun 倾角分支，需专门适配')
            else:
                raise ValueError('无法恢复原车灯效挂点：' + str(anchor))
            if 'other_anchor' in rig:
                raise ValueError('此成品包含双节点校正灯模型，当前不能可靠还原，请使用原工程')
            base = sequence[:-4]
            seq = engine.xml(read('res/' + sequence))
            objects = seq.findall('sequenceObject')
            resources = [(o.findtext('resource') or '').strip() for o in objects]
            if [r for r in resources if r] != [base + '.model']:
                raise ValueError('灯效序列引用与清单不一致：' + rid)
            for obj in objects:
                for track in obj.findall('track'):
                    default = {'position': [0, 0, 0], 'rotationEuler': [0, 0, 0], 'scale': [1, 1, 1]}.get(track.findtext('name'))
                    if default is not None:
                        frames = track.findall('frame')
                        if len(frames) != 1 or list(map(float, frames[0].findtext('value').split())) != default:
                            raise ValueError('灯效包含额外位置或缩放动画，当前无法可靠恢复')
            model = engine.xml(read('res/' + base + '.model'))
            if (model.findtext('nodelessVisual') or '').strip() != base:
                raise ValueError('灯效模型引用与清单不一致：' + rid)
            path = 'res/' + base + '.visual_processed'
            lamp_visual = engine.xml(read(path))
            lamp_matrices, _ = mesh.node_matrices(lamp_visual)
            sections = mesh.sections(read('res/' + base + '.primitives_processed'))
            parts = []; triangles = []; textures = set(); offset = 0
            for rs in lamp_visual.findall('renderSet'):
                nodes = [(n.text or '').strip() for n in rs.findall('node')]
                if len(nodes) != 1 or nodes[0] not in lamp_matrices or not np.allclose(lamp_matrices[nodes[0]], np.eye(4), atol=1e-7):
                    raise ValueError('灯效模型含额外骨骼变换，当前无法可靠恢复')
                for geo in rs.findall('geometry'):
                    vertices, skin = mesh.vertex_data(sections[geo.findtext('vertices').strip()])
                    if skin or not np.isfinite(vertices).all():
                        raise ValueError('灯效模型含不支持的蒙皮或无效坐标')
                    for pg in geo.findall('primitiveGroup'):
                        mat = pg.find('material')
                        if (mat.findtext('fx') or '').strip() != 'shaders/custom/emissive_playground.fx':
                            raise ValueError('灯效材质不是制作器生成的原生材质')
                        texture = next((p.findtext('Texture') or '').strip() for p in mat.findall('property') if (p.text or '').strip() == 'emissionMap')
                        raw = read('res/' + texture)
                        engine.dds.inspect(raw)
                        if raw[84:88] != b'DXT5':
                            raise ValueError('恢复灯效仅支持 DXT5/BC3 发光贴图')
                        textures.add(lookup[('res/' + texture).casefold()])
                        ids, (first, count) = engine.read_indices(sections, geo, pg)
                        if not len(ids) or ids.min() < first or ids.max() >= first + count or first + count > len(vertices):
                            raise ValueError('灯效模型索引越界或没有灯面')
                        parts.append(vertices); triangles.append(ids + offset); offset += len(vertices)
            if len(textures) != 1 or not parts:
                raise ValueError('独立灯模型贴图不唯一或没有可编辑灯面')
            vertices = np.concatenate(parts); indices = np.concatenate(triangles)
            preview = (np.c_[vertices[:, :3], np.ones(len(vertices))] @ anchor_matrix)[:, :3]
            original_recipe = copy.deepcopy(data.get('per_model_recipes', {}).get(rid) or data['recipe'])
            light_recipe.validate_config(original_recipe)
            identity = hashlib.sha1((name + '|' + rid).encode()).hexdigest()[:16]
            rec = dict(id='recovered_' + identity, vehicle=match[2], nation=match[1], part=rig['part'],
                       visual=path, source_visual=source_visual, primitives='res/' + base + '.primitives_processed',
                       render_set=0, geometry=0, group=0, material='恢复灯模型 ' + rid, component=0,
                       source_triangle_ids=list(range(len(indices))), texture=next(iter(textures)),
                       triangles=len(indices), supported=True, reason='', selected=True,
                       anchor=anchor, anchor_kind=kind, transform=np.eye(4).tolist(),
                       bounds=[preview.min(0).tolist(), preview.max(0).tolist()], recovered_model=True,
                       recovered_recipe=original_recipe, _vertices=vertices, _indices=indices,
                       _anchor_matrix=anchor_matrix, _preview=preview)
            if rid in data.get('per_model_recipes', {}):
                rec['配方'] = copy.deepcopy(original_recipe)
            recovered.append(rec)
            entries.append(dict(light_id=rec['id'], rig={k: rig[k] for k in ('id', 'part', 'anchor', 'anchor_kind', 'sequence')},
                                area=copy.deepcopy(areas[rid]),
                                bands=[copy.deepcopy(b) for b in data.get('bands', []) if b['model'] == rid],
                                recipe=original_recipe))
        if len(vehicles) != 1:
            raise ValueError('成品包包含多辆车，当前不能合并恢复')
    project = engine.scan(package, work, log, _remaining_only=True)
    project['lights'] += recovered
    project['recipe'] = copy.deepcopy(data['recipe'])
    project['recovery'] = dict(kind='maker_finished_package', manifest=name, runtime_scripts=scripts,
                               original_source_sha256=data.get('source_sha256'), entries=entries, old_embedded_project=old_embedded,
                               note='按独立灯模型恢复；原灯面分组与中和前贴图颜色不能完整还原。')
    log('已恢复 %d 个独立灯模型；未勾选的恢复模型在重新生成时保留成品包原效果。' % len(recovered))
    return project


def retained(project, selected):
    """Keep deselected rigs; remove precisely the authenticated old runtime/manifest."""
    recovery = project.get('recovery')
    if not recovery:
        return [], set()
    chosen = {x['id'] for x in selected}
    excluded = {recovery['manifest'], *recovery['runtime_scripts']}
    if recovery.get('old_embedded_project'):
        excluded.add(recovery['old_embedded_project'])
    return ([e for e in recovery['entries'] if e['light_id'] not in chosen], excluded)
