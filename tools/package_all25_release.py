"""Integrate all existing media and portable notes without touching animation.

No Tk/WebView/game is launched. Background scheduling covers CPU and I/O;
the package is verified through its own Python runtime and final ZIP bytes.
"""
import ast,ctypes,hashlib,io,json,os,shutil,subprocess,sys,zipfile
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import APP_NAME,ae_presets,ae_help
from wotcamo.common import ROOT
import preset_notes_catalog as catalog

WORKSPACE=ROOT.parents[1]
NAME=APP_NAME+'_25款预设整合注释版'
OUT=WORKSPACE/'交付'/NAME
SOURCE=WORKSPACE/'交付'/(NAME+'_源码')

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def copy(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache','__pycache__','*.bak','result','projects','data'))

def annotated_payload(path,index):
    """Change only description. Preserve clip/config and every original PNG byte."""
    checked,_=ae_presets.read(path)
    with zipfile.ZipFile(path) as source:
        original=json.loads(source.read('preset.json'));png=source.read('atlas.png')
    updated=dict(original,description=catalog.description(index))
    assert len(updated['description'])<=1000
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('preset.json',json.dumps(updated,ensure_ascii=False));z.writestr('atlas.png',png)
    with zipfile.ZipFile(io.BytesIO(payload.getvalue())) as z:
        saved=json.loads(z.read('preset.json'));assert saved['clip']==original['clip'] and saved['config']==original['config']
        assert z.read('atlas.png')==png
    return checked,updated,payload.getvalue()

def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.SetPriorityClass.restype=wintypes.BOOL
    assert kernel.SetPriorityClass(wintypes.HANDLE(-1),0x00100000)
    if OUT.exists() or SOURCE.exists():raise RuntimeError('同名交付已存在；请保留旧版本。')
    test_log=(ROOT/'.cache/all25_tests.log').read_text(encoding='utf-8');assert 'Ran 56 tests' in test_log and test_log.rstrip().endswith('OK')
    base=WORKSPACE/'交付/wot涂装工作台 3.1_二次元预设与调色'
    ba=WORKSPACE/'交付/碧蓝档案风格特效预设_新增9款'
    existing,issues=ae_presets.scan(base/'程序/预设/AE特效');assert len(existing)==16 and not issues
    extras=sorted(ba.glob('*.aepreset'));assert len(extras)==9
    inputs=[row['path'] for row in existing]+extras
    copy(base/'程序',OUT/'程序');copy(ROOT/'wotcamo',OUT/'程序/wotcamo')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,SOURCE/folder)
    records=[];guides=['# 25 款预设注释与使用建议\n\n原四款 01～04，二次元系列 05～16，碧蓝档案风格 17～25。每款仍可独立导出为 .aepreset；以下注释也已内嵌在预设中。\n']
    for index,path in enumerate(inputs,1):
        metadata,updated,payload=annotated_payload(path,index)
        assert metadata['name'].startswith('%02d '%index),(index,metadata['name'])
        for library in (OUT/'程序/预设/AE特效',SOURCE/'预设/AE特效'):ae_presets.store(metadata,payload,library)
        c=metadata['config'];clip=metadata['clip']
        guides.append('## '+metadata['name']+'\n\n%d 帧，%g FPS，%g 秒；素材 %d×%d；默认基准宽度 %g 米、亮度 %g。\n\n'%(clip['frames'],c['fps'],clip['frames']/c['fps'],*clip['frame_size'],c['width'],c['brightness'])+updated['description'].replace('\n','\n\n')+'\n')
        records.append(dict(name=metadata['name'],source_sha256=sha(path),annotated_sha256=hashlib.sha256(payload).hexdigest(),
                            atlas_sha256=clip['atlas_sha256'],clip_unchanged=True,config_unchanged=True,atlas_bytes_unchanged=True,description=updated['description']))
    # store() preserves overwritten files as .bak; these staging-only neutral
    # backups are not part of a fresh distribution and must not ship as clutter.
    for parent in (OUT,SOURCE):
        for backup in parent.rglob('*.aepreset.bak'):
            assert backup.resolve().is_relative_to(parent.resolve());backup.unlink()
    for library in (OUT/'程序/预设/AE特效',SOURCE/'预设/AE特效'):
        all_rows,issues=ae_presets.scan(library);assert len(all_rows)==25 and not issues
        assert len({r['name'] for r in all_rows})==25
    copy(base/'预设预览',OUT/'预设预览');copy(ba/'动画预览',OUT/'预设预览/碧蓝档案风格9款')
    for file in base.glob('*.cmd'):shutil.copy2(file,OUT/file.name)
    shutil.copy2(base/'12款特效总览.png',OUT/'12款特效总览.png')
    shutil.copy2(ba/'碧蓝档案风格9款总览.png',OUT/'碧蓝档案风格9款总览.png')
    notes=OUT/'预设注释';notes.mkdir()
    (notes/'25款使用说明.md').write_text('\n'.join(guides),encoding='utf-8')
    shutil.copy2(ba/'配色与摆放建议.md',notes/'碧蓝档案风格配色与摆放.md')
    parameters='''# 参数注释速查

| 参数 / 操作 | 如何使用 |
| --- | --- |
| 长度 / 宽度倍率 | 分别控制横向和纵向；1 为当前素材原比例，两个方向独立。 |
| 平面宽度（米） | 独立平面的基准宽度；再由长宽倍率分别调整。 |
| X / Y / Z 位置 | 独立平面相对挂点的横向、上下、前后位置，单位米。 |
| 拖动平面 / 中心点 | 自由移动位置；拖四角单独变形，拖边中点拉伸该边。 |
| Shift 拖动 | 沿平面法线调整深度；可调整整个平面或单个角点。 |
| 四角变形 | 0 为不变形；横纵以对应半尺寸为 1，深度以较短边半尺寸为 1。四角不能交叉。 |
| 贴面整体缩放 / 偏移 | 按装甲选区映射调整素材，超出选区的图案会裁掉。 |
| 吸附装甲 / 整块装甲 | 先勾选范围选项再重新吸附；旧选区不会随复选框自动扩大。 |
| 左右双侧显示 | 单侧选区不会自动生成另一侧；勾选后镜像特效。左右不对称部位建议分别选面。 |
| 颜色 / 着色强度 | 选择颜色或输入 #RRGGBB；0% 原色、100% 统一为新色。双色图案可先从低强度调起。 |
| 亮度 | 独立于调色强度；先保留各预设默认值，再根据底图微调。 |
| 播放帧率 | 每秒帧数。循环秒数等于总帧数除以 FPS；提高 FPS 会加快同一动画。 |
| 四边裁剪 | 0% 不裁；隐藏图像边缘，剩余部分保持原位，不拉伸补齐。 |
| 离面距离（米） | 贴面发光与装甲的间距；过小可能闪烁，过大会悬空。 |
| 保存为预设 | 保存素材、播放、尺寸、裁剪、变形、颜色和注释；车辆位置由工程保存。 |
| 保存 AE 工程 | 保存当前原涂装、选区、吸附点、挂点、位置和素材，供继续编辑。 |
| 自动打包 ZIP | 生成涂装 ZIP 固定带本次 .aepreset；可选择再带 .aefx。生成不等于自动安装。 |

独立平面不受装甲选区裁剪，但会被真实装甲遮挡；图案埋进装甲时，调整位置或深度。三维预览用于定位和检查动画，实际游戏曝光、遮挡、随动、开镜和 LOD 仍需最终包实测。
'''
    (notes/'参数注释速查.md').write_text(parameters,encoding='utf-8')
    readme='''# wot涂装工作台 3.1 · 25 款预设整合注释版

程序、全部 25 款特效、动画预览和注释已合在一起。解压到一个可写目录，运行“启动wot涂装工作台 3.1.cmd”。不需要再次逐个导入预设。

AE 特效窗口顶部选择预设并点“套用”。主窗口显示简短用途；“管理 / 导入…”内下方有可滚动注释，包括用途、摆放、配色、形状及显示范围。注释存进每个 .aepreset，独立导出后仍保留。

- 01～04：原四款视频 / 流星预设。
- 05～16：花瓣、爱心、星砂、极光、全息、电弧、圣光羽、魔法阵、音符、六角光域、彗尾、雪花。
- 17～25：碧蓝档案风格蓝白终端、阿洛娜、普拉娜、星野、白子、爱丽丝、桃绿双子、日奈及三一风格。

改颜色：AE → 播放与透明 → 特效颜色。长宽、位置、四角变形和左右双侧显示继续可用。生成涂装 ZIP 仍带本次预设，可选择带完整工程。

详细说明位于“预设注释”文件夹；动画示例位于“预设预览”。25 款的素材像素、播放参数和默认调色参数均沿用原版，本次只补充注释与整合。

已有自定义预设或工程请保留在原目录；本包为独立新目录，不会自动合并或覆盖你的旧库。需要自定义预设时，可从旧版导出 .aepreset 再导入本版。

本次只做后台模块、预设回读、参数和文件校验，没有打开工作台 / WebView / 游戏，也未安装模组；目视 UI 和实际游戏效果未实测。
'''
    for parent in (OUT,OUT/'程序',SOURCE):
        for name in ('README.md','AE预设说明.md','3.1更新说明.md'):(parent/name).write_text(readme,encoding='utf-8')
    (OUT/'使用说明.txt').write_text(APP_NAME+'\n\n解压后运行“启动'+APP_NAME+'.cmd”。全部 25 款已内置，无需再导入。\nAE 顶部选预设 → 套用；管理 / 导入… → 查看可滚动注释。\n调色在“播放与透明”页；长宽、位置和双侧显示保留。\n详细说明在“预设注释”，动画示例在“预设预览”。\n',encoding='utf-8-sig')
    evidence=OUT/'验证记录';evidence.mkdir()
    shutil.copy2(ROOT/'.cache/all25_tests.log',evidence/'后台回归检查.txt')
    (evidence/'25款整合与注释记录.json').write_text(json.dumps(dict(presets=records,only_description_changed=True,no_gui_or_game_started=True),ensure_ascii=False,indent=2),encoding='utf-8')
    smoke='''
import ast
from pathlib import Path
from wotcamo import ae_presets,ae_effects as ae,ae_help,ae_gui
records,issues=ae_presets.scan();assert len(records)==25 and not issues
for record in records:
    metadata,atlas=ae_presets.read(record['path'])
    for word in ('用途：','摆放：','配色：','形状：','显示：','检查：'):assert word in metadata['description']
    assert len(ae_presets.summary(record).splitlines())==2
    assert metadata['description'] in ae_presets.description_text(record)
for key in ae.DEFAULTS:
    if key not in ('part','plane','mirror','blend','placement'):assert key in ae_help.TEXT
for file in Path('wotcamo').rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
print('PACKAGED_25_PRESETS_NOTES_MODULES_OK_NO_WINDOWS')
'''
    program=OUT/'程序';environment=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([str(program/'runtime/python.exe'),'-s','-c',smoke],cwd=program,env=environment,capture_output=True,text=True,creationflags=0x08000000|0x40)
    (evidence/'包内后台检查.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    for file in (ROOT/'wotcamo').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            relative=file.relative_to(ROOT/'wotcamo');assert sha(file)==sha(program/'wotcamo'/relative)==sha(SOURCE/'wotcamo'/relative)
    listing=[dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.rglob('*') if p.is_file()]
    (OUT/'文件清单.json').write_text(json.dumps(dict(product=APP_NAME,files=listing),ensure_ascii=False,indent=2),encoding='utf-8')
    target=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in OUT.rglob('*'):
            if path.is_file():z.write(path,(Path(OUT.name)/path.relative_to(OUT)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in listing:
            with z.open(OUT.name+'/'+row['path']) as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(sha(target)+'  '+target.name+'\n',encoding='utf-8')
    print('ALL_25_READY',str(target),target.stat().st_size,sha(target),flush=True)

if __name__=='__main__':main()
