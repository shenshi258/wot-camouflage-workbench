"""Private resource graph for own-vehicle skins; global exports retain legacy paths."""
import hashlib
import re
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET
from . import light_effects as engine, light_assets
from .common import safe_join, title_name, write_json
from .preview3d_assets import Resources

VALUES = ('all', 'self')
LABELS = {'all': '所有同资源车辆', 'self': '仅自己的车辆'}
HELP = '仅影响本机显示。所有同资源车辆：引用同一模型资源的敌我车辆都会应用；仅自己的车辆：使用独立模型与贴图路径，其他车辆保留原资源。仅自己模式需所选客户端的 Python 2.7 运行库，游戏内效果待实测。'


def validate(value):
    if value not in VALUES:
        raise ValueError('涂装应用范围无效，请选择所有同资源车辆或仅自己的车辆。')
    return value


def client_info(client):
    root=engine.resolve_client_root(client)
    version=ET.parse(root/'version.xml').getroot()
    return dict(root=str(root),version=version.findtext('version','').strip(),
                realm=version.findtext('meta/realm','').strip(),
                paths_xml_sha256=engine.digest(root/'paths.xml'))


def _path(value):
    value = value.strip().replace('\\', '/').removeprefix('res/')
    if not value or value.startswith('/') or ':' in value or any(p in ('', '..', '.') for p in value.split('/')):
        raise ValueError('资源路径无效：' + value)
    return value


def _client_models(client, prefix):
    """Index names only; do not read or change installed mods or game data."""
    import xml.etree.ElementTree as ET
    names = set()
    paths = ET.parse(Path(client) / 'paths.xml').getroot()
    for node in paths.findall('.//Package'):
        package = Path(client) / (node.text or '').strip()
        if not package.is_file() or 'vehicle' not in package.name.lower():
            continue
        with zipfile.ZipFile(package) as archive:
            names.update(n for n in archive.namelist() if n.lower().startswith(prefix.lower()) and n.lower().endswith('.model'))
    loose = Path(client) / 'res' / prefix
    if loose.is_dir():
        names.update(p.relative_to(Path(client) / 'res').as_posix() for p in loose.rglob('*.model'))
    return names


