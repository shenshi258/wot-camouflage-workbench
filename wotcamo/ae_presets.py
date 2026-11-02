"""Portable AE assets and settings, independent of a vehicle or its selected faces."""
import copy
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

from PIL import Image
from . import ae_effects as ae
from .common import ROOT, atomic_write

LIBRARY_PATH = ROOT / '预设/AE特效'
SUFFIX = '.aepreset'
# Vehicle-specific placement and selection belong to the open project, never a preset.
BASE_SETTINGS = ('fps', 'width', 'brightness', 'plane', 'angle', 'blend',
            'lift', 'uv_scale', 'u_offset', 'v_offset')
SETTINGS = BASE_SETTINGS + ('uv_scale_x','uv_scale_y','crop_left','crop_right','crop_top','crop_bottom','tint_color','tint_strength') + ae.WARPS
CLIP_KEYS = ('schema', 'atlas_sha256', 'size', 'frame_size', 'packed_frame_size',
             'rects', 'frames', 'alpha')
MAX_ARCHIVE = ae.MAX_BYTES + 256 * 1024


def _metadata(data):
    if not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1:
        raise ValueError('AE 预设版本不支持。')
    name = data.get('name')
    description = data.get('description', '')
    if not isinstance(name, str) or not name.strip() or len(name) > 60 or any(ord(x) < 32 for x in name):
        raise ValueError('预设名称请填写 1～60 个可显示字符。')
    if not isinstance(description, str) or len(description) > 1000:
        raise ValueError('预设说明不能超过 1000 字。')
    values = data.get('config')
    # Earlier 3.0 presets predate independent axes and crop margins. They use
    # the neutral defaults, so adding these controls never breaks saved assets.
    if not isinstance(values, dict) or not set(BASE_SETTINGS)<=set(values)<=set(SETTINGS):
        raise ValueError('预设参数不完整，或包含车辆专用参数。')
    config = ae.config(values)
    clip = data.get('clip')
    if not isinstance(clip, dict) or set(clip) != set(CLIP_KEYS):
        raise ValueError('预设素材清单无效。')
    if type(clip['schema']) is not int or clip['schema'] != 1 or type(clip['frames']) is not int or not 1 <= clip['frames'] <= ae.MAX_FRAMES:
        raise ValueError('预设帧数无效。')
    for key in ('size', 'frame_size', 'packed_frame_size'):
        size = clip[key]
        if not isinstance(size, list) or len(size) != 2 or not all(type(x) is int and 1 <= x <= 4096 for x in size):
            raise ValueError('预设图像尺寸无效。')
    rects = clip['rects']
    if not isinstance(rects, list) or len(rects) != clip['frames']:
        raise ValueError('预设帧范围不完整。')
    for rect in rects:
        if not isinstance(rect, list) or len(rect) != 4 or not all(type(x) in (int, float) and math.isfinite(x) for x in rect):
            raise ValueError('预设帧范围无效。')
        if not 0 <= rect[0] < rect[2] <= 1 or not 0 <= rect[1] < rect[3] <= 1:
            raise ValueError('预设帧超出图集。')
    digest = clip['atlas_sha256']
    if not isinstance(digest, str) or len(digest) != 64 or any(x not in '0123456789abcdef' for x in digest):
        raise ValueError('预设素材哈希无效。')
    if clip['alpha'] != 'straight':
        raise ValueError('预设须使用直通透明图集。')
    return dict(schema=1, name=name.strip(), description=description,
                config={k: config[k] for k in SETTINGS}, clip=copy.deepcopy(clip))


def read(path, *, with_atlas=True):
    """Read bounded, fixed-name ZIP entries; no scripts or vehicle packages are accepted."""
    path = Path(path)
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('AE 预设文件过大。')
    try:
        with zipfile.ZipFile(path) as z:
            if len(z.infolist()) != 2 or set(z.namelist()) != {'preset.json', 'atlas.png'}:
                raise ValueError('AE 预设只能包含 preset.json 和 atlas.png。')
            if z.getinfo('preset.json').file_size > 128 * 1024 or z.getinfo('atlas.png').file_size > ae.MAX_BYTES:
                raise ValueError('AE 预设内容大小超限。')
            data = _metadata(json.loads(z.read('preset.json')))
            if not with_atlas:
                return data
            atlas = z.read('atlas.png')
        if hashlib.sha256(atlas).hexdigest() != data['clip']['atlas_sha256']:
            raise ValueError('预设图集哈希不匹配，文件可能已损坏。')
        with Image.open(io.BytesIO(atlas)) as image:
            if image.format != 'PNG' or image.mode != 'RGBA' or list(image.size) != data['clip']['size']:
                raise ValueError('预设图集格式或尺寸不匹配。')
            image.load()
        return data, atlas
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeError, KeyError, TypeError, RuntimeError, OverflowError) as error:
        raise ValueError('无法读取 AE 预设：' + str(error)) from error


