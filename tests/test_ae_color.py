"""No-window checks for recolouring, source preservation and export pixels."""
import io,json,tempfile,unittest,urllib.request,urllib.error,zipfile
from unittest.mock import patch
from pathlib import Path
from PIL import Image
from wotcamo import ae_effects as ae,ae_presets,preview3d

class AEColorTests(unittest.TestCase):
    def test_preview_theme_shares_setting_and_rejects_invalid_requests(self):
        state={'glass':False}
        with patch('wotcamo.ui_theme.theme_preference',side_effect=lambda:state['glass']),\
             patch('wotcamo.ui_theme.save_theme_preference',side_effect=lambda value:state.update(glass=value)):
            session=preview3d.Session(self.project(),None,launch=False)
            try:
                def get_status():
                    with urllib.request.urlopen(session.url.replace('index.html','status')) as r:return json.load(r)
                def change(data,origin=None):
                    headers={'Content-Type':'application/json'}
                    if origin:headers['Origin']=origin
                    req=urllib.request.Request(session.url.replace('index.html','theme'),data=json.dumps(data).encode(),headers=headers)
                    return urllib.request.urlopen(req)
                self.assertFalse(get_status()['uiTheme'])
                with change({'glass':True}) as response:self.assertTrue(json.load(response)['glass'])
                self.assertTrue(get_status()['uiTheme'])
                for bad in ({'glass':1},{'glass':'true'},{'glass':False,'other':1},{}):
                    with self.assertRaises(urllib.error.HTTPError):change(bad)
                with self.assertRaises(urllib.error.HTTPError):change({'glass':False},'https://example.com')
                self.assertTrue(get_status()['uiTheme'])
                with change({'glass':False}) as response:self.assertFalse(json.load(response)['glass'])
                self.assertFalse(get_status()['uiTheme'])
            finally:session.close()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        image=Image.new('RGBA',(16,8),(255,0,0,128));image.putpixel((2,3),(64,32,16,0))
        self.clip=ae.pack_frames([image],self.folder/'atlas.png')
        self.c=ae.config(dict(tint_color='#00c8ff',tint_strength=100))
    def tearDown(self):self.temp.cleanup()
    def project(self):
        source=self.folder/'source.wotmod'
        with zipfile.ZipFile(source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'example')
        return ae.source_project(source,self.folder/'work')
    def test_full_tint_can_add_missing_channels_without_changing_alpha_or_detail(self):
        image=Image.new('RGBA',(3,1));image.putdata([(255,0,0,128),(128,0,0,64),(64,32,16,0)])
        result=ae.colorize_rgba(image,self.c)
        self.assertEqual(list(result.getdata()),[(0,200,255,128),(0,100,128,64),(0,50,64,0)])
    def test_neutral_preserves_all_bytes_and_intermediate_strength_blends_rgb_only(self):
        image=Image.new('RGBA',(1,1),(255,0,0,78))
        self.assertEqual(ae.colorize_rgba(image,ae.config({})).tobytes(),image.tobytes())
        pixel=ae.colorize_rgba(image,dict(self.c,tint_strength=50)).getpixel((0,0))
        self.assertEqual(pixel,(127,100,127,78))
    def test_cache_source_unchanged_and_dds_uses_the_identical_preview_rgba(self):
        original=Path(self.clip['atlas']).read_bytes();a=ae.colorized_clip(self.clip,self.c,self.folder/'colors')
        b=ae.colorized_clip(self.clip,self.c,self.folder/'colors');self.assertEqual(a,b)
        self.assertEqual(Path(self.clip['atlas']).read_bytes(),original)
        with Image.open(a['atlas']) as image:
            restored=Image.open(io.BytesIO(ae.dds(image))).convert('RGBA');self.assertEqual(restored.tobytes(),image.tobytes())
        self.assertIs(ae.colorized_clip(self.clip,dict(self.c,tint_strength=0),self.folder/'colors'),self.clip)
    def test_preset_and_editable_project_keep_source_and_colour_parameters(self):
        data,payload=ae_presets.encode('自定义冰蓝','',self.clip,self.c);path=self.folder/'color.aepreset';path.write_bytes(payload)
        restored,clip=ae_presets.load(path,self.folder/'restored')
        self.assertEqual(restored['config']['tint_color'],'#00C8FF');self.assertEqual(restored['config']['tint_strength'],100)
        self.assertEqual(clip['atlas_sha256'],self.clip['atlas_sha256'])
        project=self.project();saved=self.folder/'saved.aefx';ae.save_project(saved,project,self.clip,self.c)
        _,loaded,values=ae.load_project(saved,self.folder/'project');self.assertEqual(values,self.c);self.assertEqual(loaded['atlas_sha256'],self.clip['atlas_sha256'])
    def test_live_route_accepts_colours_and_preview_serves_baked_pixels_without_gui(self):
        session=preview3d.Session(self.project(),None,launch=False,effect=(self.clip,ae.config({})))
        def request(values):
            return urllib.request.urlopen(urllib.request.Request(session.url.replace('index.html','effectparams'),data=json.dumps(values).encode()))
        try:
            request(dict(tint_color='#00c8ff',tint_strength=100)).close();event=session.events.get_nowait()
            self.assertEqual(event['values'],dict(tint_color='#00C8FF',tint_strength=100))
            session.update_effect(self.clip,dict(ae.DEFAULTS,**event['values']))
            with Image.open(session.folder/'ae_atlas.png') as actual,Image.open(self.clip['atlas']) as source:
                self.assertEqual(actual.tobytes(),ae.colorize_rgba(source,self.c).tobytes())
            self.assertEqual(session.effect['atlas_sha256'],ae.engine.digest(session.folder/'ae_atlas.png'))
            for bad in (dict(tint_color='red'),dict(tint_color=None),dict(tint_strength=101),dict(tint_strength=True)):
                with self.assertRaises(urllib.error.HTTPError):request(bad)
        finally:session.close()
    def test_colour_picker_and_quick_colour_enable_tint_without_creating_a_window(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from wotcamo.ae_gui import AEImporter
        class Value:
            def __init__(self,value):self.value=value
            def get(self):return self.value
            def set(self,value):self.value=value
        app=SimpleNamespace(values=dict(tint_color=Value('#FFFFFF'),tint_strength=Value('0')))
        app.set_effect_color=lambda value:AEImporter.set_effect_color(app,value)
        with patch('wotcamo.ae_gui.colorchooser.askcolor',return_value=((104,223,255),'#68dfff')):
            AEImporter.choose_effect_color(app)
        self.assertEqual(app.values['tint_color'].get(),'#68dfff');self.assertEqual(app.values['tint_strength'].get(),'100')

if __name__=='__main__':unittest.main()
