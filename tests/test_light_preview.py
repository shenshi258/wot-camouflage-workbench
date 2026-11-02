"""Offline simulation correctness and UI lifecycle; no game or original package writes."""
import copy
import time
import unittest
from unittest.mock import patch
import numpy as np
from wotcamo import light_preview, light_effects as engine, light_recipe
import test_light_wheels as wheels
import test_light_gui_selection as selection


class PreviewTests(unittest.TestCase):
    def test_wheel_segments_variants_and_originals_untouched(self):
        lights=wheels.WheelExportTests().lights()
        raw=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式='波浪')
        before=copy.deepcopy(lights)
        plan=light_preview.prepare(lights,raw)
        self.assertEqual(len(plan),12)
        self.assertGreater(len({round(b['offset'],6) for b in plan}),1)
        self.assertEqual(plan[0]['visuals'],{x['visual'] for x in lights})
        for a,b in zip(lights,before):
            np.testing.assert_array_equal(a['_vertices'],b['_vertices'])
            self.assertEqual(a.get('配方'),b.get('配方'))

    def test_modes_change_over_time_and_pause_brightness_can_be_black(self):
        for mode in light_recipe.MODES:
            raw=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式=mode,暗相系数=0)
            band=dict(config=light_recipe.validate_config(raw),offset=0)
            colors={light_preview.colors(t,band)[0] for t in np.linspace(0,6,49)}
            self.assertGreater(len(colors),3,mode)
            if mode in ('波浪','动态呼吸','流水呼吸'):
                self.assertEqual(light_preview.colors(1,band)[0],'#000000')

    def test_unselected_unsupported_and_independent_recipe(self):
        lights=wheels.WheelExportTests().lights()[:1]
        lights[0]['selected']=False
        self.assertEqual(light_preview.prepare(lights,engine.DEFAULT_RECIPE),[])
        lights[0]['selected']=True;lights[0]['supported']=False
        self.assertEqual(light_preview.prepare(lights,engine.DEFAULT_RECIPE),[])
        lights[0]['supported']=True
        lights[0]['配方']=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式='跑马灯',峰值倍率=5)
        plan=light_preview.prepare(lights,engine.DEFAULT_RECIPE)
        self.assertTrue(all(x['config']['mode']=='跑马灯' and x['config']['peak']==5 for x in plan))

    def test_dense_geometry_is_sampled_without_altering_export_input(self):
        lights=wheels.WheelExportTests().lights()[:1]
        indices=np.tile(lights[0]['_indices'],(30,1));lights[0]['_indices']=indices
        plan=light_preview.prepare(lights,engine.DEFAULT_RECIPE)
        self.assertTrue(all(x['sampled'] for x in plan));self.assertEqual(len(plan),12)
        np.testing.assert_array_equal(lights[0]['_indices'],indices)


class LiveGuiTests(unittest.TestCase):
    def setUp(self):
        from wotcamo.light_gui import LightMaker
        self.app=LightMaker();self.app.withdraw();self.app.update_idletasks()
        project=selection.make_project()
        real=wheels.WheelExportTests().lights()[0]
        real.update(material='mat',triangles=len(real['_indices']),component=0,reason='')
        project['lights']=[real]
        self.app.set_project(project);self.app.update_idletasks()

    def tearDown(self):
        if not self.app._closing:self.app.destroy()

    def wait_plan(self):
        deadline=time.perf_counter()+5
        while time.perf_counter()<deadline:
            self.app.update()
            if self.app._live_plan:return
            time.sleep(.01)
        self.fail('Live worker did not complete: '+self.app.live_note.get())

    def enable(self):
        self.app.preview_mode.set('实时灯效');self.app.change_preview_mode();self.wait_plan()

    def test_toggle_animation_pause_replay_and_selection_preserved(self):
        app=self.app;app.picked={app.project['lights'][0]['id']}
        original=copy.deepcopy(app.project['recipe'])
        app.zoom_preview(2);self.enable()
        self.assertEqual(len(app._live_tags),12)
        self.assertIsNotNone(app._live_after)
        app.pause_live();frozen=app.live_seconds();time.sleep(.02)
        self.assertEqual(frozen,app.live_seconds())
        cores=[core for _,core,_ in app._live_tags if app.canvas.find_withtag(core)]
        before=[app.canvas.itemcget(core,'fill') for core in cores]
        app._live_elapsed+=.5;app.paint_live()
        self.assertNotEqual(before,[app.canvas.itemcget(core,'fill') for core in cores])
        app.restart_live();self.assertEqual(app.live_seconds(),0)
        app.pause_live();time.sleep(.01);self.assertGreater(app.live_seconds(),0)
        picked=app.picked.copy();app.preview_mode.set('位置示意');app.change_preview_mode()
        self.assertIsNone(app._live_after);self.assertEqual(app.picked,picked)
        self.assertEqual(app._preview_zoom,2);self.assertEqual(app.project['recipe'],original)

    def test_live_drafts_never_commit_and_invalid_input_has_no_dialog(self):
        app=self.app;original=copy.deepcopy(app.project['recipe']);light=app.project['lights'][0]
        self.enable();app.peak.set('4');app.refresh_live_form();self.wait_plan()
        self.assertTrue(all(x['config']['peak']==4 for x in app._live_plan))
        self.assertEqual(app.project['recipe'],original)
        previous=app._live_plan
        with patch('wotcamo.light_gui.messagebox.showerror') as popup:
            app.step.set('');app.refresh_live_form()
            self.assertTrue(app._live_error);self.assertIs(app._live_plan,previous);popup.assert_not_called()
        app.step.set('2');app.edit_scope.set('套选模型');app._local_form_baseline=copy.deepcopy(app.read_form())
        app.picked={light['id']};app.peak.set('6');app.refresh_live_form();self.wait_plan()
        self.assertTrue(all(x['config']['peak']==6 for x in app._live_plan))
        self.assertNotIn('配方',light);self.assertEqual(app.project['recipe'],original)

    def test_stale_worker_is_discarded_and_shutdown_cancels_animation(self):
        self.enable();app=self.app
        app.after_cancel(app._live_after);app._live_after=None
        app._live_results.put(('obsolete',[],None));app.live_tick()
        self.assertTrue(app._live_plan)
        app.colors.set('#FF0000')
        app.destroy()
        self.assertIsNone(app._live_after);self.assertIsNone(app._live_edit_after)
