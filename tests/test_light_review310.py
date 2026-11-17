"""Regressions for exact envelope bounds and ownership at shared band planes."""
import copy
import unittest
import numpy as np
from wotcamo import light_assets as mesh,light_effects as engine,light_recipe as recipe
from wotcamo.preview3d_assets import evaluate_track


class ExactEnvelopeBoundsTests(unittest.TestCase):
    def config(self,mode,dimming=True,low=.08):
        raw=copy.deepcopy(engine.DEFAULT_RECIPE)
        raw.update(颜色=[dict(名称='白',RGB=[1.,1.,1.])],每色秒数=19.2,呼吸周期秒数=.2,
                   峰值倍率=1.,暗相系数=low,效果模式=mode,亮灯比例=.3,启用明暗变化=dimming)
        return recipe.validate_config(raw)

    def test_marquee_pulses_cannot_disappear_from_the_audit_sampling_grid(self):
        cfg=self.config('跑马灯',low=0.)
        self.assertEqual(cfg['period'],19.2)
        # Every old 96-grid sample was exactly between the short bright pulses.
        self.assertTrue(all(recipe.envelope_at(cfg['period']*i/96,0.,cfg)<1e-9 for i in range(97)))
        self.assertEqual(recipe.brightness_bounds(cfg),(0.,1.))
        self.assertEqual(recipe.envelope_at(.1,0.,cfg),1.)
        track=recipe.colour_track('lamp',0.,cfg)
        output=evaluate_track(track.findall('frame'),np.array([0.,.1]))
        np.testing.assert_allclose(output[:,:3],[[0,0,0],[1,1,1]],atol=1e-9)

    def test_every_dimming_mode_reports_its_exact_extrema_for_any_spatial_phase(self):
        for mode in recipe.MODES:
            if mode in recipe.COLOR_ONLY_MODES:continue
            cfg=self.config(mode)
            for phase in(0.,.017,cfg['period']-.03):
                with self.subTest(mode=mode,phase=phase):
                    self.assertEqual(recipe.brightness_bounds(cfg,phase),(.08,1.))
                    if mode!='流水呼吸':
                        # These modes bake their envelope into the colour keys.
                        minimum_time=0. if mode=='跑马灯' else .1
                        maximum_time=.1 if mode=='跑马灯' else 0.
                        if mode!='动态呼吸':minimum_time-=phase;maximum_time-=phase
                        self.assertAlmostEqual(recipe.envelope_at(minimum_time,phase,cfg),.08)
                        self.assertAlmostEqual(recipe.envelope_at(maximum_time,phase,cfg),1.)

    def test_disabled_and_colour_only_modes_are_flat_even_when_a_dark_floor_is_configured(self):
        for mode in recipe.MODES:
            for dimming in(False,True) if mode in recipe.COLOR_ONLY_MODES else(False,):
                with self.subTest(mode=mode,dimming=dimming):
                    cfg=self.config(mode,dimming)
                    self.assertEqual(recipe.brightness_bounds(cfg), (1.,1.))


class HalfOpenBandTests(unittest.TestCase):
    @staticmethod
    def vertices(points):
        vertices=np.zeros((len(points),8));vertices[:,:3]=points;vertices[:,4]=1.
        vertices[:,6]=vertices[:,0]+2*vertices[:,2]
        vertices[:,7]=vertices[:,1]-vertices[:,2]
        return vertices

    def assert_preserved(self,vertices,indices,bands):
        self.assertTrue(bands)
        self.assertAlmostEqual(sum(mesh.area(v,i)for v,i,_ in bands),mesh.area(vertices,indices),places=11)
        for output,ids,_ in bands:
            self.assertGreaterEqual(np.asarray(ids).min(),0)
            self.assertLess(np.asarray(ids).max(),len(output))
            np.testing.assert_allclose(output[:,6],output[:,0]+2*output[:,2],atol=1e-12)
            np.testing.assert_allclose(output[:,7],output[:,1]-output[:,2],atol=1e-12)
            np.testing.assert_allclose(output[:,3:6],np.tile([0.,1.,0.],(len(output),1)),atol=1e-12)

    def test_complete_face_on_internal_legacy_plane_has_one_owner(self):
        vertices=self.vertices([[0,0,.5],[1,0,.5],[0,1,.5],[0,0,1],[0,1,0]])
        indices=np.array([[0,1,2],[0,1,3],[0,2,4]])
        self.assertEqual(mesh.area(vertices,indices),1.)
        bands=mesh.split_bands(vertices,indices,False)
        self.assert_preserved(vertices,indices,bands)
        # The complete z=.5 face is retained only in the z=.5..1 band.
        face_areas=[sum(mesh.area(v,tri)for tri in np.asarray(ids).reshape(-1,3)
                        if np.all(v[tri,2]==.5))for v,ids,_ in bands]
        np.testing.assert_allclose(face_areas,[0.,.5])

    def test_complete_face_on_internal_projected_plane_keeps_uv_and_normals(self):
        vertices=self.vertices([[0,.4,0],[1,.4,0],[0,.4,1],[0,.8,0],[0,0,1]])
        indices=np.array([[0,1,2],[0,1,3],[0,2,4]])
        self.assert_preserved(vertices,indices,mesh.split_for_direction(vertices,indices,'向上',np.eye(4)))

    def test_crossing_faces_and_final_boundary_are_preserved(self):
        vertices=self.vertices([[0,0,0],[1,0,1],[0,1,1],[1,1,1]])
        indices=np.array([[0,1,2],[1,2,3]])
        self.assert_preserved(vertices,indices,mesh.split_bands(vertices,indices,False))
        # The uppermost face remains even though all three vertices equal high.
        self.assert_preserved(vertices,indices,mesh.split_for_direction(vertices,indices,'向上',np.eye(4)))

    def test_rotated_attachment_projection_preserves_crossing_faces(self):
        vertices=self.vertices([[0,0,0],[1,0,1],[0,1,1],[1,1,1]])
        indices=np.array([[0,1,2],[1,2,3]])
        transform=np.eye(4);transform[:3,:3]=[[0,1,0],[-1,0,0],[0,0,1]];transform[3,:3]=[.4,-.2,.7]
        for direction in recipe.FLOW_VECTORS:
            with self.subTest(direction=direction):
                self.assert_preserved(vertices,indices,mesh.split_for_direction(vertices,indices,direction,transform))


if __name__=='__main__':unittest.main()
