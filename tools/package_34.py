"""Build an independent 3.4 portable release from the preserved 3.3 R1 ZIP."""
import argparse,ast,hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo.common import ROOT
from wotcamo import ae_presets

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def copy(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache','__pycache__','*.bak','result'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args();workspace=args.workspace.resolve()
    old='wot涂装工作台 3.3_35款预设版_R1';name='wot涂装工作台 3.4_AE外观调节版'
    base=workspace/'交付'/(old+'.zip');out=workspace/'交付'/name;source=out.with_name(name+'_源码')
    target=out.parent/(name+'.zip')
    if any(p.exists() for p in (out,source,target)):raise RuntimeError('目标已存在；请保留旧交付并改用新修订名。')
    assert digest(base)=='797cd6206dd7f7ed882813d28fa6759fe0d2125ca478190867b1292ad52c4429'
    for filename,count in [('appearance34_tests.log',79),('appearance34_ui.log',33)]:
        log=(ROOT/'.cache'/filename).read_text(encoding='utf-8')
        assert 'Ran %d tests'%count in log and '\nOK\n' in log
    with zipfile.ZipFile(base) as z:
        assert z.testzip() is None
        for entry in z.infolist():
            path=PurePosixPath(entry.filename);assert path.parts[0]==old and '..' not in path.parts
            parts=path.parts[1:]
            if not parts or parts[0]=='验证记录' or parts[-1]=='文件清单.json':continue
            if path.suffix=='.md' and (len(parts)==1 or (len(parts)==2 and parts[0]=='程序')):continue
            dest=out.joinpath(*parts);assert dest.resolve().is_relative_to(out.resolve())
            if entry.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            dest.parent.mkdir(parents=True,exist_ok=True)
            with z.open(entry) as inp,dest.open('wb') as output:shutil.copyfileobj(inp,output)
    (out/'启动wot涂装工作台 3.3.cmd').rename(out/'启动wot涂装工作台 3.4.cmd')
    program=out/'程序';copy(ROOT/'wotcamo',program/'wotcamo')
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    for parent in (out,program,source):
        for filename in ('README.md','3.4更新说明.md'):shutil.copy2(ROOT/filename,parent/filename)
    (out/'使用说明.txt').write_text('wot涂装工作台 3.4\n运行“启动wot涂装工作台 3.4.cmd”。\nAE 的“播放与透明”页提供亮度、对比度与透明度滑条，三维预览也可调整。亮度最高 100 倍。\n0% 透明度保留原透明度，100% 完全透明。旧成品需重新生成；游戏内效果待实测。\n',encoding='utf-8-sig')
    records,issues=ae_presets.scan(program/'预设/AE特效');assert len(records)==35 and not issues
    for row in records:
        ae_presets.read(row['path'])
        assert digest(row['path'])==digest(ROOT/'预设/AE特效'/row['path'].name)
    for p in (ROOT/'wotcamo').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            rel=p.relative_to(ROOT/'wotcamo');assert digest(p)==digest(program/'wotcamo'/rel)==digest(source/'wotcamo'/rel)
    evidence=out/'验证记录';evidence.mkdir()
    for file in ('appearance34_tests.log','appearance34_ui.log'):shutil.copy2(ROOT/'.cache'/file,evidence/file)
    env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    tests=['tests.test_ae_appearance','tests.test_ae_color','tests.test_ae_presets','tests.test_ae_effects','tests.test_ae_mirrorfix','tests.test_ae_review_fixes','tests.test_ae_sides','tests.test_ae_deform','tests.test_ae_surface']
    # Run the same backend suite against the exact shipped program/runtime.
    code="import sys,unittest;sys.path.append(sys.argv[1]);r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:]));raise SystemExit(0 if r.testsRun==79 and r.wasSuccessful() else 1)"
    with (evidence/'包内后台复核.txt').open('w',encoding='utf-8') as log:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B','-c',code,str(source),*tests],cwd=program,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=0x08000000)
    assert run.returncode==0,(evidence/'包内后台复核.txt').read_text(encoding='utf-8')
    with (evidence/'包内界面复核.txt').open('w',encoding='utf-8') as log:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B',str(source/'tools/check_ui33_isolated.py'),'--program',str(program),'--tests',str(source)],cwd=program,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=0x08000000)
    assert run.returncode==0,(evidence/'包内界面复核.txt').read_text(encoding='utf-8')
    verification=dict(version='3.4',base_sha256=digest(base),background_tests=79,isolated_desktop_tests=33,packaged_runtime_recheck=True,presets=35,
        export_test_scope='Synthetic fixtures; PNG/DDS equality and material gain/blend readback. No game or native shader execution.',
        actual_running_client='not_confirmed',in_game_tested=False,whole_vehicle_loading=dict(status='not_tested'),visual_effect_observation='not_tested')
    (evidence/'验证范围.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file()]
    (out/'文件清单.json').write_text(json.dumps(dict(product=name,files=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,(Path(name)/p.relative_to(out)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in rows:
            with z.open(name+'/'+row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(digest(target)+'  '+target.name+'\n',encoding='utf-8')
    print('RELEASE_34_READY',str(target),digest(target),flush=True)

if __name__=='__main__':main()
