"""Combine compatible maker projects by rebuilding from a shared original.

This does not execute input scripts or treat an archive union as a merge.
"""
import copy
import zipfile
from pathlib import Path
from . import light_effects as engine, light_recovery, light_embedded, light_recipe
from .common import write_json


def merge_projects(packages, work, log=lambda s: None):
    paths=[Path(p).resolve() for p in packages]
    if len(paths)<2 or len({str(p).casefold() for p in paths})!=len(paths):
        raise ValueError('请选择至少两个不同的灯效成品包。')
    projects=[];inputs=[]
    for index,path in enumerate(paths):
        log('核对第 %d/%d 个成品包与内嵌工程……'%(index+1,len(paths)))
        before=engine.digest(path)
        with zipfile.ZipFile(path) as z:
            engine.check_archive(z)
            names=light_recovery.manifests(z.namelist())
            if len(names)!=1:raise ValueError('每个包必须恰有一份本制作器的灯效清单：'+path.name)
            manifest=light_recovery.read_manifest(z,names[0])
            if light_embedded.metadata(names[0],manifest) is None:
                raise ValueError('此包没有内嵌可恢复工程，不能安全合并：'+path.name)
            folder=Path(work)/('input_%03d'%index);folder.mkdir(parents=True,exist_ok=True)
            project=light_embedded.restore(z,names[0],manifest,folder,log,0)
        if engine.digest(path)!=before:raise ValueError('读取期间输入包发生变化：'+path.name)
        if project.get('recovery') or any(x.get('overlay_body') or x.get('recovered_model') for x in project['lights']):
            raise ValueError('成品恢复工程或框选灯效尚不能安全合并：'+path.name)
        selected={x['id'] for x in project['lights'] if x.get('selected')}
        if not selected or selected!=set(manifest.get('selected_ids',[])) or project['source_sha256']!=manifest.get('source_sha256'):
            raise ValueError('内嵌工程与成品清单不一致：'+path.name)
        projects.append(project);inputs.append(dict(path=str(path),sha256=before,selected=len(selected)))
    source=projects[0]['source_sha256']
    if any(p['source_sha256']!=source for p in projects):
        raise ValueError('这些包的原始涂装不同；暂不能安全合并。')
    base=projects[0]
    identities={x['id']:x for x in base['lights']}
    signatures={key:engine.geometry_digest(x) for key,x in identities.items() if x['supported']}
    chosen={};vehicles=set()
    for project in projects:
        current={x['id']:x for x in project['lights']}
        if set(current)!=set(identities) or {k:engine.geometry_digest(x) for k,x in current.items() if x['supported']}!=signatures:
            raise ValueError('输入包的灯面或原始网格不一致，已停止合并。')
        for light in project['lights']:
            if not light.get('selected'):continue
            if not light.get('supported'):raise ValueError('选中灯面不受支持。')
            vehicles.add((light['nation'],light['vehicle']))
            recipe=copy.deepcopy(engine.override_recipe(light) or project['recipe'])
            effective=light_recipe.validate_config(recipe).copy();effective.pop('raw',None)
            if light['id'] in chosen and chosen[light['id']][1]!=effective:
                raise ValueError('同一灯面在不同包中使用不同效果，请先调整：'+str(light.get('material',light['id'])))
            chosen[light['id']]=(recipe,effective)
    if len(vehicles)!=1:raise ValueError('只支持合并同一辆车的灯效。')
    for light in base['lights']:
        light['selected']=light['id'] in chosen
        if light['selected']:light['配方']=copy.deepcopy(chosen[light['id']][0])
        else:light.pop('配方',None)
    base['baseline_user_confirmed']=False
    base.pop('embedded_restore',None)
    return base,dict(inputs=inputs,shared_original_sha256=source,selected_lights=len(chosen),vehicle=list(vehicles)[0])


def build(packages,client,output_dir,work,title,baseline=False,log=lambda s:None):
    project,info=merge_projects(packages,work,log)
    project['baseline_user_confirmed']=bool(baseline)
    target,report=engine.build(project,client,output_dir,title,log,embed_recoverable=True)
    report['merge']=info
    report['limitations'].append('合并按内嵌工程重建；成品包中未记录的手工改动不会被合并。')
    write_json(target.parent/'验证记录.json',report)
    return target,report,None,None
