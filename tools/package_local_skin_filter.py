"""Package the independent cosmetic-filter helper with a clean stdlib/Tk runtime."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'standalone/local_skin_filter'


def digest(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);args=p.parse_args()
    workspace=args.workspace.resolve();name='本地涂装屏蔽 1.0_独立准备工具_待实测'
    out=workspace/'交付'/name;archive=out.with_name(name+'.zip')
    if out.exists()or archive.exists():raise RuntimeError('交付已存在，请保留旧版本并更换修订名。')
    donor=workspace/'交付/涂装仅本车转换器 1.0_独立便携版/runtime'
    if not(donor/'pythonw.exe').is_file():raise RuntimeError('缺少干净的便携运行环境。')
    out.mkdir(parents=True)
    production=[p for p in SOURCE.iterdir()if p.is_file()and not p.name.startswith('test_')and p.name!='README.md']
    for source in production:shutil.copy2(source,out/source.name)
    def ignore(folder,names):return list(names)if Path(folder).name=='site-packages'else[n for n in names if n=='__pycache__']
    shutil.copytree(donor,out/'runtime',ignore=ignore)
    launcher='@echo off\r\nchcp 65001 >nul\r\nsetlocal\r\ncd /d "%~dp0"\r\nset "PYTHONHOME=%~dp0runtime"\r\nset "PYTHONNOUSERSITE=1"\r\nset "PYTHONPATH="\r\nstart "" "%~dp0runtime\\pythonw.exe" -s -B "%~dp0entry.py"\r\n'
    (out/'启动本地涂装屏蔽.cmd').write_bytes(launcher.encode('utf-8'))
    evidence=out/'验证记录';evidence.mkdir()
    env=dict(os.environ,PYTHONHOME=str(out/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    python=out/'runtime/python.exe'
    with tempfile.TemporaryDirectory(prefix='packaged_filter_tests_',dir=ROOT/'.cache')as folder:
        tests=Path(folder)
        for source in SOURCE.glob('test_*.py'):shutil.copy2(source,tests/source.name)
        shutil.copy2(SOURCE/'filter_runtime.py.txt',tests/'filter_runtime.py.txt')
        code="import sys,unittest;from pathlib import Path;sys.path[:0]=sys.argv[1:3];import filter_builder;assert Path(filter_builder.__file__).resolve().is_relative_to(Path(sys.argv[1]));r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_filter'));raise SystemExit(not r.wasSuccessful())"
        for filename,command in [('包内后台检查.txt',[str(python),'-s','-B','-c',code,str(out),str(tests)]),
          ('包内界面检查.txt',[str(python),'-s','-B',str(ROOT/'tools/check_filter_ui.py'),'--program',str(out),'--tests',str(tests)])]:
            with(evidence/filename).open('w',encoding='utf-8')as log:
                run=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90,creationflags=0x08000000)
            if run.returncode:raise RuntimeError((evidence/filename).read_text('utf-8'))
    for source in production:
        if digest(source)!=digest(out/source.name):raise RuntimeError('交付文件与源码不一致。')
    (evidence/'验证范围.json').write_text(json.dumps(dict(app=name,backend_tests=14,ui_tests=5,
        independent_from_workbench=True,installs_or_modifies_game=False,
        in_game_tested=False,whole_vehicle_loading=dict(status='not_tested'),anti_cheat_approval='not_reviewed'),ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[dict(path=p.relative_to(out).as_posix(),sha256=digest(p),bytes=p.stat().st_size)for p in out.rglob('*')if p.is_file()]
    (out/'文件清单.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for row in rows:z.write(out/row['path'],name+'/'+row['path'])
        z.write(out/'文件清单.json',name+'/文件清单.json')
    with zipfile.ZipFile(archive)as z:
        if z.testzip():raise RuntimeError('ZIP 校验失败。')
        for row in rows:
            with z.open(name+'/'+row['path'])as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=row['sha256']:raise RuntimeError('清单不一致。')
    archive.with_name(archive.name+'.sha256').write_text(digest(archive)+'  '+archive.name+'\n',encoding='utf-8')
    source_zip=workspace/'交付/本地涂装屏蔽 1.0_源码.zip'
    with zipfile.ZipFile(source_zip,'x',zipfile.ZIP_DEFLATED)as z:
        for path in SOURCE.rglob('*'):
            if path.is_file()and'__pycache__'not in path.parts:z.write(path,'local_skin_filter/'+path.relative_to(SOURCE).as_posix())
        for name in('check_filter_ui.py','check_filter_runtime27.py','inspect_skin_filter_client.py','package_local_skin_filter.py'):
            z.write(ROOT/'tools'/name,'tools/'+name)
    with zipfile.ZipFile(source_zip)as z:
        if z.testzip():raise RuntimeError('源码 ZIP 校验失败。')
    print('PORTABLE',archive,digest(archive),archive.stat().st_size)
    print('SOURCE',source_zip,digest(source_zip),source_zip.stat().st_size)


if __name__=='__main__':main()
