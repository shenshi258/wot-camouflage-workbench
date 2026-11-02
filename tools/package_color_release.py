"""Bundle the colour editor and 16 presets without launching any UI/game."""
import ast,ctypes,hashlib,json,os,shutil,subprocess,sys,zipfile
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_presets,APP_NAME
from wotcamo.common import ROOT

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def copy(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache','__pycache__','*.bak','result','projects','data'))

def main():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.SetPriorityClass.restype=wintypes.BOOL
    assert k.SetPriorityClass(wintypes.HANDLE(-1),0x00100000)
    workspace=ROOT.parents[1];name=APP_NAME+'_二次元预设与调色'
    out=workspace/'交付'/name;source=workspace/'交付'/(name+'_源码')
    if out.exists() or source.exists():raise RuntimeError('请保留旧产物并使用新的修订名。')
    media=workspace/'交付/二次元特效预设_新增12款'
    report=json.loads((media/'制作与验证记录.json').read_text(encoding='utf-8'));assert len(report['presets'])==12
    test_log=(ROOT/'.cache/color_tests.log').read_text(encoding='utf-8');assert 'Ran 52 tests' in test_log and test_log.rstrip().endswith('OK')
    base=workspace/'交付/wot涂装工作台 3.1_双侧显示修订版_R2'
    copy(base/'程序',out/'程序');copy(ROOT/'wotcamo',out/'程序/wotcamo')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    for row in report['presets']:
        path=media/row['file'];assert sha(path)==row['sha256'];data,_=ae_presets.read(path)
        for folder in (out/'程序/预设/AE特效',source/'预设/AE特效'):ae_presets.store(data,path.read_bytes(),folder)
    copy(base/'预设预览',out/'预设预览/原四款')
    copy(media/'动画预览',out/'预设预览/新增12款')
    shutil.copy2(media/'12款特效总览.png',out/'12款特效总览.png')
    for file in base.glob('*.cmd'):shutil.copy2(file,out/file.name)
    documentation='''# wot涂装工作台 3.1 · 二次元预设与调色

内置 16 款 AE 特效：保留原四款，新增樱粉花瓣、桃心祈愿、星砂银河、极光丝带、全息扫光、电弧、圣光羽、月环魔法阵、音符、六角光域、梦彩彗尾和雪花。

## 改颜色

AE 窗口 → “播放与透明”页 → **特效颜色**。可点击取色器、填写 #RRGGBB，或点樱粉/冰蓝/紫晶/鎏金快捷色。着色强度 0% 保留素材原色，100% 改为所选颜色；中间值与原色混合。亮度单独调节。三维工具条也提供颜色、强度和恢复原色。

预览与导出使用同一份经过着色的像素，alpha 逐字节保留。素材原图集保留，改颜色不会破坏原素材。颜色参数随预设和 .aefx 工程保存，生成的涂装 ZIP 继续附带本次预设。新保存的调色预设需本版或后续版本导入。

## 导入与显示

顶部 **管理 / 导入… → 导入…**，选择 .aepreset 后套用。新增 12 款的原色文件也可导入上一版双侧显示版 3.1；调色功能需本次更新。

单侧选区仅生成该侧；需要左右同时出现时勾选 **左右双侧显示**。独立平面仍可拖动位置、拉角、调长宽和裁剪。选区、挂点与车辆位置由当前工程保留。

动画预览放在“预设预览”文件夹。总览图和 GIF 为参考合成，游戏原生曝光与泛光仍需对最终包实测。

本次仅做后台文件、参数服务、像素和包内模块检查，没有打开 Tk/WebView 或游戏窗口，没有安装任何车辆模组。目视 UI 与游戏效果未实测。
'''
    for folder in (out,out/'程序',source):
        for filename in ('README.md','3.1更新说明.md','AE预设说明.md'):(folder/filename).write_text(documentation,encoding='utf-8')
    (out/'使用说明.txt').write_text(APP_NAME+'\n运行“启动'+APP_NAME+'.cmd”。\nAE 特效顶部选择预设并套用；播放与透明 → 特效颜色。\n共 16 款内置预设。\n',encoding='utf-8-sig')
    evidence=out/'验证记录';evidence.mkdir()
    shutil.copy2(ROOT/'.cache/color_tests.log',evidence/'颜色与预设后台检查.txt')
    shutil.copy2(media/'制作与验证记录.json',evidence/'12款预设制作验证.json')
    smoke='''
import ast,io
from pathlib import Path
from PIL import Image
from wotcamo import ae_presets,ae_effects as ae,ae_gui
records,issues=ae_presets.scan();assert len(records)==16 and not issues
for row in records:ae_presets.read(row['path'])
for file in Path('wotcamo').rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
pixel=ae.colorize_rgba(Image.new('RGBA',(1,1),(255,0,0,128)),dict(tint_color='#00C8FF',tint_strength=100))
assert pixel.getpixel((0,0))==(0,200,255,128)
assert Image.open(io.BytesIO(ae.dds(pixel))).convert('RGBA').tobytes()==pixel.tobytes()
assert 'colorchooser.askcolor' in Path('wotcamo/ae_gui.py').read_text(encoding='utf-8')
assert 'aeTintColor' in Path('wotcamo/preview_web/index.html').read_text(encoding='utf-8')
print('PACKAGED_16_PRESETS_COLOR_DDS_UI_DEFINITIONS_OK_NO_WINDOWS')
'''
    program=out/'程序';env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1')
    run=subprocess.run([str(program/'runtime/python.exe'),'-s','-c',smoke],cwd=program,env=env,capture_output=True,text=True,creationflags=0x08000000|0x40)
    (evidence/'包内后台检查.txt').write_text(run.stdout+run.stderr,encoding='utf-8')
    if run.returncode:raise RuntimeError(run.stderr)
    for file in (ROOT/'wotcamo').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            relative=file.relative_to(ROOT/'wotcamo');assert sha(file)==sha(program/'wotcamo'/relative)==sha(source/'wotcamo'/relative)
    listing=[dict(path=file.relative_to(out).as_posix(),bytes=file.stat().st_size,sha256=sha(file)) for file in out.rglob('*') if file.is_file()]
    (out/'文件清单.json').write_text(json.dumps(dict(product=APP_NAME,files=listing),ensure_ascii=False,indent=2),encoding='utf-8')
    target=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in out.rglob('*'):
            if file.is_file():z.write(file,(Path(out.name)/file.relative_to(out)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in listing:assert hashlib.sha256(z.read(out.name+'/'+row['path'])).hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(sha(target)+'  '+target.name+'\n',encoding='utf-8')
    print('WORKBENCH_READY',str(target),target.stat().st_size,sha(target),flush=True)

if __name__=='__main__':main()
