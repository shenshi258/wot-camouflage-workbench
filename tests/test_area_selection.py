import unittest
from wotcamo import area_selection


class AreaSelectionTests(unittest.TestCase):
    def setUp(self):
        self.scene = dict(source_sha256='a'*64, meshes=[dict(triangles=3,
            source=dict(visual='res/vehicles/a/b/normal/lod0/hull.visual_processed',
                        render_set=0, geometry=1, group=2, triangle_ids=[0, 2, 7], texture='a.dds'))])

    def test_mapping_tracks_original_faces_and_deduplicates(self):
        result = area_selection.resolve(self.scene, [dict(mesh=0, triangles=[2, 0, 2])])
        self.assertEqual(result['source_sha256'], 'a'*64)
        self.assertEqual(result['groups'][0]['triangles'], [0, 7])
        self.assertEqual(result['groups'][0]['texture'], 'a.dds')

    def test_rejects_stale_or_bad_indices(self):
        for batch in ([dict(mesh=0, triangles=[3])], [dict(mesh=0, triangles=[True])],
                      [dict(mesh=-1, triangles=[0])], []):
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                area_selection.resolve(self.scene, batch)
        self.scene['source_sha256'] = ''
        with self.assertRaises(ValueError): area_selection.resolve(self.scene, [dict(mesh=0, triangles=[0])])

    def test_rejects_mismatched_geometry(self):
        self.scene['meshes'][0]['source']['triangle_ids'] = [0]
        with self.assertRaisesRegex(ValueError, '映射不一致'):
            area_selection.resolve(self.scene, [dict(mesh=0, triangles=[0])])


class AreaOverlayTests(unittest.TestCase):
    def test_overlay_keeps_entire_original_vehicle_and_reports_not_tested(self):
        import copy, tempfile, zipfile, json
        from pathlib import Path
        from unittest.mock import patch
        import test_light_wheels as wheels
        from wotcamo import light_assets as mesh, light_effects as engine
        vertices, ids = wheels.ring(); visual = wheels.fixture_visual(vertices, ids)
        visual.find('.//fx').text = 'shaders/std_effects/PBS_tank.fx'
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            root=Path(tmp);source=root/'input.wotmod'
            path='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'
            prim=path.replace('.visual_processed','.primitives_processed')
            raw=mesh.xml(visual); primitives=mesh.primitives(vertices,ids.ravel())
            with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
                z.writestr(path,raw);z.writestr(prim,primitives);z.writestr('res/wheel.dds',mesh.dds(True))
            project=dict(source=str(source),source_sha256=engine.digest(source),recipe=copy.deepcopy(engine.DEFAULT_RECIPE),lights=[])
            selection=dict(source_sha256=project['source_sha256'],groups=[dict(visual=path,render_set=0,geometry=0,group=0,triangles=[0,1],texture='wheel.dds')])
            project['lights']=area_selection.extract_rigid_lights(project,selection)
            with patch.object(engine,'client_info',return_value={'root':str(root)}), patch.object(engine,'compile27',side_effect=lambda s,t,c:t.write_bytes(b'test-only')), patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
                target,report=engine.build(project,root,root/'out','fixture',embed_recoverable=False)
            with zipfile.ZipFile(target) as z:
                self.assertEqual(z.read(path),raw);self.assertEqual(z.read(prim),primitives)
                manifest=json.loads(z.read(next(x for x in z.namelist() if x.endswith('/manifest.json'))))
                self.assertEqual(len(manifest['models']),1)
            self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')


class AreaPaintTests(unittest.TestCase):
    def test_paint_changes_only_selected_blocks_and_rejects_shared_uv(self):
        import tempfile, zipfile, io
        from pathlib import Path
        import numpy as np
        from PIL import Image
        from wotcamo import light_effects as engine, dds
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            root=Path(tmp);client=root/'client';client.mkdir()
            (client/'paths.xml').write_text('<root><Path>./res_mods/2.4.1.1</Path></root>')
            (client/'version.xml').write_text('<root/>')
            buf=io.BytesIO();Image.new('RGBA',(64,64),(40,40,40,255)).save(buf,format='DDS',pixel_format='DXT5');raw=buf.getvalue()
            source=root/'input.wotmod';texture='vehicles/test/TestTank/surface_AM.dds';path='res/vehicles/test/TestTank/normal/lod0/Hull.visual_processed'
            with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:z.writestr('res/'+texture,raw)
            digest=engine.digest(source);project=dict(source=str(source),source_sha256=digest)
            vertices=np.array([[0,0,0,0,0,1,.05,.05],[0,0,0,0,0,1,.3,.05],[0,0,0,0,0,1,.05,.3],
                               [0,0,0,0,0,1,.7,.7],[0,0,0,0,0,1,.9,.7],[0,0,0,0,0,1,.7,.9]],dtype='<f4')
            vertices.tofile(root/'mesh.bin');np.array([0,1,2,3,4,5],dtype='<u4').tofile(root/'mesh.idx')
            meta=dict(visual=path,render_set=0,geometry=0,group=0,texture=texture,triangle_ids=[0,1])
            body=dict(source_sha256=digest,meshes=[dict(vertex='mesh.bin',index='mesh.idx',stride=8,triangles=2,source=meta)])
            selection=area_selection.resolve(body,[dict(mesh=0,triangles=[0])]);image=root/'red.png';Image.new('RGBA',(10,10),(255,0,0,255)).save(image)
            target,report=area_selection.paint_texture(project,selection,body,root,image,client,root/'out','test')
            with zipfile.ZipFile(target) as z:changed=z.read('res/'+texture)
            self.assertEqual(dds.inspect(changed),dds.inspect(raw));self.assertNotEqual(changed,raw)
            self.assertEqual(changed[-16:],raw[-16:])
            self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
            self.assertEqual(engine.digest(source),digest)
            vertices[3:,6:8]=vertices[:3,6:8];vertices.tofile(root/'mesh.bin')
            with self.assertRaisesRegex(ValueError,'共用 UV'):
                area_selection.paint_texture(project,selection,body,root,image,client,root/'out','overlap')


class ProcessedVertexTests(unittest.TestCase):
    def test_40_byte_processed_skin_uses_last_two_weight_bytes(self):
        import struct
        from wotcamo import light_assets as mesh
        blob=b'BPVTxyznuviiiwwtb'.ljust(64,b'\0')+struct.pack('<I',0)+b'set3/xyznuviiiwwtbpc'.ljust(64,b'\0')+struct.pack('<I',1)
        blob+=struct.pack('<3fI2f8B2I',1,2,3,0,0.25,0.75,3,6,9,0,0,0,200,55,0,0)
        vertices,skin=mesh.vertex_data(blob)
        self.assertEqual(skin,[(3,6,9,200,55)])
        self.assertEqual(vertices.shape,(1,8));self.assertAlmostEqual(vertices[0,6],.25)
        with self.assertRaises(ValueError):mesh.vertex_data(blob[:-1])
