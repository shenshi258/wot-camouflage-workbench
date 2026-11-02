"""Geometry parity, non-folding footprints and portable pulled-corner settings."""
import tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae,ae_presets

class AEDeformTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.clip=ae.pack_frames([Image.new('RGBA',(32,16),(80,160,255,128))],self.root/'atlas.png')
    def tearDown(self):self.temp.cleanup()
    def test_one_corner_does_not_move_other_corners_and_grid_matches_preview(self):
        c=ae.config(dict(width=2,warp_tr_x=.3,warp_tr_y=-.2,warp_tr_z=.4))
        original,_=ae.plane_frames(self.clip,ae.config(dict(width=2)))
        corners,size=ae.plane_frames(self.clip,c)
        np.testing.assert_allclose(np.array(corners)[[0,2,3]],np.array(original)[[0,2,3]])
        np.testing.assert_allclose(np.array(corners)[1]-original[1],[.2,-.1,-.3])
        plan=ae.geometry_plan(None,self.clip,c,None);preview=ae.preview_data(self.clip,c)
        self.assertEqual(len(plan['vertices']),81);self.assertEqual(len(plan['indices']),384)
        np.testing.assert_allclose(np.array(ae.plane_weights())@np.array(corners),plan['vertices'][:,:3])
        np.testing.assert_allclose(preview['vertices'],ae.atlas_vertices(plan['vertices'],self.clip['rects'][0]))
        np.testing.assert_allclose(np.linalg.norm(plan['vertices'][:,3:6],axis=1),1)
    def test_rotation_and_all_orientations_keep_handles_on_exported_corners(self):
        for plane in ('side','front','top'):
            c=ae.config(dict(plane=plane,angle=37,warp_bl_x=.2,warp_bl_z=-.3,crop_left=10,crop_bottom=15))
            corners,_=ae.plane_frames(self.clip,c);v,ids=ae.plane_mesh(self.clip,c,[0,0,1,1])
            np.testing.assert_allclose(v[[0,8,80,72],:3],corners)
    def test_crossed_or_collapsed_quads_are_refused(self):
        for changes in (dict(warp_tl_x=2),dict(warp_tr_y=-2),dict(warp_bl_x=2,warp_br_x=-2)):
            with self.assertRaisesRegex(ValueError,'交叉'):ae.config(changes)
    def test_old_presets_load_neutral_warp_and_pulled_shape_roundtrips(self):
        _,raw=ae_presets.encode('test','',self.clip,ae.config(dict(warp_tr_x=.3,warp_bl_z=.2)))
        p=self.root/'test.aepreset';p.write_bytes(raw)
        metadata,clip=ae_presets.load(p,self.root/'restored')
        self.assertEqual(metadata['config']['warp_tr_x'],.3);self.assertEqual(metadata['config']['warp_bl_z'],.2)
        self.assertEqual(ae.config({})['warp_bl_z'],0)
    def test_new_plane_retains_animation_and_centres_surface_bounds(self):
        current=ae.config(dict(placement='surface',plane='auto',fps=30,crop_left=10,warp_tr_x=.4))
        effect=dict(vertices=[[2,1,-3,0,0,0,0,0],[2,3,1,0,0,0,1,1]],positions=[[0,0,0]],part='turret')
        c=ae.new_plane_config(self.clip,current,effect)
        self.assertEqual(c['placement'],'plane');self.assertEqual(c['part'],'turret');self.assertEqual(c['plane'],'side')
        self.assertAlmostEqual(c['x'],2.006);self.assertEqual(c['y'],2);self.assertEqual(c['z'],-1)
        self.assertEqual(c['width'],4);self.assertEqual(c['fps'],30);self.assertEqual(c['warp_tr_x'],0);self.assertEqual(c['crop_left'],0)

if __name__=='__main__':unittest.main()
