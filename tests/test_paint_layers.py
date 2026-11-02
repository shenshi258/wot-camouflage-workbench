"""Saved placements must survive later edits and export together."""
import base64,copy,io,zipfile,unittest
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
import test_paint3d
from wotcamo import paint3d,preview3d_assets,dds


class PaintLayerTests(unittest.TestCase):
    setUp=test_paint3d.Paint3DTests.setUp
    def blue(self,**values):
        buf=io.BytesIO();Image.new('RGBA',(16,8),(0,0,240,255)).save(buf,format='PNG')
        return dict(self.payload,image=base64.b64encode(buf.getvalue()).decode(),**values)

    def test_two_images_on_one_texture_survive_one_export(self):
        layers=[dict(self.payload,u=.25),self.blue(u=.75)]
        target,report=paint3d.build(self.project,self.client,self.body,{'layers':layers},self.root/'out','多图')
        with zipfile.ZipFile(target) as z:a=np.asarray(dds.decode(z.read('res/'+report['texture'])))
        self.assertGreater(int(a[32,16,0]),200);self.assertGreater(int(a[32,48,2]),200)
        self.assertEqual(len(report['layers']),2);self.assertEqual(len(report['textures']),1)

    def test_later_layer_is_on_top(self):
        target,report=paint3d.build(self.project,self.client,self.body,{'layers':[self.payload,self.blue()]},self.root/'out','覆盖')
        with zipfile.ZipFile(target) as z:a=np.asarray(dds.decode(z.read('res/'+report['texture'])))
        self.assertGreater(int(a[32,32,2]),200);self.assertLess(int(a[32,32,0]),40)

    def test_separate_textures_and_unchanged_entries(self):
        with zipfile.ZipFile(self.source) as z:files={n:z.read(n) for n in z.namelist()}
        visual=ET.fromstring(files[self.visual]);second=copy.deepcopy(visual.find('renderSet'))
        texture2='vehicles/test/TestTank/normal/lod0/turret_AM.dds'
        for p in second.findall('.//property'):
            if (p.text or '').strip()=='diffuseMap':p.find('Texture').text=texture2
        visual.append(second);files[self.visual]=ET.tostring(visual);files['res/'+texture2]=self.original
        with zipfile.ZipFile(self.source,'w') as z:
            for n,b in files.items():z.writestr(n,b)
        project=paint3d.project_from_package('test/TestTank',self.source)
        body=preview3d_assets.make_body(project,self.client,self.root/'two')
        target,report=paint3d.build(project,self.client,body,{'layers':[self.payload,self.blue(mesh=1)]},self.root/'out','双贴图')
        with zipfile.ZipFile(target) as z:
            first=np.asarray(dds.decode(z.read('res/'+report['texture'])));second=np.asarray(dds.decode(z.read('res/'+texture2)))
            self.assertGreater(int(first[32,32,0]),200);self.assertGreater(int(second[32,32,2]),200)
            self.assertEqual(z.read(self.visual),files[self.visual])
        self.assertEqual(len(report['textures']),2)

    def test_invalid_later_layer_does_not_export_partial_package(self):
        for layers in ([],[self.payload]*33,[self.payload,dict(self.payload,u=float('nan'))],[self.payload,dict(self.payload,image='!')]):
            with self.assertRaises(ValueError):paint3d.build(self.project,self.client,self.body,{'layers':layers},self.root/'out','bad')
        self.assertFalse((self.root/'out').exists())
