import copy, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from wotcamo import autosave, light_effects as engine, light_assets as mesh
from test_light_wheels import ring, fixture_visual

class AutosaveTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_preferences_and_draft_roundtrip_and_rotation(self):
        with patch.object(autosave,'FOLDER',self.root/'backups'), patch.object(autosave,'SETTINGS',self.root/'settings.json'):
            self.assertTrue(autosave.enabled('texture'))
            autosave.set_enabled('texture',False);autosave.set_enabled('lights',True)
            self.assertFalse(autosave.enabled('texture'));self.assertTrue(autosave.enabled('lights'))
            for n in range(4): path=autosave.save_draft({'prompt':str(n)})
            self.assertEqual(autosave.load_draft(path)['prompt'],'3')
            self.assertEqual(len(list(path.parent.glob('*.json'))),3)

    def test_light_backup_reopens_saved_choices_and_unapplied_draft(self):
        vertices,indices=ring();visual=fixture_visual(vertices,indices)
        path='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'; source=self.root/'input.wotmod'
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(path,mesh.xml(visual));z.writestr(path.replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,indices.ravel()));z.writestr('res/wheel.dds',mesh.dds(True))
        project=engine.scan(source,self.root/'scan');self.assertTrue(project['lights'])
        project['lights'][0]['selected']=True
        project['lights'][0]['配方']=dict(copy.deepcopy(engine.DEFAULT_RECIPE),峰值倍率=3.5)
        state={'form':{'step':'unfinished.'},'scope':'套选灯面','picked':[project['lights'][0]['id']]}
        target=self.root/'backup.wotlights';engine.save_project(project,target,autosave_ui=state)
        loaded=engine.load_project(target,self.root/'load')
        self.assertEqual(loaded['_autosave_ui'],state)
        self.assertTrue(loaded['lights'][0]['selected'])
        self.assertEqual(loaded['lights'][0]['配方']['峰值倍率'],3.5)
        self.assertEqual(loaded['source_sha256'],project['source_sha256'])
        with self.assertRaisesRegex(ValueError,'已存在'):
            engine.save_project(project,target,autosave_ui=state)

    def test_no_false_success_for_unrecoverable_body_overlay(self):
        project={'lights':[{'overlay_body':True}]}
        with self.assertRaisesRegex(ValueError,'框选灯面'):
            engine.save_project(project,self.root/'overlay.wotlights',autosave_ui={})
        self.assertFalse((self.root/'overlay.wotlights').exists())
