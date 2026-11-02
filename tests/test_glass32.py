"""Small headless checks for optional UI preferences and glass animations."""
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
from wotcamo import ui_theme,ae_presets
from tools import build_liquid_glass as glass

class GlassTests(unittest.TestCase):
    def test_dialog_focus_reloads_shared_style(self):
        class App:
            def __init__(self):self.calls=0
            def _sync_theme(self):self.calls+=1
        class Dialog:
            def __init__(self,app):self.app=app;self.options={};self.events={}
            def _root(self):return self.app
            def title(self,value):self.caption=value
            def configure(self,**kwargs):self.options.update(kwargs)
            def bind(self,event,fn,**kwargs):self.events[event]=fn
        state={'glass':False};app=App();dialog=Dialog(app)
        with patch.object(ui_theme,'theme_preference',side_effect=lambda:state['glass']):
            ui_theme.prepare_dialog(dialog,'测试')
            self.assertEqual(dialog.options['background'],ui_theme.BG)
            state['glass']=True;dialog.events['<FocusIn>']()
            self.assertEqual(dialog.options['background'],'#dbeefa');self.assertEqual(app.calls,1)
    def test_registered_controls_follow_theme_and_preserve_artwork(self):
        class App:pass
        app=App()
        class Widget:
            def __init__(self):self.options={}
            def _root(self):return app
            def configure(self,**options):self.options.update(options)
            def winfo_exists(self):return True
        field=Widget();surface=Widget();menu=Widget();artwork=Widget();artwork.options['bg']='#ff22aa'
        with patch.object(ui_theme,'theme_preference',return_value=False):
            ui_theme.register_widget(field,'field');ui_theme.register_widget(surface,'surface');ui_theme.register_widget(menu,'menu')
        self.assertEqual(field.options['bg'],'#ffffff');self.assertEqual(surface.options['bg'],'#ffffff')
        ui_theme.refresh_registered_widgets(app,True)
        self.assertEqual(field.options['bg'],'#f8fcff');self.assertEqual(surface.options['bg'],'#f1f9ff')
        self.assertEqual(menu.options['activebackground'],'#c9e9fa')
        self.assertEqual(artwork.options['bg'],'#ff22aa')
        ui_theme.refresh_registered_widgets(app,False)
        self.assertEqual(field.options['bg'],'#ffffff');self.assertEqual(surface.options['bg'],'#ffffff')
    def test_full_style_switch_restores_all_interactive_state_colours(self):
        class Style:
            def __init__(self):self.configs={};self.maps={}
            def theme_use(self,name):self.theme=name
            def configure(self,name,**kw):self.configs.setdefault(name,{}).update(kw)
            def map(self,name,**kw):self.maps.setdefault(name,{}).update(kw)
        class App:
            def configure(self,**kwargs):pass
            def option_add(self,*args):pass
        style=Style();app=App()
        with patch.object(ui_theme.ttk,'Style',return_value=style),patch.object(ui_theme,'theme_preference',return_value=True):ui_theme.configure_theme(app)
        self.assertEqual(style.maps['TCheckbutton']['background'],[('active','#f1f9ff')])
        self.assertEqual(style.maps['TButton']['background'][1],('pressed','#c7e4f4'))
        self.assertEqual(style.maps['TNotebook.Tab']['background'][0],('selected','#c9e9fa'))
        with patch.object(ui_theme.ttk,'Style',return_value=style),patch.object(ui_theme,'theme_preference',return_value=False):ui_theme.configure_theme(app)
        self.assertEqual(style.maps['TCheckbutton']['background'],[('active','#ffffff')])
        self.assertEqual(style.maps['TButton']['background'][1],('pressed','#dbe8f9'))
        self.assertEqual(style.maps['TNotebook.Tab']['background'][0],('selected','#dcecff'))
    def test_tab_style_updates_all_colours_for_both_themes(self):
        class Style:
            def __init__(self):self.config={};self.maps={}
            def configure(self,name,**options):self.config[name]=options
            def map(self,name,**options):self.maps[name]=options
        style=Style();ui_theme.configure_notebook_tabs(style,glass=True)
        glass=style.config['TNotebook.Tab'].copy();glass_map=style.maps['TNotebook.Tab'].copy()
        self.assertEqual(glass['background'],'#e5f4fc')
        self.assertEqual(glass_map['background'][0],('selected','#c9e9fa'))
        self.assertEqual(glass['bordercolor'],glass['lightcolor'])
        self.assertEqual(glass['bordercolor'],glass['darkcolor'])
        self.assertEqual(glass_map['foreground'][0][0],'disabled')
        ui_theme.configure_notebook_tabs(style,glass=False)
        classic=style.config['TNotebook.Tab'];classic_map=style.maps['TNotebook.Tab']
        self.assertNotEqual(classic['background'],glass['background'])
        self.assertEqual(classic_map['background'][0],('selected','#dcecff'))
        self.assertNotEqual(classic_map['bordercolor'],glass_map['bordercolor'])
    def test_header_switches_theme_and_updates_on_focus(self):
        class Widget:
            def __init__(self,*args,**kwargs):self.values=dict(kwargs);self.events={}
            def configure(self,**kwargs):self.values.update(kwargs)
            def pack(self,*args,**kwargs):pass
            def bind(self,event,fn,**kwargs):self.events[event]=fn
            def create_oval(self,*args,**kwargs):pass
            def winfo_reqwidth(self):return 20
            def winfo_toplevel(self):return self
        app=Widget();buttons=[];state={'glass':False};applied=[]
        def make_button(*args,**kwargs):
            button=Widget(*args,**kwargs);buttons.append(button);return button
        def save(value):state['glass']=value
        with patch.object(ui_theme.ttk,'Frame',Widget),patch.object(ui_theme.ttk,'Label',Widget),\
             patch.object(ui_theme.ttk,'Button',side_effect=make_button),patch.object(ui_theme.tk,'Canvas',Widget),\
             patch.object(ui_theme,'theme_preference',side_effect=lambda:state['glass']),\
             patch.object(ui_theme,'save_theme_preference',side_effect=save),\
             patch.object(ui_theme,'configure_theme',side_effect=lambda owner:applied.append(state['glass'])):
            header=ui_theme.build_header(app,'test');button=buttons[0]
            self.assertEqual(button.values['text'],'界面：经典')
            button.values['command']();self.assertTrue(state['glass'])
            self.assertEqual(button.values['text'],'界面：液态玻璃')
            self.assertEqual(header.logo.values['bg'],'#f1f9ff')
            button.values['command']();self.assertFalse(state['glass'])
            self.assertEqual(header.logo.values['bg'],ui_theme.CARD)
            state['glass']=True;app.events['<FocusIn>']()
            self.assertEqual(button.values['text'],'界面：液态玻璃')
    def test_theme_defaults_and_handles_corrupt_config(self):
        for data in ('{}','null','garbage','{"glass":false}'):
            with patch.object(Path,'read_text',return_value=data):self.assertFalse(ui_theme.theme_preference())
        with patch.object(Path,'read_text',side_effect=OSError):self.assertFalse(ui_theme.theme_preference())
        with patch.object(Path,'read_text',return_value='{"glass":true}'):self.assertTrue(ui_theme.theme_preference())
    def test_theme_setting_is_saved_as_a_boolean(self):
        with patch('wotcamo.common.write_json') as write:
            ui_theme.save_theme_preference(True)
        self.assertEqual(write.call_args.args[1],{'glass':True})
        self.assertEqual(write.call_args.args[0].name,'ui_theme.json')
    def test_glass_loops_and_has_real_transparency(self):
        for which in (0,1):
            start=glass.render(which,0);end=glass.render(which,1);middle=glass.render(which,.25)
            self.assertEqual(start.tobytes(),end.tobytes())
            self.assertNotEqual(start.tobytes(),middle.tobytes())
            a=np.asarray(start)[:,:,3];self.assertEqual(a.min(),0)
            self.assertGreater(np.count_nonzero((a>0)&(a<200)),200)
    def test_glass_sources_use_normal_transparency_and_portable_notes(self):
        rows,issues=ae_presets.scan();self.assertFalse(issues)
        selected=[r for r in rows if r['name'].startswith(('34 ','35 '))]
        self.assertEqual(len(selected),2)
        for row in selected:
            self.assertEqual(row['config']['blend'],'alpha')
            self.assertIn('不会实时折射',row['description'])
            ae_presets.read(row['path'])

if __name__=='__main__':unittest.main()
