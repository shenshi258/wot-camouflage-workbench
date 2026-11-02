"""Palette draft isolation and new style export validation; no game calls."""
import copy
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
import xml.etree.ElementTree as ET

from wotcamo import light_palette as palette,light_presets as presets,light_recipe as recipe
import test_light_gui_selection as selection


class PaletteTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk();self.root.withdraw()
        except tk.TclError as error:self.skipTest(str(error))
        self.callback=Mock()
        self.dialog=palette.PaletteDialog(self.root,'#ff0000, #00FF00',self.callback)

    def tearDown(self):
        if hasattr(self,'root'):self.root.destroy()

    def test_cancel_discards_draft_and_custom_picker_cancel(self):
        self.dialog.set_color('#00D9FF')
        self.callback.assert_not_called()
        with patch.object(palette.colorchooser,'askcolor',return_value=(None,None)):
            self.dialog.choose_custom()
        self.assertEqual(self.dialog.colors,['#00D9FF','#00FF00'])
        self.dialog.destroy();self.callback.assert_not_called()

    def test_apply_preserves_chosen_order_after_append_move_and_delete(self):
        self.dialog.select(1);self.dialog.set_color('#abcdEf')
        self.dialog.append_color();self.dialog.set_color('#00D9FF')
        self.dialog.move(-1);self.dialog.select(0);self.dialog.delete_color()
        self.dialog.apply()
        self.callback.assert_called_once_with('#00D9FF, #ABCDEF')

    def test_limit_invalid_hex_and_empty_apply_are_non_destructive(self):
        self.dialog.colors=['#FF0000']*12;self.dialog.selected=0
        self.dialog.append_color();self.assertEqual(len(self.dialog.colors),12)
        self.dialog.set_color('invalid');self.assertEqual(self.dialog.colors[0],'#FF0000')
        self.dialog.colors=[];self.dialog.selected=None
        self.dialog.apply();self.callback.assert_not_called()
        self.dialog.set_color('#00ffcc');self.dialog.apply()
        self.callback.assert_called_once_with('#00FFCC')

    def test_parser_accepts_chinese_separator_and_rejects_invalid_input(self):
        self.assertEqual(palette.parse_colors(' #aabbcc， #123456 '),['#AABBCC','#123456'])
        for text in ('#GG0000',', '.join(['#FF0000']*13)):
            with self.assertRaises(ValueError):palette.parse_colors(text)


class NewStyleTests(unittest.TestCase):
    def test_new_styles_export_looping_native_tracks_and_keep_custom_recipes(self):
        builtins=presets.defaults()
        self.assertEqual(len(presets.NEW_PRESETS),16)
        self.assertEqual(len(builtins),41)
        presets.validate_library({'版本':1,'预设':builtins})
        for row in presets.NEW_PRESETS:
            cfg=recipe.validate_config(builtins[row[0]]['配方'])
            track=recipe.colour_track('fixture',.137,cfg)
            frames=track.findall('frame')
            self.assertEqual(frames[0].findtext('value'),frames[-1].findtext('value'),row[0])
            self.assertAlmostEqual(float(frames[-1].findtext('startTime')),cfg['period'])
        old={'我的自定义':copy.deepcopy(builtins['波浪']),'赛博霓虹':copy.deepcopy(builtins['单色呼吸'])}
        before=copy.deepcopy(old);merged=presets.with_new_presets(old)
        self.assertEqual(old,before);self.assertEqual(merged['赛博霓虹'],old['赛博霓虹'])
        self.assertIn('极光漫游',merged)

    def test_palette_changes_only_local_form_until_explicit_apply(self):
        from wotcamo.light_gui import LightMaker
        try:app=LightMaker();app.withdraw()
        except tk.TclError as error:self.skipTest(str(error))
        try:
            app.set_project(selection.make_project());before=copy.deepcopy(app.project['recipe'])
            app.picked={'a1'};app.edit_scope.set('套选模型');app.change_edit_scope()
            dialog=app.open_palette();dialog.set_color('#123456');dialog.apply()
            self.assertTrue(app.colors.get().startswith('#123456'))
            self.assertEqual(app.project['recipe'],before)
            with self.assertRaisesRegex(ValueError,'局部参数尚未应用'):app.sync_recipe()
            app.apply_recipe_to_picked();app.sync_recipe()
            self.assertEqual(app.project['recipe'],before)
            self.assertEqual(app.records['a1']['配方']['颜色'][0]['RGB'],'#123456')
        finally:app.destroy()


if __name__=='__main__':unittest.main()
