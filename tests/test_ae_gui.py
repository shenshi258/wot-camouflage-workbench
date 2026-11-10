import unittest,tkinter as tk
from wotcamo.ae_gui import AEImporter

class AEGUITests(unittest.TestCase):
    def setUp(self):
        try:self.app=AEImporter()
        except tk.TclError as e:self.skipTest(str(e))
        self.app.geometry('1080x700');self.app.update()
    def tearDown(self):
        if hasattr(self,'app'):self.app.close()
    def test_precise_image_rotation_is_saved_without_light_flow_buttons(self):
        self.app.values['angle'].set('37');self.assertEqual(self.app.collect()['angle'],37)
        self.assertFalse(hasattr(self.app,'direction_buttons'))

    def test_typing_or_pasting_a_colour_enables_tint_and_restore_keeps_original(self):
        app=self.app;entry=app.fields['tint_color']
        app.param_tabs.select(4);app.update();entry.focus_force();app.update()
        entry.delete(0,'end');entry.insert(0,'#00C8FF');entry.event_generate('<KeyRelease>',keysym='f');app.update()
        self.assertEqual(app.collect()['tint_strength'],100)
        self.assertEqual(app.collect()['tint_color'],'#00C8FF')
        app.values['tint_strength'].set('0');app.update()
        # Navigation alone must not re-enable a deliberately restored colour.
        entry.event_generate('<KeyRelease>',keysym='Left');app.update()
        self.assertEqual(app.collect()['tint_strength'],0)
        entry.delete(0,'end');entry.insert(0,'#FF20A0');entry.event_generate('<FocusOut>');app.update()
        self.assertEqual(app.collect()['tint_strength'],100)
        self.assertEqual(app.collect()['tint_color'],'#FF20A0')

    def test_programmatic_colour_restore_does_not_enable_tint(self):
        app=self.app;values=app.collect();values.update(tint_color='#FF20A0',tint_strength=0)
        app.param_tabs.select(4);app.update();app.color_entry.focus_force();app.update()
        app.restore_settings(values);app.update()
        app.color_entry.event_generate('<FocusOut>');app.update()
        self.assertEqual(app.collect()['tint_strength'],0)

    def test_copy_paste_settings_keeps_current_assets_and_rejects_invalid_clipboard(self):
        from unittest.mock import patch
        app=self.app;clipboard={}
        app.source.set('current-source.wotmod');project={'ae_selection':{'groups':[]}};clip=object()
        app.project=project;app.clip=clip
        app.fit_mode.set('等比重复平铺');app.values['tile_repeat'].set('3');app.values['x'].set('2');app.values['brightness'].set('7.5')
        expected=app.collect()
        with patch.object(app,'clipboard_clear'),patch.object(app,'clipboard_append',side_effect=lambda text:clipboard.update(text=text)),patch.object(app,'clipboard_get',side_effect=lambda:clipboard['text']):
            app.copy_settings();app.fit_mode.set('拉伸填充（旧版）');app.values['x'].set('-3');app.paste_settings()
            self.assertEqual(app.collect(),expected)
            clipboard['text']='not settings'
            with patch('wotcamo.ae_gui.messagebox.showerror') as error:app.paste_settings();error.assert_called_once()
            self.assertEqual(app.collect(),expected)
        self.assertIs(app.project,project);self.assertIs(app.clip,clip);self.assertEqual(app.source.get(),'current-source.wotmod')

    def test_tile_option_control_and_copy_buttons_have_help_and_busy_states(self):
        from tkinter import ttk
        from wotcamo import ui_theme
        app=self.app
        self.assertTrue(app.fields['tile_repeat'].instate(['disabled']))
        app.fit_mode.set('等比重复平铺');self.assertTrue(app.fields['tile_repeat'].instate(['!disabled']))
        controls=[b for b in app.buttons if b.cget('text') in ('复制设置','粘贴设置')]
        self.assertEqual(len(controls),2)
        for control in controls+[app.fields['tile_repeat']]:self.assertIn(control,app.hover_help.providers)
        snapshot=ui_theme.lock_controls(app)
        self.assertTrue(all(w.instate(['disabled']) for w in controls))
        ui_theme.unlock_controls(snapshot);self.assertTrue(all(w.instate(['!disabled']) for w in controls))

    def test_appearance_sliders_save_values_and_reset_independently_of_placement(self):
        for key,value in [('brightness',100),('contrast',2),('transparency',65)]:
            self.app.adjustment_sliders[key].set(value)
        self.app.update()
        c=self.app.collect()
        self.assertEqual((c['brightness'],c['contrast'],c['transparency']),(100,2,65))
        self.app.values['x'].set('2');self.app.reset_appearance()
        c=self.app.collect();self.assertEqual((c['brightness'],c['contrast'],c['transparency']),(1,1,0))
        self.assertEqual(c['x'],2)
    def test_surface_modes_expose_only_relevant_controls(self):
        self.app.placement.set('贴面播放');self.app.update()
        self.assertTrue(self.app.fields['x'].instate(['disabled']));self.assertTrue(self.app.fields['lift'].instate(['disabled']))
        self.assertEqual(self.app.collect()['blend'],'alpha')
        self.app.placement.set('贴面发光');self.app.update();self.assertFalse(self.app.fields['lift'].instate(['disabled']));self.assertEqual(self.app.collect()['blend'],'add')
        self.app.placement.set('独立平面');self.app.update();self.assertFalse(self.app.fields['x'].instate(['disabled']))
    def test_surface_scaling_crop_reset_retains_the_attachment(self):
        self.app.placement.set('贴面发光');self.app.project={'ae_selection':{'groups':[]},'ae_surface_origin':{'point':[1,2,3]}}
        self.app.values['uv_scale_x'].set('2');self.app.values['uv_scale_y'].set('.5');self.app.values['crop_left'].set('10')
        values=self.app.collect();self.assertEqual(values['uv_scale_x'],2);self.assertEqual(values['uv_scale_y'],.5);self.assertEqual(values['crop_left'],10)
        self.app.reset_fitting();self.assertEqual(self.app.collect()['uv_scale_x'],1);self.assertEqual(self.app.collect()['crop_left'],0)
        self.assertIn('ae_surface_origin',self.app.project)
        self.app.clear_surface();self.assertNotIn('ae_surface_origin',self.app.project)

    def test_plane_length_and_height_controls_are_enabled_and_independent(self):
        self.app.placement.set('独立平面');self.app.update()
        for key in ('uv_scale_x','uv_scale_y'):self.assertTrue(self.app.fields[key].instate(['!disabled']))
        self.app.values['uv_scale_x'].set('2');self.assertEqual(self.app.collect()['uv_scale_y'],1)
        self.app.values['uv_scale_y'].set('.5');self.assertEqual(self.app.collect()['uv_scale_x'],2)
        self.assertEqual(self.app.param_tabs.index('current'),0)

    def test_new_plane_resets_old_shape_and_crop_but_keeps_animation_timing(self):
        self.app.project={'ae_selection':{'groups':[{'triangles':[0,1]}]}}
        self.app.placement.set('贴面发光');self.assertIn('仅显示所选侧',self.app.selection_note.get())
        self.app.values['fps'].set('30');self.app.values['warp_tr_x'].set('.4');self.app.values['crop_left'].set('20')
        self.app.new_plane();self.app.update();c=self.app.collect()
        self.assertEqual(c['placement'],'plane');self.assertEqual(c['fps'],30);self.assertEqual(c['warp_tr_x'],0);self.assertEqual(c['crop_left'],0)
        self.assertTrue(self.app.fields['warp_tr_z'].instate(['!disabled']))
        self.assertIn('不受此选区裁剪',self.app.selection_note.get())
        self.app.values['warp_tr_z'].set('.4');self.app.values['x'].set('2');self.app.reset_deform()
        self.assertEqual(self.app.collect()['warp_tr_z'],0);self.assertEqual(self.app.collect()['x'],2)

    def test_packaging_choices_and_primary_action_remain_visible_in_compact_window(self):
        for checked in (False,True):
            self.app.auto_bundle.set(checked);self.app.update_packaging();self.app.update()
            self.assertEqual(self.app.project_toggle.instate(['disabled']),not checked)
            expected='生成涂装包';self.assertEqual(self.app.export_button.cget('text'),expected)
        for widget in [self.app.export_button,self.app.project_toggle]:
            self.assertTrue(widget.winfo_ismapped());self.assertGreaterEqual(widget.winfo_rooty(),self.app.winfo_rooty())
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),self.app.winfo_rooty()+self.app.winfo_height())

if __name__=='__main__':unittest.main()
