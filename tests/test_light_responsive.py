"""Responsive editor remains usable at the declared minimum window size."""
import unittest
import tkinter as tk
from wotcamo.light_gui import LightMaker

class ResponsiveLightMakerTests(unittest.TestCase):
    def test_small_window_shows_preview_and_scrolls_to_all_recipe_actions(self):
        try: app=LightMaker()
        except tk.TclError as error:self.skipTest(str(error))
        try:
            app.geometry('980x620+0+0');app.update()
            self.assertTrue(app.canvas.winfo_ismapped())
            self.assertGreaterEqual(app.canvas.winfo_height(),100)
            self.assertLess(app.editor_viewport.yview()[1],1)
            app.editor_viewport.yview_moveto(1);app.update()
            view=app.editor_viewport
            for name in ('read_recipe_button','apply_button','restore_recipe_button','clear_all_button'):
                widget=getattr(app,name)
                self.assertTrue(widget.winfo_ismapped(),name)
                self.assertGreaterEqual(widget.winfo_rootx(),view.winfo_rootx(),name)
                self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),view.winfo_rootx()+view.winfo_width(),name)
                self.assertGreaterEqual(widget.winfo_rooty(),view.winfo_rooty(),name)
                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),view.winfo_rooty()+view.winfo_height(),name)
        finally: app.destroy()