def private_resources(source, client, tank, overrides=None):
    """Return a standalone private graph and a Py27 appearance selector.

    Only ordinary single-vehicle packages are accepted: third-party scripts,
    UML profiles and shared overrides would otherwise still affect other cars.
    """
    if not re.fullmatch(r'[A-Za-z]+/[A-Za-z0-9_-]+', tank):
        raise ValueError('涂装车型无效。')
    prefix = 'vehicles/' + tank + '/'
    overrides = {_path(k): v for k, v in (overrides or {}).items()}
    with zipfile.ZipFile(source) as archive:
        engine.check_archive(archive)
        source_resources = {n[4:]: archive.read(n) for n in archive.namelist() if n.startswith('res/') and not n.endswith('/')}
    originals = {**source_resources, **overrides}
    if not originals:
        raise ValueError('没有可以应用的涂装资源。')
    if any(not n.lower().startswith(prefix.lower()) for n in originals):
        raise ValueError('仅自己的车辆模式暂只支持单车型普通涂装；含 UML、第三方脚本或共享资源的包请使用所有同资源车辆模式。')
    if any(n.lower().endswith(('.pyc', '.py', '.seq')) for n in originals):
        raise ValueError('仅自己的车辆模式暂不支持已有动画脚本包，请先完成普通涂装。')
    token = hashlib.sha256((tank + '\0' + engine.digest(source) + '\0' + ''.join(
        k + hashlib.sha256(v).hexdigest() for k, v in sorted(overrides.items()))).encode()).hexdigest()[:16]
    namespace = 'vehicles/wot_workbench/' + token + '/'
    def private(name):
        return namespace + name.removeprefix('vehicles/')
    overlay = {n.lower(): (n, raw) for n, raw in originals.items()}
    resources = Resources(source, client)
    output, mapping, visited = {}, {}, set()
    def read(name):
        return overlay[name.lower()][1] if name.lower() in overlay else resources.read(name)
    def clone(name):
        name = _path(name)
        if not name.lower().startswith(prefix.lower()):
            return name
        target = private(name)
        if name.lower() in visited:
            return target
        visited.add(name.lower())
        raw = read(name)
        mapping[target] = name
        if name.lower().endswith(('.model', '.visual_processed', '.visual', '.mfm')):
            root = engine.xml(raw)
            for node in root.iter():
                text = (node.text or '').strip().replace('\\', '/')
                if not text.lower().startswith(prefix.lower()):
                    continue
                if node.tag in ('nodefullVisual', 'nodelessVisual'):
                    clone(text + '.visual_processed')
                    clone(text + '.primitives_processed')
                    node.text = private(text)
                elif node.tag == 'parent':
                    model = text if text.lower().endswith('.model') else text + '.model'
                    mapped = clone(model)
                    node.text = mapped if text.lower().endswith('.model') else mapped[:-6]
                elif node.tag == 'primitivesName':
                    model = text if text.lower().endswith('.primitives_processed') else text + '.primitives_processed'
                    mapped = clone(model)
                    node.text = mapped if text.lower().endswith('.primitives_processed') else mapped[:-21]
                else:
                    # Referenced textures, MFM files, animations and explicit
                    # resource paths keep their byte content and original format.
                    try:
                        node.text = clone(text)
                    except FileNotFoundError as error:
                        raise ValueError('无法复制本车资源引用：' + text) from error
            # When no primitivesName is present the engine uses the moved
            # visual's own basename. Copy that binary unchanged as well.
            if name.lower().endswith('.visual_processed') and root.find('primitivesName') is None:
                clone(name[:-17] + '.primitives_processed')
            raw = light_assets.xml(root)
        output['res/' + target] = raw
        return target
    groups, group_issues = 0, []
    try:
        models = _client_models(client, prefix) | {n for n in originals if n.lower().endswith('.model')}
        if not models:
            raise ValueError('所选客户端中找不到该车型的模型路径，不能生成仅自己模式。')
        model_paths = {n.lower(): clone(n) for n in sorted(models)}
        # Preserve provided LODs/textures even when not referenced by the normal
        # model set; every input override must remain private, never global.
        for name in originals:
            clone(name)
        class Readback:
            def read(self, name):
                return output[name] if name in output else resources.read(name)
        names = {n.lower(): n for n in output}
        for name in output:
            if not name.endswith('.visual_processed'):
                continue
            count, errors = engine.visual_group_audit(Readback(), name, names)
            original = mapping[name[4:]]
            _, existing = engine.visual_group_audit(resources, original,
                {original.replace('.visual_processed', '.primitives_processed').lower():
                 original.replace('.visual_processed', '.primitives_processed')})
            if set(errors) - set(existing):
                raise ValueError('独立资源引入网格分组错误：' + name + str(errors))
            groups += count
            group_issues.extend(dict(resource=name, location=loc, issue=message, preexisting=True)
                                for loc, message in errors)
    finally:
        resources.close()
    if not any(n in mapping.values() for n in originals):
        raise ValueError('涂装资源未被复制。')
    runtime = (Path(__file__).parent / 'vehicle_scope_runtime.py.txt').read_text(encoding='utf-8')
    runtime = runtime.replace('MODEL_PATHS = {}', 'MODEL_PATHS = ' + repr(model_paths))
    with tempfile.TemporaryDirectory(prefix='wot_scope_') as folder:
        src, compiled = Path(folder) / 'runtime.py', Path(folder) / 'runtime.pyc'
        src.write_text(runtime, encoding='utf-8')
        engine.compile27(src, compiled, client)
        script = 'scripts/client/gui/mods/mod_wot_scope_' + token + '.pyc'
        output['res/' + script] = compiled.read_bytes()
    return output, dict(value='self', namespace=namespace, runtime=script, model_paths=model_paths,
                        resource_sources=mapping, client=client_info(client),
                        groups_checked=groups, preexisting_group_issues=group_issues,
                        in_game_tested=False, whole_vehicle_loading=dict(status='not_tested'))


