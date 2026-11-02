"""Deliver 3.3 independently of the preserved 3.1 release and inputs."""
import ctypes,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import APP_NAME,ae_presets
from wotcamo.common import ROOT
from package_aefix_release import copy,digest

def main():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    assert k.SetPriorityClass(ctypes.c_void_p(-1),0x40)
    workspace=ROOT.parents[1];oldname='wot涂装工作台 3.1_33款双侧修订版_R2';name=APP_NAME+'_35款预设版_R1'
    base=workspace/'交付'/(oldname+'.zip');out=workspace/'交付'/name;source=out.with_name(name+'_源码');target=out.parent/(name+'.zip')
    if any(p.exists() for p in (out,source,target)):raise RuntimeError('目标已存在，请保留旧交付并更名。')
    assert digest(base)=='05f5d68682c3f185d0c0f8d562582abee3aeec98a07d22d0453d68112d66f46f'
    log=(ROOT/'.cache/aefix_tests.log').read_text(encoding='utf-8');assert 'Ran 84 tests' in log and log.rstrip().endswith('OK')
    ui_log=(ROOT/'.cache/ui33_review_after.log').read_text(encoding='utf-8');assert 'Ran 32 tests' in ui_log and ui_log.rstrip().endswith('OK')
    prior=json.loads((ROOT/'.cache/mirror_real_check.json').read_text(encoding='utf-8'))
    glass=json.loads((ROOT/'.cache/glass_native_check.json').read_text(encoding='utf-8'))
    assert prior['mirrored_frame_readback']==17 and glass['mirrored_frames']==96 and glass['material_readback']==192
    assert prior['whole_vehicle_loading']['status']==glass['whole_vehicle_loading']['status']=='not_tested'
    gallery=workspace/'交付/全部35款特效预览_3.3';g=json.loads((gallery/'预览制作与检查记录.json').read_text(encoding='utf-8'))
    assert len(g['effects'])==g['gif_count']==35 and g['video']['decoded_all_frames']
    out.mkdir()
    with zipfile.ZipFile(base) as z:
        for info in z.infolist():
            path=PurePosixPath(info.filename)
            if not path.parts or path.parts[0]!=oldname or '..' in path.parts:raise ValueError('交付包路径无效')
            parts=path.parts[1:]
            if not parts or parts[0]=='预设预览':continue
            if parts in [('3.1更新说明.md',),('程序','3.1更新说明.md')]:continue
            dest=out.joinpath(*parts)
            if not dest.resolve().is_relative_to(out.resolve()):raise ValueError('交付包路径越界')
            if info.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as inp,dest.open('wb') as output:shutil.copyfileobj(inp,output)
    (out/'启动wot涂装工作台 3.1.cmd').rename(out/'启动wot涂装工作台 3.3.cmd')
    copy(ROOT/'wotcamo',out/'程序/wotcamo');copy(gallery,out/'预设预览')
    copy(ROOT/'预设/AE特效',out/'程序/预设/AE特效')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    records,issues=ae_presets.scan(out/'程序/预设/AE特效');assert len(records)==35 and not issues
    with zipfile.ZipFile(base) as z:
        for record in records:
            n=record['data'] if 'data' in record else record['name']
            installed=record['path'];assert digest(installed)==digest(source/'预设/AE特效'/installed.name)
            if int(n[:2])<=33:
                assert hashlib.sha256(z.read(oldname+'/程序/预设/AE特效/'+installed.name)).hexdigest()==digest(installed)
            else:
                original=workspace/'交付/液态玻璃AE预设_新增2款'/(n+'.aepreset')
                assert digest(original)==digest(installed)
    note='''# wot涂装工作台 3.3

解压到可写目录，运行「启动wot涂装工作台 3.3.cmd」。内置全部 35 款可导入、导出的 AE 特效预设，并附有「预设预览」：32 秒动态总览、离线搜索页面与逐款动画。

## 可选液态玻璃界面

默认是经典界面。点击工作台、AE、灯效或三维预览窗口顶部的界面按钮，可在经典与液态玻璃风格之间切换。选择统一保存在程序目录中；其他编辑器及弹窗获得焦点时同步，三维预览随状态刷新同步。保存失败时会提示。桌面窗口以配色模拟玻璃，不是系统级实时背景模糊。

本次统一了主窗口、AE、灯效窗口的参数选项卡、输入框、列表、滚动区域和帮助提示的配色及交互状态；切换风格时同步变化。预览图和颜色样本保持其原有颜色。

## R1 界面问题修订

- AE 处理期间，着色强度滑条现在与其他参数一起锁定，处理结束后恢复原状态。
- 灯效处理期间，「恢复自动保存工程」同步锁定，并在操作入口阻止中途更换来源。所有参数采用统一的忙碌状态逻辑，恢复时保留原本禁用或只读的状态。
- 经典与液态玻璃界面互切时，已经创建的下拉列表同步更新底色和选中色。

上述 3 个问题均先通过测试复现，再修正。相关代码注释与回归测试已更新。此次不改动原生特效资源，保留全部 35 款预设。

## 液态玻璃 AE 预设

新增 34「液态玻璃水滴」、35「液态玻璃流带」。进入 AE 特效窗口选择预设并套用，可在播放与透明调整颜色和强度，也能设置位置、独立长宽、裁剪和左右双侧。水滴与流带是普通透明动画，以高光模拟玻璃；不实时折射或模糊车身底图。预设可通过「管理 / 导入…」导出或导入，也会随本次生成的涂装 ZIP 附带。

## 双侧与变形

独立平面左右双侧现在分别生成镜像后的网格、法线及序列；拖动变形时两侧同步。新建流动平面会保留当前方向、位置、长宽与双侧设置。贴面依据选中区域镜像，不会自动匹配另一侧不对称装甲；车体中线上的双侧平面会重合。较小窗口可滚动 AE 右侧找到尺寸、位置、变形与裁剪。

此前生成的涂装包不会自动变化，需重新生成。同一车型避免同时启用冲突的多份涂装或 AE 包。

## 验证范围

完成 84 项无窗口后台回归、32 项隔离桌面真实界面检查、双侧拖动脚本检查、全部 35 款预设与动态预览检查。包内自带运行环境另执行 39 项后台检查与同一套 32 项界面检查；后两组属于复核，不计为新增测试。界面测试在独立桌面运行，不切换当前桌面，不操作游戏。

此前以用户确认可正常使用的欧服 Pz70 原涂装为基线，离线生成玻璃双侧样例并回读 96 帧、192 个材质及两侧网格；原始资源逐字节保留。原包存在一处既有炮塔网格分组警告，该项未改动。此前欧服客户端资源检查为 2.4.1.1 #989。离线样例的整车状态为 not_tested；此次 R1 仅修订工作台界面，未重新生成该样例或启动、安装游戏。实际整车加载、玻璃效果、遮挡和远近显示需游戏内验证。你的实际客户端更新后需重新核对。
'''
    for parent in (out,out/'程序',source):
        for filename in ('README.md','3.3更新说明.md','AE预设说明.md','双侧显示修订说明.md','界面修订说明.md'):
            (parent/filename).write_text(note,encoding='utf-8')
    (out/'使用说明.txt').write_text(APP_NAME+'\n运行“启动'+APP_NAME+'.cmd”。\n35 款预设和动画预览已内置；顶部按钮可在经典与液态玻璃界面间切换。\n玻璃动画为模拟高光和透明，不实时折射底图；游戏效果待实测。\n详情见 3.3更新说明.md。\n',encoding='utf-8-sig')
    evidence=out/'验证记录';evidence.mkdir(exist_ok=True)
    for old,new in [('aefix_tests.log','3.3后台回归.txt'),('ui33_review_before.log','R1界面问题修正前复现.txt'),('ui33_review_after.log','R1界面问题修正后回归.txt'),('mirror_real_check.json','双侧原样例离线检查.json'),('glass_native_check.json','液态玻璃双侧离线检查.json')]:
        shutil.copy2(ROOT/'.cache'/old,evidence/new)
    smoke=r'''
import ast,sys,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from wotcamo import ae_presets,__version__
sys.path.append(sys.argv[1]);assert __version__=='3.3'
rows,issues=ae_presets.scan();assert len(rows)==35 and not issues
for row in rows:ae_presets.read(row['path'])
for file in Path('wotcamo').rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
names=['tests.test_glass32','tests.test_ae_mirrorfix','tests.test_ae_review_fixes','tests.test_ae_preset_notes','tests.test_ae_sides']
with patch.object(tk.Tk,'__init__',side_effect=AssertionError('禁止创建窗口')),patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('禁止创建窗口')):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
assert result.testsRun==39 and result.wasSuccessful()
print('PACKAGED_35_PRESETS_39_GUARDED_CHECKS_OK')
'''
    program=out/'程序';env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    with (evidence/'3.3包内检查.txt').open('w',encoding='utf-8') as stream:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B','-c',smoke,str(source)],cwd=program,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000|0x40)
    if run.returncode:raise RuntimeError((evidence/'3.3包内检查.txt').read_text(encoding='utf-8'))
    with (evidence/'R1包内真实界面检查.txt').open('w',encoding='utf-8') as stream:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B',str(source/'tools/check_ui33_isolated.py'),'--program',str(program),'--tests',str(source)],cwd=program,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000|0x40)
    if run.returncode:raise RuntimeError((evidence/'R1包内真实界面检查.txt').read_text(encoding='utf-8'))
    with (evidence/'双侧拖动脚本检查.txt').open('w',encoding='utf-8') as stream:
        run=subprocess.run(['C:/Program Files/nodejs/node.exe',str(source/'tests/test_mirrored_drag.js'),str(program/'wotcamo/preview_web/preview.js')],stdout=stream,stderr=subprocess.STDOUT,timeout=30,creationflags=0x08000000|0x40)
    if run.returncode:raise RuntimeError((evidence/'双侧拖动脚本检查.txt').read_text(encoding='utf-8'))
    for file in (ROOT/'wotcamo').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            rel=file.relative_to(ROOT/'wotcamo');assert digest(file)==digest(program/'wotcamo'/rel)==digest(source/'wotcamo'/rel)
    assert not list(out.rglob('__pycache__'))
    rows=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file() and p!=out/'文件清单.json']
    (out/'文件清单.json').write_text(json.dumps(dict(product=APP_NAME,files=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,(Path(name)/p.relative_to(out)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(rows)+1
        for row in rows:
            with z.open(name+'/'+row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(digest(target)+'  '+target.name+'\n',encoding='utf-8')
    print('RELEASE_33_R1_READY',target,target.stat().st_size,digest(target),flush=True)

if __name__=='__main__':main()
