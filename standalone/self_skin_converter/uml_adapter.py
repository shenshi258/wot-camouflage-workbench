"""Constrain UML profile selection while retaining its animation and rig data."""
import json
import re
import uuid
import zipfile
from contextlib import nullcontext
from pathlib import Path
import xml.etree.ElementTree as ET
from client_catalog import ClientCatalog
from preflight import inspect,sha256
from resource_graph import inspect_references
from package_audit import audit as audit_package

PROFILE=re.compile(r'^res/scripts/client/mods/umlprofiles/[^/]+\.xml$',re.I)
IDENTITY=re.compile(r'^res/vehicles/([^/]+)/([^/]+)/',re.I)


def profile_names(names):
    return [n for n in names if PROFILE.fullmatch(n.replace('\\','/'))]


def _canonical(node,skip_npc=False):
    return (node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),
            tuple(_canonical(child,skip_npc) for child in node if not(skip_npc and child.tag=='swapNPC')))


def restrict(raw):
    if len(raw)>2_000_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('UML 配置过大或含不支持的声明。')
    # Existing profiles sometimes contain invalid "--" in comments. The
    # semantic XML, including all model/animation/physics values, is retained.
    cleaned=re.sub(rb'<!--.*?-->',b'',raw,flags=re.S)
    root=ET.fromstring(cleaned);models=root.find('models')
    if models is None or not len(models):raise ValueError('UML 配置中没有模型方案。')
    before=_canonical(root,True);changes=[]
    for node in models:
        flags=node.findall('swapNPC')
        if len(flags)>1:raise ValueError('UML 方案的 swapNPC 重复，无法确认作用范围。')
        flag=flags[0] if flags else ET.SubElement(node,'swapNPC')
        old=(flag.text or '').strip();flag.text='False'
        changes.append(dict(profile=node.tag,old_swapNPC=old,new_swapNPC='False',
                            enabled=(node.findtext('enabled')or'').strip(),
                            whitelist_unchanged=True))
    if _canonical(root,True)!=before:raise ValueError('UML 非作用范围参数发生变化，已停止转换。')
    return ET.tostring(root,encoding='utf-8',xml_declaration=True),changes


def build(source,client,output_root,catalog=None):
    source=Path(source).resolve();before=sha256(source);summary=inspect(source)
    manager=nullcontext(catalog)if catalog is not None else ClientCatalog(client).scan()
    with manager as catalog:
        output_root=Path(output_root).resolve()
        if output_root.is_relative_to(catalog.root):raise ValueError('输出目录必须位于游戏目录以外。')
        for identity in summary['vehicles']:
            # A profile flag cannot isolate a simultaneous replacement of stock
            # model/texture paths. Do not label such a mixed package converted.
            if any(name.startswith(('vehicles/'+identity+'/').casefold())for name in catalog.index):
                raise ValueError('UML 包同时覆盖了原车公共目录，需要专门适配，未生成：'+identity)
        with zipfile.ZipFile(source)as archive:
            names=profile_names(archive.namelist())
            if not names:raise ValueError('未找到 UML 配置。')
            changes={};records=[]
            for info in archive.infolist():
                name=info.filename.replace('\\','/')
                if info.is_dir()or name.lower()=='meta.xml':continue
                if name in names:
                    changes[name],rows=restrict(archive.read(info))
                    records.extend(dict(file=name,**row)for row in rows)
                elif name.startswith('res/vehicles/'):
                    identity=IDENTITY.match(name)
                    if not identity or identity[1].casefold()in('common','item_defs')or identity[2].casefold()in('common','shared'):
                        raise ValueError('UML 包含原车定义或共享覆盖，需专门适配：'+name)
                    if name.lower().endswith(('.py','.pyc','.pyd','.dll')):
                        raise ValueError('UML 包内含未识别脚本，需专门适配：'+name)
                else:raise ValueError('UML 包含未能确认范围的脚本或共享覆盖：'+name)
            graph=inspect_references(source)
            def available(name):
                key=name.casefold()
                if key in catalog.index:return True
                # Production clients ship compiled effect branches, not the
                # authoring .fx source named by model materials.
                return key.endswith('.fx')and all(key[:-3]+'.'+branch+'.dx11.fxo'in catalog.index for branch in('10','11'))
            missing=[r['target']for r in graph['references']if r['availability']!='input_package'and not available(r['target'])]
            if graph['issues']:
                raise ValueError('UML 资源无法读取：'+str(graph['issues'][:6]))
            if archive.testzip():raise ValueError('UML 输入包 CRC 校验失败。')
            folder=output_root/(source.stem[:72]+'_UML仅本车_待实测_'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
            target=folder/(source.stem[:72]+'_UML仅本车_待实测.wotmod');staged=target.with_suffix('.building')
            with zipfile.ZipFile(staged,'x',zipfile.ZIP_STORED,allowZip64=False)as out:
                for info in archive.infolist():
                    if not info.is_dir():out.writestr(info.filename,changes.get(info.filename,archive.read(info)))
            with zipfile.ZipFile(staged)as out:
                if out.testzip():raise ValueError('UML 输出包 CRC 校验失败。')
                for name in out.namelist():
                    if name not in changes and out.read(name)!=archive.read(name):raise ValueError('UML 非配置资源发生变化。')
            source_names={n.removeprefix('res/').casefold():n for n in archive.namelist()}
            def baseline_read(name):
                return archive.read(source_names[name.casefold()])if name.casefold()in source_names else catalog.read(name)
            geometry_audit=audit_package(staged,baseline_read)
            if sha256(source)!=before:raise ValueError('输入包在处理时发生变化。')
            staged.rename(target)
        record=dict(application_scope='self',adapter='uml_swapNPC',
            source=dict(path=str(source),sha256=before,user_confirmed_baseline=False),
            artifact=dict(path=str(target),sha256=sha256(target),bytes=target.stat().st_size),
            client=dict(path=str(catalog.root),version=catalog.version,realm=catalog.realm),
            uml_profiles=records,requires='matching UML loader already supplied by the user; not included or installed',
            file_validation=dict(status='partial',zip_crc=True,zip_stored=True,non_profile_resources_byte_identical=True,
                preexisting_missing_dependencies=sorted(set(missing)),new_missing_dependencies=[]),
            offline_validation=dict(status='partial',adapter='uml_swapNPC',disabled_profiles=sum(x['enabled'].casefold()in('false','0')for x in records),**geometry_audit),
            whole_vehicle_loading=dict(status='not_tested'),in_game_tested=False,
            limitations=['需要与实际区服和版本匹配的原 UML 加载器；本工具不替换加载器。',
                '方案启用状态和白名单保持原样；原为关闭的方案不会自动开启。','仅改配置作用范围，游戏内效果未实测。'])
        (folder/'验证记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return target,record