def folder(output, client, tank):
    """Keep editable originals outside res; only private resources are installed."""
    output = Path(output).resolve()
    original = output / 'res'
    saved = output / 'source_res'
    staging = output / 'private_res'
    if saved.exists() or staging.exists():
        raise ValueError('独立资源暂存目录已存在，请使用新的输出目录。')
    with tempfile.TemporaryDirectory(prefix='wot_scope_folder_') as tmp:
        carrier = Path(tmp) / 'source.wotmod'
        with zipfile.ZipFile(carrier, 'w', zipfile.ZIP_STORED) as archive:
            for path in sorted(original.rglob('*')):
                if path.is_file():
                    archive.write(path, 'res/' + path.relative_to(original).as_posix())
        generated, details = private_resources(carrier, client, tank)
    for name, raw in generated.items():
        path = safe_join(staging, name[4:])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    # All three resolved paths must be direct children of this new output.
    if any(p.resolve().parent != output for p in (original, saved, staging)):
        raise ValueError('独立资源输出目录无效。')
    original.rename(saved)
    staging.rename(original)
    return details


def export_existing(source, output_dir, client, tank, value='all', title='涂装应用范围'):
    """Explicit new artifact for an existing ordinary skin, without editing it."""
    value=validate(value)
    source=Path(source).resolve()
    client_meta=client_info(client)
    before=engine.digest(source)
    out=Path(output_dir)/(title_name(title)+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True,exist_ok=False)
    target=out/(title_name(title)+'_'+('仅本车' if value=='self' else '同资源车辆')+'_待实测.wotmod')
    details=archive(source,target,client,tank,value)
    if engine.digest(source)!=before:
        raise ValueError('原始包在构建过程中发生变化，请重新选择输入。')
    # Source-comparison group checks happen before writing private resources.
    # This pass resolves final-package dependencies against the selected client.
    audit=engine.audit_package(target,target,{},client)
    if audit['missing_dependencies']:
        raise ValueError('最终包缺少依赖：'+str(audit['missing_dependencies'][:5]))
    record=dict(artifact=dict(path=str(target),sha256=engine.digest(target),bytes=target.stat().st_size),
        application_scope=details,client=client_meta,
        baseline=dict(path=str(source),sha256=before,status='unconfirmed',agent_observed=False),
        file_validation=audit,in_game_tested=False,whole_vehicle_loading=dict(status='not_tested'))
    write_json(out/'验证记录.json',record)
    (out/'使用说明.txt').write_text('应用范围：'+LABELS[value]+'。只改变本机显示，不会同步给其他玩家。\n'
        +'原输入包保留。测试前停用同款旧包，只启用这份；否则旧的全局替换仍会影响敌我车辆。\n'
        +'尚未进行游戏实测，需检查车库、同型号敌我车辆、切车、重生、残骸、开镜和 LOD。\n',encoding='utf-8-sig')
    return target,record


def archive(source, target, client, tank, scope='all', overrides=None):
    """Write a new export, preserving the original input in either mode."""
    scope = validate(scope)
    if scope == 'all':
        with zipfile.ZipFile(source) as z:
            names = {n.lower(): n for n in z.namelist()}
        changes, additions = {}, {}
        for name, raw in (overrides or {}).items():
            resource = 'res/' + _path(name)
            (changes if resource.lower() in names else additions)[names.get(resource.lower(), resource)] = raw
        engine.write_game_archive(source, target, changes=changes, added=additions)
        return dict(value='all')
    output, details = private_resources(source, client, tank, overrides)
    # The private export contains no original vehicle resource override.
    with zipfile.ZipFile(source) as z:
        excluded = [n for n in z.namelist() if n.startswith('res/')]
    engine.write_game_archive(source, target, added=output, excluded=excluded)
    engine.check_game_zip(target)
    with zipfile.ZipFile(target) as z:
        engine.check_archive(z)
        for name, raw in output.items():
            if z.read(name) != raw:
                raise ValueError('仅自己模式最终资源与生成结果不一致。')
        if any(n.startswith('res/vehicles/' + tank + '/') for n in z.namelist()):
            raise ValueError('仅自己模式仍包含全局车型替换，已停止生成。')
    return details
