"""Marquee selection geometry tests (no GUI needed)."""

import unittest
import numpy as np

from wotcamo import light_select


def face(identifier, points, anchor='Gun', texture='a.dds', visual='res/vehicles/test/normal/lod0/test.visual_processed'):
    points = np.asarray(points, dtype=float)
    return dict(id=identifier, visual=visual, anchor=anchor, anchor_kind='node', texture=texture,
                material='mat', component=0, triangles=1, supported=True, selected=False, _preview=points)


class LightSelectTests(unittest.TestCase):
    def setUp(self):
        # Two separate clusters along Z, one model each.
        self.front = face('front', [[0, 1, -2], [1, 1, -2], [0, 2, -2]])
        self.rear = face('rear', [[0, 1, 2], [1, 1, 2], [0, 2, 2]], anchor='G', texture='b.dds')
        self.other = face('other', [[5, 1, 0], [6, 1, 0], [5, 2, 0]], visual='res/vehicles/test/normal/lod0/hull.visual_processed')
        self.lights = [self.front, self.rear, self.other]

    def test_view_keeps_three_panes_and_centers_geometry(self):
        view = light_select.View(self.lights, 900, 300)
        self.assertEqual([pane['label'] for pane in view.panes], ['侧面 Z/Y', '正面 X/Y', '俯视 X/Z'])
        centre = view.screen(np.array([[3.0, 1.5, 0.0]]), view.panes[1])
        pane = view.panes[1]
        self.assertAlmostEqual(centre[0, 0], pane['left'] + pane['width'] / 2, places=6)

    def test_full_rectangle_hits_every_face(self):
        view = light_select.View(self.lights, 900, 300)
        hits = view.hit(self.lights, (0, 0, 900, 300))
        self.assertEqual(set(hits), {'front', 'rear', 'other'})

    def test_single_pane_rectangle_only_hits_that_pane(self):
        view = light_select.View(self.lights, 900, 300)
        pane = view.panes[0]
        hits = view.hit(self.lights, (pane['left'], 0, pane['left'] + pane['width'], 300))
        self.assertTrue({'front', 'rear', 'other'} <= set(hits))
        # Narrow band inside the side pane keeps only the rear cluster, which sits at +Z.
        screen = view.screen(self.rear['_preview'], pane)
        hits = view.hit(self.lights, (screen[:, 0].min() - 2, screen[:, 1].min() - 2,
                                      screen[:, 0].max() + 2, screen[:, 1].max() + 2))
        self.assertIn('rear', hits)

    def test_nearest_click_prefers_the_closest_face(self):
        view = light_select.View(self.lights, 900, 300)
        target = view.screen(self.other['_preview'], view.panes[2])
        x, y = (float(value) for value in target[0])
        self.assertEqual(view.nearest(self.lights, x, y), 'other')
        self.assertIsNone(view.nearest(self.lights, -50, -50, tolerance=2.0))

    def test_rect_normalisation_and_tiny_drag_detection(self):
        self.assertEqual(light_select.normalize_rect((10, 20, 5, 8)), (5, 8, 10, 20))
        self.assertTrue(light_select.rect_too_small((5, 5, 6, 6)))
        self.assertFalse(light_select.rect_too_small((5, 5, 60, 6)))

    def test_merge_modes_follow_drag_modifier(self):
        self.assertEqual(light_select.merge({'a'}, {'b'}, 'replace'), {'b'})
        self.assertEqual(light_select.merge({'a'}, {'b'}, 'add'), {'a', 'b'})
        self.assertEqual(light_select.merge({'a', 'b'}, {'b'}, 'subtract'), {'a'})
        self.assertEqual(light_select.drag_mode(shift=True), 'add')
        self.assertEqual(light_select.drag_mode(control=True), 'subtract')
        self.assertEqual(light_select.drag_mode(), 'replace')

    def test_expand_to_models_grows_to_whole_model(self):
        sibling = face('sibling', [[0, 1, -3]], anchor='Gun', texture='a.dds')
        lights = [self.front, sibling, self.rear, self.other]
        expanded = light_select.expand_to_models(lights, {'front'})
        self.assertEqual(expanded, {'front', 'sibling'})
        self.assertEqual(light_select.model_count(lights, expanded), 1)
        self.assertEqual(light_select.model_count(lights, {'front', 'rear', 'other'}), 3)

    def test_sample_limit_stays_usable_with_hundreds_of_faces(self):
        self.assertEqual(light_select.face_sample_limit(1), 250)
        self.assertEqual(light_select.face_sample_limit(200), 30)
        self.assertEqual(light_select.face_sample_limit(5000), light_select.MIN_POINTS_PER_FACE)

    def test_cursor_zoom_keeps_point_under_pointer(self):
        view=light_select.View(self.lights,900,300);pane=view.panes[2]
        point=self.rear['_preview'][:1];x,y=view.screen(point,pane)[0]
        view.zoom_by(2,float(x),float(y))
        np.testing.assert_allclose(view.screen(point,pane)[0],[x,y])
        self.assertEqual(view.zoom,2)

    def test_zoom_and_pan_selection_uses_only_visible_points(self):
        view=light_select.View(self.lights,900,300,zoom=2)
        pane=view.panes[2];point=self.rear['_preview'][:1]
        x,y=view.screen(point,pane)[0]
        view.pan[2]+=np.array([pane['left']+pane['width']/2-x,150-y])
        x,y=view.screen(point,pane)[0]
        self.assertEqual(view.nearest(self.lights,float(x),float(y)),'rear')
        self.assertIn('rear',view.hit(self.lights,(x-2,y-2,x+2,y+2)))
        # Move this pane's projection across its boundary. It must not be
        # rendered or selectable as a phantom point in the adjacent pane.
        view.pan[2,0]-=400
        self.assertFalse(view.visible(view.screen(point,pane),pane)[0])

    def test_zoom_limits_and_reset_state(self):
        view=light_select.View(self.lights,900,300)
        self.assertEqual(view.zoom_by(1000),20)
        self.assertEqual(view.zoom_by(.000001),.25)
        for factor in (0,-1,float('nan')):
            with self.assertRaises(ValueError):view.zoom_by(factor)


if __name__ == '__main__':
    unittest.main()
