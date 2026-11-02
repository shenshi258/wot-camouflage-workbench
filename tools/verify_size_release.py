"""Independent-axis browser roundtrip and expanded armour export/readback."""
import json,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets
from wotcamo.common import ROOT

def main():
    folder=ROOT/'.cache/test_tmp';folder.mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(folder)
    with (ROOT/'.cache/size_regression.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    print('REGRESSION',result.testsRun,len(result.failures),len(result.errors),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)
    subprocess.run([sys.executable,'-m','tests.run_requested_preset_preview','0','--armor','--size','--hidden'],cwd=ROOT,check=True)
    folder=ROOT/'.cache/preset_browser/0'
    data=json.loads((folder/'armor_project.json').read_text(encoding='utf-8'))
    project=data['project'];project['baseline_user_confirmed']=True
    target,report=ae.build(project,data['clip'],data['config'],'D:/wot/World_of_Tanks_EU',ROOT/'.cache/size_export','自由长宽与整块装甲_离线检查')
    with zipfile.ZipFile(project['source']) as original,zipfile.ZipFile(target) as built:
        assert built.testzip() is None
        for name in original.namelist():assert built.read(name)==original.read(name)
    assert report['whole_vehicle_loading']['status']=='not_tested'
    delivery=ae.bundle_delivery(target,report,project,data['clip'],data['config'],False)
    recovered,clip=ae_presets.load(target.with_suffix('.aepreset'),ROOT/'.cache/reimported_size')
    assert recovered['config']['uv_scale_x']==1.6 and recovered['config']['uv_scale_y']==.7
    assert clip['atlas_sha256']==data['clip']['atlas_sha256']
    summary=dict(artifact=report['artifact'],client=report['client'],whole_vehicle_loading=report['whole_vehicle_loading'],in_game_tested=False,
                 original_vehicle_bytes_unchanged=True,preset_parameters=recovered['config'],delivery=delivery)
    (ROOT/'.cache/size_check.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('EXPANDED_ARMOR_EXPORT_PRESET_OK',report['artifact']['sha256'],flush=True)

if __name__=='__main__':main()
