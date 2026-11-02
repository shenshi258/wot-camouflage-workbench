import io,json,tempfile,unittest,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae,preview3d_assets as assets

class AEEffectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def frames(self):
        paths=[]
        for i in [10,2,1]:
            im=Image.new('RGBA',(32,16));im.putpixel((12,8),(i,120,230,100));p=self.folder/('frame_%d.png'%i);im.save(p);paths.append(p)
        return paths
    def test_natural_frame_order_alpha_and_padding(self):
        clip=ae.import_sequence(self.frames(),self.folder/'atlas.png')
        self.assertEqual(clip['order'],['frame_1.png','frame_2.png','frame_10.png'])
        atlas=np.asarray(Image.open(clip['atlas']))
        for i,rect in enumerate(clip['rects']):
            x=round(rect[0]*atlas.shape[1]-.5);y=round(rect[1]*atlas.shape[0]-.5)
            self.assertEqual(atlas[y+8,x+12].tolist(),[[1,120,230,100],[2,120,230,100],[10,120,230,100]][i])
            self.assertTrue(np.all(atlas[y-1,x:x+32,3]==0))
    def test_sheet_order_and_invalid_grid(self):
        im=Image.new('RGBA',(32,32));im.paste((255,0,0,128),(0,0,16,16));im.paste((0,255,0,180),(16,0,32,16));p=self.folder/'sheet.png';im.save(p)
        clip=ae.import_sheet(p,2,2,2,self.folder/'atlas.png');self.assertEqual(clip['frames'],2)
        with self.assertRaises(ValueError):ae.import_sheet(p,3,2,2,self.folder/'no.png')
    def test_black_premultiplied_alpha_is_unpremultiplied(self):
        im=Image.new('RGBA',(8,8),(32,64,96,128));im.putpixel((0,0),(0,0,0,0));clip=ae.pack_frames([im],self.folder/'atlas.png',True)
        atlas=Image.open(clip['atlas']);self.assertTrue(60<=atlas.getpixel((4,4))[0]<=65)
    def test_import_rejects_opaque_empty_mismatch_and_oversize(self):
        for color in [(1,2,3,255),(0,0,0,0)]:
            with self.assertRaises(ValueError):ae.pack_frames([Image.new('RGBA',(8,8),color)],self.folder/'bad.png')
        with self.assertRaises(ValueError):ae.pack_frames([Image.new('RGBA',(8,8)),Image.new('RGBA',(9,8))],self.folder/'bad.png')
        with self.assertRaises(ValueError):ae.import_sequence([],self.folder/'bad.png')
        with self.assertRaises(ValueError):ae.config(dict(fps=float('nan')))
    def test_saved_atlas_change_is_detected(self):
        clip=ae.import_sequence(self.frames(),self.folder/'atlas.png');Path(clip['atlas']).write_bytes(b'changed')
        with self.assertRaises(ValueError):ae.validate_clip(clip)
    def test_only_one_frame_visible_at_frame_centers_and_multiple_loops(self):
        for count,fps in [(1,24),(2,60),(17,24),(128,60)]:
            clip=dict(frames=count,rects=[[0,0,1,1]]*count);c=ae.config(dict(fps=fps))
            root=ET.fromstring(ae.sequence('particles/test/',clip,c,[-1.82,0,0]))
            tracks=[next(t for t in ob.findall('track') if t.findtext('name')=='scale') for ob in root.findall('sequenceObject')[1:]]
            for loop in range(2):
                for index in range(count):
                    time=((loop*count+index+.5)/fps)%(count/fps)
                    samples=[assets.evaluate_track(tr.findall('frame'),np.array([time]))[0,0] for tr in tracks]
                    self.assertAlmostEqual(sum(samples),1,places=6);self.assertAlmostEqual(samples[index],1,places=6)
    def test_placement_is_separate_from_quad_scaling_and_preview_uses_export_geometry(self):
        clip=ae.import_sequence(self.frames(),self.folder/'atlas.png');c=ae.config(dict(width=2,x=-1.82,y=.3,z=1,mirror=True,part='gun'))
        plan=ae.preview_data(clip,c);vertices,_=ae.plane_mesh(clip,c,clip['rects'][0]);self.assertTrue(np.array_equal(plan['vertices'],vertices))
        self.assertEqual(np.ptp(vertices[:,2]),2);self.assertEqual(np.ptp(vertices[:,1]),1);self.assertTrue(np.all(vertices[:,0]==0))
        self.assertEqual(plan['positions'],[[-1.82,.3,1],[1.82,.3,1]]);self.assertEqual([plan['blendSrc'],plan['blendDst']],[5,2])
        plan=ae.preview_data(clip,dict(c,blend='alpha'));self.assertEqual(plan['blendDst'],6)
    def test_plane_axes_change_length_and_height_independently_in_preview_and_export(self):
        clip=ae.import_sequence(self.frames(),self.folder/'atlas.png')
        for sx,sy,expected in [(2,1,(4,1)),(1,2,(2,2)),(1.5,.5,(3,.5))]:
            c=ae.config(dict(width=2,uv_scale_x=sx,uv_scale_y=sy))
            vertices=ae.quad(clip,c,[0,0,1,1]);plan=ae.geometry_plan(None,clip,c,None)
            self.assertAlmostEqual(np.ptp(vertices[:,2]),expected[0]);self.assertAlmostEqual(np.ptp(vertices[:,1]),expected[1])
            dense,_=ae.plane_mesh(clip,c,[0,0,1,1])
            np.testing.assert_allclose(dense,plan['vertices'])
            preview=ae.preview_data(clip,c)
            np.testing.assert_allclose(preview['vertices'],ae.atlas_vertices(dense,clip['rects'][0]))

    def test_dds_retains_atlas_alpha_and_no_cross_cell_mips(self):
        clip=ae.import_sequence(self.frames(),self.folder/'atlas.png');im=Image.open(clip['atlas']);raw=ae.dds(im)
        actual=Image.open(io.BytesIO(raw)).convert('RGBA');self.assertTrue(np.array_equal(np.asarray(im),np.asarray(actual)))
    def test_project_roundtrip_is_self_contained_and_rejects_extra_entries(self):
        source=self.folder/'source.wotmod'
        with zipfile.ZipFile(source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/example.dds',b'example')
        p=ae.source_project(source,self.folder/'work');p['baseline_user_confirmed']=True
        clip=ae.import_sequence(self.frames(),self.folder/'atlas.png');project=self.folder/'saved.aefx'
        ae.save_project(project,p,clip,dict(ae.DEFAULTS,fps=30));Path(clip['atlas']).unlink();source.unlink()
        p2,clip2,c=ae.load_project(project,self.folder/'restored');self.assertEqual(c['fps'],30);self.assertTrue(p2['baseline_user_confirmed']);ae.validate_clip(clip2)
        with zipfile.ZipFile(project,'a') as z:z.writestr('../bad',b'x')
        with self.assertRaises(ValueError):ae.load_project(project,self.folder/'bad')

if __name__=='__main__':unittest.main()
