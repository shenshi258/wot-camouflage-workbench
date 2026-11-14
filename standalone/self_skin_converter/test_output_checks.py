import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from output_checks import check_output_directory


class OutputCheckTests(unittest.TestCase):
    def test_probe_is_removed_and_game_directory_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root=Path(d);client=root/'client';out=root/'out';client.mkdir();out.mkdir()
            self.assertEqual(check_output_directory(out,client),out.resolve())
            self.assertEqual(list(out.iterdir()),[])
            with self.assertRaises(ValueError):check_output_directory(client,client)

    def test_permission_error_is_reported_before_batch(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
            root=Path(d);client=root/'client';out=root/'out';client.mkdir();out.mkdir()
            with patch.object(Path,'open',side_effect=PermissionError('mock denied')):
                with self.assertRaisesRegex(PermissionError,'请选择|请改选'):
                    check_output_directory(out,client)
