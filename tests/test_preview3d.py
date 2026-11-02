"""Read-only 3D extraction, shared export phases, caching and local session checks."""
import copy
import io
import json
import queue
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
from wotcamo import preview3d_assets as a,preview3d,preview3d_preferences,light_assets as mesh,light_effects as engine,light_recipe as recipe
import test_light_wheels as wheels


class Preview3DTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.root=Path(self.temp.name)
        self.source=self.root/'original.wotmod';self.path='res/vehicles/german/TestTank/normal/lod0/chassis.visual_processed'
        vertices,ids=wheels.ring();visual=wheels.fixture_visual(vertices,ids)
        opaque=copy.deepcopy(visual.find('renderSet'));opaque.find('.//fx').text='shaders/std_effects/PBS_tank.fx'
        visual.insert(1,opaque)
        with zipfile.ZipFile(self.source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.path,mesh.xml(visual));z.writestr(self.path.replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,ids.ravel()))
            z.writestr('res/wheel.dds',mesh.dds(True))
        self.project=engine.scan(self.source,self.root/'scan')
        for light in self.project['lights']:light['selected']=light['supported']
        self.body=a.make_body(self.project,None,self.root/'body')

    def tearDown(self):self.temp.cleanup()

    def test_snapshot_and_body_preserve_input_and_keep_real_geometry(self):
        digest=engine.digest(self.source);a.save_snapshot(self.project,self.root/'snapshot')
        restored=a.load_snapshot(self.root/'snapshot')
        for before,after in zip(self.project['lights'],restored['lights']):
            np.testing.assert_array_equal(before['_vertices'],after['_vertices'])
            np.testing.assert_array_equal(before['_anchor_matrix'],after['_anchor_matrix'])
        self.assertEqual(engine.digest(self.source),digest)
        self.assertEqual(self.body['triangles'],48)
        self.assertEqual(len(self.body['meshes']),1)
        geometry=self.body['meshes'][0]
        values=np.fromfile(self.root/'body'/geometry['vertex'],dtype='<f4').reshape(-1,geometry['stride'])
        self.assertGreater(np.ptp(values[:,1]),.4)
        source = geometry['source']
        self.assertEqual(source['visual'], self.path)
        self.assertEqual((source['render_set'], source['geometry'], source['group']), (0, 0, 0))
        self.assertEqual(source['triangle_ids'], list(range(geometry['triangles'])))


    def test_weighted_pose_is_baked_without_changing_source_vertices(self):
        vertices=np.array([[0,0,0,0,1,0,0,0],[1,0,0,0,1,0,0,0]],float);before=vertices.copy()
        m0=np.eye(4);m0[3,:3]=[2,0,0];m1=np.eye(4);m1[3,:3]=[0,4,0]
        result=a.transformed(vertices,[(0,3,0,128,127)]*2,['A','B'],{'A':m0,'B':m1})
        np.testing.assert_allclose(result[:,:3],vertices[:,:3]+[2*128/255,4*127/255,0])
        np.testing.assert_array_equal(before,vertices)
        with self.assertRaisesRegex(ValueError,'权重无效'):
            a.transformed(vertices,[(0,3,0,255,255)]*2,['A','B'],{'A':m0,'B':m1})

    def test_resource_references_trim_whitespace_and_cannot_escape_game_assets(self):
        resources=a.Resources(self.source,None)
        try:
            self.assertEqual(resources.read('\t wheel.dds \t'),mesh.dds(True))
            for path in ('../private.png','C:/private.png','/private.png'):
                with self.assertRaisesRegex(ValueError,'相对路径'):resources.read(path)
        finally:resources.close()

    def test_static_gun_mesh_remains_outside_inclination_branch(self):
        vertices,ids=wheels.ring()
        visual=ET.fromstring(mesh.effect_visual('body','wheel.dds',vertices,len(ids),'fixture/'))
        visual.find('.//fx').text='shaders/std_effects/PBS_tank.fx'
        for name in ('Gun','static'):
            node=copy.deepcopy(visual.find('node'));node.find('identifier').text=name
            visual.find('node').append(node)
        visual.find('renderSet/node').text='Gun'
        fixed=copy.deepcopy(visual.find('renderSet'));fixed.find('node').text='static';visual.append(fixed)
        path=self.path.replace('chassis.visual_processed','gun_01.visual_processed')
        with zipfile.ZipFile(self.source,'a',zipfile.ZIP_STORED) as z:
            z.writestr(path,mesh.xml(visual));z.writestr(path.replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,ids.ravel()))
        self.project['source_sha256']=engine.digest(self.source)
        body=a.make_body(self.project,None,self.root/'posed_body')
        self.assertEqual([x['inclined'] for x in body['meshes'] if x['part']=='gun'],[True,False])
        self.assertTrue(body['pitchSupported'])

    def test_lamp_bands_match_export_and_colour_updates_reuse_geometry(self):
        # Use the same export naming, clipping and phase offsets for a real fixture.
        cfg=self.project['recipe'];cfg['效果模式']='波浪';cfg['流水方向']='四周扩散'
        cache={};first=a.make_lamps(self.project,None,self.body,self.root/'lamps_0',cache=cache)
        with patch.object(engine,'client_info',return_value={'root':str(self.root)}), \
             patch.object(engine,'compile27',side_effect=lambda source,target,client:target.write_bytes(b'offline fixture')), \
             patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
            target,_=engine.build(self.project,self.root,self.root/'out','fixture')
        with zipfile.ZipFile(target) as z:
            manifest=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/manifest.json'))))
        self.assertEqual([x['identifier'] for x in first['bands']],[x['material'] for x in manifest['bands']])
        np.testing.assert_allclose([x['phase'] for x in first['bands']],[x['offset_seconds'] for x in manifest['bands']])
        cfg['峰值倍率']=4
        with patch.object(mesh,'split_wheel',side_effect=AssertionError('geometry rebuilt on colour edit')):
            second=a.make_lamps(self.project,None,self.body,self.root/'lamps_1',cache=cache)
        self.assertEqual(first['geometryKey'],second['geometryKey']);self.assertEqual(second['meshRevision'],0)
        self.assertFalse(list((self.root/'lamps_1').glob('mesh_*.bin')))
        self.assertFalse((self.root/'lamps_1/animation.bin').exists())
        self.assertEqual(second['animationRevision'],0)
        self.assertTrue(all(track['gain']==2 for track in second['tracks']))

    def test_sampled_animation_uses_exact_export_hermite_keys(self):
        for mode in recipe.MODES:
            cfg=recipe.validate_config(dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式=mode))
            frames=recipe.colour_track('fixture',.173,cfg).findall('frame')
            times=np.array([float(f.findtext('startTime')) for f in frames])
            values=a.evaluate_track(frames,times)
            expected=np.array([list(map(float,f.findtext('value').split())) for f in frames])
            np.testing.assert_allclose(values,expected,atol=1e-8)
            self.assertTrue(np.isfinite(values).all())

    def test_unselected_lamps_are_batched_without_losing_pick_identity(self):
        project=copy.deepcopy(self.project)
        other=copy.deepcopy(project['lights'][0]);other['id']='second_lamp';other['_vertices'][:,2]+=2
        project['lights'].append(other)
        for light in project['lights']:light['selected']=False
        scene=a.make_lamps(project,None,self.body,self.root/'lamps_0')
        self.assertFalse(scene['tracks']);self.assertEqual(len(scene['meshes']),1)
        geometry=scene['meshes'][0]
        data=np.fromfile(self.root/'lamps_0'/geometry['vertex'],dtype='<f4').reshape(-1,geometry['stride'])
        self.assertEqual(set(data[:,8]),{0,1});self.assertTrue((data[:,9]==-1).all())

    def test_server_rejects_wrong_token_traversal_and_cross_origin_posts(self):
        session=preview3d.Session(self.project,None,launch=False)
        try:
            status=json.load(urllib.request.urlopen(session.url.replace('index.html','status')))
            self.assertEqual(status['state']['revision'],0)
            old=session.state['revision'];session.update(dict(session.state,picked=['face'],performance='fine'))
            self.assertEqual(session.state['revision'],old)
            for path in ('../wrong/index.html','%2e%2e/AGENTS.md'):
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(session.url.replace('index.html',path))
            request=urllib.request.Request(session.url.replace('index.html','select'),data=b'{"id":"fixture"}',headers={'Origin':'https://example.com'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,403)
            request=urllib.request.Request(session.url.replace('index.html','select'),data=b'{"id":"fixture","add":true}')
            self.assertTrue(json.load(urllib.request.urlopen(request))['ok'])
            self.assertEqual(session.events.get_nowait()['id'],'fixture')
            request=urllib.request.Request(session.url.replace('index.html','performance'),data=b'{"value":"fast"}')
            self.assertTrue(json.load(urllib.request.urlopen(request))['ok'])
            self.assertEqual(session.events.get_nowait(),dict(type='performance',value='fast'))
        finally:session.close()

    def test_exactly_three_performance_profiles_and_corrupt_preferences_fallback(self):
        self.assertEqual(tuple(preview3d_preferences.PROFILES),('流畅','均衡','高画质'))
        path=self.root/'preferences.json'
        self.assertEqual(preview3d_preferences.load(path),'均衡')
        preview3d_preferences.save('流畅',path);self.assertEqual(preview3d_preferences.load(path),'流畅')
        with self.assertRaises(ValueError):preview3d_preferences.save('other',path)
        path.write_text('[]',encoding='utf-8');self.assertEqual(preview3d_preferences.load(path),'均衡')


class Preview3DGuiTests(unittest.TestCase):
    def test_browser_performance_choice_syncs_to_main_form_and_not_recipe(self):
        import test_light_gui_selection as selection
        import tkinter as tk
        from types import SimpleNamespace
        from unittest.mock import Mock
        from wotcamo.light_gui import LightMaker
        try:app=LightMaker();app.withdraw()
        except tk.TclError as error:self.skipTest(str(error))
        try:
            app.set_project(selection.make_project());before=copy.deepcopy(app.project['recipe'])
            session=SimpleNamespace(events=queue.Queue(),viewer=SimpleNamespace(poll=lambda:None),close=Mock(),update=Mock(),closed=False)
            session.events.put(dict(type='performance',value='fine'));app.preview3d=session
            with patch.object(preview3d_preferences,'save') as save:
                app.poll_preview3d();app.sync_preview3d()
                self.assertEqual(app.performance.get(),'高画质')
                self.assertEqual(session.update.call_args.args[0]['performance'],'fine')
                save.assert_called_once_with('高画质')
            self.assertEqual(app.project['recipe'],before)
        finally:app.destroy()

    def test_draft_preview_state_does_not_commit_recipe_or_selection(self):
        import test_light_gui_selection as selection
        import tkinter as tk
        from wotcamo.light_gui import LightMaker
        try:app=LightMaker();app.withdraw()
        except tk.TclError as error:self.skipTest(str(error))
        try:
            app.set_project(selection.make_project());before=copy.deepcopy(app.project['recipe'])
            app.picked={'a1'};app.edit_scope.set('套选模型');app.change_edit_scope();app.peak.set('4')
            state=app.preview3d_state()
            self.assertEqual(state['recipe'],before)
            self.assertEqual(next(x for x in state['lights'] if x['id']=='a1')['recipe']['峰值倍率'],4)
            self.assertIsNone(next(x for x in state['lights'] if x['id']=='b1')['recipe'])
            self.assertEqual(app.project['recipe'],before)
            self.assertNotIn('配方',app.records['a1'])
        finally:app.destroy()


if __name__=='__main__':unittest.main()
