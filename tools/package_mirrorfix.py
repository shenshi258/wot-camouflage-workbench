"""Package a new 3.1 revision from the immutable 33-preset release."""
import ast,ctypes,hashlib,json,os,shutil,subprocess,sys,zipfile
from ctypes import wintypes
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import APP_NAME,ae_presets
from wotcamo.common import ROOT
from package_aefix_release import copy,digest

def main():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.SetPriorityClass.restype=wintypes.BOOL
    assert k.SetPriorityClass(wintypes.HANDLE(-1),0x40)
    workspace=ROOT.parents[1];oldname=APP_NAME+'_33款双侧修订版_R2';name=APP_NAME+'_33款镜像变形修订版'
    base=workspace/'交付'/(oldname+'.zip');out=workspace/'交付'/name;source=out.with_name(name+'_源码');target=out.parent/(name+'.zip')
    if any(p.exists() for p in (out,source,target)):raise RuntimeError('目标已存在，请保留旧版。')
    assert digest(base)=='05f5d68682c3f185d0c0f8d562582abee3aeec98a07d22d0453d68112d66f46f'
    log=(ROOT/'.cache/aefix_tests.log').read_text(encoding='utf-8');assert 'Ran 74 tests' in log and log.rstrip().endswith('OK')
    native=json.loads((ROOT/'.cache/mirror_real_check.json').read_text(encoding='utf-8'))
    assert native['ares_source_triangles']==241 and native['ares_total_triangles']==482 and native['mirrored_frame_readback']==17 and native['whole_vehicle_loading']['status']=='not_tested'
    out.mkdir()
    with zipfile.ZipFile(base) as z:
        for info in z.infolist():
            path=PurePosixPath(info.filename)
            if not path.parts or path.parts[0]!=oldname or '..' in path.parts:raise ValueError('交付包路径无效')
            dest=out.joinpath(*path.parts[1:])
            if not dest.resolve().is_relative_to(out.resolve()):raise ValueError('交付包路径越界')
            if info.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as inp,dest.open('wb') as output:shutil.copyfileobj(inp,output)
    copy(ROOT/'wotcamo',out/'程序/wotcamo')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    records,issues=ae_presets.scan(out/'程序/预设/AE特效');assert len(records)==33 and not issues
    with zipfile.ZipFile(base) as z:
        for record in records:
            name_in=oldname+'/程序/预设/AE特效/'+record['path'].name
            assert hashlib.sha256(z.read(name_in)).hexdigest()==digest(record['path'])==digest(source/'预设/AE特效'/record['path'].name)
    note='''# wot涂装工作台 3.1 · 镜像变形修订

内置 33 款特效及全部动态预览。解压到可写目录，运行「启动wot涂装工作台 3.1.cmd」。此前生成的涂装包不会自动更新，需要重新生成才能使用本次改动。

本版修复独立平面左右双侧的深度变形：另一侧的顶点、法线和三角形绕序按中线反射，预览和生成资源使用相同的镜像规则；两侧序列使用各自的逐帧网格和相同的播放节奏。贴面仍使用已有的表面镜像方式。

从独立平面新建时，保留表单中最新的位置、平面方向、旋转角和长宽倍率，重置四角变形及裁剪；不会再按变形包围盒猜测平面方向或每次偏移。已有贴面选区时在后台使用当前参数和选区重新计算平面，计算期间若选区或设置发生变化，会要求重新点击，避免旧结果覆盖新操作。

继续保留「新建流动平面」后的左右双侧设置。从已镜像的贴面新建平面时，按原选中的一侧确定平面位置和范围；如果原选区已经覆盖两侧，按首个选中三角面所在侧确定范围。

独立平面勾选双侧后，横向位置处于中线时，两个位置重合。生成涂装包前会提示调整位置；可以继续在三维中拖动到一侧，或取消双侧选项。

检查了套用预设、吸附装甲、工程恢复与拖动：套用预设不会清掉双侧选择。贴面模式会保留当前映射方向，避免侧面预设使正面或顶面选区失去有效面积；独立平面仍使用预设的方向。工程文件恢复保存时的双侧设置。

三维预览中拖动任意一侧的平面时，被拖动的一侧会跟随操作；拖动原侧四角或边上的控制点时，两侧几何会实时同步。控制点显示在原侧，松开后参数同步到编辑窗口。

AE 窗口右侧增加滚动条：窗口高度较小时可向下滚动，找到长宽、位置、变形、裁剪和颜色设置；各参数页内部也有滚动条。

贴面仍按部件中线镜像，不会自动重新匹配另一侧的不对称装甲；请在三维中观察位置、遮挡并按需要调整。普通单侧选择、长宽、裁剪、变形、调色和 33 款预设保留。

全部特效预览位于「预设预览」；其中 MP4 为 32 秒动态总览，HTML 可离线搜索、逐款播放。

74 项后台回归、双侧拖动逻辑检查和包内检查通过；Ares90 原选区与欧服 Pz70 内部样例的 17 帧左右网格、法线、索引和序列已离线回读。Pz70 原始涂装已有一处炮塔分组范围警告，原资源未改；内部样例整车状态为 not_tested。按用户允许，以同源代码打开 AE 工作台，目视检查了右侧滚动和新建平面后双侧勾选状态；未打开三维预览窗口。没有启动或操作游戏、没有安装模组；游戏整车与实际视觉效果未实测。
'''
    for parent in (out,out/'程序',source):
        for filename in ('README.md','3.1更新说明.md','AE预设说明.md','双侧显示修订说明.md'):(parent/filename).write_text(note,encoding='utf-8')
    (out/'使用说明.txt').write_text(APP_NAME+'\n运行“启动'+APP_NAME+'.cmd”。内置全部 33 款特效与预览。\n双侧独立平面的深度变形现在会镜像到另一侧；新建平面保留当前方向与位置。\n窗口较小时滚动右侧查找长宽、位置和变形设置；旧涂装包需重新生成。\n详情见“双侧显示修订说明.md”。\n',encoding='utf-8-sig')
    evidence=out/'验证记录';shutil.copy2(ROOT/'.cache/aefix_tests.log',evidence/'双侧修订后台回归.txt')
    shutil.copy2(ROOT/'.cache/mirror_real_check.json',evidence/'双侧修订真实素材离线检查.json')
    smoke=r'''
import ast,sys,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from wotcamo import ae_presets,ae_effects as ae
sys.path.append(sys.argv[1])
rows,issues=ae_presets.scan();assert len(rows)==33 and not issues
for row in rows:ae_presets.read(row['path'])
for file in Path('wotcamo').rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
names=['tests.test_ae_mirrorfix','tests.test_ae_review_fixes','tests.test_ae_preset_notes','tests.test_ae_sides']
with patch.object(tk.Tk,'__init__',side_effect=AssertionError('禁止创建窗口')),patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('禁止创建窗口')):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
assert result.testsRun==30 and result.wasSuccessful()
print('PACKAGED_33_PRESETS_30_GUARDED_CHECKS_OK')
'''
    program=out/'程序';env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    with (evidence/'双侧修订包内检查.txt').open('w',encoding='utf-8') as stream:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B','-c',smoke,str(source)],cwd=program,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000|0x40)
    if run.returncode:raise RuntimeError((evidence/'双侧修订包内检查.txt').read_text(encoding='utf-8'))
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
    print('MIRROR_FIX_RELEASE_READY',target,target.stat().st_size,digest(target),flush=True)

if __name__=='__main__':main()
