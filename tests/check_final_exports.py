"""Offline integration on the user's preserved Pz70 baseline; no game installation."""
import copy,json,sys,zipfile
from pathlib import Path
import numpy as np
from wotcamo import ae_effects as ae,area_selection,preview3d_assets as assets,light_effects as engine,light_delivery
from wotcamo.common import ROOT

folder=ROOT/'.cache/final_integration_v2';folder.mkdir(parents=True,exist_ok=True)
initial=json.loads((ROOT/'.cache/ae_integration/session_input.json').read_text(encoding='utf-8'))
project=initial['project'];clip=initial['clip'];client=Path('D:/wot/World_of_Tanks_EU')
body=assets.make_body(project,client,folder/'body')
chosen=None
for index,item in enumerate(body['meshes']):
    if item['part']!='hull':continue
    v=np.fromfile(folder/'body'/item['vertex'],dtype='<f4').reshape(-1,item['stride']);ids=np.fromfile(folder/'body'/item['index'],dtype='<u4').reshape(-1,3)
    center=v[ids,:3].mean(1);norm=v[ids,3:6].mean(1)
    pick=np.where((center[:,0]<-1.5)&(np.abs(center[:,1])<.5)&(center[:,2]>-2)&(center[:,2]<1.8)&(norm[:,0]<-.8))[0]
    if len(pick)>8:chosen=index,pick[:300].tolist();break
if chosen is None:raise RuntimeError('No suitable side faces found')
results={}
for name,triangles,mode in [('单面',[chosen[1][0]],'surface'),('区域播放',chosen[1],'surface'),('区域发光',chosen[1],'surface_glow')]:
    p=copy.deepcopy(project);p['baseline_user_confirmed']=True;p['ae_selection']=area_selection.resolve(body,[dict(mesh=chosen[0],triangles=triangles)])
    c=ae.config(dict(placement=mode,plane='auto',blend='alpha' if mode=='surface' else 'add',fps=12))
    target,report=ae.build(p,clip,c,client,folder/name,name)
    plan=ae.preview_data(clip,c,p,client)
    with zipfile.ZipFile(target) as z:
        manifest_name=next(n for n in z.namelist() if ae.MANIFEST.fullmatch(n));manifest=json.loads(z.read(manifest_name));prefix=manifest_name.rsplit('/',1)[0]+'/'
        ss=ae.mesh.sections(z.read(prefix+'frame_000.primitives_processed'));verts,_=ae.mesh.vertex_data(ss['vertices'])
        # Hull rigid overlays share bind space directly; exact final readback
        # must agree with the geometry sent to the browser (up to float32).
        assert np.max(abs(verts[:,:3]-np.asarray(plan['vertices'])[:,:3]))<1e-5
        assert np.max(abs(verts[:,6:8]-np.asarray(plan['vertices'])[:,6:8]))<1e-6
    ae.save_project(folder/name/'工程.aefx',p,clip,c)
    p2,clip2,c2=ae.load_project(folder/name/'工程.aefx',folder/name/'reopened')
    plan2=ae.preview_data(clip2,c2,p2,client);assert plan2['indices']==plan['indices']
    results[name]=dict(artifact=report['artifact'],file_validation=report['file_validation'],selected_triangles=len(triangles),preview_vertices=len(plan['vertices']),preview_export_geometry_uv_match=True,editable_roundtrip=True)
    if name=='区域发光':
        ae.bundle_delivery(target,report,p,clip,c,True)
        (folder/'surface_session.json').write_text(json.dumps(dict(project=p,clip=clip,config=c),ensure_ascii=False),encoding='utf-8')
        lp=engine.scan(p['source'],folder/'灯效输入')
        for record in lp['lights']:record['selected']=record['supported'] and record['part']=='hull'
        assert any(record['selected'] for record in lp['lights'])
        lp['baseline_user_confirmed']=True;lp['embed_recoverable']=True;lp['recipe']=copy.deepcopy(engine.DEFAULT_RECIPE);lp['recipe']['流水方向']='偏右下'
        target_l,report_l=engine.build(lp,client,folder/'灯效方向','斜向灯效',embed_recoverable=True)
        delivery=light_delivery.bundle(target_l,report_l)
        with zipfile.ZipFile(target_l) as z:
            m=json.loads(z.read(next(n for n in z.namelist() if n.startswith('res/particles/light_maker_') and n.endswith('/manifest.json'))))
            (folder/'light_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
        results['灯效方向']=dict(artifact=report_l['artifact'],file_validation=report_l['file_validation'],direction=lp['recipe']['流水方向'],delivery=delivery)
(folder/'integration_report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:dict(hash=v['artifact']['sha256'],status=v['file_validation']['status']) for k,v in results.items()},ensure_ascii=False))
