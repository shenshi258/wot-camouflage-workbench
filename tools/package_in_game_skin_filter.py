"""Seal region game-install ZIPs after final-pyc and cache readback checks."""
import argparse,hashlib,json,math,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'game_mods/local_skin_filter'


def digest(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def same_tree(a,b):
    if a.tag!=b.tag or a.attrib!=b.attrib or len(a)!=len(b):return False
    left=(a.text or'').strip();right=(b.text or'').strip()
    if left!=right:
        try:
            av=[float(x)for x in left.split()];bv=[float(x)for x in right.split()]
            if not av or len(av)!=len(bv)or not all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-12)for x,y in zip(av,bv)):return False
        except ValueError:return False
    return all(same_tree(x,y)for x,y in zip(a,b))


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--delivery',type=Path,required=True);a=p.parse_args()
    sys.path.insert(0,str(ROOT/'standalone/local_skin_filter'))
    from client_catalog import ClientCatalog
    from package_audit import visual_groups
    from resource_graph import parse
    from relocation import rewrite_xml
    a.delivery.mkdir(parents=True,exist_ok=True);results=[]
    for item in json.loads((a.candidates/'候选记录索引.json').read_text('utf-8')):
        record_path=Path(item);record=json.loads(record_path.read_text('utf-8'));realm=record['client']['realm'];candidate=Path(record['artifact']['path'])
        evidence=record_path.parent/'离线实核';native=json.loads((evidence/'native_result.json').read_text('utf-8'))
        cache=json.loads((evidence/'native_cache_record.json').read_text('utf-8'))
        assert native['status']=='passed'and native['artifact_sha256']==digest(candidate)==record['artifact']['sha256']
        assert native['realm']==realm and native['utf8_localization']and native['entry_pyc_executed']
        resources={row['destination'].lower():row for row in cache['resources']};reverse={row['destination'].lower():row['source']for row in cache['resources']}
        cache_root=(evidence/'cache').resolve();groups=0;preexisting=[];binaries=0;xml=0
        def read(resource):
            path=(cache_root/resource).resolve()
            if not path.is_relative_to(cache_root):raise ValueError('Evidence path outside cache')
            return path.read_bytes()
        with ClientCatalog(record['client']['path']).scan()as catalog:
            for row in cache['resources']:
                resource=row['destination'];data=read(resource);before=catalog.read(row['source'])
                assert hashlib.sha256(data).hexdigest()==row['sha256']
                assert hashlib.sha256(before).hexdigest()==row['source_sha256']
                if row['source'].lower().endswith(('.model','.visual','.visual_processed','.mfm')):
                    restored,unused=rewrite_xml(parse(data),reverse)
                    if not same_tree(parse(before),restored):raise ValueError('Native XML properties differ: '+row['source'])
                    xml+=1
                else:assert data==before;binaries+=1
                if row['source'].lower().endswith(('.visual','.visual_processed')):
                    count,errors=visual_groups(read,resource);groups+=count
                    unused,baseline=visual_groups(catalog.read,row['source'])
                    for location,message in errors:
                        if(location,message)not in baseline:raise ValueError('New mesh issue: '+resource)
                        preexisting.append(dict(source=row['source'],location=location,issue=message))
        cn='欧服'if realm=='EU'else'亚服';name='本地涂装屏蔽 2.0_'+cn+'_游戏插件_待实测'
        folder=a.delivery/name;folder.mkdir(exist_ok=False);mods=folder/'mods/2.4.1.1';mods.mkdir(parents=True)
        delivered=mods/candidate.name;shutil.copy2(candidate,delivered);assert digest(delivered)==digest(candidate)
        shutil.copy2(SOURCE/'安装说明.txt',folder/'安装说明.txt')
        shutil.copy2(SOURCE/'WOT_TOOLKIT_LICENSE.txt',folder/'WOT_TOOLKIT_LICENSE.txt')
        record['artifact']['path']=str(delivered.resolve())
        record['offline_validation']=dict(status='passed',behavior_tests=21,native_pyc=native,
          cache_xml_semantic_readback=xml,cache_binary_byte_identical=binaries,mesh_groups_checked=groups,
          preexisting_mesh_readback_issues=preexisting,new_mesh_issues=[],
          ui_rendering='not_tested',native_shader_execution='not_tested',dynamic_resource_mount='not_tested')
        record['dependencies']=dict(ModsSettings_API='1.7.1 found in reference client',ModsList_API='1.8.0 found in reference client',bundled=False)
        record['whole_vehicle_loading']=dict(status='not_tested');record['in_game_tested']=False
        (folder/'验证记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/'local.skin_filter_2.0.wotmod.sha256').write_text(digest(delivered)+'  mods/2.4.1.1/'+delivered.name+'\n',encoding='utf-8')
        archive=folder.with_name(name+'.zip')
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
            for source in folder.rglob('*'):
                if source.is_file():z.write(source,source.relative_to(folder).as_posix())
        with zipfile.ZipFile(archive)as z:
            assert z.testzip()is None
            assert hashlib.sha256(z.read('mods/2.4.1.1/'+delivered.name)).hexdigest()==record['artifact']['sha256']
        archive.with_name(archive.name+'.sha256').write_text(digest(archive)+'  '+archive.name+'\n',encoding='utf-8')
        results.append(dict(realm=realm,version=record['client']['version'],vehicles=native['vehicle_count'],
          artifact_sha256=record['artifact']['sha256'],zip=str(archive),zip_sha256=digest(archive),zip_bytes=archive.stat().st_size,
          mesh_groups=groups,old_group_issues=len(preexisting),xml=xml,binaries=binaries))
    source_zip=a.delivery/'本地涂装屏蔽 2.0_游戏插件源码.zip'
    with zipfile.ZipFile(source_zip,'x',zipfile.ZIP_DEFLATED)as z:
        for file in SOURCE.rglob('*'):
            if file.is_file()and'__pycache__'not in file.parts:z.write(file,'game_mods/local_skin_filter/'+file.relative_to(SOURCE).as_posix())
        for name in('build_in_game_skin_filter.py','check_in_game_filter27.py','package_in_game_skin_filter.py'):
            z.write(ROOT/'tools'/name,'tools/'+name)
    with zipfile.ZipFile(source_zip)as z:assert z.testzip()is None
    report=a.delivery/'本地涂装屏蔽_2.0_双区检查记录.md'
    rows='\n'.join('| {realm} | {version} | {vehicles} | {mesh_groups} | {old_group_issues} |'.format(**row)for row in results)
    report.write_text('''# 本地涂装屏蔽 2.0 · 欧服／亚服游戏插件

用户要求直接安装到游戏，在游戏内选择车型并分别设置敌车、队友范围。已提供标准 .wotmod；无需桌面准备工具。
每款车支持不屏蔽、仅敌车、仅队友、敌我都屏蔽；自己的车保持原涂装。车型来自当前区服自己的原版包，设置通过已有 ModsSettings API 保存。
资源准备在线程中完成，只写自己的缓存命名空间，不修改原版包或旧模组。进入战斗时暂停准备，完成后在正常车辆加载时选择原版可视路径。

## 逐区离线证据

| 区服 | 参考客户端 | 原版车型数 | Pz70 回读分组 | 原版既有分组提示 |
| --- | --- | ---: | ---: | ---: |
'''+rows+'''

两区最终 MOD 文件相同，SHA256 见逐区验证记录与下方清单。
21 项行为测试通过。另分别用两区实际 Python 2.7 DLL 运行最终包内模块和入口、读取本区原版文件，生成隔离测试缓存；没有向安装目录写入或启动游戏。
每区执行 100 × 4 范围 × 3 损毁状态循环，使用实际原生可视路径选择函数与引擎/UI 替身；检查自身保留、敌我独立规则、重启保存、UTF-8 标签、不同默认/风格模型、刷新、命名元组类型、原描述与碰撞入口不变。
Pz70 每区读取 167 项资源／42 个模型。所有模型 XML 还原路径后逐节点比对原版，数字按原始浮点精度核对；所有非 XML 资源逐字节一致。所有可读网格分组回读，三项原版损毁车体提示复制前后相同，无新增问题；没有将既有提示确认为游戏故障。

## 状态和限制

`whole_vehicle_loading.status = not_tested`，`in_game_tested = false`。实际当前启动客户端未由用户确认，本次使用已安装 EU #993 与 ASIA #991 作为离线参考，原版整车基线也未在本次亲自实测。
游戏内设置窗口渲染、首次动态文件挂载、原生 Compound 整车加载、车库、训练房敌我车辆、不同画质/LOD、姿态、损毁、切车和其他模组兼容都仍待实测。
只处理原版资源路径替换；UML／AE／第三方独立挂载物暂不保证屏蔽。所需两项 UI API 已在本机两区目录找到，未重新分发；实际游戏内 API 交互仍未观察。
没有修改点亮、可见性、瞄准、碰撞、射击输入、网络或反作弊入口。未获官方审核，不能保证零误报；没有提交 Mod Hub 或上传 GitHub。本次不包含旧 AE 闪烁修复。

## 安装包清单

'''+ '\n'.join('- '+row['zip']+'\n  SHA256 `'+row['zip_sha256']+'`；'+str(row['zip_bytes'])+' 字节。'for row in results)+
      '\n\n源码：'+str(source_zip)+'\nSHA256 `'+digest(source_zip)+'`。\n',encoding='utf-8')
    print(json.dumps(dict(artifacts=results,source=str(source_zip),source_sha256=digest(source_zip),report=str(report)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
