"""Node interpolation and real pixels from the shared baked-atlas pipeline."""
import copy
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from wotcamo import ae_animation as animation, ae_effects as ae


class AnimationNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def clip(self, colours=((240, 80, 20, 128),), size=(32, 16)):
        frames = [Image.new('RGBA', size, colour) for colour in colours]
        return ae.pack_frames(frames, self.root / 'source.png', allow_opaque=True)

    def frames(self, clip):
        with Image.open(clip['atlas']) as atlas:
            return [atlas.crop((round(a * atlas.width - .5), round(b * atlas.height - .5),
                                round(c * atlas.width + .5), round(d * atlas.height + .5))).copy()
                    for a, b, c, d in clip['rects']]

    def test_normalize_copies_orders_and_fills_neutral_pose(self):
        raw = dict(duration=3, nodes=[dict(time=2, x=40), dict(time=1)])
        normalized = animation.normalize(raw)
        self.assertEqual([node['time'] for node in normalized['nodes']], [1., 2.])
        self.assertEqual(normalized['nodes'][0]['opacity'], 100.)
        normalized['nodes'][0]['x'] = 50
        self.assertNotIn('x', raw['nodes'][1])
        self.assertEqual(raw['nodes'][0]['time'], 2)
        self.assertEqual(animation.normalize()['nodes'], [])

    def test_linear_smooth_hold_and_exact_endpoint_use_left_node_easing(self):
        value = dict(duration=2, nodes=[dict(time=.5, x=0), dict(time=1.5, x=100)])
        self.assertEqual(animation.sample(value, -1)['x'], 0)
        self.assertEqual(animation.sample(value, 4)['x'], 100)
        self.assertEqual(animation.sample(value, 1)['x'], 50)
        self.assertEqual(animation.sample(value, 1.5)['x'], 100)
        value['nodes'][0]['easing'] = 'smooth'
        self.assertEqual(animation.sample(value, .75)['x'], 15.625)
        value['nodes'][0]['easing'] = 'hold'
        self.assertEqual(animation.sample(value, 1.499)['x'], 0)
        self.assertEqual(animation.sample(value, 1.5)['x'], 100)

    def test_invalid_nodes_nan_boolean_and_duplicate_times_fail_before_writing(self):
        cases = [dict(nodes='bad'), dict(nodes=[dict(time=0)] * 65),
                 dict(duration=False), dict(duration=math.inf), dict(canvas_scale=.5),
                 dict(nodes=[dict(time=0, x=math.nan)]), dict(nodes=[dict(time=-.1)]),
                 dict(nodes=[dict(time=3)]), dict(nodes=[dict(time=1), dict(time=1)]),
                 dict(nodes=[dict(time=0, scale=0)]), dict(nodes=[dict(time=0, opacity=101)]),
                 dict(nodes=[dict(time=0, easing='invalid')]), dict(nodes=[dict(time=0, path='bad')])]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                animation.normalize(value)
        with self.assertRaises(ValueError):
            animation.sample({}, math.nan)
        with self.assertRaises(ValueError):
            animation.bake(self.clip(), dict(nodes=[dict(time=0)]), False, self.root / 'bad.png')
        self.assertFalse((self.root / 'bad.png').exists())

    def test_no_nodes_return_exact_clip_without_resampling_or_timing_change(self):
        clip = self.clip()
        self.assertIs(animation.bake(clip, dict(duration=60), 24, self.root / 'unused.png'), clip)
        self.assertFalse((self.root / 'unused.png').exists())

    def test_neutral_nodes_preserve_exact_straight_alpha_pixels_and_original(self):
        clip = self.clip(); before = Path(clip['atlas']).read_bytes()
        result = animation.bake(clip, dict(duration=.5, nodes=[dict(time=0)]), 4, self.root / 'baked.png')
        source = self.frames(clip)[0]
        self.assertEqual(result['frames'], 2)
        for frame in self.frames(result):
            self.assertEqual(frame.tobytes(), source.tobytes())
        self.assertEqual(Path(clip['atlas']).read_bytes(), before)
        ae.validate_clip(result)

    def test_bake_cannot_overwrite_the_source_atlas(self):
        clip = self.clip(); before = Path(clip['atlas']).read_bytes()
        with self.assertRaisesRegex(ValueError, '原素材'):
            animation.bake(clip, dict(nodes=[dict(time=0)]), 24, clip['atlas'])
        self.assertEqual(Path(clip['atlas']).read_bytes(), before)

    def test_gif_source_frames_loop_under_opacity_nodes_at_the_original_sample_rate(self):
        clip = self.clip(((255, 0, 0, 128), (0, 255, 0, 128), (0, 0, 255, 128)))
        config = dict(duration=1, nodes=[dict(time=0, opacity=100), dict(time=1, opacity=0)])
        result = animation.bake(clip, config, 6, self.root / 'moving.gif.png')
        actual = [np.asarray(frame) for frame in self.frames(result)]
        self.assertEqual([int(np.argmax(frame[0, 0, :3])) for frame in actual], [0, 1, 2, 0, 1, 2])
        self.assertEqual([int(frame[0, 0, 3]) for frame in actual], [128, 107, 85, 64, 43, 21])
        self.assertEqual(result['animation_info']['source_frames'], 3)
        self.assertNotIn(str(self.root), str(result['animation_info']))

    def test_real_gif_delays_and_disposal_survive_node_baking(self):
        from wotcamo import ae_media
        frames = []
        for x, colour in ((0, 'red'), (8, 'lime'), (16, 'blue')):
            image = Image.new('RGBA', (24, 12))
            image.paste(colour, (x, 2, x + 6, 8)); frames.append(image)
        path = self.root / 'variable.gif'
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=[100, 300, 200], disposal=2, loop=0)
        original = path.read_bytes()
        clip = ae_media.import_media(path, self.root / 'imported.png', fps=10)
        result = animation.bake(clip, dict(duration=1.2, nodes=[dict(time=0)]),
                                10, self.root / 'gif-nodes.png')
        pixels = [np.asarray(frame) for frame in self.frames(result)]
        self.assertEqual([int(np.argmax(frame[:, :, :3].sum((0, 1)))) for frame in pixels],
                         [0, 1, 1, 1, 2, 2] * 2)
        self.assertEqual([int(np.count_nonzero(frame[:, :, 3])) for frame in pixels], [36] * 12)
        self.assertEqual(path.read_bytes(), original)

    def test_positive_horizontal_and_vertical_motion_use_canvas_percentages(self):
        clip = self.clip(((255, 100, 0, 255),), size=(8, 4))
        base = dict(duration=1, canvas_scale=4, nodes=[dict(time=0, x=25, y=25)])
        result = animation.bake(clip, base, 1, self.root / 'translated.png')
        pixels = np.asarray(self.frames(result)[0]); ys, xs = np.where(pixels[:, :, 3] > 0)
        self.assertEqual(pixels.shape[:2], (16, 32))
        self.assertAlmostEqual(float(xs.mean()), 23.5)
        self.assertAlmostEqual(float(ys.mean()), 3.5)
        self.assertEqual(len(xs), 32)

    def test_scale_and_rotation_stay_centred_and_keep_clean_alpha_edges(self):
        clip = self.clip(((255, 120, 0, 128),), size=(16, 8))
        result = animation.bake(clip, dict(duration=1, canvas_scale=3,
                                         nodes=[dict(time=0, scale=1.5, rotation=90)]),
                                1, self.root / 'rotated.png')
        pixels = np.asarray(self.frames(result)[0]); ys, xs = np.where(pixels[:, :, 3] > 10)
        self.assertAlmostEqual(float(xs.mean()), 23.5)
        self.assertAlmostEqual(float(ys.mean()), 11.5)
        self.assertGreater(np.ptp(ys), np.ptp(xs))
        opaque = pixels[:, :, 3] > 20
        self.assertTrue(np.all(pixels[:, :, 0][opaque] >= 250))

    def test_duration_quantization_limits_and_large_canvas_are_bounded(self):
        clip = self.clip(size=(512, 256))
        result = animation.bake(clip, dict(duration=.26, canvas_scale=4, nodes=[dict(time=0)]),
                                10, self.root / 'bounded.png')
        self.assertEqual(result['frames'], 3)
        self.assertAlmostEqual(result['animation_info']['duration'], .3)
        self.assertLessEqual(max(result['packed_frame_size']), 512)
        self.assertEqual(result['frame_size'], [2048, 1024])
        with self.assertRaisesRegex(ValueError, '128'):
            animation.bake(clip, dict(duration=60, nodes=[dict(time=0)]), 60, self.root / 'too-long.png')
        self.assertFalse((self.root / 'too-long.png').exists())


if __name__ == '__main__':
    unittest.main()
