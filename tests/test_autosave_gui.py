import tempfile, time, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from wotcamo import autosave, light_effects as engine, light_assets as mesh
from test_light_wheels import ring, fixture_visual

class AutosaveGUITests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.p1=patch.object(autosave,'FOLDER',self.root/'backups');self.p2=patch.object(autosave,'SETTINGS',self.root/'settings.json')
        self.p1.start();self.p2.start();self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop)

    def test_workbench_save_and_restore(self):
        from wotcamo.gui import Workbench
        app=Workbench();app.withdraw();self.addCleanup(app.destroy)
        app.title_var.set('我的草稿');app.materials.set('E:/素材');app.prompt.delete('1.0','end');app.prompt.insert('1.0','没有写完的描述')
        app.autosave_tick()
        path=next((autosave.FOLDER/'涂装草稿').glob('*.json'))
        app.title_var.set('已改变');app.prompt.delete('1.0','end')
        with patch('wotcamo.gui.filedialog.askopenfilename',return_value=str(path)):app.restore_draft()
        self.assertEqual(app.title_var.get(),'我的草稿');self.assertEqual(app.prompt.get('1.0','end-1c'),'没有写完的描述')
        app.auto_save.set(False);app.change_autosave();app.autosave_tick()
        self.assertEqual(len(list(path.parent.glob('*.json'))),1)

    def test_light_autosave_reopens_unapplied_form(self):
        from wotcamo.light_gui import LightMaker
        vertices,indices=ring();visual=fixture_visual(vertices,indices)
        name='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed';source=self.root/'source.wotmod'
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(name,mesh.xml(visual));z.writestr(name.replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,indices.ravel()));z.writestr('res/wheel.dds',mesh.dds(True))
        project=engine.scan(source,self.root/'scan');app=LightMaker();app.withdraw();self.addCleanup(app.destroy)
        app.set_project(project);light=project['lights'][0];light['selected']=True
        app.picked={light['id']};app.active=light;app.edit_scope.set('套选灯面');app._editor_scope='套选灯面'
        app.step.set('未输入完');app.autosave_tick()
        deadline=time.monotonic()+10
        while app._autosave_running and time.monotonic()<deadline:
            app.update();time.sleep(.02)
        self.assertFalse(app._autosave_running)
        paths=list((autosave.FOLDER/'灯效工程').rglob('*.wotlights'));self.assertEqual(len(paths),1)
        loaded=engine.load_project(paths[0],self.root/'load');app.set_project(loaded)
        self.assertEqual(app.step.get(),'未输入完');self.assertEqual(app.edit_scope.get(),'套选灯面')
        self.assertEqual(app.picked,{light['id']});self.assertTrue(app.project['lights'][0]['selected'])
