"""Reversible light-mod installation and local, redacted diagnostic exports."""
import ctypes
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

from .common import ROOT, safe_join, write_json
from . import light_effects as engine


def stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8]


def client_layout(client):
    root = engine.resolve_client_root(client)
    paths = ET.parse(root / 'paths.xml').getroot()
    version = ET.parse(root / 'version.xml').getroot()
    def mount(name, package):
        choices = []
        for node in paths.findall('.//Path'):
            raw = (node.text or '').strip().replace('\\', '/').removeprefix('./')
            mask = (node.get('mask') or '').strip().lower()
            is_package = mask not in ('', 'false', '0')
            if raw.startswith(name + '/') and is_package == package:
                target = safe_join(root, raw)
                if target.parent != root / name:
                    continue
                choices.append(target)
        if len(set(choices)) != 1:
            raise ValueError('无法从 paths.xml 确认唯一的 ' + name + ' 当前版本目录。')
        return choices[0]
    return dict(root=root, mods=mount('mods', True), res_mods=mount('res_mods', False),
                version=version.findtext('version', '').strip(), realm=version.findtext('meta/realm', '').strip())


def ensure_game_closed(root):
    if os.name != 'nt':
        return
    from ctypes import wintypes as W
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', W.DWORD),
                    ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                    ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]; kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ValueError('无法检查游戏是否运行，请关闭游戏后重试。')
    try:
        entry = PROCESSENTRY32W(); entry.dwSize = ctypes.sizeof(entry)
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in ('worldoftanks.exe', 'worldoftanks64.exe'):
                process = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not process:
                    raise ValueError('检测到游戏进程，但无法确认目录，请关闭游戏后安装或恢复。')
                try:
                    size = W.DWORD(32768); buffer = ctypes.create_unicode_buffer(size.value)
                    if not kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                        raise ValueError('无法确认游戏进程目录，请关闭游戏后安装或恢复。')
                    if Path(buffer.value).resolve().is_relative_to(root):
                        raise ValueError('所选游戏正在运行，请先退出游戏，再安装或恢复。')
                finally:
                    kernel.CloseHandle(process)
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)


def log_files(root):
    result = []
    for directory in (root, root / 'win64', root / 'logs'):
        for pattern in ('game*.log', 'python*.log'):
            if directory.is_dir():
                result.extend(p for p in directory.glob(pattern) if p.is_file())
    return sorted(set(result))


def marker_path(root):
    key = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:16]
    return ROOT / '.cache/log_sessions' / (key + '.json')


def mark_test(client):
    layout = client_layout(client); root = layout['root']
    files = {}
    for path in log_files(root):
        with path.open('rb') as stream:
            prefix = stream.read(min(4096, path.stat().st_size))
        files[str(path)] = dict(offset=path.stat().st_size, prefix_bytes=len(prefix),
                               prefix_sha256=hashlib.sha256(prefix).hexdigest())
    marker = dict(client=str(root), created=datetime.now().astimezone().isoformat(), files=files)
    write_json(marker_path(root), marker)
    return marker


