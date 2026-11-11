"""UI review: theme changes, control help, and version branding."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
from wotcamo import __version__,ae_effects as ae,ae_help,ui_theme
from wotcamo.ae_gui import AEImporter
from wotcamo.gui import Workbench


class UIReview34Tests(unittest.TestCase):
    def test_new_preview_actions_have_help_and_remain_inside_compact_window(self):
        from PIL import Image
        from wotcamo.ae_media_gui import ClipPreview
        app=AEImporter()
        try:
            clip=ae.pack_frames([Image.new('RGBA',(32,16),(255,0,0,128))],app.work/'help.png')
            viewer=ClipPreview(app,clip,dict(fps=24));viewer.geometry('480x340');app.update()
            buttons=[w for frame in viewer.winfo_children() for row in frame.winfo_children() for w in row.winfo_children() if isinstance(w,ttk.Button)]
            self.assertEqual(len(buttons),3)
            for button in buttons:
                self.assertIn(button,viewer.hover_help.providers)
                self.assertNotIn('media_',viewer.hover_help.providers[button](SimpleNamespace(x=1,y=1)).title)
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),viewer.winfo_rooty()+viewer.winfo_height())
            viewer.destroy()
        finally:app.close()

    def test_library_entry_and_reset_help_match_the_current_controls(self):
        app=Workbench()
        try:
            button=next(b for b in app.buttons if b.cget('text')=='管理图片素材库')
            self.assertIn(button,app.hover_help.providers)
        finally:app.destroy()
        self.assertIn('平铺次数',ae_help.topic('重置缩放、偏移和裁剪').body)
        self.assertNotIn('当前输入不完整',ae_help.topic('粘贴设置').body)

    def test_picture_library_can_open_without_a_client_or_vehicle(self):
        from wotcamo import preview3d
        app=Workbench()
        try:
            with patch.object(app,'task',side_effect=lambda create,done:done(create())),patch.object(preview3d,'Session') as session:
                app.open_asset_library();session.assert_called_once_with(None,None,library_only=True)
                self.assertIn(session.return_value,app.paint_sessions)
            self.assertTrue(any(str(button.cget('text'))=='管理图片素材库' for button in app.buttons))
        finally:app.destroy()

    def test_scales_follow_theme_in_both_directions_and_disabled_focus_states(self):
        app=tk.Tk()
        try:
            for glass in (False,True,False):
                with patch.object(ui_theme,'theme_preference',return_value=glass):style=ui_theme.configure_theme(app)
                for orient in ('Horizontal','Vertical'):
                    name=orient+'.TScale'
                    expected='#d9edf8' if glass else '#e7edf5'
                    self.assertEqual(style.lookup(name,'troughcolor'),expected)
                    self.assertNotEqual(style.lookup(name,'background'),style.lookup(name,'background',('disabled',)))
                    self.assertEqual(style.lookup(name,'bordercolor',('focus',)),ui_theme.ACCENT)
        finally:app.destroy()

    def test_appearance_entries_scales_and_reset_have_consistent_help(self):
        app=AEImporter()
        try:
            event=SimpleNamespace(x=1,y=1)
            for key in ('brightness','contrast','transparency'):
                entry=app.fields[key];slider=app.adjustment_sliders[key]
                self.assertIn(entry,app.hover_help.providers);self.assertIn(slider,app.hover_help.providers)
                entry_help=app.hover_help.providers[entry](event);slider_help=app.hover_help.providers[slider](event)
                self.assertEqual(entry_help,slider_help)
                self.assertEqual(float(slider.cget('to')),ae.MAX_BRIGHTNESS if key=='brightness' else 3 if key=='contrast' else 100)
            reset=next(w for w in app.buttons if str(w.cget('text'))=='重置亮度、对比度与透明度')
            self.assertIn(reset,app.hover_help.providers)
            self.assertIn('1 倍',app.hover_help.providers[reset](event).body)
            self.assertIn('0%',app.hover_help.providers[reset](event).body)
            snapshot=ui_theme.lock_controls(app)
            self.assertTrue(all(w.instate(['disabled']) for w in app.adjustment_sliders.values()))
            ui_theme.unlock_controls(snapshot)
            self.assertTrue(all(w.instate(['!disabled']) for w in app.adjustment_sliders.values()))
        finally:app.close()

    def test_light_entry_uses_current_version(self):
        app=Workbench()
        def walk(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from walk(widget)
        try:
            labels=[str(w.cget('text')) for w in walk(app) if isinstance(w,ttk.Label)]
            self.assertIn('灯效制作器  ·  '+__version__,labels)
            self.assertNotIn('灯效制作器  ·  3.3',labels)
        finally:app.destroy()


if __name__=='__main__':unittest.main()
