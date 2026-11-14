import tkinter as tk,unittest
from types import SimpleNamespace
from unittest.mock import patch
from filter_gui import App


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.app=App(self.root);self.addCleanup(self.root.destroy)
    def test_compact_layout_keeps_actions_and_table_visible(self):
        self.root.geometry('900x680');self.root.update()
        self.assertEqual(self.app.client.get(),'');self.assertTrue(self.app.tree.winfo_ismapped())
        button=self.app.controls[-1];self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.root.winfo_rooty()+self.root.winfo_height())
        self.assertGreater(self.app.tree.winfo_height(),100)
    def test_toggle_filter_keeps_hidden_selections(self):
        app=self.app;app.vehicles=[dict(key='test/a',label='Alpha'),dict(key='test/b',label='Beta')];app.render()
        app.tree.focus('test/a');app.toggle();self.assertEqual(app.selected,{'test/a'})
        app.search.set('Beta');app.render();self.assertEqual(app.tree.get_children(),('test/b',));self.assertEqual(app.selected,{'test/a'})
        app.clear_selection();self.assertFalse(app.selected)
    def test_scan_selects_only_detected_vehicles_and_surfaces_script_limit(self):
        app=self.app;app.vehicles=[dict(key='test/a',label='Alpha')]
        with patch('filter_gui.messagebox.showinfo')as info:
            app.scanned(dict(vehicles={'test/a':['skin.wotmod']},warnings=['script limit'],sources=[]))
        self.assertEqual(app.selected,{'test/a'});info.assert_called_once();self.assertIn('原版路径',app.status.get())
    def test_missing_client_prevents_generation(self):
        with patch('filter_gui.messagebox.showinfo')as info,patch('filter_gui.build')as build:
            self.app.generate()
        build.assert_not_called();info.assert_called_once()
    def test_busy_blocks_toggle_and_close(self):
        self.app.busy=True
        with patch('filter_gui.messagebox.showinfo')as info:self.app.close()
        self.assertTrue(self.root.winfo_exists());info.assert_called_once()


if __name__=='__main__':unittest.main()