def install_mod(package, client, log=lambda _: None):
    package = Path(package).resolve()
    if package.suffix.lower() != '.wotmod':
        raise ValueError('请选择已完成构建的 .wotmod；.building 中间文件不能安装。')
    layout = client_layout(client); root = layout['root']
    ensure_game_closed(root)
    engine.check_game_zip(package)
    with zipfile.ZipFile(package) as z:
        engine.check_archive(z)
        names = {n for n in z.namelist() if not z.getinfo(n).is_dir()}
        if not any(n.startswith('res/particles/light_maker_') and n.endswith('/manifest.json') for n in names):
            raise ValueError('请选择灯效制作器生成的完整 .wotmod。')
    sha = engine.digest(package)
    report_path = package.parent / '验证记录.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8-sig'))
        if report.get('artifact', {}).get('sha256') != sha:
            raise ValueError('安装包与旁边的验证记录不匹配，请重新生成。')
        if report.get('whole_vehicle_loading', {}).get('status') == 'failed':
            raise ValueError('此包已被登记为失败，不能自动安装。')
        env = report.get('environment', {})
        if any(env.get(k) and env[k] != layout[k] for k in ('version', 'realm')):
            raise ValueError('所选游戏的版本或区服与生成记录不同，请选择正确客户端并重新生成。')
    target = safe_join(layout['mods'], 'light_maker_' + sha[:16] + '.wotmod')
    conflicts = set()
    resources = {n.lower() for n in names if n.startswith('res/vehicles/')}
    if layout['mods'].exists():
        for path in layout['mods'].rglob('*.wotmod'):
            if path.resolve() == package:
                raise ValueError('输入包已经放在游戏 mods 目录中，请从产物文件夹选择包进行安装。')
            if path.is_symlink() or not path.resolve().is_relative_to(layout['mods']):
                raise ValueError('mods 中存在指向外部的链接，请先人工处理：' + path.name)
            try:
                with zipfile.ZipFile(path) as z:
                    if resources.intersection(n.lower() for n in z.namelist()):
                        conflicts.add(path.resolve())
            except zipfile.BadZipFile:
                raise ValueError('现有模组包损坏，无法核对冲突：' + path.name)
    for name in names:
        if name.startswith('res/'):
            path = safe_join(layout['res_mods'], name[4:])
            if path.is_file():
                conflicts.add(path)
    # Older generated overlays can have different tokens while overriding this vehicle.
    vehicles = {n.split('/')[3] for n in resources if len(n.split('/')) > 4}
    particle_root = layout['res_mods'] / 'particles'
    if particle_root.exists():
        for manifest in particle_root.glob('light_maker_*/manifest.json'):
            data = json.loads(manifest.read_text(encoding='utf-8-sig'))
            covered = {c.get('source', '').lower().split('/')[3] for c in data.get('coverage', [])
                       if c.get('source', '').lower().startswith('res/vehicles/')}
            if vehicles.intersection(covered):
                script = safe_join(layout['res_mods'], 'scripts/client/gui/mods/mod_' + manifest.parent.name + '.pyc')
                if script.is_file():
                    conflicts.add(script)
    if target.exists():
        conflicts.add(target)
    backup = safe_join(root, 'light_maker_backups/' + stamp()); backup.mkdir(parents=True)
    manifest_path = backup / 'installation.json'
    journal = dict(schema=1, client=str(root), created=datetime.now().astimezone().isoformat(),
                   target=str(target.relative_to(root)), artifact_sha256=sha, state='preparing',
                   version=layout['version'], realm=layout['realm'], files=[])
    for path in sorted(conflicts):
        if not path.is_relative_to(root):
            raise ValueError('冲突资源不在所选游戏内，已停止安装。')
        rel = str(path.relative_to(root))
        journal['files'].append(dict(path=rel, sha256=engine.digest(path), moved=False))
    write_json(manifest_path, journal)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_suffix('.installing')
    try:
        log('复制并校验待测包，备份同名资源和同车冲突包……')
        with package.open('rb') as a, staged.open('xb') as b:
            shutil.copyfileobj(a, b)
        if engine.digest(staged) != sha:
            raise ValueError('安装复制校验失败。')
        ensure_game_closed(root)
        journal['state'] = 'installing'; write_json(manifest_path, journal)
        for record in journal['files']:
            old = safe_join(root, record['path']); saved = safe_join(backup / 'original', record['path'])
            saved.parent.mkdir(parents=True, exist_ok=True)
            if engine.digest(old) != record['sha256']:
                raise ValueError('冲突资源在安装期间被修改，已停止。')
            record['moved'] = True; write_json(manifest_path, journal)
            os.replace(old, saved)
        journal['placing_new'] = True; write_json(manifest_path, journal)
        os.replace(staged, target)
        journal['state'] = 'installed'; write_json(manifest_path, journal)
        journal['test_marker'] = mark_test(root); write_json(manifest_path, journal)
    except Exception:
        restore_install(manifest_path)
        raise
    log('已安装到 ' + str(target) + '；备份保存在 ' + str(backup))
    return dict(target=str(target), source=str(package), backup=str(manifest_path), sha256=sha, conflicts_backed_up=len(conflicts),
                whole_vehicle_loading=dict(status='not_tested'))


