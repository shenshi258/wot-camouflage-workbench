"""Build/read an offline-only EU Pz70 sample from the actual glass preset."""
import ctypes,hashlib,json,struct,sys,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets
from wotcamo.common import ROOT

def main():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    assert k.SetPriorityClass(ctypes.c_void_p(-1),0x40)
    workspace=ROOT.parents[1];folder=ROOT/'.cache/glass_native_final';folder.mkdir(exist_ok=False)
    source=workspace/'改造区/Pz70_水星野侧面流星_R1/原始涂装.wotmod';client='D:/wot/World_of_Tanks_EU'
    preset=workspace/'交付/液态玻璃AE预设_新增2款/34 液态玻璃水滴.aepreset'
    data,clip=ae_presets.load(preset,folder/'preset');project=ae.source_project(source,folder/'source')
    project['baseline_user_confirmed']=True
    values=ae.config(dict(data['config'],placement='plane',mirror=True,x=-1.82,warp_tr_z=.5,warp_bl_z=-.4,angle=17))
    assert values['blend']=='alpha' and clip['frames']==96
    target,report=ae.build(project,clip,values,client,folder/'build','玻璃双侧离线检查')
    with zipfile.ZipFile(target) as z,zipfile.ZipFile(source) as original:
        assert z.testzip() is None
        for n in original.namelist():assert z.read(n)==original.read(n)
        seqs=sorted(n for n in z.namelist() if '/ae_import_' in n and n.endswith('.seq'));assert len(seqs)==2
        prefix=seqs[0].rsplit('/',1)[0]+'/'
        for side,n in enumerate(seqs):
            objects=ET.fromstring(z.read(n)).findall('sequenceObject')[1:];assert len(objects)==96
            for i,obj in enumerate(objects):
                expected=('frame_mirror_' if side else 'frame_')+('%03d'%i)
                assert expected in obj.findtext('resource')
                visual=ET.fromstring(z.read(prefix+expected+'.visual_processed'))
                props={p.text.strip():p[0].text for p in visual.findall('.//property') if p.text and len(p)}
                assert props['srcBlend']=='5' and props['destBlend']=='6'
        for i in range(96):
            a=ae.mesh.sections(z.read(prefix+'frame_%03d.primitives_processed'%i))
            b=ae.mesh.sections(z.read(prefix+'frame_mirror_%03d.primitives_processed'%i))
            va,_=ae.mesh.vertex_data(a['vertices']);vb,_=ae.mesh.vertex_data(b['vertices'])
            np.testing.assert_allclose(vb[:,:3],va[:,:3]*[-1,1,1],atol=1e-6)
            np.testing.assert_allclose(vb[:,3:6],va[:,3:6]*[-1,1,1],atol=.01)
            np.testing.assert_allclose(vb[:,6:8],va[:,6:8],atol=1e-7)
            count=struct.unpack_from('<I',a['indices'],64)[0]
            ia=np.frombuffer(a['indices'],dtype='<u2',count=count,offset=72).reshape(-1,3)
            ib=np.frombuffer(b['indices'],dtype='<u2',count=count,offset=72).reshape(-1,3)
            np.testing.assert_array_equal(ib,ia[:,[0,2,1]])
    assert report['whole_vehicle_loading']['status']=='not_tested'
    assert report['ae_effect']['geometry_frames']==192 and report['ae_effect']['geometry_variants']==2
    result=dict(preset_sha256=hashlib.sha256(preset.read_bytes()).hexdigest(),artifact=report['artifact'],client=report['client'],
      baseline=report['baseline'],file_validation=report['file_validation'],mirrored_frames=96,material_readback=192,
      blend='SRCALPHA / INVSRCALPHA',original_vehicle_resources_unchanged=True,
      whole_vehicle_loading=report['whole_vehicle_loading'],in_game_tested=False)
    (ROOT/'.cache/glass_native_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('GLASS_NATIVE_READBACK_OK',report['artifact']['sha256'],flush=True)

if __name__=='__main__':main()
