"""Build and verify the portable AE compaction update using the 4.0 runtime."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED


SOURCE = Path(__file__).resolve().parents[1]
WORKSPACE = SOURCE.parents[1]
DELIVERY = WORKSPACE / '交付'
BASE_PRODUCT = 'wot涂装工作台 4.0'
PRODUCT = 'wot涂装工作台 4.1_成品无损精简版'
BASE_HASH = '164978c6483cd1e540a182069bf5588e3701611494cc3ac17bf4a4dd177b3826'
PATCHED_MODULES = ('__init__.py', 'ae_atlas.py', 'ae_effects.py')
BACKEND_TESTS = ('test_ae_animation', 'test_ae_animation_pipeline', 'test_ae_appearance',
    'test_ae_color', 'test_ae_deform', 'test_ae_effects', 'test_ae_export_compaction',
    'test_ae_media', 'test_ae_mirrorfix', 'test_ae_pattern', 'test_ae_presets',
    'test_ae_preset_nodes', 'test_ae_review_fixes', 'test_ae_sides', 'test_ae_surface',
    'test_ae_thin', 'test_asset_library', 'test_light_dependency_gate310', 'test_paint3d')


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def invoke(runtime, args, cwd):
    env = dict(os.environ, PYTHONHOME=str(runtime.parent), PYTHONPATH='', PYTHONNOUSERSITE='1',
               PYTHONIOENCODING='utf-8')
    run = subprocess.run([str(runtime), '-B', '-s', *args], env=env, cwd=cwd, capture_output=True,
                         encoding='utf-8', errors='replace', timeout=180)
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    return run.stdout + run.stderr


def measure(runtime, program):
    probe = SOURCE / 'tools/measure_ae_export_size.py'
    command = ("import runpy,sys; sys.path.insert(0,sys.argv[1]); "
               "probe=sys.argv[2]; sys.argv=[probe]; runpy.run_path(probe,run_name='__main__')")
    output = invoke(runtime, ['-c', command, str(program), str(probe)], program)
    return json.loads(output.strip().splitlines()[-1])


def check_hidden_preview(runtime, program):
    """Exercise the real AE playback widget without opening a user window."""
    script = """
from pathlib import Path
import tempfile
import time
import tkinter as tk
from PIL import Image
from wotcamo import APP_NAME, ae_effects as ae
from wotcamo.ae_media_gui import ClipPreview

assert APP_NAME == 'wot涂装工作台 4.1'
with tempfile.TemporaryDirectory(prefix='ae_hidden_preview_') as folder:
    frames = [Image.new('RGBA', (32, 16), value) for value in ((250, 0, 0, 200), (0, 250, 0, 200))]
    clip = ae.pack_frames(frames, Path(folder) / 'preview.png')
    root = tk.Tk()
    root.withdraw()
    try:
        preview = ClipPreview(root, clip, {'fps': 5})
        preview.withdraw()
        seen = [preview.last_frame]
        end = time.monotonic() + 1.2
        while time.monotonic() < end and len(seen) < 3:
            root.update()
            if preview.last_frame != seen[-1]:
                seen.append(preview.last_frame)
            time.sleep(.01)
        assert seen == [0, 1, 0], seen
        preview.destroy()
        root.update()
    finally:
        root.destroy()
