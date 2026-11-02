"""Read-only client build check; never launch a viewer or install the result."""
import ctypes
import json
import sys
import zipfile
from ctypes import wintypes
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets,preview3d_assets as assets
from wotcamo.common import ROOT


def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.SetPriorityClass.restype=wintypes.BOOL
    assert kernel.SetPriorityClass(wintypes.HANDLE(-1),0x00100000)
    workspace=ROOT.parents[1];work=ROOT/'.cache/aefix_export';work.mkdir(exist_ok=False)
    source=workspace/'改造区/Pz70_水星野侧面流星_R1/原始涂装.wotmod'
    client=Path('D:/wot/World_of_Tanks_EU')
    project=ae.source_project(source,work/'source');project['baseline_user_confirmed']=True
    # The baseline is the user's earlier EU-client confirmation, not our observation.
    images=[Image.new('RGBA',(16,8),(80+i*9,160,220,128)) for i in range(17)]
    clip=ae.pack_frames(images,work/'atlas.png')
    c=ae.config(dict(fps=24,mirror=True,warp_tr_y=.15,crop_bottom=5,tint_color='#80DFFF',tint_strength=40))
    target,report=ae.build(project,clip,c,client,work/'build','17帧时间边界_离线检查')
    tracks=0
    with zipfile.ZipFile(target) as z,zipfile.ZipFile(source) as original:
        assert z.testzip() is None
        for entry in z.infolist():assert entry.compress_type==zipfile.ZIP_STORED
        for name in original.namelist():assert z.read(name)==original.read(name)
        seqs=[name for name in z.namelist() if name.endswith('.seq') and '/ae_import_' in name]
        assert len(seqs)==2
        for name in seqs:
            root=ET.fromstring(z.read(name))
            for tr in root.findall('.//track'):
                if tr.findtext('name')!='scale':continue
                frames=tr.findall('frame');times=np.array([float(f.findtext('startTime')) for f in frames])
                assert np.all(np.diff(times)>0)
                with np.errstate(all='raise'):
                    result=assets.evaluate_track(frames,np.r_[times,(times[:-1]+times[1:])/2])
                assert np.isfinite(result).all();tracks+=1
    assert tracks==34 and report['whole_vehicle_loading']['status']=='not_tested'
    assert ae.PACKAGE_CONFLICT_NOTE in (target.parent/'使用说明.txt').read_text(encoding='utf-8-sig')
    bundle=ae.bundle_delivery(target,report,project,clip,c,True)
    restored,restored_clip,values=ae.load_project(target.with_suffix('.aefx'),work/'restored')
    metadata,_=ae_presets.read(target.with_suffix('.aepreset'))
    assert values==c and metadata['config']['fps']==24 and metadata['clip']['frames']==17
    result=dict(artifact=report['artifact'],client=report['client'],baseline=report['baseline'],
                source_sha256=project['source_sha256'],original_resources_unchanged=True,
                strictly_increasing_and_finite_scale_tracks=tracks,mirrored_sequences=len(seqs),
                file_validation=report['file_validation'],delivery=bundle,
                editable_project_roundtrip=True,conflict_note_in_delivery=True,
                whole_vehicle_loading=report['whole_vehicle_loading'],in_game_tested=False,no_windows_started=True)
    (ROOT/'.cache/aefix_export.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL_ARCHIVE_TRACKS_AND_BUNDLE_OK',report['artifact']['sha256'],flush=True)


if __name__=='__main__':main()
