"""Named packaging checks use a synthetic export; Blender itself is mocked."""
import tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from wotcamo import models
from wotcamo.common import read_json,write_json


class ModelPackageTests(unittest.TestCase):
    def setUp(self):
        cache=models.ROOT/'.cache';cache.mkdir(exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=cache);self.addCleanup(temp.cleanup);self.project=Path(temp.name)
        write_json(self.project/'project.json',dict(tank='test/Tank',model='vehicles/test/Tank/Hull.model',game_version='test'))
        self.out=self.project/'exports/test';res=self.out/'res/vehicles/test/Tank';res.mkdir(parents=True)
        (res/'Hull.model').write_bytes(b'synthetic model');(res/'Hull.visual_processed').write_bytes(b'synthetic visual')
        write_json(self.out/'model_validation.json',dict(roundtrip_ok=True))
        write_json(self.project/'last_export.json',dict(output='exports/test'))
        self.index=patch.object(models,'load_index',return_value={'version':'test'});self.index.start();self.addCleanup(self.index.stop)
        self.blender=patch.object(models,'run_blender');self.blender.start();self.addCleanup(self.blender.stop)

    def test_named_model_is_packed_and_final_hash_is_recorded(self):
        output=models.export(self.project,{'x':1},lambda _:None,title='我的成品模型')
        package=output/'我的成品模型.wotmod';self.assertTrue(package.is_file())
        report=read_json(output/'report.json')
        self.assertEqual(report['artifact']['sha256'],models.digest(package.read_bytes()))
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        with zipfile.ZipFile(package) as z:
            self.assertEqual(z.read('res/vehicles/test/Tank/Hull.model'),b'synthetic model')
            self.assertTrue(all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist()))
        self.assertEqual(read_json(self.project/'project.json')['package_title'],'我的成品模型')

    def test_failed_model_validation_stops_packaging(self):
        write_json(self.out/'model_validation.json',dict(roundtrip_ok=False))
        with self.assertRaisesRegex(ValueError,'回读未通过'):models.export(self.project,{'x':1},lambda _:None,title='bad')
        self.assertFalse(list(self.out.glob('*.wotmod')))