print('PASS: packaged 4.1 preview advances and loops with the real Tk component.')
"""
    return invoke(runtime, ['-c', script], program)


def main():
    base = DELIVERY / (BASE_PRODUCT + '.zip')
    target = DELIVERY / (PRODUCT + '.zip')
    assert digest(base) == BASE_HASH
    if target.exists():
        raise FileExistsError(target)
    with tempfile.TemporaryDirectory(prefix='wot_workbench_41_', dir=WORKSPACE / '改造区') as folder:
        build = Path(folder).resolve()
        assert build.parent == (WORKSPACE / '改造区').resolve()
        assert build.name.startswith('wot_workbench_41_')
        with ZipFile(base) as z:
            paths = z.namelist()
            assert all(n.startswith(BASE_PRODUCT + '/') and '..' not in n.split('/') for n in paths)
            z.extractall(build)
        package = build / BASE_PRODUCT
        program = package / '程序'
        runtime = program / 'runtime/python.exe'
        before = measure(runtime, program)

        for name in PATCHED_MODULES:
            shutil.copyfile(SOURCE / 'wotcamo' / name, program / 'wotcamo' / name)
        after = measure(runtime, program)
        assert before['version'] == '4.0' and after['version'] == '4.1'
        for name in ('repeated', 'unique', 'grid'):
            a, b = before[name], after[name]
            for key in ('frames', 'frame_size', 'fps', 'seconds', 'pixel_sha256'):
                assert a[key] == b[key], (name, key)
            assert b['bytes'] < a['bytes'], (name, a['bytes'], b['bytes'])
        assert after['repeated']['model_count'] == 12
        assert after['grid']['dds_bytes'] < before['grid']['dds_bytes']

        print('Measured AE size by case:', {name: (before[name]['bytes'], after[name]['bytes'])
              for name in ('repeated', 'unique', 'grid')}, flush=True)
        load_tests = ("import sys,unittest; sys.path[:0]=[*sys.argv[1:3],sys.argv[2]+'/tests']; "
                      "unittest.main(module=None,argv=['unittest',*sys.argv[3:]])")
        backend = invoke(runtime, ['-c', load_tests, str(program), str(SOURCE),
                                  *('tests.' + test for test in BACKEND_TESTS)], program)
        print('Backend AE suite passed', flush=True)
        ui = check_hidden_preview(runtime, program)
        print('Packaged hidden AE preview passed', flush=True)

        evidence = package / '验证记录'
        evidence.rename(package / '4.0基线验证记录')
        evidence.mkdir()
        (evidence / 'AE导出体积对比.json').write_text(json.dumps(dict(before=before, after=after,
            scope='Synthetic source. Actual workbench export/ZIP readback. No game loading.'),
            indent=2, ensure_ascii=False), encoding='utf-8')
        (evidence / '包内后台复核.txt').write_text(backend, encoding='utf-8')
        (evidence / '包内界面复核.txt').write_text(ui, encoding='utf-8')
        launcher = package / ('启动' + BASE_PRODUCT + '.cmd')
        launcher.rename(package / '启动wot涂装工作台 4.1.cmd')
        guide = package / '使用说明.txt'
        previous = guide.read_text(encoding='utf-8-sig').replace(BASE_PRODUCT, 'wot涂装工作台 4.1')
        guide.write_text(previous + '\nAE 成品自动共用相同画面和模型、缩小图集空位。导出维持播放帧数、帧率、'
                         '分辨率和每帧像素。游戏包只放 DDS，编辑工程和预设仍保留原图集。'
                         '请打开原 AE 工程或预设重新生成成品。\n'
                         '现有底包资源原样保留。新版游戏内表现仍待确认。\n', encoding='utf-8-sig')
        manifest_path = package / '文件清单.json'
        rows = []
        for path in sorted(package.rglob('*')):
            rel = path.relative_to(package)
            if path.is_file() and path != manifest_path and not {'.cache', '__pycache__'} & set(rel.parts):
                rows.append(dict(path=rel.as_posix(), bytes=path.stat().st_size, sha256=digest(path)))
        manifest_path.write_text(json.dumps(dict(product=PRODUCT, base_sha256=BASE_HASH, files=rows),
                                            ensure_ascii=False, indent=2), encoding='utf-8')
        staged_zip = build / target.name
        with ZipFile(staged_zip, 'x', ZIP_DEFLATED, compresslevel=6) as z:
            for row in rows:
                z.write(package / row['path'], PRODUCT + '/' + row['path'])
            z.write(manifest_path, PRODUCT + '/文件清单.json')
        with ZipFile(staged_zip) as z:
            for row in rows:
                with z.open(PRODUCT + '/' + row['path']) as f:
                    assert hashlib.file_digest(f, 'sha256').hexdigest() == row['sha256']
            assert len(z.namelist()) == len(rows) + 1
            assert z.read(PRODUCT + '/文件清单.json') == manifest_path.read_bytes()
        staged_zip.rename(target)
    target.with_name(target.name + '.sha256').write_text(digest(target) + '  ' + target.name + '\n', encoding='utf-8')
    print(json.dumps(dict(path=str(target), comparison=dict(before=before, after=after)), ensure_ascii=False))


if __name__ == '__main__':
    main()
