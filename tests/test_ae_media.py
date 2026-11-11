"""Real GIF disposal/timing and FFmpeg video sampling, with bounded imports."""
import io,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae,ae_media as media,ae_presets


class MediaImportTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def gif(self):
        frames=[]
        for x,colour in ((2,(255,0,0,255)),(18,(0,255,0,255)),(34,(0,0,255,255))):
            image=Image.new('RGBA',(48,24));image.paste(colour,(x,6,x+8,14));frames.append(image)
        path=self.root/'中文 动画.gif'
        frames[0].save(path,save_all=True,append_images=frames[1:],duration=[100,300,200],loop=0,disposal=2)
        return path
    def video(self,suffix='.avi'):
        import cv2
        path=self.root/('中文 视频'+suffix)
        codec='MJPG' if suffix=='.avi' else 'mp4v'
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*codec),6,(64,32))
        self.assertTrue(writer.isOpened())
        for i in range(12):
            frame=np.zeros((32,64,3),np.uint8);frame[8:24,8:56]=[20+i*12,160,240-i*10];writer.write(frame)
        writer.release();return path
    def atlas_frames(self,clip):
        with Image.open(clip['atlas']) as atlas:
            w,h=atlas.size
            return [atlas.crop((round(u*w-.5),round(v*h-.5),round(r*w+.5),round(b*h+.5))) for u,v,r,b in clip['rects']]

    def test_gif_variable_delays_and_disposal_keep_speed_and_transparency(self):
        path=self.gif();original=path.read_bytes();info=media.probe(path)
        self.assertAlmostEqual(info['duration'],.6)
        clip=media.import_media(path,self.root/'gif.png',fps=10)
        self.assertEqual(clip['frames'],6);frames=self.atlas_frames(clip)
        for frame,channel in zip(frames,(0,1,1,1,2,2)):
            rgba=np.array(frame);self.assertEqual(int(np.argmax(rgba[:,:,:3].sum((0,1)))),channel)
            self.assertEqual(int(np.count_nonzero(rgba[:,:,3])),64)
        self.assertEqual(path.read_bytes(),original);ae.validate_clip(clip)

    def test_gif_segment_uses_time_not_frame_index(self):
        clip=media.import_media(self.gif(),self.root/'gif.png',start=.2,end=.5,fps=10)
        self.assertEqual(clip['frames'],3)
        self.assertEqual([int(np.argmax(np.array(frame)[:,:,:3].sum((0,1)))) for frame in self.atlas_frames(clip)],[1,1,2])

    def test_black_background_keeps_additive_energy_and_existing_alpha(self):
        image=Image.new('RGBA',(4,1));image.putdata([(0,0,0,255),(32,64,128,255),(20,80,40,128),(80,0,40,0)])
        actual=media.black_to_alpha(image);a=np.array(actual,dtype=float)/255;b=np.array(image,dtype=float)/255
        np.testing.assert_allclose(a[:,:,:3]*a[:,:,3:],b[:,:,:3]*b[:,:,3:],atol=1/255)
        self.assertEqual(actual.getpixel((0,0))[3],0)

    def test_video_mp4_and_avi_decode_locally_with_selected_timing(self):
        for suffix in ('.avi','.mp4'):
            path=self.video(suffix);original=path.read_bytes();info=media.probe(path)
            self.assertAlmostEqual(info['duration'],2);self.assertEqual((info['width'],info['height']),(64,32))
            clip=media.import_media(path,self.root/(suffix[1:]+'.png'),start=.5,end=1.5,fps=8)
            self.assertEqual(clip['frames'],8);self.assertEqual(clip['import_info']['fps'],8)
            samples=self.atlas_frames(clip);first=np.array(samples[0]);last=np.array(samples[-1])
            self.assertTrue(np.all(first[:,:,3]==255));self.assertGreater(last[16,32,2],first[16,32,2])
            self.assertEqual(path.read_bytes(),original)

    def test_video_black_background_becomes_transparent(self):
        clip=media.import_media(self.video(),self.root/'black.png',end=1,fps=6,alpha_mode='black')
        # MJPEG 编码会在原黑底留下少量压缩噪声，透明度应接近零。
        pixels=np.array(self.atlas_frames(clip)[0]);self.assertLess(pixels[0,0,3],12);self.assertGreater(pixels[16,32,3],100)

    def test_time_limits_invalid_media_and_defaults_are_bounded(self):
        info=dict(duration=12,native_fps=30)
        self.assertEqual(media.defaults(info),dict(start=0.,end=12,fps=10))
        for options in ((0,12,24),(-1,1,24),(1,1,24),(0,13,10),(0,1,0),(0,1,float('nan')),(False,1,12)):
            with self.assertRaises(ValueError):media.plan(info,*options)
        with self.assertRaises(ValueError):media.probe('https://example.invalid/video.mp4')
        path=self.root/'broken.mp4';path.write_bytes(b'broken')
        with self.assertRaises(ValueError):media.probe(path)
        with patch.object(media,'MAX_GIF_BYTES',1),self.assertRaises(ValueError):media.probe(self.gif())

    def test_imported_clip_roundtrips_without_original_file_or_absolute_path(self):
        source=self.gif();clip=media.import_media(source,self.root/'gif.png',fps=10)
        values=ae.config(dict(fps=10));_,payload=ae_presets.encode('自带动画','',clip,values)
        path=self.root/'media.aepreset';path.write_bytes(payload)
        project_source=self.root/'source.wotmod'
        with zipfile.ZipFile(project_source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'original')
        project=ae.source_project(project_source,self.root/'source');saved=self.root/'media.aefx';ae.save_project(saved,project,clip,values)
        with zipfile.ZipFile(saved) as z:
            text=''.join(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('.json'))
            self.assertNotIn(str(source),text)
        source.unlink()
        _,restored=ae_presets.load(path,self.root/'restored');ae.validate_clip(restored)
        _,loaded,c=ae.load_project(saved,self.root/'reopened');ae.validate_clip(loaded);self.assertEqual(c['fps'],10)

    def test_imported_video_exports_matching_pixels_and_selected_blend(self):
        from xml.etree import ElementTree as ET
        video=self.video();source=self.root/'base.wotmod'
        with zipfile.ZipFile(source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'original')
        project=ae.source_project(source,self.root/'base');project['baseline_user_confirmed']=True
        client=self.root/'client';(client/'res/packages').mkdir(parents=True)
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w') as z:z.writestr('effect',b"('SRCALPHA', 5) ('ONE', 2) ('INVSRCALPHA', 6)")
        with zipfile.ZipFile(client/'res/packages/shaders.pkg','w') as z:
            for branch in ('10','11'):z.writestr('shaders/custom/emissive_playground.'+branch+'.dx11.fxo',payload.getvalue())
        def compile_stub(source,target,client):Path(target).write_bytes(b'synthetic-bytecode')
        for mode,blend,dest in [('preserve','alpha','6'),('black','add','2')]:
            clip=media.import_media(video,self.root/(mode+'.png'),end=1,fps=6,alpha_mode=mode)
            values=ae.config(dict(fps=6,blend=blend))
            with patch.object(ae.engine,'client_info',return_value={'kind':'synthetic'}),patch.object(ae.engine,'compile27',side_effect=compile_stub),patch.object(ae.engine,'audit_package',return_value={'missing_dependencies':[]}):
                target,report=ae.build(project,clip,values,str(client),self.root/mode,'Video')
            with zipfile.ZipFile(target) as z:
                texture=next(n for n in z.namelist() if n.endswith('/atlas.dds'))
                with Image.open(io.BytesIO(z.read(texture))) as actual,Image.open(clip['atlas']) as expected:self.assertEqual(actual.convert('RGBA').tobytes(),expected.tobytes())
                visual=ET.fromstring(z.read(next(n for n in z.namelist() if '/frame_000.visual_processed' in n)))
                props={p.text.strip():p[0].text for p in visual.findall('.//property') if p.text and len(p)}
                self.assertEqual(props['destBlend'],dest);self.assertEqual(z.read('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds'),b'original')
            self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')


if __name__=='__main__':unittest.main()
