"""Consistent branding, reachable dialog actions and actionable AE field help."""
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from wotcamo import APP_NAME,__version__,ae_help
from wotcamo.ae_gui import AEImporter
from wotcamo.light_gui import LightMaker
from wotcamo.gui import Workbench
from wotcamo.ui_theme import CARD,BORDER


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


class Unified31Tests(unittest.TestCase):
    def test_all_editor_headers_share_the_product_brand_and_font(self):
        self.assertEqual(__version__,'3.3')
        styles=[]
        for cls in (Workbench,LightMaker,AEImporter):
            app=cls()
            try:
                app.update_idletasks()
                brand=[w for w in widgets(app) if isinstance(w,ttk.Label) and str(w.cget('style'))=='Brand.TLabel']
                self.assertEqual(len(brand),1);self.assertEqual(brand[0].cget('text'),APP_NAME)
                styles.append(ttk.Style(app).lookup('Brand.TLabel','font'))
            finally:app.close() if cls is AEImporter else app.destroy()
        self.assertEqual(styles[0],styles[1]);self.assertEqual(styles[1],styles[2])

    def test_ae_fields_have_units_and_workflow_help(self):
        app=AEImporter()
        try:
            event=SimpleNamespace(x=1,y=1)
            for key in ('fps','width','x','y','z','uv_scale','uv_scale_x','uv_scale_y','crop_left','crop_right','crop_top','crop_bottom','lift','brightness'):
                field=app.fields[key]
                self.assertIn(field,app.hover_help.providers)
                help=app.hover_help.providers[field](event)
                self.assertGreater(len(help.body),25);self.assertNotEqual(help.title,key)
            self.assertIn('上下位置',ae_help.TEXT['y']);self.assertIn('不改变',ae_help.TEXT['y'])
            self.assertIn('aepreset',ae_help.TEXT['auto_bundle'])
            self.assertIn(app.export_button,app.hover_help.providers)
        finally:app.close()

    def test_ae_hover_help_uses_shared_palette_and_closes_with_editor(self):
        app=AEImporter()
        try:
            manager=app.hover_help;manager.delay=1
            manager.schedule(app.export_button,ae_help.topic('生成涂装包'),40,40)
            app.after(30,app.quit);app.mainloop()
            self.assertIsNotNone(manager._window)
            box=manager._window.winfo_children()[0]
            self.assertEqual(box.cget('background'),CARD);self.assertEqual(box.cget('highlightbackground'),BORDER)
            manager.hide();self.assertIsNone(manager._window)
        finally:app.close()

    def test_both_preset_dialogs_keep_actions_inside_compact_windows(self):
        for cls in (AEImporter,LightMaker):
            app=cls();old=app.tk.call('tk','scaling')
            try:
                app.tk.call('tk','scaling',2.0);app.manage_presets();app.update()
                dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
                dialog.geometry('760x440');app.update()
                self.assertTrue(dialog.title().startswith(APP_NAME))
                buttons=[w for w in widgets(dialog) if isinstance(w,ttk.Button)]
                self.assertGreaterEqual(len(buttons),6)
                for button in buttons:
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_height(),24)
                    self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
                    self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),dialog.winfo_rootx()+dialog.winfo_width())
                dialog.destroy()
            finally:
                app.tk.call('tk','scaling',old);app.close() if cls is AEImporter else app.destroy()


if __name__=='__main__':unittest.main()
