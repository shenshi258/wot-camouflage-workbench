"""Preserve edited parameters across reset, preview snapshots and export."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np

import test_light_gui_selection as gui_fixtures
import test_light_build_review as build_fixtures
import test_preview3d as preview_fixtures
from wotcamo import light_effects as engine, light_recipe as recipe, light_presets, preview3d_assets
from wotcamo.preview3d_assets import evaluate_track


class RecipeResetTests(unittest.TestCase):
    setUp = gui_fixtures.SelectionGuiTests.setUp
    tearDown = gui_fixtures.SelectionGuiTests.tearDown

    def overrides(self):
        for light in self.app.project['lights']:
            light['selected'] = True
            light['配方'] = copy.deepcopy(self.app.project['recipe'])

    def white_draft(self):
        self.app.effect_mode.set('流水渐变')
        self.app.low.set('1')
        self.app.colors.set('#FFFFFF')

    def clear(self, accepted=True):
        with patch('wotcamo.light_gui.messagebox.askyesno', return_value=accepted):
            self.app.clear_all_recipe_overrides()

    def test_global_draft_survives_reset_preview_save_and_final_assets(self):
        self.overrides(); self.white_draft()
        expected = self.app.read_form()
        self.clear()
        self.assertEqual(self.app.read_form(), expected)
        self.assertEqual(self.app.preview3d_state()['recipe'], expected)
        self.app.sync_recipe()
        self.assertEqual(self.app.project['recipe'], expected)
        self.assertTrue(all('配方' not in x for x in self.app.project['lights']))
        # Build final ZIP fixtures and inspect exported material/sequence bytes.
        # The compiler/client are mocked; this does not claim game compatibility.
        fixture = build_fixtures.LightBuildReviewTests()
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache') as tmp:
            root = Path(tmp); project = fixture.project(root)
            project['recipe'] = copy.deepcopy(self.app.project['recipe'])
            with patch.object(engine, 'audit_package', return_value={'status':'fixture_only'}):
                target, report = fixture.build(root, project)
            with zipfile.ZipFile(target) as z:
                sequences = [n for n in z.namelist() if n.endswith('.seq')]
                self.assertTrue(sequences)
                for name in sequences:
                    seq = engine.xml(z.read(name))
                    for track in seq.findall('.//track'):
                        if track.findtext('property') != 'g_tint': continue
                        values = evaluate_track(track.findall('frame'), np.linspace(0, float(seq.findtext('duration')), 193))
                        np.testing.assert_allclose(values[:,:3], expected['峰值倍率'], atol=1e-9)
                    visual = engine.xml(z.read(name.replace('.seq','.visual_processed')))
                    for prop in visual.iter('property'):
                        key = prop.text.strip()
                        if key == 'speed': self.assertEqual(float(prop.findtext('Float')), 0)
                        if key in ('g_offsetBlack','g_offsetBlackFwd'): self.assertEqual(float(prop.findtext('Float')), 1)
            self.assertEqual(report['whole_vehicle_loading']['status'], 'not_tested')

    def test_cancel_preserves_global_draft_and_overrides(self):
        self.overrides(); self.white_draft()
        before = copy.deepcopy(self.app.project['recipe'])
        self.clear(False)
        self.assertEqual(self.app.project['recipe'], before)
        self.assertEqual(self.app.read_form()['暗相系数'], 1)
        self.assertTrue(all('配方' in x for x in self.app.project['lights']))

    def test_same_mode_different_dark_floor_is_reported(self):
        self.overrides()
        self.app.low.set('1'); self.app.sync_recipe()
        _, differing, _, _ = self.app.recipe_scope_report()
        self.assertEqual(len(differing), len(self.app.project['lights']))

    def test_equivalent_color_representation_is_not_a_difference(self):
        self.white_draft(); self.app.sync_recipe(); self.overrides()
        for light in self.app.project['lights']:
            light['配方']['颜色'] = [{'名称':'different label','RGB':[1,1,1]}]
        self.assertEqual(self.app.recipe_scope_report()[1], [])

    def test_local_draft_is_preserved_without_promotion(self):
        self.overrides(); self.app.picked = {'a1'}
        self.app.edit_scope.set('套选灯面'); self.app.change_edit_scope()
        before = copy.deepcopy(self.app.project['recipe'])
        self.white_draft()
        with patch('wotcamo.light_gui.messagebox.showerror') as error:
            self.clear()
        error.assert_called_once()
        self.assertEqual(self.app.project['recipe'], before)
        self.assertEqual(self.app.read_form()['暗相系数'], 1)
        self.assertTrue(all('配方' in x for x in self.app.project['lights']))

    def test_local_applied_reset_returns_to_global_editor(self):
        self.overrides(); self.app.picked = {'a1'}
        self.app.edit_scope.set('套选灯面'); self.app.change_edit_scope()
        self.clear()
        self.assertEqual(self.app.edit_scope.get(), '全局配方')
        self.white_draft(); self.app.sync_recipe()
        self.assertEqual(self.app.project['recipe']['暗相系数'], 1)

    def test_dimming_switch_roundtrip_and_color_only_control_state(self):
        self.app.effect_mode.set('波浪');self.app.dimming.set(False)
        raw=self.app.read_form()
        self.assertIs(raw['启用明暗变化'],False)
        self.app.fill_recipe(raw)
        self.assertFalse(self.app.dimming.get())
        self.assertIn('disabled',self.app.parameter_entries['暗相系数'].state())
        self.app.effect_mode.set('无级变色')
        self.assertFalse(self.app.dimming.get())
        self.assertIn('disabled',self.app.dimming_check.state())
        self.app.effect_mode.set('流水呼吸')
        self.assertNotIn('disabled',self.app.dimming_check.state())
        self.assertFalse(self.app.dimming.get())

    def test_switching_modes_does_not_reenable_disabled_dimming(self):
        self.app.effect_mode.set('波浪');self.app.dimming.set(False)
        for mode in recipe.MODES:
            self.app.effect_mode.set(mode)
            self.assertFalse(recipe.has_dimming(recipe.validate_config(self.app.read_form())),mode)

    def test_continuous_preset_disables_dimming(self):
        self.assertIn('无级变色',self.app.preset_library)
        self.app.preset.set('无级变色');self.app.apply_preset()
        cfg=recipe.validate_config(self.app.read_form())
        self.assertEqual(cfg['mode'],'无级变色')
        self.assertFalse(recipe.has_dimming(cfg))
        self.assertEqual(cfg['curve'],'匀速')


class EnvelopeScopeTests(unittest.TestCase):
    def test_flat_envelope_does_not_guarantee_flat_color_components(self):
        raw = copy.deepcopy(engine.DEFAULT_RECIPE)
        raw.update({'效果模式':'流水渐变','暗相系数':1,'峰值倍率':1,
                    '颜色':[{'名称':'红','RGB':'#FF0000'},{'名称':'蓝','RGB':'#0000FF'}]})
        cfg = recipe.validate_config(raw)
        self.assertEqual(recipe.brightness_bounds(cfg), (1,1))
        np.testing.assert_allclose(recipe.animated_value(cfg['step']/2,0,cfg), [.5,0,.5,1])

    def test_switch_off_flattens_every_mode_even_when_low_is_zero(self):
        for mode in recipe.MODES:
            raw=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式=mode,启用明暗变化=False,
                     暗相系数=0,颜色=[{'名称':'白','RGB':'#FFFFFF'}])
            cfg=recipe.validate_config(raw)
            self.assertEqual(engine.native_pulse_values(cfg),(0,1),mode)
            frames=recipe.colour_track('test',.173,cfg).findall('frame')
            result=evaluate_track(frames,np.linspace(0,cfg['period'],1001))
            np.testing.assert_allclose(result[:,:3],cfg['peak'],atol=1e-8,err_msg=mode)
            np.testing.assert_allclose(result[:,3],1,atol=1e-8)

    def test_continuous_color_track_keeps_value_and_closed_loop(self):
        raw=light_presets.defaults()['无级变色']['配方']
        for curve in ('匀速','柔和'):
            cfg=recipe.validate_config(dict(raw,换色曲线=curve,暗相系数=0))
            for offset in (0,.173,1.991):
                frames=recipe.colour_track('test',offset,cfg).findall('frame')
                times=np.linspace(0,cfg['period'],12001)
                result=evaluate_track(frames,times)
                np.testing.assert_allclose(result[:,:3].max(1),cfg['peak'],atol=2e-8)
                self.assertGreater(np.ptp(result[:,0]),.5)
                self.assertGreaterEqual(result[:,:3].min(),-1e-8)
                np.testing.assert_allclose(result[0],result[-1],atol=1e-8)
                self.assertLess(np.abs(np.diff(result[:,:3],axis=0)).max(),.02)

    def test_invalid_switch_does_not_silently_enable_dimming(self):
        for value in ('false',0,None):
            with self.assertRaisesRegex(ValueError,'启用明暗变化'):
                recipe.validate_config(dict(engine.DEFAULT_RECIPE,启用明暗变化=value))


class PreviewDimmingTests(unittest.TestCase):
    setUp=preview_fixtures.Preview3DTests.setUp
    tearDown=preview_fixtures.Preview3DTests.tearDown

    def test_cached_preview_drops_native_and_sequence_dimming_when_disabled(self):
        cache={}
        self.project['recipe']['颜色']=[{'名称':'白','RGB':'#FFFFFF'}]
        initial=preview3d_assets.make_lamps(self.project,None,self.body,self.root/'lamps_0',cache=cache)
        self.assertTrue(all(t['nativePulse'] for t in initial['tracks']))
        for index,mode in enumerate(recipe.MODES,1):
            self.project['recipe'].update(效果模式=mode,启用明暗变化=False,暗相系数=0)
            folder=self.root/('lamps_%d'%index)
            scene=preview3d_assets.make_lamps(self.project,None,self.body,folder,cache=cache)
            self.assertFalse(any(t['nativePulse'] for t in scene['tracks']))
            data=np.fromfile(folder/'animation.bin',dtype='<f4').reshape(-1,4)
            np.testing.assert_allclose(data[:,:3],self.project['recipe']['峰值倍率'],atol=1e-6)

    def test_continuous_preview_matches_final_zip_sequences(self):
        self.project['recipe']=copy.deepcopy(light_presets.defaults()['无级变色']['配方'])
        folder=self.root/'lamps_0'
        scene=preview3d_assets.make_lamps(self.project,None,self.body,folder)
        lut=np.fromfile(folder/'animation.bin',dtype='<f4').reshape(scene['lutHeight'],scene['lutWidth'],4)
        with patch.object(engine,'client_info',return_value={'root':str(self.root)}), \
             patch.object(engine,'compile27',side_effect=lambda s,t,c:t.write_bytes(b'offline fixture')), \
             patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
            target,report=engine.build(self.project,self.root,self.root/'out','continuous_fixture')
        self.assertEqual(report['breathing_audit']['dimming_models'],[])
        self.assertTrue(all(not row['dimming_enabled'] for row in report['breathing_audit']['models']))
        tracks={}
        with zipfile.ZipFile(target) as z:
            for name in z.namelist():
                if name.endswith('.seq'):
                    for track in engine.xml(z.read(name)).findall('.//track'):
                        if track.findtext('property')=='g_tint':tracks[track.findtext('identifier')]=track
                if name.endswith('/manifest.json'):
                    self.assertEqual(json.loads(z.read(name))['recipe']['效果模式'],'无级变色')
        for index,band in enumerate(scene['bands']):
            result=evaluate_track(tracks[band['identifier']].findall('frame'),np.linspace(0,scene['tracks'][index]['period'],scene['lutWidth']))
            np.testing.assert_allclose(lut[index],result,atol=1e-6)
            self.assertFalse(scene['tracks'][index]['nativePulse'])


if __name__ == '__main__': unittest.main()
