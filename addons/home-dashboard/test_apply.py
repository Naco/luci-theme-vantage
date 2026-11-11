import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('overlay', Path(__file__).with_name('apply.py'))
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class OverlayTests(unittest.TestCase):
    def test_rejects_wrong_build(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected input'):
            overlay.transform(b'changed', {'input_sha256': overlay.digest(b'expected')})

    def test_rejects_overlapping_edits(self):
        data = b'abcdef'
        manifest = {'input_sha256': overlay.digest(data), 'edits': [
            {'start': 1, 'end': 4, 'text': 'x'}, {'start': 3, 'end': 5, 'text': 'y'}]}
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            overlay.transform(data, manifest)

    @unittest.skipUnless(os.environ.get('HOME_DASHBOARD_STOCK'), 'requires extracted official APKs')
    def test_release_and_corruption(self):
        stock = Path(os.environ['HOME_DASHBOARD_STOCK'])
        manifest = json.loads(Path(__file__).with_name('v1.0.19-apk.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(overlay.build(stock, Path(temporary), manifest), 4)
            for name, entry in manifest['files'].items():
                original = (stock / 'www/luci-static/resources' / name).read_bytes()
                with self.assertRaisesRegex(ValueError, 'Unexpected input'):
                    overlay.transform(original + b'\n', entry)


if __name__ == '__main__':
    unittest.main()
