"""Offline regressions for interrupted builds and native Pulse preview timing."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from wotcamo import light_assets as mesh, light_effects as engine, light_recipe as recipe
import test_light_wheels as fixtures


class LightBuildReviewTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)

    def test_legacy_pulse_breathing_is_synchronous_with_white_phase_map(self):
        raw=copy.deepcopy(engine.DEFAULT_RECIPE)
        raw['颜色']=[{'名称':'白','RGB':'#FFFFFF'}]
        cfg=recipe.validate_config(raw)
        for time in (0., .2, .7, 1.):
            np.testing.assert_allclose(recipe.animated_value(time,0,cfg),
                                       recipe.animated_value(time,.5,cfg),atol=1e-10)
        self.assertGreater(recipe.animated_value(0,0,cfg)[0],
                           recipe.animated_value(cfg['breath']/2,0,cfg)[0])
        cfg=recipe.validate_config(dict(raw,效果模式='波浪'))
        self.assertNotAlmostEqual(recipe.animated_value(0,0,cfg)[0],
                                  recipe.animated_value(0,.5,cfg)[0])

    def project(self,root):
        source=root/'original.wotmod';lights=fixtures.WheelExportTests().lights()
        vertices,ids=fixtures.ring();visual=fixtures.fixture_visual(vertices,ids)
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
            for light in lights:
                z.writestr(light['visual'],mesh.xml(visual))
                z.writestr(light['visual'].replace('.visual_processed','.primitives_processed'),
                           mesh.primitives(vertices,ids.ravel()))
            z.writestr('res/wheel.dds',mesh.dds(True))
        return dict(source=str(source),source_sha256=engine.digest(source),
                    recipe=copy.deepcopy(engine.DEFAULT_RECIPE),lights=lights)

    def build(self,root,project):
        with patch.object(engine,'client_info',return_value={'root':str(root/'client')}), \
             patch.object(engine,'compile27',side_effect=lambda source,target,client:target.write_bytes(b'offline fixture')):
            return engine.build(project,root/'client',root/'out','review')

    def test_failed_final_audit_does_not_publish_an_installable_package(self):
        with tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache') as tmp:
            root=Path(tmp);project=self.project(root)
            with patch.object(engine,'audit_package',side_effect=ValueError('injected audit failure')):
                with self.assertRaisesRegex(ValueError,'injected audit failure'):
                    self.build(root,project)
            self.assertFalse(list((root/'out').rglob('*.wotmod')))
            self.assertEqual(engine.digest(project['source']),project['source_sha256'])

    def test_failed_report_write_does_not_publish_an_installable_package(self):
        with tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache') as tmp:
            root=Path(tmp);project=self.project(root);write_json=engine.write_json
            def fail_record(path,value):
                if Path(path).name=='验证记录.json':raise OSError('injected record failure')
                return write_json(path,value)
            with patch.object(engine,'audit_package',return_value={'status':'fixture_only'}), \
                 patch.object(engine,'write_json',side_effect=fail_record):
                with self.assertRaisesRegex(OSError,'injected record failure'):
                    self.build(root,project)
            self.assertFalse(list((root/'out').rglob('*.wotmod')))

    def test_success_publishes_record_bound_to_final_package(self):
        with tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache') as tmp:
            root=Path(tmp);project=self.project(root)
            with patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
                target,record=self.build(root,project)
            self.assertTrue(target.is_file())
            self.assertFalse(list(target.parent.glob('*.building')))
            self.assertEqual(record['artifact']['path'],str(target))
            self.assertEqual(record['artifact']['sha256'],engine.digest(target))
            self.assertEqual(record,json.loads((target.parent/'验证记录.json').read_text(encoding='utf-8')))
            self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested')


if __name__=='__main__':unittest.main()
