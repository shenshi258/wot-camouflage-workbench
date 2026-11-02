"""Shared appearance, compact layouts and recovery after callback failures."""
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import unittest
from wotcamo import APP_NAME
from wotcamo.gui import Workbench
from wotcamo.light_gui import LightMaker
from wotcamo.ae_gui import AEImporter
from wotcamo.ui_theme import configure_theme,lock_controls,unlock_controls,start_progress,stop_progress

class UIConsistencyTests(unittest.TestCase):
    def test_all_editors_share_brand_primary_style_and_caption(self):
        styles=[]
        for cls in (Workbench,LightMaker,AEImporter):
            app=cls()
            try:
                app.update();self.assertTrue(app.title().startswith(APP_NAME))
                style=ttk.Style(app)
                self.assertEqual(style.theme_use(),'clam')
                self.assertNotIn('Apple.',str(style.layout('TButton')))
                styles.append([style.lookup('Accent.TButton',key,state) for key,state in [('background',()),('foreground',()),('background',('disabled',)),('foreground',('disabled',)),('font',())]])
                button=app.build_button if cls is LightMaker else app.export_button if cls is AEImporter else next(b for b in app.buttons if b.cget('text')=='生成涂装包')
                self.assertEqual(button.cget('text'),'生成涂装包')
            finally:
                if cls is AEImporter:app.close()
                else:app.destroy()
        self.assertEqual(styles[0],styles[1]);self.assertEqual(styles[1],styles[2])

    def test_busy_state_keeps_readonly_and_originally_disabled_controls(self):
        app=tk.Tk();configure_theme(app)
        try:
            combo=ttk.Combobox(app,state='readonly');combo.pack()
            disabled=ttk.Button(app,text='not available',state='disabled');disabled.pack()
            enabled=ttk.Entry(app);enabled.pack()
            snapshot=lock_controls(app);self.assertTrue(combo.instate(['disabled']));self.assertTrue(enabled.instate(['disabled']))
            unlock_controls(snapshot)
            self.assertTrue(combo.instate(['readonly','!disabled']));self.assertTrue(disabled.instate(['disabled']));self.assertTrue(enabled.instate(['!disabled']))
        finally:app.destroy()

    def test_idle_progress_is_not_an_indeterminate_loading_block(self):
        app=tk.Tk();progress=ttk.Progressbar(app)
        try:
            start_progress(progress);self.assertEqual(str(progress.cget('mode')),'indeterminate')
            stop_progress(progress);self.assertEqual(str(progress.cget('mode')),'determinate');self.assertEqual(float(progress.cget('value')),0)
        finally:app.destroy()

    def test_light_library_footer_has_room_at_small_window_and_higher_font_scale(self):
        app=LightMaker()
        old_scale=app.tk.call('tk','scaling')
        try:
            for scaling in (1.3333,1.6667,2.0):
                app.tk.call('tk','scaling',scaling);app.geometry('1040x750');app.update()
                button=app.scan_issue_button;parent=button.master
                self.assertGreaterEqual(button.winfo_height(),28)
                self.assertGreaterEqual(button.winfo_rooty(),parent.winfo_rooty())
                self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),parent.winfo_rooty()+parent.winfo_height())
                self.assertLessEqual(app.build_button.winfo_rooty()+app.build_button.winfo_height(),app.winfo_rooty()+app.winfo_height())
        finally:app.tk.call('tk','scaling',old_scale);app.destroy()

    def test_main_prompt_keeps_its_height_at_higher_font_scale(self):
        app=Workbench();old_scale=app.tk.call('tk','scaling')
        try:
            app.tk.call('tk','scaling',2.0);app.geometry('1040x750');app.update()
            self.assertGreaterEqual(app.prompt.winfo_height(),50)
            viewport=app.page_viewports[0]
            self.assertGreaterEqual(app.nav_pages[0].winfo_height(),viewport.winfo_height())
        finally:app.tk.call('tk','scaling',old_scale);app.destroy()

    def test_ae_callback_failure_unlocks_controls_and_keeps_polling(self):
        app=AEImporter()
        try:
            app.after_cancel(app.poll_id);app.busy=True;app._busy_controls=lock_controls(app)
            app.events.put(('done',lambda result:(_ for _ in ()).throw(RuntimeError('UI callback test')),None))
            with patch('wotcamo.ae_gui.messagebox.showerror') as error:app.poll();error.assert_called_once()
            self.assertFalse(app.busy);self.assertTrue(app.export_button.instate(['!disabled']))
            self.assertTrue(app.fields['uv_scale'].instate(['disabled']))
            self.assertTrue(app.tk.call('after','info',app.poll_id))
        finally:app.close()

    def test_main_callback_failure_does_not_leave_navigation_locked(self):
        app=Workbench()
        try:
            app.after_cancel(app._drain_after);app.busy=True;app._busy_controls=lock_controls(app)
            app.events.put(('done',(lambda result:(_ for _ in ()).throw(RuntimeError('UI callback test')),None)))
            with patch('wotcamo.gui.messagebox.showerror') as error:app.drain();error.assert_called_once()
            self.assertFalse(app.busy);self.assertTrue(app.tanks.instate(['readonly','!disabled']))
            self.assertTrue(all(b.instate(['!disabled']) for b in app.nav_buttons))
            self.assertTrue(app.tk.call('after','info',app._drain_after))
        finally:app.destroy()

if __name__=='__main__':unittest.main()
