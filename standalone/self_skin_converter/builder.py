"""Experimental offline builder: narrow supported inputs, never installs mods.

Generated files are explicitly pending game tests. Unknown resource types,
unresolved dependencies and unrecognised scripts stop the build instead of
being silently dropped or falsely labeled successful.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
import zipfile
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from asset_plan import plan
from client_catalog import ClientCatalog
from preflight import inspect,sha256
from relocation import rewrite_xml,serialize_xml,token_for
from resource_graph import game_path,parse
from client_probe import verify as verify_client_api
from insignia_adapter import parse_script as parse_insignia
from ae_adapter import analyse as analyse_ae
from package_audit import audit as audit_package

ALLOWED=('.dds','.model','.visual','.visual_processed','.primitives','.primitives_processed','.mfm','.vt')
XML_EXT=('.model','.visual','.visual_processed','.mfm')
DEFINITION_NATIONS={'french':'france','chinese':'china','czech':'czech','swedish':'sweden',
                    'polish':'poland','italian':'italy','japanese':'japan','german':'germany',
                    'american':'usa','british':'uk','russian':'ussr'}


def _compile27(source,target,client):
    dll=Path(client)/'win64/python27.dll'
    if not dll.is_file():raise ValueError('所选客户端缺少 win64/python27.dll，无法编译切换脚本。')
    source=Path(source).resolve();target=Path(target).resolve()
    try:source.read_bytes().decode('ascii')
    except UnicodeDecodeError as error:raise ValueError('模型资源路径含不支持的非 ASCII 字符，无法编译游戏脚本。') from error
    helper=r'''import ctypes,sys
library=ctypes.PyDLL(sys.argv[1])
ctypes.c_int.in_dll(library,'Py_NoSiteFlag').value=1
library.Py_Initialize()
library.PyRun_SimpleString.argtypes=[ctypes.c_char_p]
source,target=sys.argv[2:]
code=("import marshal\nsrc=open(u%s,'rb').read()\n" % ascii(source)+
      "code=compile(src,'self_skin.py','exec')\n"+
      "open(u%s,'wb').write('\\x03\\xf3\\x0d\\x0a\\x00\\x00\\x00\\x00'+marshal.dumps(code))\n" % ascii(target))
if library.PyRun_SimpleString(code.encode('ascii')):sys.exit(1)
'''
    run=subprocess.run([sys.executable,'-c',helper,str(dll),str(source),str(target)],
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if run.returncode or not target.is_file() or target.read_bytes()[:4]!=b'\x03\xf3\x0d\x0a':
        raise ValueError('无法编译客户端脚本：'+run.stdout.decode('utf-8','replace')[-1000:])


def _check_source(archive,nation,vehicle,adapted=()):
    seen=set();canonical_scripts=set();insignia=[];scripts=[];ignored=[];prefix=('res/vehicles/'+nation+'/'+vehicle+'/').casefold()
    for info in archive.infolist():
        name=info.filename.replace('\\','/');key=name.casefold()
        if name.startswith('/') or ':' in name or '..' in name.split('/') or key in seen:
            raise ValueError('输入包包含不安全或重复的路径：'+name)
        seen.add(key)
        if info.is_dir() or key=='meta.xml':continue
        if name in adapted:continue
        script_key=('res/'+key) if key.startswith('scripts/') else key
        if script_key.startswith('res/scripts/client/gui/mods/mod_insignia_') and script_key.endswith('.pyc'):
            if script_key in canonical_scripts:raise ValueError('徽记脚本的两种路径发生冲突：'+name)
            canonical_scripts.add(script_key)
            if info.file_size>65536:raise ValueError('徽记脚本过大，无法安全识别。')
            raw=archive.read(info);insignia.extend(parse_insignia(raw,nation,vehicle))
            scripts.append(dict(path=name,sha256=hashlib.sha256(raw).hexdigest(),adapter='insignia_slot'))
            continue
        if key.startswith(('res/vehicles/item_defs/','res/scripts/item_defs/vehicles/')):
            raise ValueError('输入覆盖了游戏车型定义，尚不能安全隔离：'+name)
        if key.startswith('res/gui/maps/vehicles/decals/'):
            raise ValueError('输入覆盖了游戏共享徽记贴图，直接复制会影响其他车辆，暂不能安全转换：'+name)
        if key.startswith('res/particles/'):
            raise ValueError('输入包含独立光效资源，暂不能安全保留其逐车行为：'+name)
        if not key.startswith(prefix):
            raise ValueError('输入含脚本、共享资源或其他车型，暂不能安全转换：'+name)
        if key.endswith('.psd'):
            ignored.append(dict(path=name,reason='设计源文件不参与游戏资源生成；原输入包保留。'))
            continue
        if not key.endswith(ALLOWED):
            raise ValueError('输入包含尚不支持的资源类型：'+name)
    bad=archive.testzip()
    if bad:raise ValueError('输入包 CRC 校验失败：'+bad)
    return insignia,scripts,ignored


def build(source,client,output_root,compiler=_compile27,catalog=None):
    """Build a conservative candidate; no game compatibility is implied."""
    source=Path(source).resolve();output_root=Path(output_root).resolve()
    report=inspect(source)
    if len(report['vehicles'])!=1:raise ValueError('每个输入包必须只包含一款标准车型。')
    nation,vehicle=report['vehicles'][0].split('/')
    manager=nullcontext(catalog) if catalog is not None else ClientCatalog(client).scan()
    with manager as catalog:
        if ClientCatalog(client).root!=catalog.root:raise ValueError('缓存客户端与所选客户端不一致。')
        if output_root.is_relative_to(catalog.root):raise ValueError('请将输出目录放在游戏目录以外。')
        definition='scripts/item_defs/vehicles/%s/%s.xml'%(DEFINITION_NATIONS.get(nation.casefold(),nation),vehicle)
        try:definition_root=parse(catalog.read(definition))
        except (OSError,KeyError,ValueError,ET.ParseError) as error:
            raise ValueError('客户端缺少或无法读取所选车型定义：'+str(error)) from error
        dual_mode=any('siege' in node.tag.casefold() for node in definition_root.iter())
        client_api=verify_client_api(catalog,require_composite=dual_mode,require_hangar=True)
        with zipfile.ZipFile(source) as archive:
            extras,ae_records,ae_source=analyse_ae(archive,nation,vehicle,catalog.root,compiler)
            insignia,script_records,ignored=_check_source(archive,nation,vehicle,extras)
            script_records+=ae_records
            source_entries={x.filename[4:].casefold():x for x in archive.infolist()
                            if not x.is_dir() and x.filename.casefold().startswith('res/')}
            prefix=('vehicles/'+nation+'/'+vehicle+'/').casefold()
            extra_models=[]
            for node in definition_root.iter('undamaged'):
                path=game_path(node.text)
                if (path and path.casefold().startswith(prefix) and path.casefold().endswith('.model')
                    and Path(path).stem.lower().split('_')[0] in ('chassis','hull','turret','gun')):
                    extra_models.append(path)
            has_crash=any('/crash/' in name or '/destroyed/' in name for name in source_entries)
            extra_destroyed=[]
            if has_crash:
                for node in definition_root.iter():
                    if node.tag not in ('destroyed','exploded'):continue
                    path=game_path(node.text)
                    if (path and path.casefold().startswith(prefix) and path.casefold().endswith('.model')
                        and Path(path).stem.lower().split('_')[0] in ('chassis','hull','turret','gun')):
                        extra_destroyed.append(path)
                if not extra_destroyed:
                    raise ValueError('输入有损毁资源，但客户端车型定义未找到对应模型，已停止转换。')
            spec=plan(source,catalog,nation,vehicle,report['sha256'],extra_models=extra_models,
                      extra_destroyed_models=extra_destroyed)
            if spec['diagnostics']:
                raise ValueError('资源依赖未能确认，已停止转换：\n'+'\n'.join(spec['diagnostics'][:12]))
            model_map={name.casefold():spec['mapping'][name.casefold()] for name in spec['resources']
                       if name.casefold().endswith('.model')}
            parts={Path(n).stem.lower().split('_')[0] for n in spec['root_models']}
            if not {'chassis','hull','turret','gun'}.issubset(parts):
                raise ValueError('缺少可选择的四个基本部件，不能安全转换。')
            # Only actual paths are remapped. XML is re-read in the output for
            # structural checks; binary references and game behavior remain untested.
            for name in spec['resources']:
                if not name.casefold().endswith(ALLOWED):
                    raise ValueError('依赖包含尚不支持的资源类型：'+name)
            output_root.mkdir(parents=True,exist_ok=True)
            folder=output_root/(source.stem[:72]+'_仅本车_待实测_'+uuid.uuid4().hex[:8])
            folder.mkdir(exist_ok=False)
            target=folder/(source.stem[:72]+'_仅本车_待实测.wotmod')
            token=token_for(report['sha256']);changed=0;texture_refs=0
            with tempfile.TemporaryDirectory(dir=folder) as work:
                script=Path(work)/'runtime.py';compiled=Path(work)/'runtime.pyc';temp=Path(work)/'candidate.building'
                template=(Path(__file__).parent/'game_runtime_template.py.txt').read_text('ascii')
                runtime=template.replace('__MODEL_MAP__',repr(model_map)).replace('__INSIGNIA__',repr(insignia)).replace('__TOKEN__',token)
                script.write_text(runtime,encoding='ascii');compiler(script,compiled,catalog.root)
                meta=ET.Element('root')
                for key,value in [('id','local.self_skin.'+token),('version','1.0'),('name','Own-vehicle skin pending game validation')]:
                    ET.SubElement(meta,key).text=value
                with zipfile.ZipFile(temp,'x',compression=zipfile.ZIP_STORED,allowZip64=False) as out:
                    out.writestr('meta.xml',ET.tostring(meta,encoding='utf-8',xml_declaration=True))
                    out.writestr('res/scripts/client/gui/mods/mod_self_skin_'+token+'.pyc',compiled.read_bytes())
                    for name,data in extras.items():out.writestr(name,data)
                    for name in spec['resources']:
                        info=source_entries.get(name.casefold())
                        data=archive.read(info) if info else catalog.read(name)
                        if name.casefold().endswith('.vt'):
                            lower=data.lower()
                            markers=(b'vehicles/',b'vehicles\\',b'v\x00e\x00h\x00i\x00c\x00l\x00e\x00s\x00')
                            if data[:8]!=bytes.fromhex('0bb00bb002000000') or any(m in lower for m in markers):
                                raise ValueError('VT 资源结构或内含路径未能确认：'+name)
                        if name.casefold().endswith(XML_EXT):
                            root=parse(data)
                            if name.casefold().endswith(('.visual','.visual_processed','.mfm')):
                                for node in root.iter():
                                    reference=game_path(node.text)
                                    if node.tag in ('Texture','texture') and reference and reference.casefold() in source_entries:
                                        texture_refs+=1
                            edited,count=rewrite_xml(root,spec['mapping']);changed+=count
                            for node in edited.iter():
                                old=game_path(node.text)
                                if old and old.casefold() in spec['mapping']:
                                    raise ValueError('仍有资源指向未隔离的路径，已停止转换：'+old)
                            data=serialize_xml(edited)
                        out.writestr('res/'+spec['mapping'][name.casefold()],data)
                if not changed or (not report['models'] and not texture_refs):
                    raise ValueError('没有找到与输入贴图匹配的模型引用，未生成可用候选包。')
                with zipfile.ZipFile(temp) as out:
                    if out.testzip() is not None:raise ValueError('候选包 CRC 校验失败。')
                    for item in out.infolist():
                        if item.compress_type!=zipfile.ZIP_STORED:raise ValueError('候选包包含不支持的压缩条目。')
                        if item.filename.lower().endswith(XML_EXT):parse(out.read(item))
                def baseline_read(name):
                    info=source_entries.get(name.casefold())
                    return archive.read(info)if info else catalog.read(name)
                geometry_audit=audit_package(temp,baseline_read,
                    {new.casefold():old for old,new in spec['mapping'].items()})
                if sha256(source)!=report['sha256']:raise ValueError('输入包在处理期间发生变化，未生成候选包。')
                (folder/'运行脚本.py').write_text(runtime,encoding='ascii')
                if ae_source:(folder/'AE挂载脚本.py').write_text(ae_source,encoding='ascii')
                os.replace(temp,target)
            outcome=dict(application_scope='self',adapter='ordinary_or_insignia',source=dict(path=str(source),sha256=report['sha256'],user_confirmed_baseline=False),
                artifact=dict(path=str(target),sha256=sha256(target),bytes=target.stat().st_size),
                client=dict(path=str(catalog.root),version=catalog.version,realm=catalog.realm,
                            paths_xml_sha256=sha256(catalog.root/'paths.xml'),version_xml_sha256=sha256(catalog.root/'version.xml'),
                            appearance_api=client_api),
                file_validation=dict(status='partial',zip_crc=True,zip_stored=True,xml_readback=True,
                                     client_override_order='not_tested',binary_dependencies='not_tested'),
                offline_validation=dict(status='partial',isolated_resources=len(spec['resources']),rewritten_xml_references=changed,
                                        rewritten_source_texture_references=texture_refs,binary_embedded_references='not_tested',
                                        engine_object_copy='not_tested',dual_mode=dual_mode,source_has_crash=has_crash,adapted_scripts=script_records,
                                        insignia_slots=len(insignia),ignored_design_files=ignored,**geometry_audit),
                whole_vehicle_loading=dict(status='not_tested'),in_game_tested=False,
                limitations=['逐车切换、车库与战斗、切车和 LOD、客户端模组兼容及游戏视觉效果均未验证。',
                             '脚本仅支持已识别的徽记登记及逐项匹配的 AE 挂载模板；未知脚本会拒绝转换。',
                             '仅基于所选客户端原版资源，不代表实际客户端及其他已安装模组覆盖关系。',
                             '不要同时启用原涂装与转换包；原包可能继续覆盖其他车辆。'])
            (folder/'验证记录.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
            return target,outcome
