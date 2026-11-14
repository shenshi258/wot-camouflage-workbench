"""Build a read-only candidate dependency plan, not an installable mod."""
import zipfile
from resource_graph import game_path, parse
from relocation import make_mapping,token_for

MAX_XML=32*1024*1024


def plan(source,catalog,nation,vehicle,source_hash,extra_models=(),extra_destroyed_models=()):
    """Resolve normal, destroyed, visual and LOD parent links for one vehicle.

    Client resources are only candidates: mod overrides, binary embedded
    references, LOD transitions and game loading remain unverified.
    """
    if not catalog.index:raise ValueError('请先扫描用户选择的客户端。')
    prefix=('vehicles/'+nation+'/'+vehicle+'/').casefold()
    with zipfile.ZipFile(source) as archive:
        entries={i.filename.casefold():i for i in archive.infolist() if not i.is_dir()}
        owned={key[4:]:info.filename[4:] for key,info in entries.items()
               if key.startswith('res/'+prefix) and not key.endswith('.psd')}
        if not owned:raise ValueError('输入包没有所选车型的资源。')
        roots={x.casefold():x for x in catalog.vehicle_models(nation,vehicle)}
        for key,name in owned.items():
            if key.endswith('.model') and '/normal/lod0/' in key:roots[key]=name
        for name in extra_models:
            candidate=game_path(name)
            if not candidate or not candidate.casefold().startswith(prefix) or not candidate.casefold().endswith('.model'):
                raise ValueError('车型定义引用了不安全或不属于本车的模型。')
            if candidate.casefold() not in owned and candidate.casefold() not in catalog.index:
                raise ValueError('车型定义引用的模型未找到：'+candidate)
            roots[candidate.casefold()]=candidate
        if not roots:raise ValueError('没有找到该车型的普通或风格模型。')
        staged=dict(owned);diagnostics=[];queue=[('model',value) for value in roots.values()];visited=set()
        # Source-owned crash and track model references need the same dependency
        # audit as normal models; they are not considered normal model roots.
        queue.extend(('model',name) for key,name in owned.items() if key.endswith('.model'))
        for value in extra_destroyed_models:
            name=game_path(value)
            if not name or not name.casefold().startswith(prefix) or not name.casefold().endswith('.model'):
                raise ValueError('损毁模型引用不安全或不属于本车。')
            if name.casefold() not in owned and name.casefold() not in catalog.index:
                raise ValueError('车型定义中的损毁模型未找到：'+name)
            queue.append(('model',name))

        def exists(name):return ('res/'+name.casefold()) in entries or name.casefold() in catalog.index
        def read(name):
            item=entries.get('res/'+name.casefold())
            if item:
                if item.file_size>MAX_XML:raise ValueError('XML 模型资源过大：'+name)
                return archive.read(item)
            path,entry=catalog.index[name.casefold()]
            if path not in catalog.archives:catalog.archives[path]=zipfile.ZipFile(path)
            info=catalog.archives[path].getinfo(entry)
            if info.file_size>MAX_XML:raise ValueError('XML 模型资源过大：'+name)
            return catalog.archives[path].read(info)
        def include(kind,value,from_name):
            name=game_path(value)
            if not name:diagnostics.append('无效引用：'+from_name);return
            if not name.casefold().startswith(prefix):
                diagnostics.append('跨车型或共享资源未纳入：'+name);return
            if not exists(name):diagnostics.append('未找到依赖：'+name);return
            staged.setdefault(name.casefold(),name)
            if kind in ('model','visual','material'):queue.append((kind,name))

        while queue:
            kind,name=queue.pop()
            key=name.casefold()
            if key in visited:continue
            visited.add(key)
            if len(visited)>10000:raise ValueError('模型依赖数量过多，已中止规划。')
            staged.setdefault(key,name)
            if key in catalog.collisions and ('res/'+key) not in entries:
                diagnostics.append('客户端中存在同名资源，优先级需核对：'+name)
            try:root=parse(read(name))
            except Exception as error:
                diagnostics.append('无法读取：%s（%s）'%(name,str(error)[:160]));continue
            if kind=='model':
                for node in root.iter():
                    value=(node.text or '').strip()
                    if not value:continue
                    if node.tag=='parent':include('model',value if value.lower().endswith('.model') else value+'.model',name)
                    elif node.tag in ('nodefullVisual','nodelessVisual'):
                        stem=game_path(value)
                        if not stem:diagnostics.append('无效 visual 引用：'+name);continue
                        if stem.lower().endswith(('.visual','.visual_processed')):visual=stem
                        else:
                            choices=[stem+'.visual_processed',stem+'.visual']
                            visual=next((v for v in choices if exists(v)),choices[0])
                        include('visual',visual,name)
            else:
                suffix='.visual_processed' if key.endswith('.visual_processed') else '.visual'
                if kind=='visual':
                    primitive=name[:-len(suffix)]+('.primitives_processed' if suffix=='.visual_processed' else '.primitives')
                    include('binary',primitive,name)
                    # Some client visuals have an adjacent VT sidecar.
                    vt=name[:-len(suffix)]+'.vt'
                    if exists(vt):include('binary',vt,name)
                for node in root.iter():
                    value=(node.text or '').strip()
                    if node.tag=='material' and value.lower().endswith('.mfm'):
                        material=game_path(value)
                        if material and (material.casefold() in owned or material.casefold().startswith(prefix)):
                            include('material',material,name)
                    if node.tag in ('Texture','texture'):
                        texture=game_path(value)
                        if not texture and value:
                            diagnostics.append('无效贴图引用：'+name)
                        elif texture and texture.casefold().endswith('.psd'):
                            diagnostics.append('游戏模型引用了不支持直接处理的 PSD：'+texture)
                        elif texture and texture.casefold() in owned:
                            staged.setdefault(texture.casefold(),texture)
                        elif texture and not exists(texture):
                            diagnostics.append('未找到贴图（其他模组尚未检查）：'+texture)
        mapping=make_mapping(staged.values(),token_for(source_hash))
        return dict(root_models=sorted(roots.values()),resources=sorted(staged.values()),
                    mapping=mapping,diagnostics=sorted(set(diagnostics)),
                    status='planning_only',whole_vehicle_loading='not_tested')
