"""GUI-level checks for marquee selection and per-model recipes.

The window is created withdrawn, so no dialog is left on screen. When tkinter
cannot start (headless session) the tests skip instead of failing.
"""

import unittest
import copy
from pathlib import Path
from unittest.mock import patch
import numpy as np

from wotcamo import light_effects as engine, light_select

try:
    import tkinter as tk
except Exception:  # pragma: no cover - tkinter is bundled with the runtime
    tk = None

VISUAL_A = 'res/vehicles/test_vehicle/normal/lod0/gun_01.visual_processed'
VISUAL_B = 'res/vehicles/test_vehicle/normal/lod0/gun_02.visual_processed'


def face(identifier, visual, anchor, texture, points, part='gun', supported=True):
    points = np.asarray(points, dtype=float)
    return dict(id=identifier, vehicle='test_vehicle', nation='test', part=part, visual=visual,
                primitives=visual.replace('.visual_processed', '.primitives_processed'),
                render_set=0, geometry=0, group=0, material='mat', component=0,
                source_triangle_ids=[0], texture=texture, triangles=1,
                supported=supported, reason='' if supported else '需适配', selected=False,
                anchor=anchor, anchor_kind='node', transform=np.eye(4).tolist(),
                _preview=points, _vertices=np.zeros((len(points), 8)),
                _indices=np.array([[0, 1, 2]]), _anchor_matrix=np.eye(4),
                bounds=[points.min(0).tolist(), points.max(0).tolist()])


def make_project():
    lights = [
        face('a1', VISUAL_A, 'Gun', 'a.dds', [[0, 0, -1], [1, 0, -1], [0, 1, -1]]),
        face('a2', VISUAL_A, 'Gun', 'a.dds', [[0, 0, -2], [1, 0, -2], [0, 1, -2]]),
        face('g1', VISUAL_A, 'G', 'a.dds', [[0, 0, 3], [1, 0, 3], [0, 1, 3]]),
        face('b1', VISUAL_B, 'Gun', 'b.dds', [[5, 0, 0], [6, 0, 0], [5, 1, 0]]),
    ]
    recipe = dict(engine.DEFAULT_RECIPE)
    return dict(schema=1, source='input.wotmod', source_sha256='0' * 64, lights=lights,
                scan_issues=[], recipe=recipe, baseline_user_confirmed=False)


