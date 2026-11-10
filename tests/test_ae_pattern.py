"""Preserved image ratios, atlas-safe repetition and portable settings."""
import io,json,tempfile,unittest,urllib.request,urllib.error,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae,ae_presets,preview3d,area_selection

class PatternTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.vertices=np.array([[0,0,0,1,0,0,0,0],[0,0,4,1,0,0,1,0],[0,2,4,1,0,0,1,1],[0,2,0,1,0,0,0,1]],dtype=float)
        self.indices=np.array([[0,1,2],[0,2,3]])
        self.record=dict(part='hull',anchor='hull',anchor_kind='part',_vertices=self.vertices,_indices=self.indices,_anchor_matrix=np.eye(4))
        source=self.root/'source.wotmod'
        with zipfile.ZipFile(source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'original')
        self.project=ae.source_project(source,self.root/'source')
        self.project['ae_selection']=dict(source_sha256=self.project['source_sha256'],groups=[dict(triangles=[0,1])])
        self.clip=ae.pack_frames([Image.new('RGBA',(32,32),(100,150,200,120))],self.root/'atlas.png')
    def tearDown(self):self.tmp.cleanup()
    def plan(self,mode,**kw):
        c=ae.config(dict(placement='surface_glow',plane='side',fit_mode=mode,**kw))
        with patch.object(area_selection,'extract_rigid_lights',return_value=[self.record]):return ae.geometry_plan(self.project,self.clip,c,None)
    def test_contain_leaves_space_and_cover_crops_without_stretching_square(self):
        contained=self.plan('contain')['vertices']
        np.testing.assert_allclose(np.ptp(contained[:,1:3],axis=0),[2,2])
        covered=self.plan('cover')['vertices']
        np.testing.assert_allclose(np.ptp(covered[:,1:3],axis=0),[2,4])
        np.testing.assert_allclose(np.ptp(covered[:,6:8],axis=0),[1,.5])
        legacy=self.plan('stretch')['vertices']
        np.testing.assert_allclose(np.ptp(legacy[:,6:8],axis=0),[1,1])
        self.assertEqual(ae.config({})['fit_mode'],'stretch')
    def test_tiles_wrap_inside_each_frame_and_density_preserves_ratio(self):
        for repeat in (1,2,4):
            plan=self.plan('tile',tile_repeat=repeat);v=plan['vertices'];tri=v[np.array(plan['indices']).reshape(-1,3)]
            self.assertGreaterEqual(v[:,6:8].min(),-1e-8);self.assertLessEqual(v[:,6:8].max(),1+1e-8)
            area=np.linalg.norm(np.cross(tri[:,1,:3]-tri[:,0,:3],tri[:,2,:3]-tri[:,0,:3]),axis=1).sum()/2
            self.assertAlmostEqual(area,8)
            for t in tri:
                # For a square tile, physical metres per U and V are equal.
                coefficients=np.linalg.lstsq(np.c_[t[:,2],t[:,1],np.ones(3)],t[:,6:8],rcond=None)[0]
                self.assertAlmostEqual(abs(coefficients[0,0]),repeat/4,places=6)
                self.assertAlmostEqual(abs(coefficients[1,1]),repeat/4,places=6)
        np.testing.assert_array_equal(self.record['_vertices'],self.vertices)
    def test_rotated_mirrored_and_cropped_tiles_keep_valid_uv_and_area(self):
        p=self.plan('tile',angle=23,crop_left=10,crop_right=10,mirror=True)
        self.assertGreater(p['mirrored_triangles'],0)
        v=p['vertices'];self.assertTrue(np.isfinite(v).all())
        self.assertGreaterEqual(v[:,6].min(),.1-1e-8);self.assertLessEqual(v[:,6].max(),.9+1e-8)
        self.assertGreaterEqual(v[:,7].min(),-1e-8);self.assertLessEqual(v[:,7].max(),1+1e-8)
    def test_plane_tile_drag_weights_reproduce_exported_warped_geometry(self):
        c=ae.config(dict(fit_mode='tile',tile_repeat=3,uv_scale_y=2,warp_tr_z=.4,warp_bl_x=.3,mirror=True))
        plan=ae.geometry_plan(None,self.clip,c,None);data=ae.preview_data(self.clip,c)
        weights=np.asarray(data['weights']);corners=np.asarray(data['corners'])
        self.assertEqual(len(weights),len(plan['vertices']))
        np.testing.assert_allclose(weights.sum(1),1,atol=1e-8)
        np.testing.assert_allclose(weights@corners,plan['vertices'][:,:3],atol=1e-8)
        self.assertTrue(np.all(np.array(data['local_uv'])>=-1e-8));self.assertTrue(np.all(np.array(data['local_uv'])<=1+1e-8))
    def test_dense_tiling_is_bounded_and_settings_are_validated(self):
        for bad in (dict(fit_mode='repeat'),dict(tile_repeat=17),dict(tile_repeat=True)):
            with self.assertRaises(ValueError):ae.config(bad)
        with patch.object(area_selection,'extract_rigid_lights',return_value=[self.record]),self.assertRaises(ValueError):
            ae.geometry_plan(self.project,dict(self.clip,frame_size=[4096,1]),ae.config(dict(placement='surface_glow',fit_mode='tile',tile_repeat=16)),None)
    def test_settings_roundtrip_rejects_unrelated_clipboard_and_contains_no_asset(self):
        c=ae.config(dict(x=2,part='turret',fit_mode='tile',tile_repeat=3,brightness=9,mirror=True))
        text=ae.encode_settings(c);self.assertEqual(ae.decode_settings(text),c)
        self.assertNotIn('source',text);self.assertNotIn('atlas',text);self.assertNotIn('client',text)
        for bad in ('hello','[]','null',text.replace('"schema": 1','"schema": true'),text.replace('"config": {','"config": {"path": "file",'),text+' '*65536):
            with self.assertRaises(ValueError):ae.decode_settings(bad)
    def test_project_and_preset_keep_mapping_and_original_atlas(self):
        c=ae.config(dict(fit_mode='tile',tile_repeat=3))
        _,raw=ae_presets.encode('Tile','',self.clip,c);path=self.root/'tile.aepreset';path.write_bytes(raw)
        data,clip=ae_presets.load(path,self.root/'preset');self.assertEqual(data['config']['fit_mode'],'tile');self.assertEqual(data['config']['tile_repeat'],3)
        self.assertEqual(clip['atlas_sha256'],self.clip['atlas_sha256'])
        saved=self.root/'project.aefx';ae.save_project(saved,self.project,self.clip,c)
        _,_,values=ae.load_project(saved,self.root/'reopened');self.assertEqual(values,c)
    def test_preview_routes_validate_mapping_and_queue_clipboard_actions(self):
        session=preview3d.Session(self.project,None,launch=False,effect=(self.clip,ae.config({})))
        def request(route,data):return urllib.request.urlopen(urllib.request.Request(session.url.replace('index.html',route),data=json.dumps(data).encode()))
        try:
            with request('effectparams',dict(fit_mode='tile',tile_repeat=3)):pass
            self.assertEqual(session.events.get_nowait()['values'],dict(fit_mode='tile',tile_repeat=3))
            for action in ('copy','paste'):
                with request('effectsettings',dict(action=action)):pass
                self.assertEqual(session.events.get_nowait(),dict(type='effectsettings',action=action))
            for route,data in [('effectparams',dict(fit_mode='bad')),('effectsettings',dict(action='readfile')),('effectsettings',dict(action='copy',path='file'))]:
                with self.assertRaises(urllib.error.HTTPError):request(route,data)
        finally:session.close()

    def test_final_export_matches_preview_mesh_for_fit_and_tile_modes(self):
        # 合成客户端只验证导出链，不证明原生渲染或游戏整车可用。
        from xml.etree import ElementTree as ET
        client=self.root/'client';(client/'res/packages').mkdir(parents=True)
        binary=io.BytesIO()
        with zipfile.ZipFile(binary,'w') as z:z.writestr('effect',b"('SRCALPHA', 5) ('ONE', 2) ('INVSRCALPHA', 6)")
        with zipfile.ZipFile(client/'res/packages/shaders.pkg','w') as z:
            for branch in ('10','11'):z.writestr('shaders/custom/emissive_playground.'+branch+'.dx11.fxo',binary.getvalue())
        self.project['baseline_user_confirmed']=True
        def compile_stub(source,target,client):Path(target).write_bytes(b'synthetic-bytecode')
        for placement,mode in [('surface_glow','contain'),('surface_glow','cover'),('surface_glow','tile'),('plane','tile')]:
            c=ae.config(dict(placement=placement,plane='side',fit_mode=mode,tile_repeat=3,mirror=True))
            with patch.object(area_selection,'extract_rigid_lights',return_value=[self.record]),patch.object(ae.engine,'client_info',return_value={'kind':'synthetic'}),patch.object(ae.engine,'compile27',side_effect=compile_stub),patch.object(ae.engine,'audit_package',return_value={'missing_dependencies':[]}):
                preview=ae.preview_data(self.clip,c,self.project,None)
                target,report=ae.build(self.project,self.clip,c,str(client),self.root/(placement+mode),'Pattern')
            with zipfile.ZipFile(target) as z:
                name=next(n for n in z.namelist() if n.endswith('/frame_000.primitives_processed'))
                sections=ae.mesh.sections(z.read(name));v,_=ae.mesh.vertex_data(sections['vertices'])
                np.testing.assert_allclose(v[:,[0,1,2,6,7]],np.asarray(preview['vertices'])[:,[0,1,2,6,7]],atol=1e-6)
                manifest=json.loads(z.read(name.rsplit('/',1)[0]+'/manifest.json'))
                self.assertEqual(manifest['config']['fit_mode'],mode);self.assertEqual(manifest['config']['tile_repeat'],3)
                self.assertEqual(z.read('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds'),b'original')
            self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')

if __name__=='__main__':unittest.main()
