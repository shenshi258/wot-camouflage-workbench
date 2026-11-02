"""Bundle 33 presets while retaining the audited 3.1 implementation."""
import ctypes,json,os,shutil,subprocess,sys,zipfile,hashlib
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import APP_NAME,ae_presets
from wotcamo.common import ROOT
from package_aefix_release import copy,digest


def main():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.SetPriorityClass.restype=wintypes.BOOL
    assert k.SetPriorityClass(wintypes.HANDLE(-1),0x40)
    workspace=ROOT.parents[1];name=APP_NAME+'_33款视觉增强版'
    base=workspace/'交付'/(APP_NAME+'_25款预设审查修订版');media=workspace/'交付/视觉增强特效预设_新增8款'
    gallery=workspace/'交付/全部33款特效预览'
    out=workspace/'交付'/name;source=out.with_name(name+'_源码');target=out.parent/(name+'.zip')
    if any(p.exists() for p in (out,source,target)):raise RuntimeError('交付已存在，请保留旧版。')
    report=json.loads((media/'制作与验证记录.json').read_text(encoding='utf-8'));assert len(report['presets'])==8
    previews=json.loads((gallery/'预览制作与检查记录.json').read_text(encoding='utf-8'))
    assert previews['gif_count']==33 and previews['video']['decoded_all_frames'] and previews['video']['frames']==960
    for file in ('ae_effects.py','ae_gui.py','preview3d.py','light_effects.py','light_runtime.py.txt','preview_web/preview.js'):
        assert digest(ROOT/'wotcamo'/file)==digest(base/'程序/wotcamo'/file),file
    # Replace the old sampled preview directory with a complete source-based
    # gallery in this new output tree. The existing delivery remains intact.
    out.mkdir()
    for child in base.iterdir():
        if child.name=='预设预览':continue
        if child.is_dir():copy(child,out/child.name)
        else:shutil.copy2(child,out/child.name)
    copy(ROOT/'wotcamo',out/'程序/wotcamo')
    for row in report['presets']:
        path=media/row['file'];assert digest(path)==row['sha256'];metadata,_=ae_presets.read(path)
        ae_presets.store(metadata,path.read_bytes(),out/'程序/预设/AE特效')
        ae_presets.store(metadata,path.read_bytes(),ROOT/'预设/AE特效')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    original={p.name:digest(p) for p in (base/'程序/预设/AE特效').glob('*.aepreset')};assert len(original)==25
    for filename,sha in original.items():assert digest(out/'程序/预设/AE特效'/filename)==sha
    records,issues=ae_presets.scan(out/'程序/预设/AE特效');assert len(records)==33 and not issues
    assert len({r['name'] for r in records})==33
    for record in records:assert digest(record['path'])==digest(source/'预设/AE特效'/record['path'].name)
    for record in records:
        row=next(r for r in previews['effects'] if r['name']==record['name'])
        assert digest(record['path'])==row['preset_sha256']
    copy(gallery,out/'预设预览')
    shutil.copy2(media/'新增8款视觉特效总览.png',out/'新增8款视觉特效总览.png')
    shutil.copy2(media/'导入与摆放说明.md',out/'预设注释/新增8款视觉效果使用说明.md')
    guide='''# wot涂装工作台 3.1 · 33款视觉增强版

解压到可写目录，运行「启动wot涂装工作台 3.1.cmd」。原 25 款完整保留，新增 8 款视觉增强特效，全部已内置，无需逐个导入。

## 新增效果

26 星蝶双轨巡游 · 双重光轨、扇动翼片与星尘拖尾。

27 琉璃花镜绽放 · 三层花瓣、细金花脉与流动星枝。

28 深空引力星环 · 倾斜轨道、环绕光点与长条星流。

29 幻彩水晶棱镜 · 多面切光、悬浮水晶与底部折光带。

30 月潮泡影流光 · 上升虹彩气泡、月白反光与水纹。

31 绯樱弧刃残光 · 尖细弧刃、多层残影、樱瓣与火星。

32 极光星门回廊 · 六角星门、分段辉环与双侧极光带。

33 梦色花火星瀑 · 多点错峰花火、细亮尾丝与落星。

## 使用

AE 顶部选择预设 → 套用。管理 / 导入… 中可阅读每款的用途、摆放、配色和形状注释。新增 8 款均为透明底、96 帧、24 FPS、4 秒循环。

## 全部特效预览

「预设预览／全部33款特效动态总览.mp4」是 32 秒动态总览，共 4 页，每页 8 秒，保留各自播放速度；全部 960 帧已解码检查。

「预设预览／全部33款特效预览.html」支持离线分类、搜索、切换静态／动画和查看摆放注释。「单款动画」目录中的 33 个 GIF 全部从预设原图集重做，保留完整循环时长与原有透明起止段。旧版抽帧 GIF 不再用于本版预览；新增 8 款各有完整 96 帧。

「播放与透明 → 特效颜色」调颜色和着色强度；0% 保留原色，100% 统一色调。多色效果建议先从低强度开始。长宽、位置、裁剪、四角变形、装甲吸附和双侧显示沿用审查修订版。

普通点选／框选提交只更新承载选区，保留呈现与透明设置；需要贴面时手动切换呈现方式，或明确使用「吸附装甲」。生成涂装 ZIP 继续附带本次 .aepreset，可选附完整 .aefx 工程。

同车型只启用一份涂装或 AE 特效包，更换效果前停用旧包。旧版本、已有工程和自定义预设请保留；本包为独立新目录，不自动覆盖旧库。也可单独导入「视觉增强特效预设_新增8款.zip」中的 .aepreset。

## 检查范围

本次只新增媒体预设与注释、更新数量说明；素材播放、混合、原生挂载、导出代码沿用审查修订版。旧 25 款预设逐文件 SHA256 不变。新增 8 款已检查循环端点与接缝、预设导入回读、两种调色的 alpha 保留、DDS 像素一致及 GIF 完整帧／4 秒时长。

包内另做 15 项只读检查并禁止创建 Tk／Toplevel 窗口；源代码与程序文件一致，最终 ZIP 按清单逐文件校验。没有打开工作台、WebView 或游戏，未生成或安装车辆模组。游戏整车与视觉效果未实测，媒体预设的整车状态为 not_tested。

新增说明见「预设注释／新增8款视觉效果使用说明.md」，结果见「验证记录／新增8款制作与验证记录.json」和「33款包内检查.txt」。此前 25 款审查修订的历史说明和记录保留，不代表新媒体已通过游戏验收。
'''
    for parent in (ROOT,out,out/'程序',source):
        for filename in ('README.md','3.1更新说明.md','AE预设说明.md'):(parent/filename).write_text(guide,encoding='utf-8')
    for parent in (out,out/'程序',source):
        (parent/'界面修订说明.md').write_text('本版沿用 3.1 审查修订版界面，预设数量统一为 33 款。预设管理仍为两行按钮与可滚动注释；普通选面不改透明方式。新增 8 款的使用注释随 .aepreset 导出保留。\n',encoding='utf-8')
    (out/'使用说明.txt').write_text(APP_NAME+'\n\n解压后运行“启动'+APP_NAME+'.cmd”。全部 33 款预设已内置。\nAE 顶部选预设 → 套用；新增款编号 26～33。\n播放与透明 → 特效颜色；管理 / 导入… → 查看使用注释。\n全部特效预览：预设预览/全部33款特效动态总览.mp4；HTML 可分类搜索、逐款观看。\n同车型只启用一份涂装或 AE 特效包，更换前停用旧包。\n',encoding='utf-8-sig')
    evidence=out/'验证记录';shutil.copy2(media/'制作与验证记录.json',evidence/'新增8款制作与验证记录.json')
    shutil.copy2(gallery/'预览制作与检查记录.json',evidence/'全部33款预览制作与检查记录.json')
    (evidence/'旧25款预设完整保留.json').write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    smoke=r'''
import ast,io,sys,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from wotcamo import ae_presets,ae_effects as ae,ae_help
sys.path.append(sys.argv[1])
records,issues=ae_presets.scan();assert len(records)==33 and not issues
for r in records:
    d,png=ae_presets.read(r['path'])
    for section in ('用途：','摆放：','配色：','形状：','显示：','检查：'):assert section in d['description']
assert '33 款' in ae_help.TEXT['preset']
for file in Path('wotcamo').rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
image=ae.colorize_rgba(Image.new('RGBA',(1,1),(255,0,0,128)),dict(tint_color='#00C8FF',tint_strength=100))
assert image.getpixel((0,0))==(0,200,255,128)
assert Image.open(io.BytesIO(ae.dds(image))).convert('RGBA').tobytes()==image.tobytes()
with patch.object(tk.Tk,'__init__',side_effect=AssertionError('禁止创建窗口')),patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('禁止创建窗口')):
    suite=unittest.defaultTestLoader.loadTestsFromNames(['tests.test_ae_review_fixes','tests.test_ae_preset_notes','tests.test_ae_sides'])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
print('33_PRESETS_15_GUARDED_CHECKS_COLOR_DDS_OK')
'''
    program=out/'程序';env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',
                             PYTHONIOENCODING='utf-8',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    with (evidence/'33款包内检查.txt').open('w',encoding='utf-8') as log:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B','-c',smoke,str(source)],cwd=program,env=env,
                           stdout=log,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000|0x40)
    if run.returncode:raise RuntimeError((evidence/'33款包内检查.txt').read_text(encoding='utf-8'))
    for file in (ROOT/'wotcamo').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            relative=file.relative_to(ROOT/'wotcamo');assert digest(file)==digest(program/'wotcamo'/relative)==digest(source/'wotcamo'/relative)
    assert not list(out.rglob('__pycache__'))
    listing=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file() and p!=out/'文件清单.json']
    (out/'文件清单.json').write_text(json.dumps(dict(product=APP_NAME,files=listing),ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,(Path(name)/p.relative_to(out)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(listing)+1
        for row in listing:
            with z.open(name+'/'+row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(digest(target)+'  '+target.name+'\n',encoding='utf-8')
    print('VISUAL_33_PROGRAM_READY',target,target.stat().st_size,digest(target),flush=True)


if __name__=='__main__':main()
