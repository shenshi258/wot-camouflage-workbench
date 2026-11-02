"""Offline regression using the user's preserved Ares selection and EU baseline."""
import ctypes,hashlib,json,sys,zipfile
from ctypes import wintypes
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae
from wotcamo.common import ROOT

def main():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.SetPriorityClass.restype=wintypes.BOOL
    assert k.SetPriorityClass(wintypes.HANDLE(-1),0x40)
    workspace=ROOT.parents[1];folder=ROOT/'.cache/mirror_real_final';folder.mkdir(exist_ok=False)
    old=workspace/'改造区/Ares90_AE半边排查';project_path=old/'用户原工程.aefx'
    with zipfile.ZipFile(project_path) as z:data=json.loads(z.read('ae_project.json'))
    project=data['project'];project['source']=str(old/'还原工程/source.wotmod')
    with open(project['source'],'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==project['source_sha256']
    clip=dict(data['clip'],atlas=str(old/'还原工程/atlas.png'));c=ae.config(dict(data['config'],mirror=True))
    one=ae.geometry_plan(project,clip,dict(c,mirror=False),None)
    preview=ae.preview_data(clip,c,project,None)
    assert preview['original_vertex_count']==len(one['vertices']) and len(preview['vertices'])>len(one['vertices'])
    new=ae.new_plane_config(clip,c,preview);assert new['mirror'] and new['plane']=='side' and abs(new['x'])>.5
    source_bound=np.asarray(preview['vertices'])[:preview['original_vertex_count'],:3]
    np.testing.assert_allclose(new['x'],(source_bound[:,0].min()+source_bound[:,0].max())/2-.006)
    positions=ae.positions(ae.validate_bilateral_placement(new));assert len(positions)==2 and positions[0][0]*positions[1][0]<0
    print('ARES_SELECTED_SIDE_AND_MIRROR_OK',len(one['vertices'])//3,positions,flush=True)
    # User previously confirmed this original Pz70 skin in the EU client.
    source=workspace/'改造区/Pz70_水星野侧面流星_R1/原始涂装.wotmod';client='D:/wot/World_of_Tanks_EU'
    test_project=ae.source_project(source,folder/'source');test_project['baseline_user_confirmed']=True
    frames=[Image.new('RGBA',(16,8),(60+i*8,170,220,128)) for i in range(17)]
    test_clip=ae.pack_frames(frames,folder/'atlas.png')
    test_config=ae.config(dict(ae.new_plane_config(test_clip,dict(placement='plane',mirror=True,x=-1.82)),warp_tr_z=.5,warp_bl_z=-.4,angle=17))
    target,report=ae.build(test_project,test_clip,test_config,client,folder/'build','双侧开关回归检查')
    with zipfile.ZipFile(target) as z,zipfile.ZipFile(source) as original:
        assert z.testzip() is None
        for n in original.namelist():assert z.read(n)==original.read(n)
        seqs=sorted(n for n in z.namelist() if '/ae_import_' in n and n.endswith('.seq'));assert len(seqs)==2
        results=[]
        for n in seqs:
            root=ET.fromstring(z.read(n));objects=root.findall('sequenceObject')[1:];assert len(objects)==17
            position=next(t.findtext('frame/value') for t in objects[0].findall('track') if t.findtext('name')=='position')
            results.append(dict(frames=len(objects),position=position))
        assert results[0]['position']=='-1.82 0.0 0.0' and results[1]['position']=='1.82 0.0 0.0'
        for i in range(17):
            prefix=seqs[0].rsplit('/',1)[0]+'/'
            a=ae.mesh.sections(z.read(prefix+'frame_%03d.primitives_processed'%i))
            b=ae.mesh.sections(z.read(prefix+'frame_mirror_%03d.primitives_processed'%i))
            va,_=ae.mesh.vertex_data(a['vertices']);vb,_=ae.mesh.vertex_data(b['vertices'])
            np.testing.assert_allclose(vb[:,:3],va[:,:3]*[-1,1,1],atol=1e-6)
            np.testing.assert_allclose(vb[:,3:6],va[:,3:6]*[-1,1,1],atol=.01)
            np.testing.assert_allclose(vb[:,6:8],va[:,6:8],atol=1e-7)
            import struct
            count=struct.unpack_from('<I',a['indices'],64)[0]
            ia=np.frombuffer(a['indices'],dtype='<u2',count=count,offset=72).reshape(-1,3)
            ib=np.frombuffer(b['indices'],dtype='<u2',count=count,offset=72).reshape(-1,3)
            np.testing.assert_array_equal(ib,ia[:,[0,2,1]])
        assert all('frame_mirror_' in o.findtext('resource') for o in ET.fromstring(z.read(seqs[1])).findall('sequenceObject')[1:])
    assert report['whole_vehicle_loading']['status']=='not_tested'
    assert report['ae_effect']['geometry_frames']==34 and report['ae_effect']['geometry_variants']==2
    result=dict(ares_original_sha256=project['source_sha256'],ares_source_triangles=len(one['indices'])//3,
                ares_total_triangles=len(preview['indices'])//3,ares_plane_positions=positions,
                artifact=report['artifact'],client=report['client'],baseline=report['baseline'],file_validation=report['file_validation'],
                original_vehicle_resources_unchanged=True,actual_sequence_readback=results,mirrored_frame_readback=17,
                whole_vehicle_loading=report['whole_vehicle_loading'],in_game_tested=False)
    (ROOT/'.cache/mirror_real_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FINAL_NATIVE_SEQ_READBACK_OK',report['artifact']['sha256'],flush=True)

if __name__=='__main__':main()
