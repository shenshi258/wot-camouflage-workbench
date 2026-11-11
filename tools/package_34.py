"""Build a versioned portable release from the preserved 3.3 R1 runtime ZIP."""
import argparse,ast,hashlib,json,os,re,shutil,subprocess,sys,unittest,zipfile
import importlib.metadata as package_metadata
import importlib.util as import_util
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo.common import ROOT
from wotcamo import ae_presets,__version__

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def copy(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache','__pycache__','*.bak','result'))

def main(version='3.4',label='AE外观调节版',ui_count=36,extra_tests=(),web_markers=(),preset_count=35,extra_guide='',runtime_packages=()):
    if version!=__version__:raise RuntimeError('打包器版本与源码不一致，请使用当前版本的打包入口。')
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--revision',default='')
    parser.add_argument('--backend-log',type=Path,default=ROOT/'.cache/appearance34_tests.log')
    parser.add_argument('--ui-log',type=Path,default=ROOT/'.cache/appearance34_ui.log')
    parser.add_argument('--web-log',type=Path)
    args=parser.parse_args();workspace=args.workspace.resolve()
    if args.revision and not re.fullmatch(r'R[1-9][0-9]*',args.revision):parser.error('修订名须为 R1、R2 等。')
    old='wot涂装工作台 3.3_35款预设版_R1';name='wot涂装工作台 '+version+'_'+label
    if args.revision:name+='_'+args.revision
    base=workspace/'交付'/(old+'.zip');out=workspace/'交付'/name;source=out.with_name(name+'_源码')
    target=out.parent/(name+'.zip')
    if any(p.exists() for p in (out,source,target)):raise RuntimeError('目标已存在；请保留旧交付并改用新修订名。')
    assert digest(base)=='797cd6206dd7f7ed882813d28fa6759fe0d2125ca478190867b1292ad52c4429'
    tests=['tests.test_ae_appearance','tests.test_ae_color','tests.test_ae_presets','tests.test_ae_effects','tests.test_ae_mirrorfix','tests.test_ae_review_fixes','tests.test_ae_sides','tests.test_ae_deform','tests.test_ae_surface','tests.test_glass32']
    tests+=list(extra_tests)
    backend_count=unittest.defaultTestLoader.loadTestsFromNames(tests).countTestCases()
    for path,count in [(args.backend_log,backend_count),(args.ui_log,ui_count)]:
        log=path.read_text(encoding='utf-8')
        assert 'Ran %d tests'%count in log and '\nOK\n' in log
    if web_markers:
        if not args.web_log:parser.error('当前版本需要三维预览交互检查记录。')
        log=args.web_log.read_text(encoding='utf-8')
        assert all(marker in log for marker in web_markers)
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
    (out/'启动wot涂装工作台 3.3.cmd').rename(out/('启动wot涂装工作台 '+version+'.cmd'))
    program=out/'程序';copy(ROOT/'wotcamo',program/'wotcamo');copy(ROOT/'预设',program/'预设')
    dependencies=[]
    for module_name,distribution_name in runtime_packages:
        spec=import_util.find_spec(module_name)
        if spec is None or not spec.submodule_search_locations:raise RuntimeError('缺少打包组件：'+module_name)
        package_dir=Path(spec.origin).parent
        copy(package_dir,program/'runtime/Lib/site-packages'/module_name)
        distribution=package_metadata.distribution(distribution_name)
        metadata_file=next(p for p in distribution.files if p.name=='METADATA' and str(p.parent).endswith('.dist-info'))
        metadata_dir=Path(distribution.locate_file(metadata_file)).parent
        copy(metadata_dir,program/'runtime/Lib/site-packages'/metadata_dir.name)
        dependencies.append(dict(module=module_name,distribution=distribution_name,version=distribution.version))
    for folder in ('wotcamo','tests','tools','config','blender','reference','预设'):copy(ROOT/folder,source/folder)
    # 项目介绍、双语更新说明及致谢保留在源码中，不附进便携包。
    for filename in ('README.md',version+'更新说明.md'):shutil.copy2(ROOT/filename,source/filename)
    (out/'使用说明.txt').write_text('wot涂装工作台 '+version+'\n运行“启动wot涂装工作台 '+version+'.cmd”。\n'+extra_guide+'AE 可复制/粘贴设置，在“长宽与贴合”选择等比适配或重复平铺；三维预览展开“缩放与裁剪”也可使用。\n亮度最高 100 倍；透明度 0% 保留原透明度，100% 完全透明。旧成品需重新生成；游戏内效果待实测。\n',encoding='utf-8-sig')
    records,issues=ae_presets.scan(program/'预设/AE特效');assert len(records)==preset_count and not issues
    for row in records:
        ae_presets.read(row['path'])
        assert digest(row['path'])==digest(ROOT/'预设/AE特效'/row['path'].name)
    for p in (ROOT/'wotcamo').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            rel=p.relative_to(ROOT/'wotcamo');assert digest(p)==digest(program/'wotcamo'/rel)==digest(source/'wotcamo'/rel)
    evidence=out/'验证记录';evidence.mkdir()
    for path in (args.backend_log,args.ui_log):shutil.copy2(path,evidence/path.name)
    if args.web_log:shutil.copy2(args.web_log,evidence/args.web_log.name)
    env=dict(os.environ,PYTHONHOME=str(program/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    # Run the same backend suite against the exact shipped program/runtime.
    code="import sys,unittest;sys.path.append(sys.argv[1]);r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:]));raise SystemExit(0 if r.testsRun==int(sys.argv[2]) and r.wasSuccessful() else 1)"
    with (evidence/'包内后台复核.txt').open('w',encoding='utf-8') as log:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B','-c',code,str(source),str(backend_count),*tests],cwd=program,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=0x08000000)
    assert run.returncode==0,(evidence/'包内后台复核.txt').read_text(encoding='utf-8')
    with (evidence/'包内界面复核.txt').open('w',encoding='utf-8') as log:
        run=subprocess.run([str(program/'runtime/python.exe'),'-s','-B',str(source/'tools/check_ui33_isolated.py'),'--program',str(program),'--tests',str(source)],cwd=program,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=0x08000000)
    assert run.returncode==0,(evidence/'包内界面复核.txt').read_text(encoding='utf-8')
    verification=dict(version=version,revision=args.revision,base_sha256=digest(base),background_tests=backend_count,isolated_desktop_tests=ui_count,preview_script_checks=list(web_markers),packaged_runtime_recheck=True,presets=preset_count,runtime_dependencies=dependencies,
        export_test_scope='Synthetic fixtures; PNG/DDS, material appearance, aspect fitting, per-tile clipping and preview/export geometry checks. No game or native shader execution.',
        actual_running_client='not_confirmed',in_game_tested=False,whole_vehicle_loading=dict(status='not_tested'),visual_effect_observation='not_tested')
    (evidence/'验证范围.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
    # 包内复核生成的临时会话不进入交付；仅打包经过清单校验的文件。
    rows=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file() and '.cache' not in p.relative_to(out).parts]
    (out/'文件清单.json').write_text(json.dumps(dict(product=name,files=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for row in rows:z.write(out/row['path'],name+'/'+row['path'])
        z.write(out/'文件清单.json',name+'/文件清单.json')
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in rows:
            with z.open(name+'/'+row['path']) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
    target.with_name(target.name+'.sha256').write_text(digest(target)+'  '+target.name+'\n',encoding='utf-8')
    print('RELEASE_READY',str(target),digest(target),flush=True)

if __name__=='__main__':main()
