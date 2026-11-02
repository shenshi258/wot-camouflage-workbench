"""Finished-package editing: source preservation, safe restore and replacement."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
from wotcamo import light_effects as engine, light_assets as mesh, light_recovery, preview3d_assets as preview
from test_light_wheels import ring, fixture_visual


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        vertices,indices=ring()
        visual=fixture_visual(vertices,indices)
        visual.append(copy.deepcopy(visual.find('renderSet')))
        for anchor, x in (('W_R0',1.),('W_L0',-1.)):
            child=copy.deepcopy(visual.find('node'))
            child.find('identifier').text=anchor
            child.find('transform/row3').text='%s 0 0'%x
            visual.find('node').append(child)
        self.visual='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'
        original=self.root/'original.wotmod'
        with zipfile.ZipFile(original,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.visual,mesh.xml(visual))
            z.writestr(self.visual.replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,indices.ravel()))
            z.writestr('res/wheel.dds',mesh.dds(True))
            z.writestr('res/unrelated.dat',b'leave me alone')
        lights=[]
        for i,anchor in enumerate(('W_R0','W_L0')):
            matrix=np.eye(4);matrix[3,0]=1 if i==0 else -1
            lights.append(dict(id=str(i),visual=self.visual,anchor=anchor,anchor_kind='node',
                texture='res/wheel.dds',selected=True,supported=True,part='chassis',vehicle='TestTank',nation='test',
                render_set=i,geometry=0,group=0,source_triangle_ids=list(range(len(indices))),
                _vertices=vertices,_indices=indices,_preview=vertices[:,:3]+matrix[3,:3],_anchor_matrix=matrix))
        lights[1]['配方']=dict(copy.deepcopy(engine.DEFAULT_RECIPE),峰值倍率=3.7)
        project=dict(source=str(original),source_sha256=engine.digest(original),recipe=copy.deepcopy(engine.DEFAULT_RECIPE),lights=lights)
        self.finished=self.build(project)

    def build(self,project):
        def compile_fixture(source,target,client):target.write_bytes(b'offline test fixture, never executable')
        with patch.object(engine,'client_info',return_value={'root':str(self.root/'client')}), \
             patch.object(engine,'compile27',side_effect=compile_fixture), \
             patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
            target,report=engine.build(project,self.root/'client',self.root/'outputs','recovery_fixture',embed_recoverable=False)
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        return target

    def restore(self,path=None):
        return engine.scan(path or self.finished,self.root/'work')

    def manifest(self,path):
        with zipfile.ZipFile(path) as z:
            names=light_recovery.manifests(z.namelist())
            self.assertEqual(len(names),1)
            return names[0],json.loads(z.read(names[0]))

    def changed(self,mutate):
        path=self.root/'modified.wotmod'
        with zipfile.ZipFile(self.finished) as a,zipfile.ZipFile(path,'w',zipfile.ZIP_STORED) as b:
            for n in a.namelist():
                raw=a.read(n)
                if light_recovery.MANIFEST.fullmatch(n):
                    data=json.loads(raw);mutate(data);raw=json.dumps(data).encode()
                b.writestr(n,raw)
        return path

    def test_restores_geometry_recipe_and_motion_frame_without_changing_source(self):
        before=engine.digest(self.finished);project=self.restore()
        self.assertEqual(before,engine.digest(self.finished))
        self.assertEqual(len(project['lights']),2)
        self.assertTrue(all(x['selected'] and x['recovered_model'] for x in project['lights']))
        self.assertEqual(project['lights'][1]['配方']['峰值倍率'],3.7)
        self.assertFalse(project['baseline_user_confirmed'])
        for rec in project['lights']:
            np.testing.assert_allclose(rec['_preview'],rec['_vertices'][:,:3]+rec['_anchor_matrix'][3,:3])
            self.assertEqual(rec['source_visual'],self.visual)
            self.assertAlmostEqual(mesh.area(rec['_vertices'],rec['_indices']),mesh.area(*ring()),places=7)

    def test_saved_recovery_project_reopens_with_choices_and_local_recipes(self):
        project=self.restore();project['lights'][0]['selected']=False
        project['lights'][1]['配方']['峰值倍率']=5.1
        target=self.root/'saved.wotlights';engine.save_project(project,target)
        loaded=engine.load_project(target,self.root/'reopened')
        self.assertFalse(loaded['lights'][0]['selected'])
        self.assertEqual(loaded['lights'][1]['配方']['峰值倍率'],5.1)
        self.assertEqual(loaded['source_sha256'],project['source_sha256'])
        self.assertIn('recovery',loaded)

    def test_rebuild_replaces_runtime_keeps_deselected_rig_and_vehicle_bytes(self):
        project=self.restore();old_name,old=self.manifest(self.finished)
        project['lights'][1]['selected']=False;project['recipe']['峰值倍率']=6.
        result=self.build(project);name,data=self.manifest(result)
        self.assertEqual(len(data['models']),2)
        self.assertEqual(data['per_model_recipes']['retained_000']['峰值倍率'],3.7)
        with zipfile.ZipFile(self.finished) as a,zipfile.ZipFile(result) as b:
            self.assertNotIn(old_name,b.namelist())
            self.assertNotIn(old['runtime_scripts'][0],b.namelist())
            self.assertEqual(len([n for n in b.namelist() if light_recovery.SCRIPT.fullmatch(n)]),1)
            for n in a.namelist():
                if n.startswith('res/vehicles/') or n=='res/unrelated.dat':self.assertEqual(a.read(n),b.read(n))
            retained=data['models'][1]['sequence']
            self.assertEqual(a.read('res/'+retained),b.read('res/'+retained))
        restored=self.restore(result)
        self.assertEqual(len(restored['lights']),2)
        self.assertEqual(restored['recipe']['峰值倍率'],6.)
        self.assertEqual(restored['lights'][1]['配方']['峰值倍率'],3.7)

    def test_repeated_rebuilds_do_not_accumulate_active_runtimes_or_models(self):
        first=self.restore();first['lights'][0]['selected']=False
        second=self.restore(self.build(first));second['lights'][1]['selected']=False
        output=self.build(second);_,data=self.manifest(output)
        self.assertEqual(len(data['models']),2)
        self.assertEqual(len(self.restore(output)['lights']),2)
        with zipfile.ZipFile(output) as z:self.assertEqual(len([n for n in z.namelist() if light_recovery.SCRIPT.fullmatch(n)]),1)

    def test_restored_model_can_render_in_vehicle_preview(self):
        project=self.restore();bands=preview.lamp_plan(project,{'chassis':self.visual})
        self.assertTrue(bands)
        folder=self.root/'lamps_1';folder.mkdir()
        project['lights'][1]['selected']=False
        project['recipe']['峰值倍率']=10.
        cache={};preview.make_lamps(project,None,{'visuals':{'chassis':self.visual}},folder,cache=cache)
        peaks={b['model_key'][0][0]:b['config']['peak'] for b in cache['bands']}
        self.assertEqual(peaks[project['lights'][0]['visual']],10.)
        self.assertEqual(peaks[project['lights'][1]['visual']],3.7)

    def test_path_traversal_in_manifest_is_rejected(self):
        p=self.changed(lambda d:d['models'][0].update(sequence='../../private.seq'))
        with self.assertRaisesRegex(ValueError,'路径无效'):self.restore(p)

    def test_unknown_dual_node_correction_is_rejected_instead_of_flattened(self):
        p=self.changed(lambda d:d['models'][0].update(other_anchor='W_R1'))
        with self.assertRaisesRegex(ValueError,'双节点'):self.restore(p)

    def test_missing_source_or_unknown_scope_has_actionable_failure(self):
        p=self.changed(lambda d:d.update(scope='foreign producer'))
        with self.assertRaisesRegex(ValueError,'原成品包未修改'):self.restore(p)

    def test_untracked_maker_script_is_rejected(self):
        p=self.changed(lambda d:None)
        with zipfile.ZipFile(p,'a') as z:z.writestr('res/scripts/client/gui/mods/mod_light_maker_0123456789ab.pyc',b'never run')
        with self.assertRaisesRegex(ValueError,'未记录'):self.restore(p)

    def test_legacy_manifest_without_runtime_field_recovers(self):
        p=self.changed(lambda d:d.pop('runtime_scripts'))
        self.assertEqual(len(self.restore(p)['lights']),2)

    def test_arbitrary_particle_manifest_is_not_a_maker_finished_package(self):
        self.assertEqual(light_recovery.manifests(['res/particles/other/manifest.json']),[])


if __name__=='__main__':unittest.main()
