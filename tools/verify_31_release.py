"""Check UI regressions and a real ZIP's reusable preset without changing its game archive."""
import json,os,shutil,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets
from wotcamo.common import ROOT

def main():
    folder=ROOT/'.cache/test_tmp';folder.mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(folder)
    with (ROOT/'.cache/unified31_regression.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    print('REGRESSION',result.testsRun,len(result.failures),len(result.errors),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)
    # Use the previously read-back native package. The 3.1 change adds a file to
    # the outer ZIP; hash the inner bytes again rather than rebuilding geometry.
    previous=ROOT.parent/'wot_workbench_3_armor'
    old_code=(previous/'wotcamo/ae_effects.py').read_text(encoding='utf-8').split('def bundle_delivery(')[0]
    new_code=(ROOT/'wotcamo/ae_effects.py').read_text(encoding='utf-8').split('def bundle_delivery(')[0]
    assert old_code==new_code
    summary=json.loads((previous/'.cache/armor_export_check_summary.json').read_text(encoding='utf-8'))
    data=json.loads((previous/'.cache/preset_browser/0/armor_project.json').read_text(encoding='utf-8'))
    out=ROOT/'.cache/zip_with_preset';out.mkdir()
    source=Path(summary['artifact']['path']);target=out/'3.1_预设打包检查.wotmod';os.link(source,target)
    for name in ('验证记录.json','使用说明.txt'):shutil.copy2(source.parent/name,out/name)
    delivery=ae.bundle_delivery(target,dict(artifact=summary['artifact']),data['project'],data['clip'],data['config'],False)
    with zipfile.ZipFile(delivery['path']) as z:
        assert z.testzip() is None
        with z.open(target.name) as stream:
            import hashlib
            actual=hashlib.file_digest(stream,'sha256').hexdigest()
        assert actual==summary['artifact']['sha256']==ae.engine.digest(source)
        assert not any(name.endswith('.aefx') for name in z.namelist())
        assert delivery['effect_preset'] in z.namelist()
    metadata,clip=ae_presets.load(target.with_suffix('.aepreset'),out/'reimported')
    assert metadata['config']['crop_left']==12 and metadata['config']['uv_scale_x']==1.6
    assert clip['atlas_sha256']==data['clip']['atlas_sha256']
    record=dict(delivery=delivery,native_archive_bytes_unchanged=True,
                recovered_preset=dict(name=metadata['name'],config=metadata['config'],atlas_sha256=clip['atlas_sha256']),
                baseline_client=summary['client'],in_game_tested=False,whole_vehicle_loading=summary['whole_vehicle_loading'])
    (ROOT/'.cache/zip_with_preset_check.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REAL_ZIP_PRESET_REIMPORT_OK',actual,flush=True)

if __name__=='__main__':main()