class SelectionGuiTests(unittest.TestCase):
    def setUp(self):
        if tk is None:
            self.skipTest('tkinter 不可用')
        from wotcamo.light_gui import LightMaker
        try:
            self.app = LightMaker()
            self.app.withdraw()
            self.app.update_idletasks()
        except Exception as error:  # pragma: no cover - depends on the desktop session
            self.skipTest('无法创建窗口：%s' % error)
        self.app.set_project(make_project())
        self.app.update_idletasks()

    def tearDown(self):
        app = getattr(self, 'app', None)
        if app is not None:
            try: app.destroy()
            except Exception: pass

    def rect(self):
        """The whole preview canvas, so a marquee covers every face."""
        return (0, 0, 6000, 6000)

    def use_all_faces(self):
        self.app.preview_scope.set('全部灯面')
        self.app.draw_preview()

    def test_single_face_mode_changes_only_target_and_preview_draft(self):
        self.app.picked={'a1'}
        self.app.edit_scope.set('套选灯面');self.app.change_edit_scope()
        self.app.peak.set('4');self.app.color_curve.set('匀速无缝')
        state=self.app.preview3d_state()
        by_id={x['id']:x for x in state['lights']}
        self.assertEqual(by_id['a1']['recipe']['换色曲线'],'匀速')
        self.assertIsNone(by_id['a2']['recipe'])
        self.app.apply_recipe_to_picked()
        self.assertEqual(self.app.records['a1']['配方']['峰值倍率'],4)
        self.assertNotIn('配方',self.app.records['a2'])
        self.assertIn('灯面',self.app.apply_button.cget('text'))

    def test_tree_parent_and_leaf_selection_updates_preview_selection(self):
        self.app.tree.selection_set('a1');self.app.on_pick()
        self.assertEqual(self.app.picked,{'a1'})
        self.app.tree.selection_set(self.app.tree.parent('a1'));self.app.on_pick()
        self.assertEqual(self.app.picked,{'a1','a2','g1'})

    def test_irrelevant_fields_are_disabled_and_reenabled(self):
        self.app.effect_mode.set('流水渐变')
        self.assertIn('disabled',self.app.parameter_entries['呼吸周期'].state())
        self.assertIn('disabled',self.app.parameter_entries['暗相系数'].state())
        self.app.effect_mode.set('跑马灯')
        self.assertNotIn('disabled',self.app.parameter_entries['呼吸周期'].state())
        self.assertNotIn('disabled',self.app.parameter_entries['亮灯比例'].state())

    def test_actions_require_a_target_and_client_is_not_assumed(self):
        self.assertEqual(self.app.client.get(),'')
        self.assertIn('disabled',self.app.apply_button.state())
        self.assertIn('disabled',self.app.build_button.state())
        self.app.tree.selection_set('a1');self.app.on_pick()
        self.assertNotIn('disabled',self.app.apply_button.state())
        self.app.select_all(True)
        self.assertNotIn('disabled',self.app.build_button.state())

    def test_snapshot_freezes_choices_and_uses_readonly_geometry(self):
        snapshot=self.app.project_snapshot()
        self.app.project['lights'][0]['selected']=True
        self.assertFalse(snapshot['lights'][0]['selected'])
        self.assertFalse(snapshot['lights'][0]['_vertices'].flags.writeable)
        self.assertTrue(self.app.project['lights'][0]['_vertices'].flags.writeable)

    def test_callback_failure_keeps_job_polling(self):
        def broken(_):raise RuntimeError('fixture callback failure')
        self.app.after_cancel(self.app._drain_after);self.app._drain_after=None
        self.app.events.put(('done',(broken,None)));self.app.busy=True
        with patch.object(self.app,'write_error') as log,patch('wotcamo.light_gui.messagebox.showerror'):
            self.app.drain()
        self.assertFalse(self.app.busy);self.assertIsNotNone(self.app._drain_after)
        self.assertIn('fixture callback failure',log.call_args.args[0])

    def test_marquee_on_current_model_only_sees_that_model(self):
        self.app.apply_marquee(self.rect(), 0)
        self.assertEqual(len(self.app.picked), 3)
        self.assertIn('3 块灯面', self.app.pick_text.get())
        self.assertIn('2 个模型', self.app.pick_text.get())

    def test_marquee_selects_faces_and_reports_model_count(self):
        self.use_all_faces()
        self.app.apply_marquee(self.rect(), 0)
        self.assertEqual(len(self.app.picked), 4)
        self.assertIn('4 块灯面', self.app.pick_text.get())
        self.assertIn('3 个模型', self.app.pick_text.get())

    def test_alt_marquee_expands_to_whole_model(self):
        from wotcamo.light_gui import LightMaker
        fresh = LightMaker(); fresh.withdraw(); fresh.set_project(make_project())
        try:
            fresh.apply_marquee(self.rect(), 0)
            view = fresh._preview_view
            screen = view.screen(fresh.project['lights'][0]['_preview'], view.panes[0])
            box = (screen[:, 0].min() - 1, screen[:, 1].min() - 1,
                   screen[:, 0].max() + 1, screen[:, 1].max() + 1)
            fresh.picked = set()
            fresh.apply_marquee(box, 0x20000)  # Alt: expand to models
            self.assertEqual(fresh.picked, {'a1', 'a2'})
        finally:
            fresh.destroy()

    def test_control_marquee_subtracts(self):
        self.use_all_faces()
        self.app.apply_marquee(self.rect(), 0)
        self.assertEqual(len(self.app.picked), 4)
        view = self.app._preview_view
        screen = view.screen(self.app.project['lights'][0]['_preview'], view.panes[0])
        box = (screen[:, 0].min() - 1, screen[:, 1].min() - 1, screen[:, 0].max() + 1, screen[:, 1].max() + 1)
        self.app.apply_marquee(box, 0x4)  # Ctrl: subtract the boxed face
        self.assertNotIn('a1', self.app.picked)
        self.assertIn('a2', self.app.picked)

    def test_pick_scope_all_and_clear(self):
        self.use_all_faces()
        self.app.pick_scope_all()
        self.assertEqual(len(self.app.picked), 4)
        self.app.pick_clear()
        self.assertEqual(self.app.picked, set())
        self.assertIn('0 块灯面', self.app.pick_text.get())

    def test_together_setting_writes_one_recipe_per_model(self):
        self.use_all_faces()
        self.app.apply_marquee(self.rect(), 0)
        self.app.mark_picked(True)
        self.assertTrue(all(x['selected'] for x in self.app.project['lights']))
        self.app.apply_recipe_to_picked()
        recipe = engine.override_recipe(self.app.project['lights'][0])
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe['颜色'], self.app.read_form()['颜色'])
        # Every face of model A shares the same override, model B has its own copy.
        for light in self.app.project['lights']:
            self.assertIsNotNone(engine.override_recipe(light))
        self.assertIn('3 个模型', self.app.status.get())
        # The tree marks independent recipes so the state is visible without the preview.
        self.assertIn('⚙', self.app.tree.item('a1', 'text'))
        engine.model_recipes([x for x in self.app.project['lights'] if x['selected']])

    def test_restoring_global_recipe_removes_override(self):
        self.use_all_faces()
        self.app.apply_marquee(self.rect(), 0)
        self.app.apply_recipe_to_picked()
        self.assertTrue(engine.override_recipe(self.app.project['lights'][0]))
        self.app.clear_recipe_on_picked()
        self.assertFalse(any(engine.override_recipe(x) for x in self.app.project['lights']))
        self.assertNotIn('⚙', self.app.tree.item('a1', 'text'))

    def test_mixed_recipe_inside_one_model_is_refused(self):
        lights = self.app.project['lights']
        lights[0]['配方'] = dict(engine.DEFAULT_RECIPE, 每色秒数=1)
        lights[1]['配方'] = dict(engine.DEFAULT_RECIPE, 每色秒数=3)
        with self.assertRaisesRegex(ValueError, '配方不一致'):
            engine.model_recipes(lights)

    def test_scope_switch_draws_without_error(self):
        self.app.preview_scope.set('全部灯面')
        self.app.draw_preview()
        self.app.preview_scope.set('当前模型')
        self.app.draw_preview()

    def test_click_selects_nearest_face(self):
        self.use_all_faces()
        view = light_select.View(self.app.preview_lights(), 600, 220)
        # Top view separates the three co-linear gun faces along Z.
        x, y = view.screen(self.app.project['lights'][2]['_preview'], view.panes[2])[0]
        self.app.pick_at(float(x), float(y))
        self.assertEqual(self.app.picked, {'g1'})

    def set_local_green(self):
        self.app.picked={'a1'}
        self.app.colors.set('#00FF00')
        self.app.peak.set('5')
        self.app.step.set('4')
        self.app.apply_recipe_to_picked()

    def test_local_apply_then_save_keeps_other_models_global(self):
        original=copy.deepcopy(self.app.project['recipe'])
        self.set_local_green()
        self.assertEqual(self.app.edit_scope.get(),'套选模型')
        # Exercise the same save handler as the real Save Project button.
        with patch('wotcamo.light_gui.filedialog.asksaveasfilename',return_value='saved.wotlights'), \
             patch.object(self.app,'job',side_effect=lambda action,done: action()), \
             patch.object(engine,'save_project') as save:
            self.app.save_project()
            save.assert_called_once()
            saved=save.call_args.args[0]
            self.assertEqual(saved['recipe'],original)
            self.assertEqual(engine.override_recipe(saved['lights'][0])['颜色'][0]['RGB'],'#00FF00')
            self.assertIsNone(engine.override_recipe(saved['lights'][-1]))
        self.assertEqual(self.app.project['recipe'],original)

    def test_local_apply_then_build_keeps_other_models_global(self):
        original=copy.deepcopy(self.app.project['recipe'])
        self.set_local_green()
        with patch.object(engine,'resolve_client_root',return_value=Path('mock_client')), \
             patch.object(self.app,'job',side_effect=lambda action,done: action()), \
             patch('wotcamo.light_delivery.bundle',return_value={}), \
             patch.object(engine,'build',return_value=(Path('pending.wotmod'),{})) as build:
            self.app.build()
            build.assert_called_once()
            project=build.call_args.args[0]
            self.assertEqual(project['recipe'],original)
            self.assertEqual(engine.override_recipe(project['lights'][0])['峰值倍率'],5)
            self.assertIsNone(engine.override_recipe(project['lights'][-1]))

    def test_global_draft_survives_switch_to_local_and_back(self):
        self.app.colors.set('#123456')
        self.app.edit_scope.set('套选模型');self.app.change_edit_scope()
        self.assertEqual(self.app.project['recipe']['颜色'][0]['RGB'],'#123456')
        self.app.edit_scope.set('全局配方');self.app.change_edit_scope()
        self.assertEqual(self.app.colors.get(),'#123456')
        self.assertEqual(self.app.edit_scope.get(),'全局配方')

    def test_unapplied_local_changes_cannot_silently_enter_saved_project(self):
        original=copy.deepcopy(self.app.project['recipe'])
        self.app.edit_scope.set('套选模型');self.app.change_edit_scope()
        self.app.peak.set('6')
        with self.assertRaisesRegex(ValueError,'局部参数尚未应用'):
            self.app.sync_recipe()
        self.assertEqual(self.app.project['recipe'],original)
        self.app.picked={'a1'};self.app.apply_recipe_to_picked()
        self.app.sync_recipe()
        self.assertEqual(self.app.project['recipe'],original)

    def test_read_local_recipe_and_restore_global(self):
        self.set_local_green()
        self.app.edit_scope.set('全局配方');self.app.change_edit_scope()
        self.app.picked={'a1'};self.app.load_picked_recipe()
        self.assertEqual(self.app.colors.get(),'#00FF00')
        self.assertEqual(self.app.peak.get(),'5.0')
        self.app.clear_recipe_on_picked();self.app.sync_recipe()
        self.assertIsNone(engine.override_recipe(self.app.records['a1']))
        self.assertIsNone(engine.override_recipe(self.app.records['a2']))

    def test_new_project_resets_local_editor(self):
        self.set_local_green()
        self.app.set_project(make_project())
        self.assertEqual(self.app.edit_scope.get(),'全局配方')
        self.assertIsNone(self.app._local_form_baseline)
        self.assertFalse(any(engine.override_recipe(x) for x in self.app.project['lights']))

    def test_tree_toggle_operates_on_all_highlighted_faces(self):
        self.app.tree.selection_set('a1','b1')
        self.app.toggle_current()
        self.assertTrue(self.app.records['a1']['selected'])
        self.assertTrue(self.app.records['b1']['selected'])
        self.assertFalse(self.app.records['a2']['selected'])

    def test_unchanged_global_form_keeps_exact_float_palette(self):
        original=copy.deepcopy(self.app.project['recipe'])
        self.app.sync_recipe()
        self.app.edit_scope.set('套选模型');self.app.change_edit_scope()
        self.app.edit_scope.set('全局配方');self.app.change_edit_scope()
        self.app.sync_recipe()
        self.assertEqual(self.app.project['recipe'],original)

    def test_discard_invalid_local_draft_allows_saving(self):
        original=copy.deepcopy(self.app.project['recipe'])
        self.set_local_green()
        self.app.peak.set('not a number')
        self.app.discard_recipe_draft()
        self.app.sync_recipe()
        self.assertEqual(self.app.project['recipe'],original)
        self.assertEqual(self.app.peak.get(),'5.0')

    def test_read_picked_compares_against_latest_global_draft(self):
        self.app.records['a1']['配方']=copy.deepcopy(self.app.project['recipe'])
        self.app.picked={'a1','b1'}
        self.app.colors.set('#00FF00')
        self.app.load_picked_recipe()
        self.assertIn('配方不同',self.app.status.get())
        self.assertEqual(self.app.edit_scope.get(),'全局配方')

    def test_preview_zoom_pan_reset_does_not_change_selection_or_recipe(self):
        from types import SimpleNamespace
        self.use_all_faces();self.app.picked={'a1'};self.app.records['a1']['selected']=True
        recipe=copy.deepcopy(self.app.project['recipe'])
        self.app.zoom_preview(2)
        self.assertEqual(self.app.zoom_text.get(),'200%')
        self.app.on_pan_press(SimpleNamespace(x=20,y=80))
        self.app.on_pan_drag(SimpleNamespace(x=60,y=100))
        np.testing.assert_array_equal(self.app._preview_pan[0],[40,20])
        self.app.on_pan_release(None)
        self.app.reset_preview()
        self.assertEqual(self.app.zoom_text.get(),'100%')
        self.assertEqual(self.app.picked,{'a1'})
        self.assertTrue(self.app.records['a1']['selected'])
        self.assertEqual(self.app.project['recipe'],recipe)

    def test_wheel_zoom_keeps_focus_and_marquee_hits_after_redraw(self):
        from types import SimpleNamespace
        self.use_all_faces();view=self.app._preview_view;pane=view.panes[2]
        point=self.app.records['g1']['_preview'][:1]
        x,y=view.screen(point,pane)[0]
        self.app.on_preview_wheel(SimpleNamespace(delta=120,x=float(x),y=float(y)))
        view=self.app._preview_view
        np.testing.assert_allclose(view.screen(point,view.panes[2])[0],[x,y])
        self.app.apply_marquee((x-3,y-3,x+3,y+3))
        self.assertIn('g1',self.app.picked)


if __name__ == '__main__':
    unittest.main()
