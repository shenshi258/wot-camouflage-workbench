"""Read-only batch inspection for the conditional-skin converter prototype.

This module deliberately does not emit installable mods: identifying resources
does not establish that per-vehicle model switching works in the game.
"""
import hashlib
import re
import zipfile
from pathlib import Path

VEHICLE = re.compile(r'^res/vehicles/([^/]+)/([^/]+)/(.+)$', re.I)
MODEL_EXTS = ('.model', '.visual', '.visual_processed', '.primitives', '.primitives_processed')
# Descriptor files under res/vehicles/item_defs are not a second vehicle.
NON_VEHICLE_NAMESPACES = frozenset(('item_defs','common'))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect(path):
    """Classify one archive without extracting files or changing its contents."""
    path = Path(path).resolve()
    result = dict(path=str(path), sha256=sha256(path), bytes=path.stat().st_size,
                  status='analysis_only', whole_vehicle_loading='not_tested')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        seen = set()
        vehicles, styles = set(), set()
        texture_count = model_count = script_count = unsafe_count = 0
        ordinary_overrides = style_overrides = 0
        for entry in entries:
            name = entry.filename.replace('\\', '/')
            key = name.casefold()
            if name.startswith('/') or ':' in name or '..' in name.split('/'):
                unsafe_count += 1
            if key in seen:
                raise ValueError('存在大小写或路径形式重复的资源：' + name)
            seen.add(key)
            if entry.is_dir():
                continue
            if key.endswith(('.py', '.pyc', '.pyd', '.dll')) and '/scripts/' in '/'+key:
                script_count += 1
            match = VEHICLE.match(name)
            if not match:
                continue
            nation, vehicle, tail = match.groups()
            if nation.casefold() in NON_VEHICLE_NAMESPACES:
                continue
            vehicles.add((nation, vehicle))
            parts = tail.split('/')
            is_style = len(parts) >= 3 and parts[0].casefold() == '_skins'
            if is_style:
                styles.add((nation, vehicle, parts[1]))
            if key.endswith('.dds'):
                texture_count += 1
                if is_style:style_overrides += 1
                else:ordinary_overrides += 1
            elif key.endswith(MODEL_EXTS):
                model_count += 1
                if is_style:style_overrides += 1
                else:ordinary_overrides += 1
        if unsafe_count:
            raise ValueError('包中包含不安全的资源路径')
        if model_count and texture_count:kind='模型与贴图'
        elif model_count:kind='模型'
        elif texture_count:kind='普通贴图'
        else:kind='未识别到车型模型或贴图'
        concerns=[]
        if ordinary_overrides:concerns.append('含非 3D 风格目录资源；需要逐项确认是否覆盖原版共享资源。')
        if style_overrides:concerns.append('含 3D 风格目录；仅凭路径不能证明所有材质都已隔离。')
        if script_count:concerns.append('包中含脚本；转换时必须单独处理兼容与冲突。')
        if len(vehicles)>1:concerns.append('包中包含多款车型，需要分别确定资源归属。')
        if not vehicles:concerns.append('未发现标准车型目录，不能判断适用车型。')
        result.update(kind=kind, vehicles=[a+'/'+b for a,b in sorted(vehicles,key=lambda x:(x[0].casefold(),x[1].casefold()))],
                      style_directories=[a+'/'+b+'/'+c for a,b,c in sorted(styles,key=lambda x:tuple(v.casefold() for v in x))],
                      textures=texture_count,models=model_count,scripts=script_count,
                      shared_path_resources=ordinary_overrides,style_path_resources=style_overrides,
                      entries=len(entries),observations=concerns,crc_validation='not_checked',
                      conversion='分析完成；生成时仍会检查脚本、资源和客户端接口。')
    return result


def inspect_many(paths):
    results=[]
    for path in paths:
        try:
            results.append(inspect(path))
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            results.append(dict(path=str(path),status='error',error=str(error)))
    return results
