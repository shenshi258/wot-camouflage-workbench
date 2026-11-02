"""Offline-only release checks for draggable animated planes."""
import json,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets
from wotcamo.common import ROOT

def main():
    folder=ROOT/'.cache/test_tmp';folder.mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(folder)
    with (ROOT/'.cache/deform_regression.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    print('REGRESSION',result.testsRun,len(result.failures),len(result.errors),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)
    subprocess.run([sys.executable,'-m','tests.run_requested_preset_preview','0','--deform','--hidden'],cwd=ROOT,check=True)
    folder=ROOT/'.cache/preset_browser/0'
    browser=json.loads((folder/'browser_report.json').read_text(encoding='utf-8'))
    assert not browser.get('error') and len(browser['deform']['stages'])==5
    data=json.loads((folder/'armor_project.json').read_text(encoding='utf-8'))
    # Export the actually dragged shape, rather than the reset rectangle.
    c=ae.config(browser['deform']['stages'][-1]['after']['config'])
    project=data['project'];project['baseline_user_confirmed']=True
    target,report=ae.build(project,data['clip'],c,'D:/wot/World_of_Tanks_EU',ROOT/'.cache/deform_export','拖动变形平面_离线检查')
    with zipfile.ZipFile(project['source']) as original,zipfile.ZipFile(target) as built:
        assert built.testzip() is None
        for name in original.namelist():assert built.read(name)==original.read(name)
        manifest=json.loads(built.read(next(n for n in built.namelist() if n.endswith('/manifest.json') and '/ae_import_' in n)))
        np.testing.assert_allclose(manifest['preview']['corners'],browser['deform']['stages'][-1]['after']['corners'])
    assert report['whole_vehicle_loading']['status']=='not_tested'
    delivery=ae.bundle_delivery(target,report,project,data['clip'],c,True)
    recovered,clip=ae_presets.load(target.with_suffix('.aepreset'),ROOT/'.cache/reimported_deform')
    restored,restored_clip,saved=ae.load_project(target.with_suffix('.aefx'),ROOT/'.cache/reimported_project')
    assert saved==c
    for key in ae.WARPS:assert recovered['config'][key]==c[key]
    assert clip['atlas_sha256']==data['clip']['atlas_sha256']
    summary=dict(artifact=report['artifact'],client=report['client'],whole_vehicle_loading=report['whole_vehicle_loading'],in_game_tested=False,
                 original_vehicle_bytes_unchanged=True,preset_parameters=recovered['config'],delivery=delivery,
                 dragged_corner_export_parity=True,editable_project_positions_and_shape_preserved=True)
    (ROOT/'.cache/deform_check.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DRAGGED_PLANE_EXPORT_PRESET_PROJECT_OK',report['artifact']['sha256'],flush=True)

if __name__=='__main__':main()
