"""Background-only packaging. Never opens Tk/WebView or touches a game client."""
import ctypes,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import APP_NAME,ae_presets
from wotcamo.common import ROOT

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def copy(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache','__pycache__','*.bak','result','projects','data'))

def main():
    kernel=ctypes.windll.kernel32;kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x00100000)
    workspace=ROOT.parents[1];name=APP_NAME+'_双侧显示修订版_R2';out=workspace/'交付'/name
    if out.exists():raise RuntimeError('已有同名产物，请保留旧版本。')
    base=workspace/'交付/wot涂装工作台 3.1_平面变形修订版'
    log=(ROOT/'.cache/sides_tests.log').read_text(encoding='utf-8');assert 'Ran 46 tests' in log and log.rstrip().endswith('OK')
    copy(base/'程序',out/'程序');copy(ROOT/'wotcamo',out/'程序/wotcamo')
    for item in base.iterdir():
        if item.is_file() and item.suffix.lower() in ('.cmd','.png'):shutil.copy2(item,out/item.name)
    copy(base/'预设预览',out/'预设预览')
    documentation='''# wot涂装工作台 3.1 · 双侧显示修订

在 AE 窗口“选择呈现方式”下方，或三维工具条勾选 **左右双侧显示**。

单侧选区默认只生成这一侧。旧版贴面模式禁用了镜像，因此选了左侧后，右侧不会自动出现。本版允许贴面播放、贴面发光显式镜像到另一侧；保留原侧的形状、位置、UV、速度、亮度及材质。镜像在部件空间中计算，只修改附加特效网格，不修改原车节点。

已同时选中的对称三角面不会重复叠加。左右不对称的造型建议分别选面；新的双侧显示仍需要游戏内确认遮挡、随动、开镜与 LOD。保存 AE 工程会保留双侧开关；单独的素材预设继续只保存素材和播放/尺寸参数。

保留平面拖动、四角变形、独立长宽、裁剪，以及原四款内置预设。生成涂装 ZIP 仍附带本次使用的预设，可选带完整 .aefx 工程。

本次只运行后台数据、HTTP 参数和包内模块检查，没有打开制作器窗口、WebView 或游戏；没有进行目视 UI 复核或游戏实测。
'''
    for folder in (out,out/'程序'):
        (folder/'README.md').write_text(documentation,encoding='utf-8')
        for doc in ('3.1更新说明.md','AE预设说明.md','界面修订说明.md'):
            (folder/doc).write_text(documentation+'\n\n'+(ROOT/doc).read_text(encoding='utf-8'),encoding='utf-8')
    (out/'使用说明.txt').write_text(APP_NAME+'\n运行“启动'+APP_NAME+'.cmd”。\nAE 窗口呈现方式下方勾选“左右双侧显示”。\n本次没有自动安装、启动或操作游戏。\n',encoding='utf-8-sig')
    evidence=out/'验证记录';evidence.mkdir()
    shutil.copy2(ROOT/'.cache/sides_tests.log',evidence/'双侧功能后台检查.txt')
    shutil.copy2(ROOT/'.cache/sides_export.json',evidence/'用户双侧包离线记录.json')
    smoke='''
from wotcamo import ae_effects as ae,ae_presets,ae_gui
from pathlib import Path
import ast
records,issues=ae_presets.scan();assert len(records)==4 and not issues
for placement in ('plane','surface','surface_glow'):assert ae.config(dict(placement=placement,mirror=True))['mirror'] is True
for path in Path('wotcamo').rglob('*.py'):ast.parse(path.read_text(encoding='utf-8'))
gui=Path('wotcamo/ae_gui.py').read_text(encoding='utf-8')
assert "text='左右双侧显示（镜像到另一侧）',variable=self.mirror" in gui
assert "if surface:self.mirror.set(False)" not in gui
assert 'aeMirror' in Path('wotcamo/preview_web/index.html').read_text(encoding='utf-8')
print('PACKAGED_SIDES_MODULES_PRESETS_UI_DEFINITIONS_OK_NO_WINDOWS')
'''
    program=out/'程序';env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([str(program/'runtime/python.exe'),'-s','-c',smoke],cwd=program,env=env,capture_output=True,text=True,creationflags=0x08000000|0x40)
    (evidence/'包内后台检查.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    source=workspace/'交付'/(name+'_源码')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    for file in (ROOT/'wotcamo').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            relative=file.relative_to(ROOT/'wotcamo')
            assert sha(file)==sha(program/'wotcamo'/relative)==sha(source/'wotcamo'/relative)
    files=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in out.rglob('*') if p.is_file()]
    (out/'文件清单.json').write_text(json.dumps(dict(product=APP_NAME,files=files),ensure_ascii=False,indent=2),encoding='utf-8')
    target=out.with_suffix('.zip')
    # with_suffix would drop the dotted version; append .zip to the full name.
    target=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in out.rglob('*'):
            if file.is_file():z.write(file,(Path(out.name)/file.relative_to(out)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in files:assert hashlib.sha256(z.read(out.name+'/'+row['path'])).hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(sha(target)+'  '+target.name+'\n',encoding='utf-8')
    print(json.dumps(dict(path=str(target),bytes=target.stat().st_size,sha256=sha(target)),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
