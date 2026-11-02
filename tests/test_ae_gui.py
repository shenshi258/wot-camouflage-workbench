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
