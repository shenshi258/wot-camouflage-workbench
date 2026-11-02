"""Regression coverage for stable navigation and compact-window layout."""
import unittest
import tkinter as tk
from tkinter import ttk
from wotcamo.gui import Workbench


class WorkbenchUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = Workbench()
        except tk.TclError as error:
            self.skipTest('Tk display unavailable: ' + str(error))
        self.app.geometry('1040x750+0+0')
        self.app.update()

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.destroy()

    def test_selected_tabs_keep_size_and_navigate(self):
        expected = [(b.winfo_width(), b.winfo_height()) for b in self.app.nav_buttons]
        self.assertTrue(all(size == expected[0] for size in expected))
        for index, button in enumerate(self.app.nav_buttons):
            button.invoke(); self.app.update()
            self.assertEqual(self.app.current_page, index)
            self.assertTrue(button.instate(['selected']))
            self.assertEqual([(b.winfo_width(), b.winfo_height()) for b in self.app.nav_buttons], expected)

    def test_compact_window_keeps_inputs_actions_and_log_visible(self):
        def find_button(parent, name):
            for child in parent.winfo_children():
                if isinstance(child, ttk.Button) and child.cget('text') == name:
                    return child
                found = find_button(child, name)
                if found is not None: return found
            return None
        for page, names in ((0, ('生成涂装包','用配方文件生成','打开原版模型','打开已有涂装')),
                            (1, ('创建模型工程','导出模型并打包','选择已有工程')),
                            (2, ('打开灯效制作器','将当前涂装交给灯效制作器')),
                            (3, ('打开 AE 特效导入',)),
                            (4, ('保存设置','打开完整使用说明'))):
            self.app.select_page(page); self.app.update()
            region=self.app.nav_pages[page]
            for name in names:
                widget=find_button(region,name)
                self.assertIsNotNone(widget, name)
                self.assertTrue(widget.winfo_ismapped(), name)
                self.assertGreaterEqual(widget.winfo_rooty(), region.winfo_rooty(), name)
                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), region.winfo_rooty()+region.winfo_height(), name)
                self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), region.winfo_rootx()+region.winfo_width(), name)
        self.app.select_page(0); self.app.update()
        self.assertGreaterEqual(self.app.prompt.winfo_height(), 50)
        self.assertLessEqual(self.app.logs.winfo_rooty()+self.app.logs.winfo_height(), self.app.winfo_rooty()+self.app.winfo_height())


if __name__ == '__main__': unittest.main()
