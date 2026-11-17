"""Time-keyed motion inside an RGBA element's canvas.

These nodes animate the image in its own two-dimensional canvas, not a vehicle
or a path through the three-dimensional scene. Baking uses the existing atlas
pipeline so the local preview and exported effect receive the same pixels.
"""
import bisect
import copy
import math
from pathlib import Path

from PIL import Image


DEFAULT = dict(duration=2.0, canvas_scale=1.0, nodes=[])
DEFAULT_NODE = dict(time=0.0, x=0.0, y=0.0, rotation=0.0, scale=1.0,
                    opacity=100.0, easing='linear')
POSE_FIELDS = ('x', 'y', 'rotation', 'scale', 'opacity')
EASINGS = ('linear', 'smooth', 'hold')
MAX_NODES = 64
MAX_FRAME_EDGE = 512


def _number(value, name, low=None, high=None):
    if isinstance(value, bool):
        raise ValueError('动画参数必须是数值：' + name)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('动画参数必须是数值：' + name)
    if not math.isfinite(number):
        raise ValueError('动画参数必须是有限数值：' + name)
    if low is not None and not low <= number <= high:
        raise ValueError('动画参数超出范围：' + name)
    return number


def normalize(value=None):
    """Return an independent validated configuration, ordered by node time.

    Missing pose fields use the neutral pose. Duplicate times are an error:
    silently dropping one would make the editor display a different animation.
    """
    if value is None:
        value = {}
    if not isinstance(value, dict) or not set(value) <= set(DEFAULT):
        raise ValueError('动画节点设置无效。')
    result = copy.deepcopy(DEFAULT)
    result.update(value)
    result['duration'] = _number(result['duration'], '时长', .1, 60.0)
    result['canvas_scale'] = _number(result['canvas_scale'], '画布留白', 1.0, 4.0)
    nodes = result['nodes']
    if not isinstance(nodes, list) or len(nodes) > MAX_NODES:
        raise ValueError('动画节点最多 64 个。')
    normalized = []
    limits = dict(time=(0.0, result['duration']), x=(-200.0, 200.0),
                  y=(-200.0, 200.0), rotation=(-3600.0, 3600.0),
                  scale=(.01, 10.0), opacity=(0.0, 100.0))
    for node in nodes:
        if not isinstance(node, dict) or 'time' not in node or not set(node) <= set(DEFAULT_NODE):
            raise ValueError('动画节点内容无效，请填写节点时间。')
        item = dict(DEFAULT_NODE)
        item.update(node)
        for key, (low, high) in limits.items():
            item[key] = _number(item[key], key, low, high)
        if item['easing'] not in EASINGS:
            raise ValueError('动画过渡方式请选择线性、平滑或保持。')
        normalized.append(item)
    normalized.sort(key=lambda node: node['time'])
    if any(a['time'] == b['time'] for a, b in zip(normalized, normalized[1:])):
        raise ValueError('同一时间只能有一个动画节点，请修改时间或更新已有节点。')
    result['nodes'] = normalized
    return result


def _sample(animation, time):
    nodes = animation['nodes']
    if not nodes:
        return {key: DEFAULT_NODE[key] for key in POSE_FIELDS}
    index = bisect.bisect_right([node['time'] for node in nodes], time)
    if index == 0:
        return {key: nodes[0][key] for key in POSE_FIELDS}
    if index == len(nodes):
        return {key: nodes[-1][key] for key in POSE_FIELDS}
    left, right = nodes[index - 1:index + 1]
    weight = (time - left['time']) / (right['time'] - left['time'])
    if left['easing'] == 'smooth':
        weight = weight * weight * (3.0 - 2.0 * weight)
    elif left['easing'] == 'hold':
        weight = 0.0
    return {key: left[key] + (right[key] - left[key]) * weight for key in POSE_FIELDS}


def sample(value, time):
    """Sample a pose in seconds, holding the nearest pose outside its nodes.

    The caller controls looping. Sampling at the last node returns that node;
    baking samples at 0, 1/FPS, ... before the quantized loop boundary.
    """
    return _sample(normalize(value), _number(time, '采样时间'))


