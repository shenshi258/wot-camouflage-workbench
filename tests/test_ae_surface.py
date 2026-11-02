"""Selected-face isolation, source authentication, fitting and delivered bundle checks."""
import copy,json,tempfile,unittest,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae,light_assets as mesh

class AESurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.clip=ae.pack_frames([Image.new('RGBA',(32,16),(80,160,255,128))],self.root/'atlas.png')
        self.source=self.root/'source.wotmod';self.visual='res/vehicles/german/G197_Pz_Kpfw_Neu/normal/lod0/hull.visual_processed'
        self.v=ae.quad(self.clip,ae.config(dict(width=2)),[0,0,1,1]);self.ids=[0,1,2,0,2,3]
        with zipfile.ZipFile(self.source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.visual,mesh.effect_visual('body','test.dds',self.v,2,prefix='test/'))
            z.writestr(self.visual.replace('.visual_processed','.primitives_processed'),mesh.primitives(self.v,self.ids))
        self.project=ae.source_project(self.source,self.root/'work')
        self.project['ae_selection']=dict(schema=1,source_sha256=self.project['source_sha256'],groups=[dict(visual=self.visual,render_set=0,geometry=0,group=0,triangles=[0])])
        self.c=ae.config(dict(placement='surface',plane='auto'))
    def tearDown(self):self.temp.cleanup()
    def test_single_triangle_does_not_draw_the_unselected_half(self):
        plan=ae.surface_geometry(self.project,self.c,None)
        self.assertEqual(len(plan['indices']),3);self.assertEqual(plan['selected_triangles'],1)
        self.assertEqual(plan['anchor'],'hull');self.assertEqual(plan['anchor_kind'],'part')
        self.assertTrue(np.allclose(plan['vertices'][:,0],.001))
        self.assertTrue(np.allclose(plan['vertices'][:,1:3],self.v[:3,1:3]))
    def test_both_faces_keep_surface_shape_and_glow_lifts_only_the_overlay(self):
        self.project['ae_selection']['groups'][0]['triangles']=[0,1]
        plain=ae.surface_geometry(self.project,self.c,None)
        glow=ae.surface_geometry(self.project,ae.config(dict(self.c,placement='surface_glow',lift=.02)),None)
        self.assertEqual(len(plain['indices']),6)
        self.assertTrue(np.allclose(glow['vertices'][:,0]-plain['vertices'][:,0],.019))
        self.assertTrue(np.array_equal(glow['vertices'][:,1:],plain['vertices'][:,1:]))
    def test_image_scale_and_offset_clip_within_selected_triangle(self):
        plan=ae.surface_geometry(self.project,ae.config(dict(self.c,uv_scale=.5,u_offset=.1,angle=45)),None)
        uv=plan['vertices'][:,6:8];self.assertGreaterEqual(uv.min(),-1e-10);self.assertLessEqual(uv.max(),1+1e-10)
        # Test barycentric containment against the original chosen triangle.
        tri=self.v[:3,1:3];matrix=np.vstack((tri.T,np.ones(3)))
        for point in plan['vertices'][:,1:3]:
            weights=np.linalg.solve(matrix,np.r_[point,1]);self.assertGreaterEqual(weights.min(),-1e-8)
    def test_preview_and_export_share_surface_uvs_and_geometry(self):
        plan=ae.surface_geometry(self.project,self.c,None);preview=ae.preview_data(self.clip,self.c,self.project,None)
        expected=ae.atlas_vertices(plan['vertices'],self.clip['rects'][0]);self.assertTrue(np.allclose(preview['vertices'],expected))
        self.assertEqual(preview['indices'],plan['indices']);self.assertEqual(preview['positions'],[[0,0,0]])
    def test_unselected_state_can_open_preview_but_cannot_build_geometry(self):
        self.project.pop('ae_selection');preview=ae.preview_data(self.clip,self.c,self.project,None)
        self.assertTrue(preview['awaiting_selection']);self.assertEqual(preview['positions'],[])
        with self.assertRaises(ValueError):ae.geometry_plan(self.project,self.clip,self.c,None)
    def test_selection_cannot_cross_digest_or_triangle_bounds(self):
        self.project['ae_selection']['source_sha256']='0'*64
        with self.assertRaises(ValueError):ae.surface_geometry(self.project,self.c,None)
        self.project['ae_selection']['source_sha256']=self.project['source_sha256'];self.project['ae_selection']['groups'][0]['triangles']=[2]
        with self.assertRaises(ValueError):ae.surface_geometry(self.project,self.c,None)
    def test_no_implicit_mirror_of_unselected_faces(self):
        plain=ae.surface_geometry(self.project,self.c,None)
        both=ae.surface_geometry(self.project,ae.config(dict(self.c,mirror=True)),None)
        self.assertEqual(len(plain['indices']),3);self.assertEqual(len(both['indices']),6)
        np.testing.assert_array_equal(both['vertices'][:len(plain['vertices'])],plain['vertices'])
        self.assertEqual(both['mirrored_triangles'],1)
    def test_selection_survives_editable_project_without_original_external_files(self):
        path=self.root/'saved.aefx';ae.save_project(path,self.project,self.clip,self.c)
        project,clip,c=ae.load_project(path,self.root/'restored')
        self.assertEqual(project['ae_selection'],self.project['ae_selection']);self.assertEqual(c,self.c)
        self.assertEqual(ae.surface_geometry(project,c,None)['selected_triangles'],1)
    def test_independent_axis_scaling_changes_only_the_requested_axis(self):
        self.project['ae_selection']['groups'][0]['triangles']=[0,1]
        horizontal=ae.surface_geometry(self.project,ae.config(dict(self.c,uv_scale_x=.5)),None)['vertices']
        vertical=ae.surface_geometry(self.project,ae.config(dict(self.c,uv_scale_y=.5)),None)['vertices']
        self.assertAlmostEqual(np.ptp(horizontal[:,2]),1);self.assertAlmostEqual(np.ptp(horizontal[:,1]),1)
        self.assertAlmostEqual(np.ptp(vertical[:,2]),2);self.assertAlmostEqual(np.ptp(vertical[:,1]),.5)

    def test_four_edge_crop_trims_geometry_without_stretching_remaining_uvs(self):
        self.project['ae_selection']['groups'][0]['triangles']=[0,1]
        values=ae.config(dict(self.c,crop_left=25,crop_top=20))
        plan=ae.surface_geometry(self.project,values,None);v=plan['vertices']
        np.testing.assert_allclose(v[:,6:8].min(0),[.25,.2],atol=1e-7)
        np.testing.assert_allclose(v[:,6:8].max(0),[1,1],atol=1e-7)
        self.assertAlmostEqual(np.ptp(v[:,2]),1.5);self.assertAlmostEqual(np.ptp(v[:,1]),.8)
        preview=ae.preview_data(self.clip,values,self.project,None)
        np.testing.assert_allclose(preview['vertices'],ae.atlas_vertices(v,self.clip['rects'][0]))
        quad=ae.quad(self.clip,ae.config(dict(width=2,crop_left=25,crop_top=20)),[0,0,1,1])
        self.assertAlmostEqual(np.ptp(quad[:,2]),1.5);self.assertAlmostEqual(np.ptp(quad[:,1]),.8)
        with self.assertRaisesRegex(ValueError,'100'):ae.config(dict(crop_left=60,crop_right=40))

    def test_snap_origin_is_authenticated_centers_the_image_and_survives_project_save(self):
        self.project['ae_selection']['groups'][0]['triangles']=[0,1]
        point=[0,.2,-.5]
        self.project['ae_surface_origin']=dict(source_sha256=self.project['source_sha256'],point=point)
        plan=ae.surface_geometry(self.project,self.c,None);v=plan['vertices']
        np.testing.assert_allclose(v[:,6],-(v[:,2]-point[2])/2+.5,atol=1e-7)
        np.testing.assert_allclose(v[:,7],-(v[:,1]-point[1])+.5,atol=1e-7)
        path=self.root/'snap.aefx';ae.save_project(path,self.project,self.clip,self.c)
        restored,clip,values=ae.load_project(path,self.root/'snap_restored')
        self.assertEqual(restored['ae_surface_origin'],self.project['ae_surface_origin'])
        np.testing.assert_allclose(ae.surface_geometry(restored,values,None)['vertices'],v)
        for invalid in ([.1,.2,-.5],[0,100,-.5],[float('nan'),0,0]):
            self.project['ae_surface_origin']['point']=invalid
            with self.assertRaises(ValueError):ae.surface_geometry(self.project,self.c,None)

    def test_preview_parameter_route_validates_crop_and_returns_authenticated_snap_events(self):
        import urllib.request,urllib.error
        from wotcamo import preview3d
        session=preview3d.Session(self.project,None,launch=False,effect=(self.clip,ae.config({})))
        def request(route,data):
            return urllib.request.urlopen(urllib.request.Request(session.url.replace('index.html',route),data=json.dumps(data).encode()))
        try:
            scene=dict(source_sha256=self.project['source_sha256'],meshes=[dict(triangles=2,source=dict(self.project['ae_selection']['groups'][0],triangle_ids=[0,1]))])
            (session.folder/'body.json').write_text(json.dumps(dict(scene=scene)),encoding='utf-8')
            request('effectparams',dict(uv_scale_x=.5,crop_left=10)).close()
            event=session.events.get_nowait();self.assertEqual(event['type'],'effectparams');self.assertEqual(event['values']['uv_scale_x'],.5)
            request('effectparams',dict(mirror=True)).close()
            event=session.events.get_nowait();self.assertIs(event['values']['mirror'],True)
            with self.assertRaises(urllib.error.HTTPError):request('effectparams',dict(mirror='false'))
            for values in (dict(crop_left=60,crop_right=40),dict(x=31),dict(uv_scale_x=float('nan'))):
                with self.assertRaises(urllib.error.HTTPError):request('effectparams',values)
            request('bodyselect',dict(batches=[dict(mesh=0,triangles=[0])],snap=True,point=[0,0,0])).close()
            event=session.events.get_nowait();self.assertTrue(event['snap']);self.assertEqual(event['selection']['source_sha256'],self.project['source_sha256'])
            with self.assertRaises(urllib.error.HTTPError):request('bodyselect',dict(batches=[dict(mesh=0,triangles=[0])],snap=True,point=[0,0,100]))
        finally:session.close()

    def test_bundle_contains_exact_game_archive_and_optional_editable_project(self):
        target=self.root/'example.wotmod';target.write_bytes(self.source.read_bytes())
        report=dict(artifact=dict(sha256=ae.engine.digest(target)))
        (self.root/'验证记录.json').write_text(json.dumps(report),encoding='utf-8');(self.root/'使用说明.txt').write_text('待实测',encoding='utf-8')
        result=ae.bundle_delivery(target,report,self.project,self.clip,self.c,True)
        with zipfile.ZipFile(result['path']) as z:
            self.assertEqual(z.read(target.name),target.read_bytes());self.assertIn('example.aefx',z.namelist())
            self.assertIn('example.aepreset',z.namelist())
            from wotcamo import ae_presets
            saved,atlas=ae_presets.read(target.with_suffix('.aepreset'))
            self.assertEqual(saved['clip']['atlas_sha256'],self.clip['atlas_sha256'])
            self.assertEqual(saved['config']['fps'],self.c['fps'])
            self.assertEqual(result['effect_preset_sha256'],ae.engine.digest(target.with_suffix('.aepreset')))
        self.assertEqual(result['game_archive_sha256'],report['artifact']['sha256'])
        with self.assertRaises(ValueError):ae.bundle_delivery(target,report,self.project,self.clip,self.c)

    def test_effect_preset_is_bundled_even_without_an_editable_project(self):
        target=self.root/'without_project.wotmod';target.write_bytes(self.source.read_bytes())
        report=dict(artifact=dict(sha256=ae.engine.digest(target)))
        for name in ('验证记录.json','使用说明.txt'):(self.root/name).write_text('offline',encoding='utf-8')
        values=ae.config(dict(self.c,uv_scale_x=1.6,crop_left=12))
        result=ae.bundle_delivery(target,report,self.project,self.clip,values,False)
        from wotcamo import ae_presets
        data,clip=ae_presets.load(target.with_suffix('.aepreset'),self.root/'reimported')
        self.assertEqual(data['config']['crop_left'],12);self.assertEqual(data['config']['uv_scale_x'],1.6)
        with zipfile.ZipFile(result['path']) as z:
            self.assertEqual(z.read(target.name),self.source.read_bytes());self.assertIn('without_project.aepreset',z.namelist())
            self.assertFalse(any(name.endswith('.aefx') for name in z.namelist()))

if __name__=='__main__':unittest.main()
