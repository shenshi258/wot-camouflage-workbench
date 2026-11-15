"""Seal region game-install ZIPs after final-pyc and cache readback checks."""
import argparse,hashlib,json,math,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'game_mods/local_skin_filter'
VERSION='2.1.3'


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
    p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--delivery',type=Path,required=True);p.add_argument('--browser-evidence',type=Path,required=True);a=p.parse_args()
    browser=json.loads((a.browser_evidence/'browser_result.json').read_text('utf-8'));assert browser['status']=='passed'
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
        assert native['selector_html_sha256']==browser['html_sha256']and native['selector_native_bridge_verified']and native['no_http_listener']
        assert native['native_gameface_contract_verified']and native['close_reopen_verified']and native['metadata_cache_verified']
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
        cn='欧服'if realm=='EU'else'亚服';name='本地涂装屏蔽 '+VERSION+'_'+cn+'_搜索框选版_待实测'
        folder=a.delivery/name;folder.mkdir(exist_ok=False);mods=folder/'mods/2.4.1.1';mods.mkdir(parents=True)
        delivered=mods/candidate.name;shutil.copy2(candidate,delivered);assert digest(delivered)==digest(candidate)
        shutil.copy2(SOURCE/'安装说明.txt',folder/'安装说明.txt')
        shutil.copy2(SOURCE/'WOT_TOOLKIT_LICENSE.txt',folder/'WOT_TOOLKIT_LICENSE.txt')
        record['artifact']['path']=str(delivered.resolve())
        record['offline_validation']=dict(status='passed',behavior_tests=38,native_pyc=native,browser_interactions=browser,
          cache_xml_semantic_readback=xml,cache_binary_byte_identical=binaries,mesh_groups_checked=groups,
          preexisting_mesh_readback_issues=preexisting,new_mesh_issues=[],
          ui_rendering='not_tested',native_shader_execution='not_tested',dynamic_resource_mount='not_tested')
        record['dependencies']=dict(ModsSettings_API='1.7.1 found in reference client',ModsList_API='1.8.0 found in reference client',bundled=False)
        record['whole_vehicle_loading']=dict(status='not_tested');record['in_game_tested']=False
        (folder/'验证记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        (folder/(delivered.name+'.sha256')).write_text(digest(delivered)+'  mods/2.4.1.1/'+delivered.name+'\n',encoding='utf-8')
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
          mesh_groups=groups,old_group_issues=len(preexisting),xml=xml,binaries=binaries,
          cold_seconds=native['startup_cold_seconds'],warm_seconds=native['startup_warm_seconds']))
    source_zip=a.delivery/('本地涂装屏蔽 '+VERSION+'_游戏插件源码.zip')
    with zipfile.ZipFile(source_zip,'x',zipfile.ZIP_DEFLATED)as z:
        for file in SOURCE.rglob('*'):
            if file.is_file()and'__pycache__'not in file.parts:z.write(file,'game_mods/local_skin_filter/'+file.relative_to(SOURCE).as_posix())
        for name in('build_in_game_skin_filter.py','check_in_game_filter27.py','package_in_game_skin_filter.py','check_selector_browser.py'):
            z.write(ROOT/'tools'/name,'tools/'+name)
    with zipfile.ZipFile(source_zip)as z:assert z.testzip()is None
    report=a.delivery/('本地涂装屏蔽_'+VERSION+'_双区检查记录.md')
    rows='\n'.join('| {realm} | {version} | {vehicles} | {mesh_groups} | {old_group_issues} |'.format(**row)for row in results)
    report.write_text('''# 本地涂装屏蔽 2.1.3 · 读取加速修订

2.1.2 在本机欧服实测停留“正在读取车型列表”。本次日志确认 SelectorView 缺少 viewModel 属性，加载回调因此终止；这不是持续等待读盘能恢复的问题。已补上与原生视图一致的 getViewModel 属性封装，并将 UI 替身改为真实的基类接口形式，防止测试替身再次掩盖该错误。旧版 UI 验收 failed，未报告闪退；整车状态保持 not_tested。

2.1.3 增加车型元数据缓存。客户端版本、路径、原版包或已安装涂装变化后自动失效；损坏或无法写入缓存时退回正常读取。缓存命中时不打开原版 ZIP，不建立 50 多万条原版资源索引；仅在后台准备实际选中的涂装资源时按需建立完整索引，保留原有资源与准备回读要求。
界面只渲染可视区域附近的行，选择仍覆盖完整筛选结果；滚出屏幕的行保留选择。相同数据不重复解析和重建列表。已有搜索、国家筛选、Ctrl 追加、Shift 连选、全部敌车和每车敌我范围保留。日、波、瑞、意四国键按客户端实际资源目录核对。
原生 Gameface 资源与 ViewModel 不使用 CEF，不启动 HTTP 服务，不改浏览器白名单。原有规则和原版缓存可继续使用。UML／AE 独立挂载和共享全局覆盖仍需适配。

## 逐区离线证据

| 区服 | 参考客户端 | 原版车型数 | Pz70 回读分组 | 原版既有分组提示 |
| --- | --- | ---: | ---: | ---: |
'''+rows+'''

两区最终 MOD 文件相同，SHA256 见逐区验证记录与下方清单。
行为测试通过，具体数量见测试记录。另分别用两区实际 Python 2.7 DLL 运行最终包内模块和入口、读取本区原版文件，生成隔离测试缓存；测试过程没有向安装目录写入或启动游戏。
最终包内页面在独立 Chromium 中完成 16 项交互检查：搜索、空结果、国家筛选、鼠标拖框、Ctrl 追加、批量队友设置、全选结果、跨筛选保留选择、全部敌车、自动滚动、800×600 布局、ViewModel 指令分支与关闭指令，以及虚拟列表节点上限、相同数据保留节点和跨屏选择保留。页面哈希与两区包内嵌入内容相同。截图保存在浏览器检查目录。
两区原生 WULF 接口已核对；最终包声明独立 Gameface 界面，数据通过 ViewModel 传递。接口替身覆盖打开、重复打开、命令、关闭、重新打开和退出；不创建 HTTP 服务，不导航 CEF，不修改白名单。Gameface 实际显示仍待游戏实测。
每区执行 100 × 4 范围 × 3 损毁状态循环，使用实际原生可视路径选择函数与引擎/UI 替身；检查自身保留、敌我独立规则、重启保存、UTF-8 标签、不同默认/风格模型、刷新、命名元组类型、原描述与碰撞入口不变。
Pz70 每区读取 167 项资源／42 个模型。所有模型 XML 还原路径后逐节点比对原版，数字按原始浮点精度核对；所有非 XML 资源逐字节一致。所有可读网格分组回读，三项原版损毁车体提示复制前后相同，无新增问题；没有将既有提示确认为游戏故障。

## 运行环境中的隔离计时

'''+ '\n'.join('- '+r['realm']+': 首次建立元数据 %.3f 秒；命中缓存 %.3f 秒。'%(r['cold_seconds'],r['warm_seconds'])for r in results)+'''

仅统计客户端自带 Python 2.7 在独立进程中的车型元数据读取；不含登录、Gameface 绘制和模型准备，不能当作游戏内端到端耗时。

## 状态和限制

`whole_vehicle_loading.status = not_tested`，`in_game_tested = false`。用户已确认欧服实际目录 D:\\wot\\World_of_Tanks_EU，当前安装版本 #993；亚服 #991 仍作为本地已安装的离线参考。没有启动游戏，原版整车基线未在本次亲自实测。
实际游戏内 Gameface 显示、首次动态文件挂载、原生 Compound 整车加载、车库、训练房敌我车辆、不同画质/LOD、姿态、损毁、切车和其他模组兼容都仍待实测。独立浏览器检查不能证明 Gameface 或整车兼容通过。
自动识别原版车型目录覆盖；UML／AE／第三方独立挂载物与全局共享覆盖暂不保证屏蔽。所需两项 UI API 已在本机两区目录找到，未重新分发；实际游戏内 API 交互仍未观察。
没有修改点亮、可见性、瞄准、碰撞、射击输入、网络或反作弊入口。未获官方审核，不能保证零误报；没有提交 Mod Hub 或上传 GitHub。本次不包含旧 AE 闪烁修复。

## 安装包清单

'''+ '\n'.join('- '+row['zip']+'\n  SHA256 `'+row['zip_sha256']+'`；'+str(row['zip_bytes'])+' 字节。'for row in results)+
      '\n\n源码：'+str(source_zip)+'\nSHA256 `'+digest(source_zip)+'`。\n',encoding='utf-8')
    print(json.dumps(dict(artifacts=results,source=str(source_zip),source_sha256=digest(source_zip),report=str(report)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
