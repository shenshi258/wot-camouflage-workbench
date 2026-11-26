import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image
from wotcamo import ae_atlas, ae_effects as ae


def frame_box(atlas, rect, border=0):
    width, height = atlas.size
    return (round(rect[0] * width - .5) - border, round(rect[1] * height - .5) - border,
            round(rect[2] * width + .5) + border, round(rect[3] * height + .5) + border)


class ExportCompactionTests(unittest.TestCase):
    def test_identical_pixels_share_storage_in_the_finished_dual_side_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = Image.new('RGBA', (120, 64), (245, 10, 85, 150))
            b = Image.new('RGBA', (120, 64), (10, 150, 245, 75))
            clip = ae.pack_frames([a, a, b, a, b, b] * 4, root / 'old-atlas.png')
            source = root / 'input.wotmod'
            retained = 'res/vehicles/german/G197_Pz_Kpfw_Neu/original.dds'
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr(retained, b'synthetic base')
            project = ae.source_project(source, root / 'unused')
            project['baseline_user_confirmed'] = True  # Synthetic test fixture.
            client = root / 'client'
            shaders = client / 'res/packages'
            shaders.mkdir(parents=True)
            binary = io.BytesIO()
            with zipfile.ZipFile(binary, 'w') as z:
                z.writestr('effect', b"('SRCALPHA', 5) ('ONE', 2)")
            with zipfile.ZipFile(shaders / 'shaders.pkg', 'w') as z:
                for branch in ('10', '11'):
                    z.writestr(f'shaders/custom/emissive_playground.{branch}.dx11.fxo', binary.getvalue())
            with (patch.object(ae.engine, 'client_info', return_value={'kind': 'synthetic'}),
                  patch.object(ae.engine, 'compile27', side_effect=lambda _, target, __: target.write_bytes(b'synthetic')),
                  patch.object(ae.engine, 'audit_package', return_value={'missing_dependencies': []})):
                output, report = ae.build(project, clip, {'fps': 12, 'mirror': True}, client, root / 'out', 'Test')
            with zipfile.ZipFile(output) as z, Image.open(clip['atlas']) as before:
                names = z.namelist()
                prefix = next(n for n in names if n.endswith('/manifest.json')).removesuffix('manifest.json')
                manifest = json.loads(z.read(prefix + 'manifest.json'))
                layout = manifest['export_layout']
                self.assertEqual(layout['frame_models'], [0, 0, 1, 0, 1, 1] * 4)
                self.assertEqual(manifest['clip']['frame_size'], [120, 64])
                self.assertEqual(manifest['clip']['packed_frame_size'], [120, 64])
                self.assertEqual(layout['unique_frames'], 2)
                self.assertLess(layout['dds_bytes'], layout['original_dds_bytes'] / 2)
                self.assertNotIn(prefix + 'atlas.png', names)
                self.assertEqual(z.read(retained), b'synthetic base')
                with Image.open(io.BytesIO(z.read(prefix + 'atlas.dds'))) as after:
                    for old, index in zip(clip['rects'], layout['frame_models']):
                        new = layout['rects'][index]
                        self.assertEqual(before.crop(frame_box(before, old, 2)).tobytes(),
                                         after.crop(frame_box(after, new, 2)).tobytes())
                for side, tag in [(0, 'frame_'), (1, 'frame_mirror_')]:
                    seq = ET.fromstring(z.read(prefix + f'effect_{side}.seq'))
                    self.assertAlmostEqual(float(seq.findtext('duration')), 2)
                    slots = seq.findall('sequenceObject')[1:]
                    self.assertEqual(len(slots), 24)
                    for obj, index in zip(slots, layout['frame_models']):
                        resource = obj.findtext('resource')
                        self.assertTrue(resource.endswith(f'{tag}{index:03d}.model'))
                        self.assertIn('res/' + resource, names)
                self.assertEqual(len([n for n in names if n.startswith(prefix) and n.endswith('.model')]), 4)
            self.assertEqual(report['ae_effect']['fps'], 12)
            self.assertEqual(report['ae_effect']['geometry_frames'], 4)

    def test_old_atlas_with_custom_edges_stays_in_place(self):
        image = Image.new('RGBA', (32, 32))
        custom = (0, 0, .47, .47)
        distinct = (.53, .53, 1, 1)
        atlas, tiles, frames = ae_atlas.compact(image, [custom, distinct, custom])
        self.assertIs(atlas, image)
        self.assertEqual(tiles, [custom, distinct])
        self.assertEqual(frames, [0, 1, 0])

    def test_different_filter_gutters_prevent_deduplication(self):
        atlas = Image.new('RGBA', (32, 16))
        rects = ((2.5 / 32, 2.5 / 16, 5.5 / 32, 5.5 / 16),
                 (10.5 / 32, 2.5 / 16, 13.5 / 32, 5.5 / 16))
        atlas.putpixel((1, 2), (50, 80, 100, 120))
        _, tiles, frames = ae_atlas.compact(atlas, rects)
        self.assertEqual(len(tiles), 2)
        self.assertEqual(frames, [0, 1])
