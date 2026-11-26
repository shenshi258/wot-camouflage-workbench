"""Compare lossless AE output size using synthetic inputs, without running WoT."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_STORED

from PIL import Image, ImageDraw
from wotcamo import __version__, ae_effects as ae


def draw_frame(index):
    image = Image.new('RGBA', (480, 270))
    x = 20 + 7 * index
    draw = ImageDraw.Draw(image)
    draw.rectangle((max(0, x - 34), 110, x + 12, 121), fill=(123, 144, 221, 110))
    draw.ellipse((x, 93, x + 45, 138), fill=(31, 156, 253, 223))
    return image


def export_case(root, project, client, name, frames, preview_dir=None):
    clip = ae.pack_frames(frames, root / f'{name}.png')
    fps = 24
    with (patch.object(ae.engine, 'client_info', return_value={'kind': 'synthetic'}),
          patch.object(ae.engine, 'compile27', side_effect=lambda _, target, __: target.write_bytes(b'fixture')),
          patch.object(ae.engine, 'audit_package', return_value={'missing_dependencies': []})):
        package, _ = ae.build(project, clip, {'fps': fps}, client, root / name, name)
    with ZipFile(package) as z:
        assert z.testzip() is None and all(i.compress_type == ZIP_STORED for i in z.infolist())
        prefix = next(n for n in z.namelist() if n.endswith('/manifest.json')).removesuffix('manifest.json')
        manifest = json.loads(z.read(prefix + 'manifest.json'))
        layout = manifest.get('export_layout', {'rects': clip['rects'], 'frame_models': list(range(len(frames)))})
        sequence = ET.fromstring(z.read(prefix + 'effect_0.seq'))
        slots = sequence.findall('sequenceObject')[1:]
        assert len(slots) == len(frames)
        raw = z.read(prefix + 'atlas.dds')
        with Image.open(io.BytesIO(raw)) as atlas:
            w, h = atlas.size
            playback = hashlib.sha256()
            for frame, (index, slot, expected) in enumerate(zip(layout['frame_models'], slots, frames)):
                assert slot.findtext('resource').endswith(f'frame_{index:03d}.model')
                assert 'res/' + slot.findtext('resource') in z.namelist()
                u, v, r, b = layout['rects'][index]
                texture = atlas.crop((round(u*w-.5), round(v*h-.5), round(r*w+.5), round(b*h+.5)))
                assert texture.size == expected.size and texture.tobytes() == expected.tobytes()
                if preview_dir is not None:
                    texture.save(preview_dir / f'{name}-{frame:02d}.png')
                playback.update(texture.tobytes())
            return dict(bytes=package.stat().st_size, dds_bytes=len(raw), atlas_size=atlas.size,
                        frames=len(slots), frame_size=clip['packed_frame_size'], fps=fps,
                        seconds=float(sequence.findtext('duration')), pixel_sha256=playback.hexdigest(),
                        model_count=len({slot.findtext('resource') for slot in slots}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-dir', type=Path)
    options = parser.parse_args()
    if options.preview_dir is not None:
        options.preview_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ae_volume_') as folder:
        root = Path(folder)
        source = root / 'baseline.wotmod'
        with ZipFile(source, 'w') as z:
            z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/original.dds', b'synthetic fixture')
        project = ae.source_project(source, root / 'unused')
        project['baseline_user_confirmed'] = True  # Only satisfies the synthetic fixture's precondition.
        client = root / 'client'
        shaders = client / 'res/packages'
        shaders.mkdir(parents=True)
        shader = io.BytesIO()
        with ZipFile(shader, 'w') as z:
            z.writestr('effect', b"('SRCALPHA', 5) ('ONE', 2)")
        with ZipFile(shaders / 'shaders.pkg', 'w') as z:
            for branch in ('10', '11'):
                z.writestr(f'shaders/custom/emissive_playground.{branch}.dx11.fxo', shader.getvalue())
        frames = [draw_frame(i) for i in range(48)]
        print(json.dumps(dict(version=__version__,
            repeated=export_case(root, project, client, 'repeated', [frames[i // 4] for i in range(48)], options.preview_dir),
            unique=export_case(root, project, client, 'unique', frames, options.preview_dir),
            grid=export_case(root, project, client, 'grid', frames[:10]))))
