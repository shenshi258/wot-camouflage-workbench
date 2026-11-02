"""Read UML model choices for the preview without changing the source package."""
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from . import light_effects as engine

PARTS = ('chassis', 'hull', 'turret', 'gun')
RESOURCE = re.compile(r'^vehicles/([^/]+)/([^/]+)/', re.I)


def profiles(archive):
    names = {name.casefold(): name for name in archive.namelist()}
    found = []
    for name in archive.namelist():
        if not re.match(r'^res/scripts/client/mods/umlprofiles/[^/]+\.xml$', name, re.I):
            continue
        info = archive.getinfo(name)
        if info.file_size > 2_000_000:
            raise ValueError('UML 配置过大，无法安全预览。')
        # Some existing UML profiles contain non-XML "--" inside comments.
        data = re.sub(rb'<!--.*?-->', b'', archive.read(name), flags=re.S)
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
            raise ValueError('UML 配置包含不支持的声明。')
        try:
            root = ET.fromstring(data)
        except ET.ParseError as error:
            raise ValueError('UML 配置无法读取：%s' % error) from error
        models = root.find('models')
        if models is None:
            continue
        for node in models:
            visuals, identities, bases = {}, set(), set()
            for part in PARTS:
                model = (node.findtext(part + '/undamaged') or '').strip().replace('\\', '/')
                match = RESOURCE.match(model)
                if not match or '..' in PurePosixPath(model).parts or not model.lower().endswith('.model'):
                    continue
                identities.add((match[1].casefold(), match[2].casefold()))
                model_entry = names.get(('res/' + model).casefold())
                if model_entry is None:
                    continue
                model_root = engine.xml(archive.read(model_entry))
                visual = (model_root.findtext('nodefullVisual') or model_root.findtext('nodelessVisual') or '').strip().replace('\\', '/')
                if visual and not visual.startswith('/') and '..' not in PurePosixPath(visual).parts:
                    visual_entry = names.get(('res/' + visual + '.visual_processed').casefold())
                    if visual_entry:
                        visuals[part] = visual_entry
                destroyed = (node.findtext(part + '/destroyed') or '').strip().replace('\\', '/')
                base = RESOURCE.match(destroyed)
                if base:
                    bases.add((base[1].casefold(), base[2].casefold()))
            if visuals and len(identities) == 1:
                found.append(dict(file=name, tag=node.tag, identity=next(iter(identities)), bases=bases,
                                  enabled=(node.findtext('enabled') or '').strip().lower(),
                                  visuals=visuals, hull_position=node.findtext('chassis/hullPosition')))
    return found


def choose(archive, nation, vehicle):
    target = (nation.casefold(), vehicle.casefold())
    matches = [p for p in profiles(archive) if target == p['identity'] or target in p['bases']]
    if not matches:
        return None
    signatures = {(p['identity'], tuple(sorted(p['visuals'].items())), (p['hull_position'] or '').strip()) for p in matches}
    if len(signatures) != 1:
        raise ValueError('该车型存在多套不同的 UML 模型配置，暂无法自动选择；请先使用只包含一套配置的包。')
    return matches[0]
