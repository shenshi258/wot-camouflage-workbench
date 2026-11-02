"""Hover-help behaviour and coverage; no game or file-dialog interaction."""
import tkinter as tk
from tkinter import ttk
import unittest
import re
from types import SimpleNamespace
from unittest.mock import Mock
from wotcamo import light_help, light_recipe
from wotcamo.light_gui import LightMaker
from wotcamo.light_tooltips import fit_position


class HoverHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app=LightMaker();cls.app.withdraw();cls.app.update_idletasks()
        except tk.TclError as error:
            raise unittest.SkipTest(str(error))

    @classmethod
    def tearDownClass(cls):
        cls.app.hover_help.hide();cls.app.destroy()

    def setUp(self):
        self.app.hover_help.hide()
        self.app.hover_help.delay=1

    def pump(self):
        self.app.after(20,self.app.quit)
        self.app.mainloop()

    def test_every_main_interactive_control_has_detailed_help(self):
        event=SimpleNamespace(x=1,y=1,state=0,x_root=10,y_root=10)
        for widget in self.app.widgets:
            with self.subTest(widget=str(widget)):
                self.assertIn(widget,self.app.hover_help.providers)
                spec=self.app.hover_help.providers[widget](event)
                self.assertTrue(spec.title)
                self.assertGreaterEqual(len(spec.body),35)

    def test_every_mode_direction_and_preset_has_choice_help(self):
        for mode in light_recipe.MODES:
            self.assertIn(mode,light_help.MODES)
            self.assertEqual(light_help.option('效果模式',mode).title,mode)
        for direction in light_recipe.DIRECTIONS:
            self.assertIn(direction,light_help.DIRECTIONS)
            self.assertEqual(light_help.option('流水方向',direction).title,direction)
        for name in self.app.preset_library:
            self.assertIn('模式：',light_help.option('预设',name,self.app).body)

    def test_hover_waits_and_never_invokes_the_button(self):
        action=Mock();button=self.app.button(self.app,'保存工程',action)
        try:
            manager=self.app.hover_help
            focus=str(self.app.tk.call('focus'))
            manager.schedule(button,light_help.topic('保存工程'),100,100)
            self.assertIsNone(manager._window)
            self.pump()
            self.assertIsNotNone(manager._window)
            self.assertIsNone(manager._window.grab_current())
            self.assertEqual(str(self.app.tk.call('focus')),focus)
            action.assert_not_called()
        finally:
            self.app.widgets.remove(button);button.destroy()

    def test_leaving_before_delay_cancels_the_popup(self):
        manager=self.app.hover_help;widget=self.app.check
        manager.schedule(widget,light_help.topic('已确认原版正常运行'),100,100)
        widget.event_generate('<Leave>')
        self.pump()
        self.assertIsNone(manager._pending);self.assertIsNone(manager._window)

    def test_destroying_owner_cleans_pending_help(self):
        button=tk.Button(self.app)
        self.app.hover_help.attach(button,lambda e:light_help.topic('保存工程'))
        self.app.hover_help.schedule(button,light_help.topic('保存工程'),100,100)
        button.destroy();self.pump()
        self.assertIsNone(self.app.hover_help._window)
        self.assertNotIn(button,self.app.hover_help.providers)

    def test_dropdown_hover_callback_reads_the_individual_choice(self):
        widget=next(w for w in self.app.widgets if isinstance(w,ttk.Combobox)
                    and str(w.cget('textvariable'))==str(self.app.effect_mode))
        popdown=widget.tk.call('ttk::combobox::PopdownWindow',widget)
        path=str(popdown)+'.f.l'
        widget.tk.call(path,'delete',0,'end')
        widget.tk.call(path,'insert','end',*light_recipe.MODES)
        script=widget.tk.call('bind',path,'<Motion>')
        command=str(script).strip().splitlines()[-1].split()[0]
        widget.tk.call(command,0,200,200)
        self.assertEqual(self.app.hover_help._spec.title,self.app.engine_modes[0])
        self.assertEqual(self.app.hover_help._spec.body,light_help.option('效果模式',self.app.engine_modes[0],self.app).body)

    def test_menu_hover_explains_action_without_installing(self):
        menu=self.app.install_menu
        menu.activate(0)
        # An unmapped native menu does not dispatch generated mouse events.
        # Invoke its registered hover handler without posting a live menu.
        command=re.search(r'\[([^\s]+)',menu.bind('<<MenuSelect>>')).group(1)
        menu.tk.call(command)
        self.assertEqual(self.app.hover_help._spec.title,'安装已有灯效包')
        self.assertIsNone(self.app.last_install)
        for index in range(menu.index('end')+1):
            if menu.type(index)!='separator':
                self.assertGreater(len(light_help.topic(menu.entrycget(index,'label')).body),35)

    def test_help_replacement_cancels_old_timer(self):
        manager=self.app.hover_help
        manager.schedule(self.app.check,light_help.topic('暗相系数'),100,100)
        previous=manager._serial
        manager.schedule(self.app.check,light_help.topic('峰值倍率'),100,100)
        manager._show(previous)
        self.assertIsNone(manager._window)
        self.pump();self.assertEqual(manager._spec.title,'峰值倍率')

    def test_edge_position_keeps_popup_on_screen(self):
        self.assertEqual(fit_position(990,790,300,200,0,0,1000,800),(690,590))
        self.assertEqual(fit_position(-2000,-300,300,200,-1000,0,1000,800),(-990,10))

    def test_preset_manager_buttons_and_list_have_help(self):
        self.app.manage_presets()
        dialog=next(w for w in self.app.winfo_children() if isinstance(w,tk.Toplevel))
        try:
            def walk(widget):
                for child in widget.winfo_children():
                    yield child;yield from walk(child)
            controls=[w for w in walk(dialog) if w.winfo_class() in ('TButton','Listbox')]
            self.assertEqual(len(controls),9)
            self.assertTrue(all(w in self.app.hover_help.providers for w in controls))
        finally:dialog.destroy()


if __name__=='__main__':unittest.main()