def _canvas(frame, size, pose, fit):
    """Inverse affine sampling avoids allocating a huge rotated/scaled image.

    Positive x moves right and positive y moves up. Positive rotation is
    counterclockwise. Premultiplied resampling keeps transparent edges clean;
    the result is converted back to the straight alpha used by the atlas.
    """
    width, height = size
    scale = fit * pose['scale']
    angle = math.radians(pose['rotation'])
    cosine, sine = math.cos(angle) / scale, math.sin(angle) / scale
    centre_x = width * (.5 + pose['x'] / 100.0)
    centre_y = height * (.5 - pose['y'] / 100.0)
    matrix = (cosine, -sine,
              frame.width / 2.0 - cosine * centre_x + sine * centre_y,
              sine, cosine,
              frame.height / 2.0 - sine * centre_x - cosine * centre_y)
    # Preserve exact pixels for the common neutral, unpadded pose.
    if size == frame.size and matrix == (1.0, -0.0, 0.0, 0.0, 1.0, 0.0):
        rendered = frame.copy()
    else:
        rendered = frame.convert('RGBa').transform(
            size, Image.Transform.AFFINE, matrix,
            resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0)).convert('RGBA')
    if pose['opacity'] != 100.0:
        factor = pose['opacity'] / 100.0
        rendered.putalpha(rendered.getchannel('A').point([round(alpha * factor) for alpha in range(256)]))
    return rendered


def bake(clip, animation, fps, destination):
    """Bake image/GIF playback and node motion to a bounded RGBA atlas.

    The source clip is already sampled at ``fps`` by the existing importer.
    Its original frame order loops independently beneath the node motion. No
    source path is stored in animation metadata. With no nodes, the exact input
    clip is returned and its timing, pixels and aspect are left untouched.
    """
    animation = normalize(animation)
    fps = _number(fps, '帧率', 1.0, 60.0)
    if not animation['nodes']:
        return clip
    # Import here because ae_effects integrates this module into its own config.
    from . import ae_effects as ae

    ae.validate_clip(clip)
    target = Path(destination)
    if target.resolve() == Path(clip['atlas']).resolve() or (
            target.exists() and target.samefile(clip['atlas'])):
        raise ValueError('动画缓存不能覆盖原素材图集，请使用新的输出文件。')
    count = math.ceil(animation['duration'] * fps - 1e-9)
    if not 1 <= count <= ae.MAX_FRAMES:
        raise ValueError('动画需要 %d 帧，最多 128 帧；请缩短时长或降低帧率。' % count)
    with Image.open(clip['atlas']) as atlas:
        source = []
        for left, top, right, bottom in clip['rects']:
            bounds = (round(left * atlas.width - .5), round(top * atlas.height - .5),
                      round(right * atlas.width + .5), round(bottom * atlas.height + .5))
            frame = atlas.crop(bounds).convert('RGBA')
            if min(frame.size) < 1:
                raise ValueError('源素材的帧尺寸无效。')
            source.append(frame)
    if len({frame.size for frame in source}) != 1:
        raise ValueError('源动画各帧尺寸不一致，请重新导入。')
    source_size = source[0].size
    wanted = tuple(value * animation['canvas_scale'] for value in source_size)
    fit = min(1.0, MAX_FRAME_EDGE / max(wanted))
    size = tuple(max(1, round(value * fit)) for value in wanted)
    frames = [_canvas(source[index % len(source)], size,
                      _sample(animation, index / fps), fit) for index in range(count)]
    result = ae.pack_frames(frames, destination, allow_opaque=True)
    logical = [value * animation['canvas_scale'] for value in clip['frame_size']]
    logical_fit = min(1.0, 4096.0 / max(logical))
    result['frame_size'] = [max(1, round(value * logical_fit)) for value in logical]
    if 'import_info' in clip:
        result['import_info'] = copy.deepcopy(clip['import_info'])
    result['animation_info'] = dict(schema=1, duration=count / fps, fps=fps,
                                    nodes=len(animation['nodes']), source_frames=clip['frames'],
                                    source_atlas_sha256=clip['atlas_sha256'])
    return result