def encode(name, description, clip, values):
    ae.validate_clip(clip)
    config = ae.config(values)
    data = _metadata(dict(schema=1, name=name, description=description,
                          config={k: config[k] for k in SETTINGS},
                          clip={k: clip[k] for k in CLIP_KEYS}))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('preset.json', json.dumps(data, ensure_ascii=False))
        z.write(clip['atlas'], 'atlas.png')
    return data, output.getvalue()


def library_file(name, directory=None):
    # Names never become paths. Case variants refer to the same library slot.
    key = hashlib.sha256(name.strip().casefold().encode('utf-8')).hexdigest()[:24]
    return Path(directory if directory is not None else LIBRARY_PATH) / (key + SUFFIX)


def store(data, payload, directory=None):
    target = library_file(data['name'], directory)
    if target.exists():
        atomic_write(target.with_suffix(SUFFIX + '.bak'), target.read_bytes())
    atomic_write(target, payload)
    return target


def scan(directory=None):
    records, issues = [], []
    for path in sorted(Path(directory if directory is not None else LIBRARY_PATH).glob('*' + SUFFIX)):
        try:
            data = read(path, with_atlas=False)
            records.append(dict(data, path=path))
        except (ValueError, OSError) as error:
            issues.append((path, str(error)))
    return sorted(records, key=lambda item: item['name'].casefold()), issues


def summary(record):
    """A bounded, two-line caption keeps long notes out of the main layout."""
    clip=record['clip'];c=record['config']
    blend='发光叠加' if c['blend']=='add' else '普通透明'
    detail='%d 帧 · %g FPS · %g 秒 · %d×%d · %s'%(clip['frames'],c['fps'],clip['frames']/c['fps'],*clip['frame_size'],blend)
    description=str(record.get('description') or '').strip()
    first=description.splitlines()[0][:72] if description else '可在“管理 / 导入…”查看预设说明。'
    return detail+'\n'+first+' 套用保留当前位置与选区。'


def description_text(record):
    """Portable notes are stored in the preset itself, not in vehicle settings."""
    if not record:return '选择左侧预设，查看用途、摆放和配色建议；可导出为独立 .aepreset。'
    c=record['config'];clip=record['clip']
    heading='%s\n%d 帧 / %g FPS / %g 秒；素材 %d×%d；基准宽度 %g 米。'%(record['name'],clip['frames'],c['fps'],clip['frames']/c['fps'],*clip['frame_size'],c['width'])
    body=str(record.get('description') or '').strip() or '这个自定义预设没有填写说明。可先套用，再调节颜色、长宽和位置。'
    return heading+'\n\n'+body


def load(path, folder):
    data, atlas = read(path)
    # A content-addressed cache prevents loading one preset from mutating another.
    target = Path(folder) / (data['clip']['atlas_sha256'] + '.png')
    atomic_write(target, atlas)
    clip = dict(data['clip'], atlas=str(target.resolve()))
    ae.validate_clip(clip)
    return data, clip


def poster(path, size=(280, 180)):
    """Show an actual middle frame with the preset's additive/alpha blend."""
    data, atlas = read(path)
    with Image.open(io.BytesIO(atlas)) as original:
        image=ae.colorize_rgba(original,data['config'])
        rect = data['clip']['rects'][data['clip']['frames']//2]
        crop = (math.floor(rect[0]*image.width), math.floor(rect[1]*image.height),
                math.ceil(rect[2]*image.width), math.ceil(rect[3]*image.height))
        frame = image.crop(crop).convert('RGBA')
    import numpy as np
    frame.thumbnail(size, Image.Resampling.LANCZOS)
    rgba = np.asarray(frame, dtype=float)/255
    rgb = rgba[:,:,:3]*data['config']['brightness']*rgba[:,:,3:]
    background = np.array([20,25,35])/255
    rgb += background if data['config']['blend']=='add' else background*(1-rgba[:,:,3:])
    return Image.fromarray(np.uint8(np.clip(rgb,0,1)*255),'RGB')


def apply_settings(current, saved):
    current = ae.config(current)
    values={key:saved[key] for key in SETTINGS}
    # Surface mapping follows the chosen armor, while plane orientation is
    # an authored effect setting. A side-oriented preset must not flatten a
    # selected front/top surface or replace its explicit mapping direction.
    if current['placement']!='plane':values.pop('plane')
    return ae.config(dict(current, **values))