def restore_install(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    journal = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    layout = client_layout(journal['client']); root = layout['root']
    expected_backup_root = root / 'light_maker_backups'
    if manifest_path.parent.parent != expected_backup_root or manifest_path.name != 'installation.json':
        raise ValueError('不是所选游戏的制作器安装备份。')
    ensure_game_closed(root)
    if journal['state'] == 'restored':
        raise ValueError('这次安装已经恢复。')
    allowed = (layout['mods'], layout['res_mods'])
    def checked(rel):
        path = safe_join(root, rel)
        if not any(path.is_relative_to(p) for p in allowed):
            raise ValueError('备份记录中的恢复路径无效。')
        return path
    target = checked(journal['target']); backup = manifest_path.parent
    if target.exists() and journal.get('placing_new') and engine.digest(target) != journal['artifact_sha256']:
        raise ValueError('已安装包被其他程序修改，未覆盖；请人工处理。')
    ready = []
    for record in journal['files']:
        old = checked(record['path']); saved = safe_join(backup / 'original', record['path'])
        if saved.exists():
            if engine.digest(saved) != record['sha256']:
                raise ValueError('备份内容校验失败，停止恢复。')
            if old.exists() and old != target:
                raise ValueError('恢复位置已有新文件，未覆盖：' + old.name)
            ready.append((old, saved))
        elif record['moved'] and not (old.exists() and engine.digest(old) == record['sha256']):
            raise ValueError('备份资源缺失，停止恢复。')
    if target.exists() and journal.get('placing_new'):
        os.replace(target, backup / ('disabled_' + uuid.uuid4().hex[:8] + '.wotmod'))
    for old, saved in ready:
        old.parent.mkdir(parents=True, exist_ok=True); os.replace(saved, old)
    staged = target.with_suffix('.installing')
    if staged.exists():
        os.replace(staged, backup / ('unfinished_' + uuid.uuid4().hex[:8] + '.bin'))
    journal['state'] = 'restored'; write_json(manifest_path, journal)
    return str(manifest_path)


def latest_install(client):
    root = client_layout(client)['root']
    for path in sorted((root / 'light_maker_backups').glob('*/installation.json'), reverse=True):
        if json.loads(path.read_text(encoding='utf-8-sig')).get('state') in ('installed', 'installing', 'preparing'):
            return path
    raise ValueError('所选游戏没有可恢复的制作器安装记录。')


_SECRET = re.compile(r'token|password|passwd|authorization|credential|ticket|session|access.?key|login.?key|player.?id|account|user.?id|dbid|login|登录|口令|密码|令牌', re.I)
_ERROR = re.compile(r'\[(?:ERROR|CRITICAL|FATAL)\]|traceback|exception|assertion|compound building failed|type="crash"|failed to load|ZIP64', re.I)
_LIGHT = re.compile(r'LightMaker|light_maker_|SpiderBreathing|independent (?:VFX|model|lights)|emissive_playground', re.I)


def redact(text):
    if _SECRET.search(text) or re.search(r'\beyJ[A-Za-z0-9_-]{20,}', text):
        return '[已过滤敏感记录]'
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[EMAIL]', text)
    text = re.sub(r'(?i)([A-Z]:[\\/]Users[\\/])[^\\/\s]+', r'\1[USER]', text)
    text = re.sub(r'(?i)(\b(?:ip|host|address)\s*[=:]\s*)[^\s,;]+', r'\1[ADDRESS]', text)
    return text


def redacted_lines(lines):
    hidden = False
    result = []
    header = re.compile(r'^\[?\d{4}-\d{2}-\d{2}[ T]|^(?:INFO|WARNING|ERROR|CRITICAL|DEBUG)\s')
    for line in lines:
        if header.search(line):
            hidden = False
        safe = redact(line)
        if safe == '[已过滤敏感记录]':
            hidden = True
            # Never retain arbitrary text from a sensitive line. Preserve only
            # fixed diagnostic markers; continuation lines remain suppressed.
            markers = []
            if _ERROR.search(line): markers.append('[ERROR]')
            for marker in ('Compound building failed', 'LightMaker', 'light_maker_', 'emissive_playground'):
                if marker.lower() in line.lower(): markers.append(marker)
            result.append('[已过滤敏感记录]' + ((' ' + ' '.join(markers)) if markers else ''))
            continue
        result.append('[已过滤敏感记录]' if hidden else safe)
    return result


def export_logs(client=None, files=None, output_dir=None, since_mark=True, package=None):
    layout = client_layout(client) if client else None
    paths = [Path(p).resolve() for p in files] if files else log_files(layout['root'])
    marker = None
    if layout and since_mark and marker_path(layout['root']).exists():
        marker = json.loads(marker_path(layout['root']).read_text(encoding='utf-8-sig'))
    if not paths:
        raise ValueError('没有找到 game.log 或 python.log，可用“选择日志文件提取”手动选择。')
    sections = []; summaries = []; crashes = []; model_failures = []
    for path in paths:
        if path.suffix.lower() != '.log' or not path.is_file():
            raise ValueError('请选择可读取的 .log 文件。')
        size = path.stat().st_size; start = max(0, size - 32 * 1024 * 1024)
        method = 'latest_launch_or_last_32MB'; old = (marker or {}).get('files', {}).get(str(path))
        if old and size >= old['offset']:
            with path.open('rb') as stream:
                prefix = stream.read(old['prefix_bytes'])
            if hashlib.sha256(prefix).hexdigest() == old['prefix_sha256']:
                start = max(old['offset'], size - 32 * 1024 * 1024)
                method = 'since_test_marker' if start == old['offset'] else 'since_test_marker_tail32MB'
        with path.open('rb') as stream:
            stream.seek(start); raw = stream.read(size - start)
        encoding = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
        text = raw.decode(encoding, errors='replace'); lines = text.splitlines()
        if not method.startswith('since_test_marker'):
            launches = [i for i, line in enumerate(lines) if '[WinMain] Command line:' in line]
            if launches:
                lines = lines[launches[-1]:]; method = 'latest_launch'
        safe_lines = redacted_lines(lines)
        wanted = set(); errors = 0
        for i, line in enumerate(lines):
            if _ERROR.search(line) or _LIGHT.search(line) or '[WinMain] Command line:' in line:
                if _ERROR.search(line):
                    errors += 1
                wanted.update(range(max(0, i - 2), min(len(lines), i + 9)))
            if 'type="crash"' in line:
                crashes.append(safe_lines[i])
            if 'Compound building failed' in line:
                model_failures.append(safe_lines[i])
        selected = sorted(wanted)[-12000:]
        excerpt = '\n'.join('%d: %s' % (i + 1, safe_lines[i]) for i in selected)
        sections.append('===== %s | %s | section-relative line numbers =====\n%s' % (path.name, method, excerpt or '此范围没有匹配的错误或灯效记录。'))
        summaries.append(dict(file=path.name, range=method, byte_start=start, file_bytes=size,
                              scanned_lines=len(lines), matching_errors=errors, excerpt_lines=len(selected),
                              excerpt_limited=len(wanted) > 12000))
    summary = dict(created=datetime.now().astimezone().isoformat(), logs=summaries,
                   crashes=crashes[-30:], compound_failures=model_failures[-30:],
                   scope='Error/context and light-loader records only. Sensitive records filtered. No raw logs or crash dumps included. Local export only.',
                   limitations='Log errors do not identify the root cause or prove visibility. Older errors can precede this mod. Hash identifies a selected package, not necessarily the package active during a historical log.',
                   whole_vehicle_loading=dict(status='not_tested'))
    if layout:
        summary['client'] = dict(root=redact(str(layout['root'])), version=layout['version'], realm=layout['realm'])
    if marker:
        summary['test_marker_time'] = marker['created']
    if package and Path(package).is_file():
        summary['selected_artifact'] = dict(name=Path(package).name, sha256=engine.digest(package))
    if layout:
        try:
            installation = json.loads(latest_install(layout['root']).read_text(encoding='utf-8-sig'))
            summary['latest_installation'] = {k: installation[k] for k in ('created', 'artifact_sha256', 'version', 'realm', 'state')}
        except ValueError:
            pass
    destination = Path(output_dir or ROOT / 'result/灯效日志'); destination.mkdir(parents=True, exist_ok=True)
    target = destination / ('灯效报错摘录_' + stamp() + '.zip')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as z:
        z.writestr('错误与灯效摘录.txt', '\n\n'.join(sections).encode('utf-8-sig'))
        z.writestr('排查摘要.json', json.dumps(summary, ensure_ascii=False, indent=2).encode('utf-8'))
    return target, summary
