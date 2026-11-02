"""UI/HTTP regressions, real browser roundtrips and one offline vehicle-package readback."""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo.common import ROOT
from wotcamo import ae_effects as ae


def main():
    folder=ROOT/'.cache/test_tmp';folder.mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(folder)
    with (ROOT/'.cache/armor_regression.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    print('REGRESSION',result.testsRun,len(result.failures),len(result.errors),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)
    for index in range(4):
        args=[sys.executable,'-m','tests.run_requested_preset_preview',str(index)]
        if index==0:args.append('--armor')
        subprocess.run(args,cwd=ROOT,check=True)
    data=json.loads((ROOT/'.cache/preset_browser/0/armor_project.json').read_text(encoding='utf-8'))
    project=data['project'];original=ae.engine.digest(project['source'])
    # This is the user's earlier baseline confirmation, not an agent game test.
    project['baseline_user_confirmed']=True
    output=ROOT/'.cache/armor_export_check'
    target,report=ae.build(project,data['clip'],data['config'],'D:/wot/World_of_Tanks_EU',output,'装甲吸附裁剪_离线检查')
    with zipfile.ZipFile(project['source']) as old,zipfile.ZipFile(target) as new:
        assert new.testzip() is None
        for name in old.namelist():assert new.read(name)==old.read(name)
    assert ae.engine.digest(project['source'])==original
    assert report['whole_vehicle_loading']['status']=='not_tested'
    summary=dict(artifact=report['artifact'],input_sha256=original,
                 original_vehicle_bytes_unchanged=True,client=report.get('client'),
                 config=data['config'],snap_origin=project['ae_surface_origin'],
                 whole_vehicle_loading=report['whole_vehicle_loading'],in_game_tested=False)
    (ROOT/'.cache/armor_export_check_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('OFFLINE_EXPORT_READBACK_OK',report['artifact']['sha256'],flush=True)


if __name__=='__main__':main()
