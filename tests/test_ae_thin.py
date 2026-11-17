"""Real thin image imports must retain their aspect and usable atlas UVs."""
import io,tempfile,unittest,zipfile
from pathlib import Path
from PIL import Image
from wotcamo import ae_effects as ae,ae_media,ae_presets


class ThinImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def picture(self,size,alpha=128):
        path=self.root/('%dx%d_%d.png'%(*size,alpha))
        mode='RGB' if alpha==255 else 'RGBA';colour=(245,80,30) if mode=='RGB' else (245,80,30,alpha)
        Image.new(mode,size,colour).save(path)
        return path

    def frames(self,clip):
        with Image.open(clip['atlas']) as atlas:
            return [atlas.crop((round(left*atlas.width-.5),round(top*atlas.height-.5),
                                round(right*atlas.width+.5),round(bottom*atlas.height+.5))).convert('RGBA')
                    for left,top,right,bottom in clip['rects']]

    def test_opaque_and_transparent_thin_pictures_have_nonzero_uv_area(self):
        for size in ((1,1),(128,1),(1,128),(4096,4),(4,4096)):
            for alpha in (128,255):
                with self.subTest(size=size,alpha=alpha):
                    path=self.picture(size,alpha);original=path.read_bytes()
                    clip=ae_media.import_picture(path,self.root/(path.stem+'_atlas.png'))
                    ae.validate_clip(clip)
                    self.assertEqual(clip['frame_size'],list(size));self.assertGreaterEqual(min(clip['packed_frame_size']),2)
                    self.assertTrue(all(left<right and top<bottom for left,top,right,bottom in clip['rects']))
                    geometry=ae.preview_data(clip,ae.config(dict(plane='front',width=1.25)))['vertices']
                    width=max(vertex[0]for vertex in geometry)-min(vertex[0]for vertex in geometry)
                    height=max(vertex[1]for vertex in geometry)-min(vertex[1]for vertex in geometry)
                    self.assertAlmostEqual(width/height,size[0]/size[1])
                    pixels=self.frames(clip)[0]
                    self.assertEqual(pixels.getextrema()[3],(alpha,alpha))
                    # Fully opaque pixels are exact; semitransparent resize may
                    # round straight RGB by one, while alpha and aspect stay exact.
                    actual=pixels.getpixel((pixels.width//2,pixels.height//2))
                    for channel,expected in zip(actual[:3],(245,80,30)):self.assertLessEqual(abs(channel-expected),1)
                    self.assertEqual(path.read_bytes(),original)

    def test_thin_image_preset_and_project_roundtrip_preserve_logical_size(self):
        source=self.root/'source.wotmod'
        with zipfile.ZipFile(source,'w') as archive:archive.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'original')
        project=ae.source_project(source,self.root/'source');project['baseline_user_confirmed']=True
        values=ae.config(dict(fps=10,animation=dict(duration=.2,nodes=[dict(time=0)])))
        for size in ((1,1),(128,1),(1,128),(4096,4)):
            with self.subTest(size=size):
                picture=self.picture(size);clip=ae_media.import_picture(picture,self.root/(picture.stem+'_atlas.png'))
                name=picture.stem;unused,payload=ae_presets.encode(name,'thin image',clip,values)
                preset=self.root/(name+'.aepreset');preset.write_bytes(payload)
                unused,reopened=ae_presets.load(preset,self.root/('preset_'+name));ae.validate_clip(reopened)
                self.assertEqual(reopened['frame_size'],list(size))
                saved=self.root/(name+'.aefx');ae.save_project(saved,project,clip,values)
                unused,restored,settings=ae.load_project(saved,self.root/('project_'+name));ae.validate_clip(restored)
                self.assertEqual(restored['frame_size'],list(size));self.assertEqual(settings['animation'],values['animation'])
                prepared=ae.playback_clip(restored,settings,self.root/('motion_'+name));ae.validate_clip(prepared)
                self.assertEqual(prepared['frames'],2);self.assertEqual(prepared['frame_size'],list(size))
                self.assertTrue(all(a<b and c<d for a,c,b,d in prepared['rects']))

    def test_regular_dimensions_retain_existing_atlas_pixels_and_rects(self):
        frames=[Image.new('RGBA',(12,8),colour)for colour in ((255,0,0,128),(0,255,0,64),(0,0,255,255))]
        clip=ae.pack_frames(frames,self.root/'regular.png');ae.validate_clip(clip)
        self.assertEqual(clip['size'],[64,16]);self.assertEqual(clip['packed_frame_size'],[12,8])
        expected=Image.new('RGBA',(64,16))
        for frame,x in zip(frames,(2,18,34)):expected.paste(frame,(x,2))
        with Image.open(clip['atlas']) as actual:self.assertEqual(actual.tobytes(),expected.tobytes())
        self.assertEqual(clip['rects'],[[(x+.5)/64,2.5/16,(x+11.5)/64,9.5/16]for x in (2,18,34)])
        before=io.BytesIO();expected.save(before,format='PNG')
        self.assertEqual(Path(clip['atlas']).read_bytes(),before.getvalue())

    def test_fully_invisible_picture_keeps_existing_clear_validation_error(self):
        image=self.root/'invisible.png';Image.new('RGBA',(1,1)).save(image)
        with self.assertRaisesRegex(ValueError,'完全透明'):ae_media.import_picture(image,self.root/'invisible_atlas.png')


if __name__=='__main__':unittest.main()
