"""Regressions reproduced on 3.3; run on an isolated Windows desktop."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from wotcamo import ui_theme
from wotcamo.ae_gui import AEImporter
from wotcamo.light_gui import LightMaker

def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)

class UIRegressionTests(unittest.TestCase):
    def test_tint_slider_is_locked_and_restored_with_other_controls(self):
        app=AEImporter()
        try:
            scales=[w for w in widgets(app) if isinstance(w,ttk.Scale)];self.assertTrue(scales)
            snapshot=ui_theme.lock_controls(app)
            self.assertTrue(all(w.instate(['disabled']) for w in scales))
            ui_theme.unlock_controls(snapshot)
            self.assertTrue(all(w.instate(['!disabled']) for w in scales))
        finally:app.close()

    def test_restore_autosave_while_busy_does_not_change_source(self):
        app=SimpleNamespace(busy=True,source=Mock(),work_dir=lambda:Path('unused'),job=Mock(),set_project=Mock())
        with patch('wotcamo.light_gui.filedialog.askopenfilename',return_value='different.wotlights') as choose:
            LightMaker.restore_autosave(app)
        choose.assert_not_called();app.source.set.assert_not_called();app.job.assert_not_called()

    def test_light_restore_button_locks_during_background_work(self):
        app=LightMaker()
        try:
            restore=next(w for w in widgets(app) if isinstance(w,ttk.Button) and w.cget('text')=='恢复自动保存工程')
            with patch('wotcamo.light_gui.threading.Thread'):
                app.job(lambda:None,lambda _:None)
            self.assertTrue(restore.instate(['disabled']))
            app.after_cancel(app._drain_after)
            app.events.put(('done',(lambda _:None,None)));app.drain()
            self.assertTrue(restore.instate(['!disabled']))
        finally:app.busy=False;app.destroy()

    def test_existing_combobox_dropdown_updates_with_theme(self):
        app=tk.Tk()
        try:
            with patch.object(ui_theme,'theme_preference',return_value=False):ui_theme.configure_theme(app)
            combo=ttk.Combobox(app,values=('first','second'));combo.pack()
            path=str(app.tk.call('ttk::combobox::PopdownWindow',combo))+'.f.l'
            for glass in (True,False):
                with patch.object(ui_theme,'theme_preference',return_value=glass):ui_theme.configure_theme(app)
                self.assertEqual(app.tk.call(path,'cget','-background'),ui_theme.palette(glass)['field'])
                self.assertEqual(app.tk.call(path,'cget','-selectbackground'),ui_theme.palette(glass)['selected'])
        finally:app.destroy()
