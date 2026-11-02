"""v2.1.2: every non-pulse mode must be provably flat, and recipes must be explicit."""
import json
import unittest

from wotcamo import light_effects as engine, light_recipe as recipe


def cfg(mode, colors=('#EAFBFF',), step=2.0, breath=2.0, peak=1.8, low=1.0,
        direction='同步', delay=0.0, duty=.3, curve=None):
    data = {'颜色': [{'名称': '颜色%d' % (i + 1), 'RGB': c} for i, c in enumerate(colors)],
            '每色秒数': step, '呼吸周期秒数': breath, '峰值倍率': peak, '暗相系数': low,
            '流水方向': direction, '每米延迟秒数': delay, '效果模式': mode, '亮灯比例': duty}
    if curve:
        data['换色曲线'] = curve
    return data


class NativePulseValues(unittest.TestCase):
    def test_pulse_mode_maps_breath_to_speed_and_low_to_dark_phase(self):
        for breath in (0.5, 2.0, 3.0):
            speed, dark = engine.native_pulse_values(recipe.validate_config(cfg('流水呼吸', breath=breath, low=.08)))
            self.assertAlmostEqual(speed, 4 / breath)
            self.assertAlmostEqual(dark, .08)

    def test_every_other_mode_writes_zero_speed_and_flat_dark_phase(self):
        # speed=0 freezes the native ramp on the tested client; 1.0 removes any
        # residual dimming if another branch reads g_offsetBlackFwd instead.
        for mode in ('流水渐变', '百花齐放', '动态呼吸', '波浪', '跑马灯'):
            speed, dark = engine.native_pulse_values(recipe.validate_config(cfg(mode)))
            self.assertEqual(speed, 0, mode)
            self.assertEqual(dark, 1.0, mode)


class BrightnessBounds(unittest.TestCase):
    def test_gradient_is_flat_even_with_a_dark_low(self):
        low, high = recipe.brightness_bounds(recipe.validate_config(cfg('流水渐变', low=.08)))
        self.assertEqual((low, high), (1.0, 1.0))

    def test_low_one_flattens_the_sequence_envelope(self):
        for mode in ('动态呼吸', '波浪', '百花齐放', '跑马灯'):
            low, high = recipe.brightness_bounds(recipe.validate_config(cfg(mode, low=1.0)))
            self.assertAlmostEqual(low, high, places=6, msg=mode)

    def test_dark_low_reports_a_visible_dim(self):
        low, high = recipe.brightness_bounds(recipe.validate_config(cfg('动态呼吸', low=.08, breath=3.0)))
        self.assertLess(low, .1)
        self.assertAlmostEqual(high, 1.0, places=6)

    def test_native_pulse_mode_reports_the_dark_phase(self):
        low, high = recipe.brightness_bounds(recipe.validate_config(cfg('流水呼吸', low=.2)))
        self.assertAlmostEqual(low, .2)
        self.assertAlmostEqual(high, 1.0)


class ExplicitRecipe(unittest.TestCase):
    def test_default_recipe_states_mode_and_duty(self):
        # A missing 效果模式 silently means 流水呼吸, which is the reported trap.
        self.assertIn('效果模式', engine.DEFAULT_RECIPE)
        self.assertIn('亮灯比例', engine.DEFAULT_RECIPE)
        parsed = recipe.validate_config(json.loads(json.dumps(engine.DEFAULT_RECIPE)))
        self.assertEqual(parsed['mode'], '流水呼吸')


if __name__ == '__main__':
    unittest.main()
