"""Add a second side without recompiling runtime or borrowing another client.

The original export was produced on a CN client unavailable here. Keep its
compiled runtime, materials, textures, sequence and every vehicle resource.
Only reflected overlay geometry/bounds and portable editing metadata change.
"""
import ctypes,hashlib,json,sys,unittest,zipfile,tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets,light_assets as mesh
from wotcamo.common import ROOT

def background():
    kernel=ctypes.windll.kernel32
    kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x00100000)

def main():
    background()
    workspace=ROOT.parents[1];evidence=ROOT/'.cache';evidence.mkdir(exist_ok=True)
    temp=evidence/'test_tmp';temp.mkdir(exist_ok=True);tempfile.tempdir=str(temp)
    suites=['tests.test_ae_sides','tests.test_ae_surface','tests.test_ae_effects','tests.test_ae_deform','tests.test_ae_presets']
    with (evidence/'sides_tests.log').open('w',encoding='utf-8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    print('BACKGROUND_TESTS',result.testsRun,len(result.failures),len(result.errors),flush=True)
    if not result.wasSuccessful():raise SystemExit(1)
    original=workspace/'改造区/Ares90_AE半边排查'
    project,clip,c=ae.load_project(original/'用户原工程.aefx',evidence/'user_project')
    plain=ae.geometry_plan(project,clip,c,None);c['mirror']=True
    both=ae.geometry_plan(project,clip,c,None)
    np.testing.assert_array_equal(both['vertices'][:len(plain['vertices'])],plain['vertices'])
    assert both['mirrored_triangles']==len(plain['indices'])//3
    assert np.min(both['vertices'][:,0])<0<np.max(both['vertices'][:,0])
    out=workspace/'交付/Ares90_AE左右双侧_待实测';out.mkdir(exist_ok=False)
    target=out/'Ares90_AE左右双侧_待实测.wotmod'
    modified={};original_native=original/'用户原效果.wotmod'
    with zipfile.ZipFile(original_native) as source:
        manifest_name=next(n for n in source.namelist() if '/ae_import_' in n and n.endswith('/manifest.json'))
        manifest=json.loads(source.read(manifest_name));prefix=manifest_name.removesuffix('manifest.json')
        for i,rect in enumerate(clip['rects']):
            vertices=ae.atlas_vertices(both['vertices'],rect)
            base=prefix+'frame_%03d'%i
            primitive=mesh.primitives(vertices,both['indices'])
            # Compare encoded original-side vertex payload, including packed
            # normals and frame UVs; only count/header and the added side differ.
            old_vb=mesh.sections(source.read(base+'.primitives_processed'))['vertices']
            new_vb=mesh.sections(primitive)['vertices']
            assert old_vb[136:]==new_vb[136:len(old_vb)],i
            visual=ae.ET.fromstring(source.read(base+'.visual_processed'))
            low=vertices[:,:3].min(0);high=vertices[:,:3].max(0)
            visual.find('boundingBox/min').text=' '.join(format(x,'.9g') for x in low)
            visual.find('boundingBox/max').text=' '.join(format(x,'.9g') for x in high)
            visual.find('geometrySize').text=str(len(vertices)*24+len(both['indices'])*2)
            modified[base+'.primitives_processed']=primitive;modified[base+'.visual_processed']=mesh.xml(visual)
        manifest['config']=c;manifest['preview']=ae.preview_data(clip,c,project,None)
        modified[manifest_name]=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
        ae.engine.write_game_archive(original_native,target,modified)
        with zipfile.ZipFile(target) as final,zipfile.ZipFile(project['source']) as vehicle:
            assert final.testzip() is None
            for name in final.namelist():
                assert final.getinfo(name).compress_type==zipfile.ZIP_STORED
                assert final.read(name)==modified.get(name,source.read(name))
            for name in vehicle.namelist():assert final.read(name)==vehicle.read(name)
    original_report=json.loads((original/'用户原验证记录.json').read_text(encoding='utf-8-sig'))
    report=dict(artifact=dict(path=str(target),sha256=ae.engine.digest(target),bytes=target.stat().st_size),
        input_artifact=dict(path=str(original_native),sha256=ae.engine.digest(original_native)),
        client=original_report['client'],baseline=original_report['baseline'],
        file_validation=dict(status='passed',zip_crc=True,stored_only=True,original_vehicle_resources_unchanged=True,
            original_side_vertex_payload_unchanged_all_frames=True,materials_textures_sequences_and_compiled_runtime_unchanged=True),
        offline_validation=dict(status='partial',scope='All final frame geometry read back; bilateral positions, normals, winding and original-side bytes checked. CN client not locally accessible; client dependencies/shader execution not revalidated.'),
        ae_effect=dict(frames=clip['frames'],fps=c['fps'],mirrored=True,original_triangles=len(plain['indices'])//3,added_triangles=both['mirrored_triangles']),
        in_game_tested=False,whole_vehicle_loading=dict(status='not_tested',reason='New hash; final CN-client game observation required'))
    (out/'验证记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'使用说明.txt').write_text('仅补另一侧特效，原侧的位置、尺寸、帧序、速度、材质、贴图与原车资源保持不变。\n包内记录的客户端为国服 2.4.1.1；该客户端不在本机，未安装、未启动游戏，实际效果待你复测。\n只启用一份同车型效果包，避免旧包覆盖。\n编辑可打开附带 .aefx；新版工作台呈现方式下方勾选“左右双侧显示”。\n',encoding='utf-8-sig')
    delivery=ae.bundle_delivery(target,report,project,clip,c,True)
    restored,restored_clip,restored_config=ae.load_project(target.with_suffix('.aefx'),evidence/'restored_both')
    assert restored_config['mirror'] is True
    (evidence/'sides_export.json').write_text(json.dumps(dict(report=report,delivery=delivery),ensure_ascii=False,indent=2),encoding='utf-8')
    print('BILATERAL_PACKAGE_OK',json.dumps(delivery,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
