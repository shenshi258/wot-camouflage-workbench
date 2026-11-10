"""Read the shipped meteor asset, recolour it, and inspect synthetic exports."""
import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae,ae_presets as presets
from tools import build_meteor_rain_preset as meteor


class MeteorPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=presets.library_file(meteor.NAME)
        cls.data,cls.raw=presets.read(cls.path)
        with Image.open(io.BytesIO(cls.raw)) as image:cls.image=image.copy()

    def test_all_frames_are_transparent_visible_multicolour_and_loop_smoothly(self):
        data=self.data;self.assertEqual(data['clip']['frames'],96);self.assertEqual(data['config']['fps'],24)
        self.assertEqual(data['config']['tint_strength'],0);self.assertEqual(data['config']['fit_mode'],'contain')
        frames=[]
        w,h=self.image.size
        for u,v,r,b in data['clip']['rects']:
            frame=np.asarray(self.image.crop((round(u*w),round(v*h),round(r*w),round(b*h))),dtype=float)
            self.assertEqual(frame[:,:,3].min(),0);self.assertGreater(np.count_nonzero(frame[:,:,3]>32),100)
            visible=frame[frame[:,:,3]>32,:3];dominant=np.argmax(visible,axis=1)
            self.assertTrue(all(np.count_nonzero(dominant==channel)>20 for channel in range(3)))
            frames.append(frame)
        steps=[np.abs(a-b).mean() for a,b in zip(frames,frames[1:]+frames[:1])]
        self.assertLessEqual(steps[-1],3*np.median(steps))
        self.assertEqual(meteor.render(0).tobytes(),meteor.render(1).tobytes())

    def test_selected_colour_changes_pixels_keeps_alpha_and_roundtrips_as_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,clip=presets.load(self.path,Path(tmp)/'loaded')
            for colour in ('#00C8FF','#FF2080'):
                values=dict(data['config'],tint_color=colour,tint_strength=100)
                baked=ae.colorized_clip(clip,values,Path(tmp)/'colours')
                with Image.open(baked['atlas']) as image:
                    self.assertNotEqual(image.tobytes(),self.image.tobytes())
                    self.assertEqual(image.getchannel('A').tobytes(),self.image.getchannel('A').tobytes())
                    np.testing.assert_array_equal(np.asarray(image),np.asarray(ae.appearance_rgba(self.image,values)))
                metadata,payload=presets.encode('Meteor '+colour,'',clip,values)
                target=Path(tmp)/(colour[1:]+'.aepreset');target.write_bytes(payload)
                saved,atlas=presets.read(target)
                self.assertEqual(saved['config']['tint_color'],colour);self.assertEqual(atlas,self.raw)

    def test_each_colour_export_uses_the_baked_atlas_and_preserves_original_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,clip=presets.load(self.path,root/'loaded')
            source=root/'source.wotmod'
            with zipfile.ZipFile(source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'original')
            project=ae.source_project(source,root/'project');project['baseline_user_confirmed']=True
            client=root/'client';(client/'res/packages').mkdir(parents=True)
            blob=io.BytesIO()
            with zipfile.ZipFile(blob,'w') as z:z.writestr('effect',b"('SRCALPHA', 5) ('ONE', 2) ('INVSRCALPHA', 6)")
            with zipfile.ZipFile(client/'res/packages/shaders.pkg','w') as z:
                for branch in ('10','11'):z.writestr('shaders/custom/emissive_playground.'+branch+'.dx11.fxo',blob.getvalue())
            def compile_stub(source,target,client):Path(target).write_bytes(b'synthetic-bytecode')
            for colour in ('#00C8FF','#FF2080'):
                values=dict(data['config'],tint_color=colour,tint_strength=100)
                with patch.object(ae.engine,'client_info',return_value={'kind':'synthetic'}),patch.object(ae.engine,'compile27',side_effect=compile_stub),patch.object(ae.engine,'audit_package',return_value={'missing_dependencies':[]}):
                    target,report=ae.build(project,clip,values,str(client),root/colour[1:],'Meteor')
                with zipfile.ZipFile(target) as z:
                    texture=next(name for name in z.namelist() if name.endswith('/atlas.dds'))
                    with Image.open(io.BytesIO(z.read(texture))) as actual:
                        self.assertEqual(actual.convert('RGBA').tobytes(),ae.appearance_rgba(self.image,values).tobytes())
                    self.assertEqual(z.read('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds'),b'original')
                self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')


if __name__=='__main__':unittest.main()
