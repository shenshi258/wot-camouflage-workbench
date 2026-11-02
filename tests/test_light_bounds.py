import unittest
import numpy as np
from wotcamo.light_assets import render_bounds

class LightBoundsTests(unittest.TestCase):
    def test_planar_wheel_bounds_expand_only_flat_axis_without_geometry_change(self):
        vertices=np.array([[.071,0.,0.],[.071,.5,0.],[.071,0.,.5]])
        before=vertices.copy();low,high=render_bounds(vertices)
        np.testing.assert_allclose(high-low,[.01,.5,.5]);np.testing.assert_array_equal(vertices,before)
        self.assertTrue((vertices>=low).all() and (vertices<=high).all())

    def test_volume_and_thin_but_non_degenerate_lamps_stay_exact(self):
        vertices=np.array([[-1.,-.1,-.003],[1.,.1,.003]])
        low,high=render_bounds(vertices)
        np.testing.assert_array_equal(low,vertices[0]);np.testing.assert_array_equal(high,vertices[1])

    def test_near_flat_rotated_frame_and_all_flat_axes(self):
        for vertices in (np.array([[0.,0.,0.],[1e-12,.5,.5]]),np.array([[1.,2.,3.]])):
            low,high=render_bounds(vertices)
            self.assertTrue(((high-low)>=.009999).all())
            self.assertTrue((vertices>=low).all() and (vertices<=high).all())

    def test_invalid_geometry_is_not_serialized_as_invalid_bounds(self):
        for vertices in ([],[[np.nan,0,0]],[[np.inf,0,0]],[[1,2]]):
            with self.assertRaises(ValueError):render_bounds(vertices)
