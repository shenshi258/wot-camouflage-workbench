"""Appearance controls: pixels, old assets, live requests and exported resources."""
import io,json,tempfile,unittest,urllib.request,urllib.error,zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from PIL import Image
from wotcamo import ae_effects as ae,ae_presets,preview3d


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.image=Image.new('RGBA',(3,1));self.image.putdata([(64,128,192,128),(192,64,128,64),(255,120,60,0)])
        self.clip=ae.pack_frames([self.image.resize((6,4),Image.Resampling.NEAREST)],self.root/'atlas.png')
        source=self.root/'source.wotmod'
        with zipfile.ZipFile(source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'original')
        self.project=ae.source_project(source,self.root/'source')
    def tearDown(self):self.temp.cleanup()
    def test_neutral_and_brightness_do_not_clip_or_change_source_texture(self):
        self.assertEqual(ae.appearance_rgba(self.image,{}).tobytes(),self.image.tobytes())
        self.assertEqual(ae.appearance_rgba(self.image,dict(brightness=100)).tobytes(),self.image.tobytes())
        self.assertEqual(ae.config({})['contrast'],1)
        for values in (dict(brightness=100.01),dict(brightness=0),dict(contrast=3.01),dict(transparency=-1),dict(transparency=101),dict(contrast=True),dict(transparency=float('nan'))):
            with self.assertRaises(ValueError):ae.config(values)
    def test_contrast_changes_rgb_and_transparency_only_scales_alpha(self):
        contrasted=ae.appearance_rgba(self.image,dict(contrast=2))
        self.assertEqual(list(contrasted.getdata()),[(0,128,255,128),(255,0,128,64),(255,112,0,0)])
        faded=ae.appearance_rgba(self.image,dict(contrast=2,transparency=50))
        self.assertEqual(list(faded.getdata()),[(0,128,255,64),(255,0,128,32),(255,112,0,0)])
        self.assertEqual(ae.appearance_rgba(self.image,dict(transparency=100)).getchannel('A').getextrema(),(0,0))
        self.assertEqual(ae.appearance_rgba(self.image,dict(contrast=0)).getchannel('A').tobytes(),self.image.getchannel('A').tobytes())
    def test_cache_restarts_from_source_and_preset_project_roundtrip(self):
        values=ae.config(dict(brightness=100,contrast=1.7,transparency=45,tint_color='#68DFFF',tint_strength=50))
        before=Path(self.clip['atlas']).read_bytes()
        adjusted=ae.colorized_clip(self.clip,values,self.root/'colors')
        self.assertEqual(adjusted,ae.colorized_clip(self.clip,values,self.root/'colors'))
        self.assertNotEqual(adjusted['atlas'],ae.colorized_clip(self.clip,dict(values,transparency=46),self.root/'colors')['atlas'])
        self.assertEqual(before,Path(self.clip['atlas']).read_bytes())
        self.assertIs(ae.colorized_clip(self.clip,{},self.root/'colors'),self.clip)
        _,payload=ae_presets.encode('Appearance','',self.clip,values);preset=self.root/'preset.aepreset';preset.write_bytes(payload)
        record,clip=ae_presets.load(preset,self.root/'preset')
        for key in ('brightness','contrast','transparency'):self.assertEqual(record['config'][key],values[key])
        self.assertEqual(clip['atlas_sha256'],self.clip['atlas_sha256'])
        saved=self.root/'project.aefx';ae.save_project(saved,self.project,self.clip,values)
        _,clip,restored=ae.load_project(saved,self.root/'reopened');self.assertEqual(restored,values)
    def test_live_request_and_preview_dds_use_same_rgba(self):
        values=dict(brightness=100,contrast=2,transparency=50)
        session=preview3d.Session(self.project,None,launch=False,effect=(self.clip,ae.config({})))
        def request(data):return urllib.request.urlopen(urllib.request.Request(session.url.replace('index.html','effectparams'),data=json.dumps(data).encode()))
        try:
            with request(values):pass
            self.assertEqual(session.events.get_nowait()['values'],values)
            session.update_effect(self.clip,values)
            with Image.open(session.folder/'ae_atlas.png') as actual,Image.open(self.clip['atlas']) as source:
                expected=ae.appearance_rgba(source,values)
                self.assertEqual(actual.tobytes(),expected.tobytes())
                self.assertEqual(Image.open(io.BytesIO(ae.dds(actual))).convert('RGBA').tobytes(),expected.tobytes())
            for bad in (dict(brightness=101),dict(contrast=float('inf')),dict(transparency=101)):
                with self.assertRaises(urllib.error.HTTPError):request(bad)
        finally:session.close()
    def test_export_writes_gain_once_and_matches_preview_pixels_for_both_blends(self):
        # Synthetic client/source: this checks the authoring pipeline, never
        # claims native shader execution, Python 2.7 validity or game loading.
        client=self.root/'client';(client/'res/packages').mkdir(parents=True)
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,'w') as z:z.writestr('effect',b"('SRCALPHA', 5) ('ONE', 2) ('INVSRCALPHA', 6)")
        with zipfile.ZipFile(client/'res/packages/shaders.pkg','w') as z:
            for branch in ('10','11'):z.writestr('shaders/custom/emissive_playground.'+branch+'.dx11.fxo',inner.getvalue())
        self.project['baseline_user_confirmed']=True
        def compile_stub(source,target,client):Path(target).write_bytes(b'synthetic-test-bytecode')
        for blend,dest in [('add','2'),('alpha','6')]:
            values=ae.config(dict(brightness=100,contrast=1.6,transparency=55,blend=blend))
            with patch.object(ae.engine,'client_info',return_value={'kind':'synthetic'}),patch.object(ae.engine,'compile27',side_effect=compile_stub),patch.object(ae.engine,'audit_package',return_value={'missing_dependencies':[]}):
                target,report=ae.build(self.project,self.clip,values,str(client),self.root/blend,'Appearance')
            with zipfile.ZipFile(target) as z:
                png=next(n for n in z.namelist() if n.endswith('/atlas.png'))
                baked=Image.open(io.BytesIO(z.read(png))).convert('RGBA')
                with Image.open(self.clip['atlas']) as source:self.assertEqual(baked.tobytes(),ae.appearance_rgba(source,values).tobytes())
                dds=Image.open(io.BytesIO(z.read(png.replace('.png','.dds')))).convert('RGBA')
                self.assertEqual(baked.tobytes(),dds.tobytes())
                visual=ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.visual_processed'))))
                props={p.text.strip():p[0].text for p in visual.findall('.//property') if p.text and len(p)}
                self.assertEqual([float(x) for x in props['g_tint'].split()],[100,100,100,1])
                self.assertEqual(props['srcBlend'],'5');self.assertEqual(props['destBlend'],dest)
                self.assertEqual(z.read('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds'),b'original')
            self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')


if __name__=='__main__':unittest.main()
