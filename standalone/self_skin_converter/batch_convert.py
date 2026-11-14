"""Independent batch router; inputs stay read-only and no mod is installed."""
import argparse
import json
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from preflight import inspect,sha256
from client_catalog import ClientCatalog
from output_checks import check_output_directory
import builder
import uml_adapter

VERSION='1.0'
APP_NAME='涂装仅本车转换器 '+VERSION


def classify(path):
    row=inspect(path)
    with zipfile.ZipFile(path)as z:
        names=z.namelist()
        if uml_adapter.profile_names(names):row['package_type']='UML 配置包'
        elif any('/ae_import_'in n and n.endswith('/manifest.json')for n in names):row['package_type']='AE 动画脚本包'
        elif row['scripts']:row['package_type']='含脚本涂装（逐类识别）'
        else:row['package_type']='普通涂装'
    return row


def _expanded(paths,work):
    """Read inner wotmods only; documentation is never extracted or executed."""
    for number,value in enumerate(paths):
        source=Path(value).resolve()
        try:
            if source.suffix.lower()not in('.zip','.wotmod'):raise ValueError('请选择 .wotmod 或 ZIP 文件。')
            with zipfile.ZipFile(source)as z:
                inner=[i for i in z.infolist()if not i.is_dir()and i.filename.lower().endswith('.wotmod')]
                if source.suffix.lower()=='.wotmod'or not inner:
                    yield source,dict(path=str(source),sha256=sha256(source))
                    continue
                if len(inner)>128:raise ValueError('ZIP 内超过 128 个涂装包，请分批处理。')
                outer_hash=sha256(source)
                for index,info in enumerate(inner):
                    name=info.filename.replace('\\','/')
                    if name.startswith('/')or ':'in name or '..'in name.split('/'):raise ValueError('ZIP 内涂装路径无效。')
                    if info.file_size>2_000_000_000:raise ValueError('内部涂装包超过 2 GB，暂不支持。')
                    folder=Path(work)/('%03d_%03d'%(number,index));folder.mkdir()
                    file=folder/Path(name).name
                    with z.open(info)as inp,file.open('xb')as out:shutil.copyfileobj(inp,out)
                    yield file,dict(path=str(source),sha256=outer_hash,member=name,member_sha256=sha256(file))
        except (OSError,ValueError,zipfile.BadZipFile)as error:
            yield None,dict(path=str(source),error=str(error))


def analyse_many(paths):
    results=[]
    with tempfile.TemporaryDirectory(prefix='skin_inspect_')as work:
        for source,origin in _expanded(paths,work):
            if source is None:results.append(dict(origin,status='error'));continue
            try:
                item=classify(source);item['origin']=origin;item['path']=origin['path'];results.append(item)
            except Exception as error:results.append(dict(path=origin['path'],origin=origin,status='error',error=str(error)))
    return results


def convert_many(paths,client,output,progress=lambda *args:None,cancel=None,baseline_confirmed=False):
    cancel=cancel or threading.Event();results=[];catalog=None
    try:
        catalog=ClientCatalog(client)
        output=Path(output).resolve()
        if output.is_relative_to(catalog.root):raise ValueError('输出目录必须位于游戏目录以外。')
        output.mkdir(parents=True,exist_ok=True)
        check_output_directory(output,catalog.root)
        progress(0,len(paths),'读取所选客户端：'+catalog.realm+' '+catalog.version)
        catalog.scan()
        with tempfile.TemporaryDirectory(prefix='skin_convert_')as work:
            for index,(source,origin)in enumerate(_expanded(paths,work),1):
                display=Path(origin.get('member')or origin['path']).name
                if cancel.is_set():
                    results.append(dict(path=origin['path'],origin=origin,status='cancelled',error='已停止后续任务。'));continue
                progress(index,len(paths),display)
                if source is None:results.append(dict(origin,status='error'));continue
                try:
                    summary=classify(source)
                    with zipfile.ZipFile(source)as archive:is_uml=bool(uml_adapter.profile_names(archive.namelist()))
                    if is_uml:target,record=uml_adapter.build(source,catalog.root,output,catalog=catalog)
                    else:target,record=builder.build(source,catalog.root,output,catalog=catalog)
                    record['input_origin']=origin
                    record['source']['user_confirmed_baseline']=bool(baseline_confirmed)
                    record['converter_version']=VERSION
                    # Reports refer to the retained user input, including an
                    # inner-member identity if a temporary carrier was needed.
                    record['source']['path']=origin['path']
                    (target.parent/'验证记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                    (target.parent/'先读说明.txt').write_text('这是仅本车待实测包，未自动安装。\n'
                        +'先停用同款原涂装，只启用本份；同一车型的不同候选包分别测试。\n'
                        +'普通包、UML 和已适配脚本按各自方式处理，详见验证记录。UML 包仍需要原 UML 加载器。\n'
                        +'原输入保留。请核对车库、同型敌我车辆、切车、开镜、重生、残骸和 LOD；游戏效果未验证。\n',encoding='utf-8-sig')
                    results.append(dict(path=origin['path'],origin=origin,name=display,status='candidate',
                        package_type=summary['package_type'],vehicles=summary['vehicles'],target=str(target),record=record))
                except Exception as error:
                    results.append(dict(path=origin['path'],origin=origin,name=display,status='error',error=str(error)))
        report=Path(output)/('批次记录_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]+'.json')
        report.write_text(json.dumps(dict(converter_version=VERSION,application_scope='self',
            client=dict(path=str(catalog.root),version=catalog.version,realm=catalog.realm),results=results,
            in_game_tested=False,whole_vehicle_loading=dict(status='not_tested')),ensure_ascii=False,indent=2),encoding='utf-8')
        return results,report
    finally:
        if catalog:catalog.close()


def main():
    p=argparse.ArgumentParser(description='批量将涂装另存为仅本车待测包，不安装游戏资源。')
    p.add_argument('files',nargs='+',type=Path);p.add_argument('--client',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--inspect',action='store_true')
    args=p.parse_args()
    if args.inspect:print(json.dumps(analyse_many(args.files),ensure_ascii=False,indent=2));return
    if not args.client or not args.output:p.error('转换需要 --client 和 --output。')
    results,report=convert_many(args.files,args.client,args.output,progress=lambda n,total,name:print(name,flush=True))
    print('REPORT',report)
    print('CANDIDATES',sum(r['status']=='candidate'for r in results),'NOT_GENERATED',sum(r['status']!='candidate'for r in results))
    if any(r['status']=='error'for r in results):raise SystemExit(1)


if __name__=='__main__':main()
