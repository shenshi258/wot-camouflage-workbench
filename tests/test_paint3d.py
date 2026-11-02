import base64, io, json, struct, tempfile, unittest, zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from wotcamo import paint3d, preview3d_assets, light_assets as mesh, light_effects as engine, dds
from test_light_wheels import ring, fixture_visual

class Paint3DTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.client=self.root/'client';(self.client/'res/packages').mkdir(parents=True)
        (self.client/'version.xml').write_text('<root><version>2.4.1</version></root>')
        (self.client/'paths.xml').write_text('<root><Path>res_mods/2.4.1</Path></root>')
        self.source=self.root/'input.wotmod';self.visual='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'
        vertices,indices=ring();visual=fixture_visual(vertices,indices);visual.find('.//fx').text='shaders/std_effects/PBS_tank.fx'
        texture='vehicles/test/TestTank/normal/lod0/chassis_AM.dds'
        for prop in visual.findall('.//property'):
            if (prop.text or '').strip()=='diffuseMap':prop.find('Texture').text=texture
        arr=np.full((64,64,4),255,dtype=np.uint8);arr[:8,:,3]=0;arr[...,:3]=80
        image=io.BytesIO();Image.fromarray(arr).save(image,format='DDS',pixel_format='DXT5');self.original=image.getvalue()
        with zipfile.ZipFile(self.source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.visual,mesh.xml(visual));z.writestr(self.visual.replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,indices.ravel()));z.writestr('res/'+texture,self.original)
        self.project=paint3d.project_from_package('test/TestTank',self.source)
        self.body=preview3d_assets.make_body(self.project,self.client,self.root/'body')
        b=io.BytesIO();Image.new('RGBA',(16,8),(240,0,0,255)).save(b,format='PNG')
        self.payload={'mesh':0,'u':.5,'v':.5,'scale':.25,'angle':0,'image':base64.b64encode(b.getvalue()).decode()}

    def test_export_preserves_source_and_writes_visible_image(self):
        before=engine.digest(self.source)
        target,report=paint3d.build(self.project,self.client,self.body,self.payload,self.root/'result','示例')
        self.assertEqual(engine.digest(self.source),before);self.assertEqual(engine.digest(target),report['artifact']['sha256'])
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        with zipfile.ZipFile(target) as z:
            engine.check_archive(z);data=z.read('res/'+report['texture']);self.assertTrue(all(x.compress_type==zipfile.ZIP_STORED for x in z.infolist()))
        expected=np.asarray(dds.decode(self.original));actual=np.asarray(dds.decode(data))
        self.assertGreater(int(actual[32,32,0]),int(expected[32,32,0])+80)
        np.testing.assert_array_equal(actual[...,3],expected[...,3]);dds.verify_matches(data,self.original)
        self.assertEqual(report['file_validation']['status'],'passed')

    def test_bad_payload_or_modified_source_is_rejected(self):
        for change in ({'u':float('nan')},{'scale':2},{'image':'!!!'},{'mesh':100}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                paint3d.build(self.project,self.client,self.body,dict(self.payload,**change),self.root/'out','test')
        with zipfile.ZipFile(self.source,'a') as z:z.writestr('res/other',b'changed')
        with self.assertRaisesRegex(ValueError,'已改变'):
            paint3d.build(self.project,self.client,self.body,self.payload,self.root/'out','test')

    def test_preview_placement_preserves_base_alpha_and_clips_at_edge(self):
        original=Image.new('RGBA',(64,32),(40,40,40,0));decal=Image.new('RGBA',(20,10),(250,10,20,255))
        out=paint3d.render_placement(original,decal,0,0,.5,45)
        a=np.asarray(out);self.assertEqual(a[...,3].max(),0);self.assertGreater(int(a[...,0].max()),40)

    def test_stock_project_is_empty_carrier_not_confirmed_baseline(self):
        project=paint3d.create_stock_project('test/TestTank',self.root/'stock')
        self.assertEqual(project['source_kind'],'client_stock');self.assertFalse(project['baseline_user_confirmed'])
        with zipfile.ZipFile(project['source']) as z:self.assertEqual(z.namelist(),['meta.xml'])

    def test_cross_vehicle_package_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'当前所选车型'):paint3d.project_from_package('test/Other',self.source)

    def test_alpha_is_preserved_for_every_original_mip(self):
        for fmt in ('DXT1','DXT3','DXT5'):
            payload=[];header=None
            for n in (32,16,8):
                a=np.full((n,n,4),255,dtype=np.uint8);a[...,:3]=70
                if fmt=='DXT1':a[:n//2,:,3]=0
                else:a[...,3]=np.arange(n,dtype=np.uint8)[None,:]*int(255/(n-1))
                b=io.BytesIO();Image.fromarray(a).save(b,format='DDS',pixel_format=fmt);raw=b.getvalue()
                if header is None:header=bytearray(raw[:128]);struct.pack_into('<I',header,28,3)
                payload.append(raw[128:])
            reference=bytes(header)+b''.join(payload)
            original=dds.decode(reference);modified=original.copy();modified.paste((240,10,10,255),(0,0,8,8));modified.putalpha(original.getchannel('A'))
            result=paint3d.encode_preserve_alpha(modified,reference)
            for old,new in zip(dds.decode_mips(reference),dds.decode_mips(result)):
                np.testing.assert_array_equal(np.asarray(old.convert('RGBA'))[...,3],np.asarray(new.convert('RGBA'))[...,3])

    def test_rejects_light_package_with_embedded_effects(self):
        with zipfile.ZipFile(self.source,'a') as z:z.writestr('res/particles/light_maker_012345abcdef/manifest.json','{}')
        with self.assertRaisesRegex(ValueError,'灯效成品包'):paint3d.project_from_package('test/TestTank',self.source)

    def test_workbench_entry_opens_selected_stock_model(self):
        from unittest.mock import patch,Mock
        from wotcamo.gui import Workbench
        app=Workbench();app.withdraw();self.addCleanup(app.destroy)
        app.tank.set('test/TestTank');app.title_var.set('贴图示例');app.cfg['wot_root']=str(self.client)
        token=Mock();created=[]
        with patch('wotcamo.gui.wotdata.load_index',return_value={'vehicles':{'test/TestTank':{}}}), \
             patch('wotcamo.preview3d.Session',return_value=token) as session, \
             patch.object(app,'task',side_effect=lambda work,done:done(work())):
            app.open_paint_preview(False)
        project,client=session.call_args.args[:2]
        self.assertEqual(project['vehicle'],'TestTank');self.assertEqual(project['source_kind'],'client_stock')
        self.assertEqual(client,str(self.client));self.assertEqual(session.call_args.kwargs['paint']['title'],'贴图示例')
        self.assertIn(token,app.paint_sessions)
        app.paint_sessions.clear()

    def test_export_endpoint_requires_paint_session_and_same_origin(self):
        import urllib.request,urllib.error
        from wotcamo import preview3d
        from unittest.mock import patch
        patcher=patch.object(preview3d,'ROOT',self.root);patcher.start();self.addCleanup(patcher.stop)
        regular=preview3d.Session(self.project,str(self.client),launch=False)
        self.addCleanup(regular.close)
        def request(session,headers=None):
            url=session.url.replace('index.html?paint=1','paint').replace('index.html','paint')
            return urllib.request.Request(url,data=json.dumps(self.payload).encode(),headers={'Content-Type':'application/json',**(headers or {})})
        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(request(regular))
        self.assertEqual(denied.exception.code,403)
        session=preview3d.Session(self.project,str(self.client),launch=False,paint={'title':'测试'})
        self.addCleanup(session.close)
        preview3d_assets.write_json(session.folder/'body.json',{'folder':str(self.root/'body'),'scene':self.body})
        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(request(session,{'Origin':'https://example.com'}))
        self.assertEqual(denied.exception.code,403)
        with urllib.request.urlopen(request(session)) as response:result=json.load(response)
        self.assertTrue(result['ok']);self.assertTrue(Path(result['path']).is_file())
        self.assertEqual(session.events.get_nowait()['type'],'paint_complete')
