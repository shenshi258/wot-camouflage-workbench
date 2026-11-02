"""Versioned engineering snapshots inside game-ignored maker resource files."""
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import light_recipe

FILENAME = 'editable_project.wotlights'
ENTRIES = {'source.wotmod', 'project.json', 'extracted_lights.npz'}
MAX_SOURCE = zipfile.ZIP64_LIMIT - 1
MAX_METADATA = 32 * 1024 * 1024
MAX_CACHE = 512 * 1024 * 1024
MAX_DEPTH = 4


def hash_stream(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(chunk)
    return h.hexdigest()


def check_snapshot(path):
    """Validate all entry CRCs and source hash without trusting cached numpy data."""
    with zipfile.ZipFile(path) as z:
        if len(z.namelist()) != 3 or set(z.namelist()) != ENTRIES:
            raise ValueError('内嵌工程条目不完整或重复')
        for name, limit in (('source.wotmod', MAX_SOURCE), ('project.json', MAX_METADATA), ('extracted_lights.npz', MAX_CACHE)):
            if z.getinfo(name).file_size > limit:
                raise ValueError('内嵌工程资源过大：' + name)
        saved = json.loads(z.read('project.json'))
        if saved.get('schema') != 1 or not isinstance(saved.get('lights'), list):
            raise ValueError('不支持的内嵌工程格式')
        if not re.fullmatch(r'[0-9a-f]{64}', saved.get('source_sha256', '')):
            raise ValueError('内嵌工程输入校验记录无效')
        light_recipe.validate_config(saved['recipe'])
        for light in saved['lights']:
            if isinstance(light.get('配方'), dict):
                light_recipe.validate_config(light['配方'])
        with z.open('source.wotmod') as f:
            if hash_stream(f) != saved['source_sha256']:
                raise ValueError('内嵌工程原始输入哈希不匹配')
        # Read cached data for CRC only; restoration derives geometry from source.
        with z.open('extracted_lights.npz') as f:
            hash_stream(f)
    return dict(source_sha256=saved['source_sha256'], lights=len(saved['lights']),
                selected=sum(bool(x.get('selected')) for x in saved['lights']),
                source_kind='finished_package_recovery' if saved.get('recovery') else 'original_project')


def metadata(manifest_name, data):
    value = data.get('embedded_project')
    if value is None:
        return None
    expected = manifest_name.rsplit('/', 1)[0] + '/' + FILENAME
    if (not isinstance(value, dict) or value.get('schema') != 1 or value.get('path') != expected
            or not isinstance(value.get('bytes'), int) or isinstance(value['bytes'], bool)
            or not 0 < value['bytes'] < zipfile.ZIP64_LIMIT
            or not isinstance(value.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', value['sha256'])):
        raise ValueError('内嵌工程引用或校验记录无效')
    return value


def extract_checked(archive, info, destination):
    if archive.getinfo(info['path']).file_size != info['bytes']:
        raise ValueError('内嵌工程文件大小不匹配')
    with archive.open(info['path']) as source, Path(destination).open('xb') as target:
        shutil.copyfileobj(source, target)
    with Path(destination).open('rb') as f:
        if hash_stream(f) != info['sha256']:
            raise ValueError('内嵌工程校验失败，不能保证完整还原')
    return check_snapshot(destination)


def restore(archive, manifest_name, data, work, log, depth):
    from . import light_effects as engine
    info = metadata(manifest_name, data)
    if info is None:
        return None
    if depth >= MAX_DEPTH:
        raise ValueError('内嵌工程嵌套过深，已停止恢复')
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='embedded_', dir=work))
    backup = folder / FILENAME
    log('发现内嵌工程，核对完整性并恢复生成前的灯面、勾选和配方……')
    summary = extract_checked(archive, info, backup)
    project = engine.load_project(backup, folder / 'source', log,
                                  require_complete=True, _embedded_depth=depth + 1)
    # Historical baseline feedback is not a game validation on the next machine.
    historical_baseline = project.get('baseline_user_confirmed', False)
    project['baseline_user_confirmed'] = False
    project['embedded_restore'] = dict(project_sha256=info['sha256'], restored_completely=True,
                                       source_kind=summary['source_kind'],
                                       historical_baseline_user_confirmed=historical_baseline,
                                       note='恢复到生成时保存的工程状态；不补回此前已丢失的数据，不沿用游戏验收结论。')
    backup.unlink()  # Only this call's own temporary copy; source stays in folder/source.
    log('内嵌工程已完整恢复：%d 块灯面，原始输入与灯面几何校验一致。' % len(project['lights']))
    return project


def audit(archive, manifest_name, data):
    info = metadata(manifest_name, data)
    if info is None:
        return dict(enabled=False)
    from .common import ROOT
    with tempfile.TemporaryDirectory(prefix='embedded_audit_', dir=ROOT / '.cache') as folder:
        summary = extract_checked(archive, info, Path(folder) / FILENAME)
    return dict(enabled=True, status='passed', sha256=info['sha256'], bytes=info['bytes'], **summary)
