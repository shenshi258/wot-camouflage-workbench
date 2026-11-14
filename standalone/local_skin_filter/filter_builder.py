"""Build a private VANILLA resource pack; never installs or edits any mod.

The input catalog reads only native .pkg files in the selected paths.xml. Mod
archives are inspected as ZIP entry lists, never imported or executed. This is
an experimental cosmetic selector, not an anti-cheat bypass or approval claim.
"""
import hashlib,json,os,re,subprocess,sys,tempfile,uuid,zipfile
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from client_catalog import ClientCatalog
from client_api import check as check_api
from resource_graph import game_path,parse
from relocation import rewrite_xml,serialize_xml
from package_audit import audit

XML=('.model','.visual','.visual_processed','.mfm')
ALLOWED=XML+('.dds','.vt','.primitives','.primitives_processed')
PRIVATE='vehicles/_local_skin_filter/'


def digest(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def vehicle_list(catalog):
    found={}
    for key,(_,name) in catalog.index.items():
        if not key.startswith('vehicles/')or '/normal/lod0/'not in key or not key.endswith('.model'):continue
        parts=name.split('/')
        if len(parts)<5:continue
        ident='/'.join(parts[1:3]).casefold()
        found.setdefault(ident,dict(key=ident,label=parts[2].replace('_',' ')+' ['+parts[1]+']'))
    return sorted(found.values(),key=lambda v:v['key'])


def scan_overrides(catalog, paths):
    """Return only actual stock-path replacements. Do not infer UML script scope."""
    known={v['key']for v in vehicle_list(catalog)};hits={};warnings=[];sources=[]
    for path in map(Path,paths):
        source=dict(path=str(path.resolve()),bytes=path.stat().st_size if path.is_file()else None)
        found=set();scripts=0;custom=set();shared=0
        def inspect(name):
            nonlocal scripts,shared
            name=game_path(name)
            if not name:return
            key=name.casefold()
            if key.startswith('scripts/')and key.endswith(('.py','.pyc','.pyd')):scripts+=1
            if key.startswith(('shaders/','vehicles/common/')):shared+=1
            parts=key.split('/')
            if len(parts)>3 and parts[0]=='vehicles':
                vehicle='/'.join(parts[1:3])
                if vehicle in known and key in catalog.index:found.add(vehicle)
                elif parts[1]not in('common','item_defs','_local_skin_filter'):custom.add(vehicle)
        if path.is_dir():
            for item in path.rglob('*'):
                if item.is_file():inspect(item.relative_to(path).as_posix())
        else:
            with zipfile.ZipFile(path)as archive:
                for item in archive.infolist():
                    if not item.is_dir():inspect(item.filename)
        for key in found:hits.setdefault(key,[]).append(str(path))
        source.update(vehicles=sorted(found),script_entries=scripts,custom_namespaces=sorted(custom),shared_entries=shared)
        sources.append(source)
        if scripts or custom or shared:
            warnings.append(path.name+'：含脚本／自有模型／共享资源；本版只保护识别到的原版模型路径，额外挂载不在范围内。')
    return dict(vehicles=hits,warnings=warnings,sources=sources)


def installed_inputs(client):
    root=Path(client);version=ET.parse(root/'paths.xml').getroot();paths=[]
    for node in version.findall('.//Paths/Path'):
        value=(node.text or '').strip().replace('\\','/')
        if value.startswith('./'):value=value[2:]
        if not value or value.startswith('/')or ':'in value or '..'in value.split('/'):continue
        path=(root/value).resolve()
        if not path.is_relative_to(root.resolve())or not path.exists():continue
        if node.get('mask')=='*.wotmod':paths.extend(sorted(path.rglob('*.wotmod')))
        elif 'res_mods'in path.parts:paths.append(path)
    return paths


def vanilla_plan(catalog, selected):
    """Follow every native model/LOD/material/texture edge for selected vehicles.

    Shader identifiers, collision and physics data remain native. All selected
    vehicle XML and referenced texture/material dependencies receive private
    paths, including textures stored outside the vehicle directory.
    """
    valid={v['key']for v in vehicle_list(catalog)}
    if not selected or not set(selected).issubset(valid):raise ValueError('请选择客户端中存在的车型。')
    resources={};queue=[];shaders=set();missing=[]
    def add(value,kind=None,owner='root'):
        name=game_path(value)
        if not name:raise ValueError('无效资源引用：'+owner)
        key=name.casefold()
        if key not in catalog.index:
            missing.append(owner+' → '+name);return
        actual=catalog.index[key][1]
        if key in resources:return
        if not key.endswith(ALLOWED):raise ValueError('尚未支持的原版资源：'+actual)
        resources[key]=actual
        if key.endswith(XML):queue.append(actual)
        if len(resources)>30000:raise ValueError('所选车型资源过多，请分批制作。')
    roots=[]
    for key,(_,name)in catalog.index.items():
        if key.endswith('.model')and any(key.startswith('vehicles/'+v+'/')for v in selected):
            roots.append(name);add(name)
    if not roots:raise ValueError('没有找到所选车型模型。')
    for vehicle in selected:
        parts={Path(n).stem.casefold().split('_')[0]for n in roots
               if n.casefold().startswith('vehicles/'+vehicle+'/')and '/normal/lod0/'in n.casefold()}
        if not {'chassis','hull','turret','gun'}.issubset(parts):raise ValueError('车型缺少四个原版部件：'+vehicle)
    while queue:
        name=queue.pop();raw=catalog.read(name)
        if len(raw)>32*1024*1024:raise ValueError('XML 资源过大：'+name)
        tree=parse(raw);lower=name.casefold()
        if lower.endswith(('.visual','.visual_processed')):
            suffix='.visual_processed'if lower.endswith('.visual_processed')else'.visual'
            stem=name[:-len(suffix)]
            add(stem+('.primitives_processed'if suffix=='.visual_processed'else'.primitives'),owner=name)
            if (stem+'.vt').casefold()in catalog.index:add(stem+'.vt',owner=name)
        for node in tree.iter():
            value=(node.text or '').strip()
            if not value or len(node):continue
            if node.tag=='parent':add(value if value.lower().endswith('.model')else value+'.model',owner=name)
            elif node.tag in('nodefullVisual','nodelessVisual'):
                stem=game_path(value)
                if not stem:raise ValueError('visual 引用无效：'+name)
                choices=[stem]if stem.casefold().endswith(('.visual','.visual_processed'))else[stem+'.visual_processed',stem+'.visual']
                add(next((p for p in choices if p.casefold()in catalog.index),choices[0]),owner=name)
            elif node.tag=='fx':
                shader=game_path(value)
                # Production WG clients ship compiled FXO branches, not .fx sources.
                compiled=[shader[:-3]+'.'+branch+'.dx11.fxo'for branch in('10','11')]if shader and shader.lower().endswith('.fx')else[]
                if not shader or (shader.casefold()not in catalog.index and not all(p.casefold()in catalog.index for p in compiled)):
                    missing.append(name+' → 着色器 '+value)
                else:shaders.add(shader)
            elif node.tag in('Texture','texture'):
                add(value,owner=name)
            elif value.casefold().endswith(ALLOWED):
                add(value,owner=name)
    if missing:raise ValueError('原版资源依赖不完整，停止生成：\n'+'\n'.join(missing[:12]))
    return dict(resources=resources,roots=sorted(roots),shaders=sorted(shaders))


def compile27(source,target,client):
    """Use the legitimate client's compiler in a separate offline helper process."""
    dll=Path(client)/'win64/python27.dll'
    if not dll.is_file():raise ValueError('客户端缺少 win64/python27.dll。')
    helper=r'''import ctypes,sys
d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1
d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p]
src,target=sys.argv[2:]
code="import marshal\ncode=compile(open(u%s,'rb').read(),'local_skin_filter.py','exec')\n"%ascii(src)
code+="open(u%s,'wb').write('\\x03\\xf3\\x0d\\x0a\\x00\\x00\\x00\\x00'+marshal.dumps(code))\n"%ascii(target)
sys.exit(bool(d.PyRun_SimpleString(code.encode('ascii'))))
'''
    run=subprocess.run([sys.executable,'-c',helper,str(dll),str(Path(source).resolve()),str(Path(target).resolve())],
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45,creationflags=0x08000000)
    if run.returncode or not Path(target).is_file():raise ValueError('游戏脚本编译失败：'+run.stdout.decode('utf-8','replace')[-800:])


def build(catalog,selected,output,inspection=None,compiler=compile27,progress=lambda s:None):
    selected=sorted(set(selected));output=Path(output).resolve()
    if output.is_relative_to(catalog.root):raise ValueError('请将输出目录放在游戏目录以外。')
    if catalog.realm not in('EU','NA','ASIA','SEA'):raise ValueError('本版仅为 Wargaming 欧服／美服／亚服准备。')
    progress('核对客户端外观接口…');api=check_api(catalog)
    progress('读取原版模型、LOD、材质和贴图…');plan=vanilla_plan(catalog,selected)
    token=hashlib.sha256((catalog.version+'|'+','.join(selected)+'|'+uuid.uuid4().hex).encode()).hexdigest()[:20]
    mapping={key:PRIVATE+token+'/'+name for key,name in plan['resources'].items()}
    models={key:mapping[key]for key in mapping if key.endswith('.model')}
    vehicles=[dict(v,var='car_'+hashlib.sha256(v['key'].encode()).hexdigest()[:16])for v in vehicle_list(catalog)if v['key']in selected]
    source=(Path(__file__).parent/'filter_runtime.py.txt').read_text('ascii')
    source=source.replace('__MODEL_PATHS__',ascii(models)).replace('__VEHICLES__',ascii(vehicles))
    folder=output/('本地涂装屏蔽_待实测_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+token[:8]);folder.mkdir(parents=True)
    target=folder/'local_skin_filter_1.0_pending.wotmod';manifest=[];changed=0
    try:
        with tempfile.TemporaryDirectory(dir=folder)as work:
            work=Path(work);script=work/'runtime.py';pyc=work/'runtime.pyc';temp=work/'building.wotmod'
            script.write_text(source,encoding='ascii');compiler(script,pyc,catalog.root)
            progress('生成独立原版资源保护包…')
            with zipfile.ZipFile(temp,'x',compression=zipfile.ZIP_STORED,allowZip64=False)as out:
                meta=ET.Element('root')
                for k,v in [('id','local.skin_filter'),('version','1.0'),('name','Local skin filter - pending game tests')]:ET.SubElement(meta,k).text=v
                out.writestr('meta.xml',ET.tostring(meta,encoding='utf-8',xml_declaration=True))
                out.writestr('res/scripts/client/gui/mods/mod_zz_local_skin_filter.pyc',pyc.read_bytes())
                for key,name in sorted(plan['resources'].items()):
                    data=catalog.read(name);before=hashlib.sha256(data).hexdigest()
                    if key.endswith('.vt')and(data[:8]!=bytes.fromhex('0bb00bb002000000')or any(p in data.lower()for p in(b'vehicles/',b'vehicles\\'))):
                        raise ValueError('VT 边车数据未能确认：'+name)
                    if key.endswith(XML):
                        tree,n=rewrite_xml(parse(data),mapping);changed+=n;data=serialize_xml(tree)
                        for node in tree.iter():
                            old=game_path(node.text)
                            if old and old.casefold()in mapping:raise ValueError('仍有原路径引用：'+old)
                    dest='res/'+mapping[key];out.writestr(dest,data)
                    manifest.append(dict(source=name,source_sha256=before,destination=dest,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
            progress('回读最终包并检查全部网格分组…')
            with zipfile.ZipFile(temp)as z:
                if z.testzip():raise ValueError('输出包 CRC 失败。')
                seen=set()
                for i in z.infolist():
                    if i.filename.casefold()in seen or i.compress_type!=zipfile.ZIP_STORED:raise ValueError('输出路径重复或存在压缩条目。')
                    seen.add(i.filename.casefold())
                for row in manifest:
                    if hashlib.sha256(z.read(row['destination'])).hexdigest()!=row['sha256']:raise ValueError('最终资源清单不一致。')
            meshes=audit(temp,catalog.read,{new.casefold():plan['resources'][old]for old,new in mapping.items()})
            os.replace(temp,target)
        (folder/'运行脚本.py').write_text(source,encoding='ascii')
        record=dict(tool='Local skin filter 1.0',artifact=dict(path=str(target),sha256=digest(target),bytes=target.stat().st_size),
          client=dict(path=str(catalog.root),realm=catalog.realm,version=catalog.version,
            actual_user_launch_confirmed=False,paths_xml_sha256=digest(catalog.root/'paths.xml'),
            version_xml_sha256=digest(catalog.root/'version.xml'),api=api),
          baseline=dict(source='native .pkg only; no mods/res_mods bytes used',user_confirmed_working=False,agent_in_game_observed=False),
          selected_vehicles=vehicles,inspection=inspection or {},
          file_validation=dict(status='partial',crc=True,stored_only=True,manifest_readback=True,xml_references_relocated=changed,
                               original_shader_identifiers=plan['shaders'],installed_override_order='not_tested'),
          offline_validation=dict(status='partial',**meshes,resources=len(manifest),model_paths=len(models),
                                  shaders='unchanged; engine execution not tested',rendering='not_tested'),
          whole_vehicle_loading=dict(status='not_tested'),in_game_tested=False,
          limits=['Normal stock resource-path overrides only; independent UML/third-party attachments are not removed.',
                 'Official outfit/style selection, collisions, spotting, visibility and inputs are not changed.',
                 'Changes apply at the next normal vehicle load. No live forced rebuild.',
                 'Requires separately installed ModsSettings API and ModsList API. No official approval or anti-cheat guarantee.',
                 'Client version/graphics branch, game appearance and other-mod compatibility require in-game testing.'])
        (folder/'验证记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'资源清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'使用说明.txt').write_text((Path(__file__).parent/'使用说明.txt').read_text('utf-8'),encoding='utf-8')
        return target,record
    except Exception as error:
        (folder/'未完成.txt').write_text('未生成可交付版本：'+str(error),encoding='utf-8')
        raise
