"""Create a standalone distribution with a clean stdlib/Tk runtime, then recheck it."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'standalone/self_skin_converter'
MODULES=('test_builder','test_client_probe','test_client_pyc','test_insignia_adapter',
         'test_output_checks','test_batch_convert','test_self_runtime','test_uml_adapter','test_ae_adapter')


def digest(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True)
    args=p.parse_args();workspace=args.workspace.resolve();name='涂装仅本车转换器 1.0_独立便携版'
    out=workspace/'交付'/name;archive=out.with_name(name+'.zip')
    if out.exists()or archive.exists():raise RuntimeError('交付已存在，请保留旧版并使用新修订。')
    donor=workspace/'交付/wot涂装工作台 3.9_涂装应用范围版/程序/runtime'
    if not(donor/'pythonw.exe').is_file():raise RuntimeError('缺少便携 Python/Tk 运行环境。')
    out.mkdir(parents=True)
    production=[p for p in SOURCE.iterdir()if p.is_file()and not p.name.startswith('test_')and p.name!='README.md']
    for source in production:shutil.copy2(source,out/source.name)
    def ignore(folder,names):
        # This app uses only stdlib/Tk: no NumPy, Pillow, OpenCV, browser or AE presets.
        return list(names)if Path(folder).name=='site-packages'else[n for n in names if n=='__pycache__']
    shutil.copytree(donor,out/'runtime',ignore=ignore)
    launcher='@echo off\r\nchcp 65001 >nul\r\nsetlocal\r\ncd /d "%~dp0"\r\nset "PYTHONHOME=%~dp0runtime"\r\nset "PYTHONNOUSERSITE=1"\r\nset "PYTHONPATH="\r\nstart "" "%~dp0runtime\\pythonw.exe" -s -B "%~dp0entry.py"\r\n'
    (out/'启动涂装仅本车转换器.cmd').write_bytes(launcher.encode('utf-8'))
    evidence=out/'验证记录';evidence.mkdir()
    env=dict(os.environ,PYTHONHOME=str(out/'runtime'),PYTHONNOUSERSITE='1',PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    python=out/'runtime/python.exe'
    with tempfile.TemporaryDirectory(prefix='packaged_self_tests_',dir=ROOT/'.cache')as folder:
        tests=Path(folder)
        for source in SOURCE.glob('test_*.py'):shutil.copy2(source,tests/source.name)
        for source in SOURCE.glob('*.txt'):shutil.copy2(source,tests/source.name)
        code="import sys,unittest;from pathlib import Path;sys.path[:0]=sys.argv[1:3];import builder,ae_adapter;assert Path(builder.__file__).resolve().is_relative_to(Path(sys.argv[1]));r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:]));raise SystemExit(not r.wasSuccessful())"
        with(evidence/'包内后台检查.txt').open('w',encoding='utf-8')as log:
            run=subprocess.run([str(python),'-s','-B','-c',code,str(out),str(tests),*MODULES],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000)
        if run.returncode:raise RuntimeError((evidence/'包内后台检查.txt').read_text(encoding='utf-8'))
        with(evidence/'包内界面检查.txt').open('w',encoding='utf-8')as log:
            run=subprocess.run([str(python),'-s','-B',str(ROOT/'tools/check_converter_ui.py'),'--program',str(out),'--tests',str(tests)],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90,creationflags=0x08000000)
        if run.returncode:raise RuntimeError((evidence/'包内界面检查.txt').read_text(encoding='utf-8'))
    for source in production:
        if digest(source)!=digest(out/source.name):raise RuntimeError('独立程序源文件不一致。')
    # Freeze provenance before normal GUI use creates .cache or conversion output.
    (evidence/'验证范围.json').write_text(json.dumps(dict(app=name,backend_tests=36,ui_tests=5,
        independent_from_workbench=True,third_party_scripts='known insignia registrations and exact AE-template matches only',
        uml='swapNPC False; activation, whitelist and all non-profile resources preserved',
        in_game_tested=False,whole_vehicle_loading=dict(status='not_tested')),ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[dict(path=p.relative_to(out).as_posix(),sha256=digest(p),bytes=p.stat().st_size)for p in out.rglob('*')if p.is_file()and '.cache'not in p.relative_to(out).parts]
    (out/'文件清单.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for row in rows:z.write(out/row['path'],name+'/'+row['path'])
        z.write(out/'文件清单.json',name+'/文件清单.json')
    with zipfile.ZipFile(archive)as z:
        if z.testzip():raise RuntimeError('独立程序 ZIP 校验失败。')
        for row in rows:
            with z.open(name+'/'+row['path'])as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=row['sha256']:raise RuntimeError('独立程序清单不一致。')
    archive.with_name(archive.name+'.sha256').write_text(digest(archive)+'  '+archive.name+'\n',encoding='utf-8')
    print('STANDALONE_READY',archive,digest(archive),archive.stat().st_size)


if __name__=='__main__':main()
