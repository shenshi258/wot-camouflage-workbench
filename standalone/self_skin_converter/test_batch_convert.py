import tempfile,unittest,zipfile,threading
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import batch_convert as batch
import test_builder as fixtures


class BatchTests(unittest.TestCase):
    def test_nested_zip_is_inspected_without_extracting_documents(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);skin=root/'skin.wotmod'
            with zipfile.ZipFile(skin,'w')as z:z.writestr('res/vehicles/test/Tank/skin_AM.dds',b'pixels')
            outer=root/'input.zip'
            with zipfile.ZipFile(outer,'w')as z:
                z.write(skin,'folder/skin.wotmod');z.writestr('README.txt','do not execute anything')
            rows=batch.analyse_many([outer])
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['vehicles'],['test/Tank'])
            self.assertEqual(rows[0]['origin']['member'],'folder/skin.wotmod')
            self.assertFalse((root/'README.txt').exists())

    def test_one_bad_file_does_not_prevent_later_candidate_or_change_input(self):
        fixture=fixtures.BuilderTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        bad=fixture.root/'bad.wotmod'
        with zipfile.ZipFile(bad,'w')as z:z.writestr('res/vehicles/test/TestTank/skin_AM.dds',b'p');z.writestr('res/scripts/client/gui/mods/unknown.pyc',b'unknown')
        original=fixture.skin.read_bytes()
        real=batch.builder.build
        with patch('batch_convert.builder.build',side_effect=lambda *args,**kwargs:real(*args,**kwargs,compiler=fixture.fake_compile)):
            rows,report=batch.convert_many([bad,fixture.skin],fixture.client,fixture.root/'output')
        self.assertEqual([r['status']for r in rows],['error','candidate'])
        self.assertTrue(report.exists());self.assertEqual(fixture.skin.read_bytes(),original)

    def test_cancel_does_not_generate_remaining_files(self):
        fixture=fixtures.BuilderTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        cancel=threading.Event();cancel.set()
        rows,report=batch.convert_many([fixture.skin],fixture.client,fixture.root/'output',cancel=cancel)
        self.assertEqual(rows[0]['status'],'cancelled')
        self.assertFalse(list((fixture.root/'output').rglob('*.wotmod')))


if __name__=='__main__':unittest.main()
