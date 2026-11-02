"""Ship an independent repaired revision; no GUI, browser or game is started."""
import ast
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import APP_NAME,ae_presets
from wotcamo.common import ROOT


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def copy(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache','__pycache__','*.bak','result'))


def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.SetPriorityClass.restype=wintypes.BOOL
    assert kernel.SetPriorityClass(wintypes.HANDLE(-1),0x00100000)
    workspace=ROOT.parents[1];name=APP_NAME+'_25款预设审查修订版'
    base=workspace/'交付'/(APP_NAME+'_25款预设整合注释版')
    out=workspace/'交付'/name;source=out.with_name(name+'_源码');target=out.parent/(name+'.zip')
    resume='--resume' in sys.argv
    if target.exists() or (not resume and any(p.exists() for p in (out,source))):raise RuntimeError('修订目录或 ZIP 已存在，请保留旧版并更名。')
    log=(ROOT/'.cache/aefix_tests.log').read_text(encoding='utf-8')
    assert 'Ran 59 tests' in log and log.rstrip().endswith('OK')
    export=json.loads((ROOT/'.cache/aefix_export.json').read_text(encoding='utf-8'))
    assert export['strictly_increasing_and_finite_scale_tracks']==34
    assert export['whole_vehicle_loading']['status']=='not_tested'
    copy(base,out);copy(ROOT/'wotcamo',out/'程序/wotcamo')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    for file in ROOT.glob('*.md'):
        for parent in (out,out/'程序',source):shutil.copy2(file,parent/file.name)
    shutil.copy2(workspace/'AE特效审查报告_给GPT.md',out/'验证记录/原审查报告_保留原文.md')
    (out/'使用说明.txt').write_text(APP_NAME+'\n\n解压到可写目录，运行“启动'+APP_NAME+'.cmd”。内置 25 款预设，无需逐个导入。\n本次修复动画时间边界、选区改写参数与预设按钮布局，详见 README 和审查结论复核与修复。\n同车型只启用一份涂装或 AE 特效包；更换效果前停用旧包。\n',encoding='utf-8-sig')
    records,issues=ae_presets.scan(out/'程序/预设/AE特效');assert len(records)==25 and not issues
    originals={p.name:digest(p) for p in (base/'程序/预设/AE特效').glob('*.aepreset')}
    unchanged=[]
    for record in records:
        path=record['path'];assert digest(path)==originals[path.name]
        assert digest(path)==digest(source/'预设/AE特效'/path.name)
        unchanged.append(dict(name=record['name'],sha256=digest(path)))
    evidence=out/'验证记录'
    shutil.copy2(ROOT/'.cache/aefix_tests.log',evidence/'本次后台回归检查.txt')
    shutil.copy2(ROOT/'.cache/aefix_export.json',evidence/'本次导出回读.json')
    (evidence/'25款预设完整文件未改动.json').write_text(json.dumps(unchanged,ensure_ascii=False,indent=2),encoding='utf-8')
    smoke=r'''
import ast,faulthandler,io,sys,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from wotcamo import ae_presets,ae_effects as ae
program=Path.cwd();source=Path(sys.argv[1]);sys.path.append(str(source))
# Keep the packaged-runtime check read-only. File/HTTP regressions have their
# own guarded 59-test run; this process must not create temporary directories.
faulthandler.dump_traceback_later(45,file=sys.stderr)
records,issues=ae_presets.scan();assert len(records)==25 and not issues
for row in records:ae_presets.read(row['path'])
for file in (program/'wotcamo').rglob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
assert '同一车型' in ae.PACKAGE_CONFLICT_NOTE
assert all(b>a for a,b in zip([t for t,_ in ae.frame_keys(16,17,24)],[t for t,_ in ae.frame_keys(16,17,24)][1:]))
pixel=ae.colorize_rgba(Image.new('RGBA',(1,1),(255,0,0,128)),dict(tint_color='#00C8FF',tint_strength=100))
assert pixel.getpixel((0,0))==(0,200,255,128)
assert Image.open(io.BytesIO(ae.dds(pixel))).convert('RGBA').tobytes()==pixel.tobytes()
names=['tests.test_ae_review_fixes','tests.test_ae_preset_notes','tests.test_ae_sides']
with patch.object(tk.Tk,'__init__',side_effect=AssertionError('Window creation forbidden')),patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('Window creation forbidden')):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
if not result.wasSuccessful():raise SystemExit(1)
faulthandler.cancel_dump_traceback_later()
print('PACKAGED_25_PRESETS_15_GUARDED_CHECKS_AND_PIXEL_DDS_OK')
'''
    program=out/'程序'
    environment=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',
                     OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    with (evidence/'包内后台检查.txt').open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(program/'runtime/python.exe'),'-s','-B','-c',smoke,str(source),str(ROOT/'.cache/test_tmp')],
                              cwd=program,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=180,creationflags=0x08000000|0x40)
    if result.returncode:raise RuntimeError((evidence/'包内后台检查.txt').read_text(encoding='utf-8'))
    for file in (ROOT/'wotcamo').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            relative=file.relative_to(ROOT/'wotcamo')
            assert digest(file)==digest(program/'wotcamo'/relative)==digest(source/'wotcamo'/relative)
    assert not list(out.rglob('__pycache__'))
    entries=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
             for p in out.rglob('*') if p.is_file() and p!=out/'文件清单.json']
    (out/'文件清单.json').write_text(json.dumps(dict(product=APP_NAME,files=entries),ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in out.rglob('*'):
            if file.is_file():z.write(file,(Path(name)/file.relative_to(out)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in entries:
            with z.open(name+'/'+row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
        assert len(z.namelist())==len(entries)+1
    target.with_name(target.name+'.sha256').write_text(digest(target)+'  '+target.name+'\n',encoding='utf-8')
    print('AE_FIX_RELEASE_READY',str(target),target.stat().st_size,digest(target),flush=True)


if __name__=='__main__':main()
