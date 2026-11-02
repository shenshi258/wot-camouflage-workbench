"""Shared light recipe validation and native colour key generation."""

import json, math, hashlib, colorsys
from fractions import Fraction

import xml.etree.ElementTree as ET

MODES = ('无级变色', '流水呼吸', '流水渐变', '百花齐放', '动态呼吸', '波浪', '跑马灯')
COLOR_ONLY_MODES = ('流水渐变', '无级变色')
# WOT bind-space axes: +X vehicle right, +Y up, +Z front. Diagonals
# are normalized, so one metre has the same delay in every direction.
FLOW_VECTORS={'向上':(0.,1.,0.),'向下':(0.,-1.,0.),'向左':(-1.,0.,0.),'向右':(1.,0.,0.),
              '偏左上':(-2**-.5,2**-.5,0.),'偏右上':(2**-.5,2**-.5,0.),
              '偏左下':(-2**-.5,-2**-.5,0.),'偏右下':(2**-.5,-2**-.5,0.)}
DIRECTIONS = ('向车头', '向车尾', '同步', '四周扩散',*FLOW_VECTORS)

def has_dimming(config):
    return config['mode'] not in COLOR_ONLY_MODES and config.get('dimming', True)

def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + ' 必须是数字')
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError('%s 必须在 %s～%s 之间' % (name, low, high))
    return float(value)

def read_config(path):
    return validate_config(json.loads(path.read_text(encoding='utf-8-sig')))

def validate_config(config):
    required = {'颜色', '每色秒数', '呼吸周期秒数', '峰值倍率', '暗相系数', '流水方向', '每米延迟秒数'}
    optional = {'效果模式', '亮灯比例', '换色曲线', '启用明暗变化'}
    if not isinstance(config, dict) or not required <= set(config) or set(config) - required - optional:
        raise ValueError('配置字段应为：' + '、'.join(sorted(required)))
    colors = config['颜色']
    if not isinstance(colors, list) or not 1 <= len(colors) <= 12:
        raise ValueError('颜色列表需要 1～12 种颜色；仅一种颜色时就是单色呼吸')
    palette = []
    for i, color in enumerate(colors):
        if not isinstance(color, dict) or set(color) != {'名称', 'RGB'} or not isinstance(color['名称'], str):
            raise ValueError('每种颜色应包含 名称 和 RGB')
        rgb = color['RGB']
        if isinstance(rgb, str) and len(rgb) == 7 and rgb.startswith('#'):
            try:
                rgb = [int(rgb[k:k + 2], 16) / 255 for k in (1, 3, 5)]
            except ValueError:
                raise ValueError('RGB 十六进制格式应为 #RRGGBB')
        if not isinstance(rgb, list) or len(rgb) != 3:
            raise ValueError('RGB 应为三个 0～1 的数，或 "#RRGGBB"')
        palette.append([number(x, '颜色 %d 的 RGB' % (i + 1), 0, 1) for x in rgb])
    step = number(config['每色秒数'], '每色秒数', .2, 120)
    breath = number(config['呼吸周期秒数'], '呼吸周期秒数', .2, 120)
    peak = number(config['峰值倍率'], '峰值倍率', .01, 10)
    low = number(config['暗相系数'], '暗相系数', 0, 1)
    delay = number(config['每米延迟秒数'], '每米延迟秒数', 0, 10)
    direction = config['流水方向']
    if direction not in DIRECTIONS:
        raise ValueError('流水方向只支持：' + '、'.join(DIRECTIONS))
    mode = config.get('效果模式', '流水呼吸')
    if mode not in MODES:
        raise ValueError('不支持的效果模式')
    dimming = config.get('启用明暗变化', mode not in COLOR_ONLY_MODES)
    if not isinstance(dimming, bool):
        raise ValueError('启用明暗变化 必须是 true 或 false')
    dimming = dimming and mode not in COLOR_ONLY_MODES
    duty = number(config.get('亮灯比例', .3), '亮灯比例', .05, 1)
    curve = config.get('换色曲线', '柔和')
    if curve not in ('柔和', '匀速'):
        raise ValueError('换色曲线只支持柔和或匀速')
    if curve=='匀速':
        # Repeated adjacent colours would otherwise insert a full stationary
        # interval, including when the final colour repeats the first.
        unique=[]
        for color in palette:
            if not unique or color!=unique[-1]:unique.append(color)
        if len(unique)>1 and unique[-1]==unique[0]:unique.pop()
        palette=unique
    palette_period = step * len(palette)
    period = palette_period
    if dimming and mode != '流水呼吸':
        if abs(step-round(step,3))>1e-9 or abs(breath-round(breath,3))>1e-9:
            raise ValueError('新呼吸模式的时间最多支持 3 位小数，以保证循环首尾准确衔接。')
        a = Fraction(str(palette_period)).limit_denominator(1000)
        b = Fraction(str(breath)).limit_denominator(1000)
        period = float(Fraction(math.lcm(a.numerator, b.numerator), math.gcd(a.denominator, b.denominator)))
        if period > 360:
            raise ValueError('颜色与呼吸的共同循环超过 360 秒，请把两个时间改成简单倍数，例如每色 2 秒、呼吸 2 或 4 秒。')
    return dict(raw=config, palette=[[x * peak for x in c] for c in palette],
                step=step, period=period, palette_period=palette_period, breath=breath, peak=peak,
                low=low, delay=delay, direction=direction, mode=mode, duty=duty, curve=curve, dimming=dimming)

def hue_color(a, b, weight):
    """Shortest hue path with interpolated saturation/value; no RGB grey dip.

    Equal-value colour stops retain that value. Deliberately dark/black stops
    keep their intended value; this is not a promise of equal perceived light.
    """
    ha, sa, va = colorsys.rgb_to_hsv(*a)
    hb, sb, vb = colorsys.rgb_to_hsv(*b)
    if sa < 1e-12: ha = hb
    if sb < 1e-12: hb = ha
    delta = (hb - ha + .5) % 1 - .5
    return list(colorsys.hsv_to_rgb((ha + delta * weight) % 1,
                                   sa + (sb-sa)*weight, va + (vb-va)*weight))

def color_at(time, offset, config):
    """Sample the cyclic palette; the legacy eased curve remains the default."""
    u = ((time + offset) % config.get('palette_period', config['period'])) / config['step']
    i = min(int(u), len(config['palette']) - 1)
    w = u - i
    a, b = config['palette'][i], config['palette'][(i + 1) % len(config['palette'])]
    # The last segment interpolates back to the first colour without a hold.
    linear = config.get('curve', '柔和') == '匀速'
    eased = w if linear else w * w * (3 - 2 * w)
    if config.get('mode') == '无级变色':
        color = hue_color(a, b, eased)
        lo, hi = max(0., w-1e-6), min(1., w+1e-6)
        ease = (lambda x:x) if linear else (lambda x:x*x*(3-2*x))
        before, after = hue_color(a,b,ease(lo)), hue_color(a,b,ease(hi))
        return color + [1.], [(y-x)/((hi-lo)*config['step']) for x,y in zip(before,after)] + [0.]
    color = [x * (1 - eased) + y * eased for x, y in zip(a, b)] + [1.]
    tangent = [(y - x) * (1 if linear else 6 * w * (1 - w)) / config['step'] for x, y in zip(a, b)] + [0.]
    return color, tangent

def colour_track(identifier, offset, config):
    track = ET.Element('track')
    for key, value in [('name', 'material property color'), ('type', 'vector4'),
                       ('identifier', identifier), ('property', 'g_tint')]:
        ET.SubElement(track, key).text = value
    period = config['period']
    if config['mode'] == '无级变色':
        return linear_animated_track(track,offset,config)
    if config.get('curve') == '匀速' and config.get('mode') not in ('流水呼吸','流水渐变'):
        return linear_animated_track(track,offset,config)
    if config.get('mode', '流水呼吸') != '流水呼吸' and not (config.get('curve')=='匀速' and config.get('mode')=='流水渐变'):
        density = max(48, math.ceil(8 / config['duty'])) if config['mode']=='跑马灯' else 48
        interval = min(config['step'],config['breath']) if has_dimming(config) else config['step']
        count = max(48, math.ceil(period / interval * density))
        if count > 12000:
            raise ValueError('此配方关键帧过多，请缩短共同循环或调整时间比例。')
        times = [period * i / count for i in range(count + 1)]
        delta = interval * 1e-5
        colors = [animated_value(t,offset,config) for t in times];tangents=[]
        # Explicitly close the value loop; modulo arithmetic can differ by a
        # few floating-point units at the mathematically identical endpoint.
        colors[-1]=colors[0][:]
        for t in times:
            before = animated_value(t - delta, offset, config)
            after = animated_value(t + delta, offset, config)
            tangents.append([(b - a) / (2 * delta) for a, b in zip(before, after)])
        # Monotone Hermite limiting prevents negative or overbright interpolation.
        for i in range(len(times)-1):
            for channel in range(3):
                slope=(colors[i+1][channel]-colors[i][channel])/(times[i+1]-times[i])
                if abs(slope)<1e-12:
                    tangents[i][channel]=tangents[i+1][channel]=0.;continue
                for j in (i,i+1):
                    if tangents[j][channel]/slope<0:tangents[j][channel]=0.
                a,b=tangents[i][channel]/slope,tangents[i+1][channel]/slope
                if a*a+b*b>9:
                    scale=3/math.hypot(a,b)
                    tangents[i][channel]*=scale;tangents[i+1][channel]*=scale
        for channel in range(3):
            a,b=tangents[0][channel],tangents[-1][channel]
            tangent=math.copysign(min(abs(a),abs(b)),a) if a*b>0 else 0.
            tangents[0][channel]=tangents[-1][channel]=tangent
        for t,color,tangent in zip(times,colors,tangents):append_frame(track,t,color,tangent)
        return track
    times = [0., period]
    for i in range(len(config['palette'])):
        t = (i * config['step'] - offset) % period
        if 1e-8 < t < period - 1e-8:
            times.append(t)
    for t in sorted(set(times)):
        color, tangent = color_at(t, offset, config)
        incoming = color_at(t - config['step'] * 1e-7, offset, config)[1] if config.get('curve') == '匀速' else tangent
        append_frame(track, t, color, tangent, incoming)
    frames=track.findall('frame')
    for key in ('value','inTangent','outTangent'):
        frames[-1].find(key).text=frames[0].find(key).text
    return track


def linear_animated_track(track, offset, config):
    """Retain separate incoming/outgoing slopes at each colour corner."""
    period=config['period'];step=config['step'];breath=config['breath']
    density=max(48,math.ceil(8/config['duty'])) if config['mode']=='跑马灯' else 48
    interval=min(step,breath) if has_dimming(config) else step
    count=max(48,math.ceil(period/interval*density))
    if count>12000:raise ValueError('此配方关键帧过多，请缩短共同循环或调整时间比例。')
    times={period*i/count for i in range(count+1)}
    palette_period=config['palette_period']
    for cycle in range(math.ceil(period/palette_period)+1):
        for i in range(len(config['palette'])):
            t=cycle*palette_period+i*step-(offset%palette_period)
            if 1e-8<t<period-1e-8:times.add(t)
    if config['mode']=='无级变色':
        # Place keys exactly at HSV sector boundaries, where the maximum RGB
        # channel changes. Interpolating across an unsampled corner can dim it.
        for i,a in enumerate(config['palette']):
            b=config['palette'][(i+1)%len(config['palette'])]
            ha,sa,_=colorsys.rgb_to_hsv(*a);hb,sb,_=colorsys.rgb_to_hsv(*b)
            if sa<1e-12:ha=hb
            if sb<1e-12:hb=ha
            delta=(hb-ha+.5)%1-.5
            if abs(delta)<1e-12:continue
            for sector in range(math.floor(min(ha,ha+delta)*6), math.ceil(max(ha,ha+delta)*6)+1):
                weight=(sector/6-ha)/delta
                if not 0<weight<1:continue
                if config.get('curve')!='匀速':
                    low,high=0.,1.
                    for _ in range(48):
                        mid=(low+high)/2
                        if mid*mid*(3-2*mid)<weight:low=mid
                        else:high=mid
                    weight=(low+high)/2
                t=((i+weight)*step-offset)%palette_period
                if 1e-8<t<period-1e-8:times.add(t)
    ordered=sorted(times);times=[]
    for t in ordered:
        if not times or t-times[-1]>1e-9:
            times.append(t)
    times[0]=0.;times[-1]=period
    if len(times)>12000:raise ValueError('此配方关键帧过多，请缩短共同循环或调整时间比例。')
    delta=interval*1e-6
    colors=[animated_value(t,offset,config) for t in times]
    incoming=[];outgoing=[]
    for t,color in zip(times,colors):
        before=animated_value(t-delta,offset,config);after=animated_value(t+delta,offset,config)
        incoming.append([(a-b)/delta for a,b in zip(color,before)])
        outgoing.append([(a-b)/delta for a,b in zip(after,color)])
    # Bound interpolation within each segment without joining the slopes of
    # adjacent colour segments, which would create a perceptible stop.
    for i in range(len(times)-1):
        for channel in range(3):
            slope=(colors[i+1][channel]-colors[i][channel])/(times[i+1]-times[i])
            if abs(slope)<1e-12:
                outgoing[i][channel]=incoming[i+1][channel]=0.;continue
            if outgoing[i][channel]/slope<0:outgoing[i][channel]=0.
            if incoming[i+1][channel]/slope<0:incoming[i+1][channel]=0.
            a=outgoing[i][channel]/slope;b=incoming[i+1][channel]/slope
            if a*a+b*b>9:
                scale=3/math.hypot(a,b)
                outgoing[i][channel]*=scale;incoming[i+1][channel]*=scale
    colors[-1]=colors[0][:]
    incoming[-1]=incoming[0][:];outgoing[-1]=outgoing[0][:]
    for t,color,inc,out in zip(times,colors,incoming,outgoing):append_frame(track,t,color,out,inc)
    return track


def append_frame(track, time, color, tangent, incoming=None):
    frame = ET.SubElement(track, 'frame')
    for key, value in [('startTime', format(time, '.12g')),
                       ('value', ' '.join(format(x, '.12g') for x in color)),
                       ('inTangent', ' '.join(format(x, '.12g') for x in (incoming if incoming is not None else tangent))),
                       ('outTangent', ' '.join(format(x, '.12g') for x in tangent)), ('tangentMode', '0')]:
        ET.SubElement(frame, key).text = value


def envelope_at(time, offset, config):
    """Brightness factor the sequence applies at this time; 1.0 means no dimming."""
    mode = config['mode']
    if not has_dimming(config):return 1.
    # Legacy Pulse uses a shared white phaseMap: only its colour keys receive
    # spatial offsets. Sequence-driven wave modes still offset their envelope.
    phase = (time + (0 if mode in ('动态呼吸','流水呼吸') else offset)) / config['breath']
    if mode == '流水渐变':
        envelope = 1.
    elif mode == '跑马灯':
        distance = abs((phase % 1) - .5)
        envelope = .5 * (1 + math.cos(2 * math.pi * distance / config['duty'])) if distance < config['duty'] / 2 else 0.
    else:
        envelope = .5 * (1 + math.cos(2 * math.pi * phase))
    return config['low'] + (1 - config['low']) * envelope


def animated_value(time, offset, config):
    color, _ = color_at(time, offset, config)
    brightness = envelope_at(time, offset, config)
    return [x * brightness for x in color[:3]] + [1.]


def brightness_bounds(config, offset=0.0, samples=96):
    """Recipe envelope bounds, not measured pixel or perceived brightness.

    流水呼吸 leaves dimming to the native Pulse shader, so the colour track only
    carries colour there and the bounds come from 暗相系数 plus the shader ramp.
    流水渐变 bakes a flat envelope, so its bounds are exactly 1.0.
    """
    if not has_dimming(config):return (1., 1.)
    if config['mode'] == '流水呼吸':
        return (config['low'], 1.)
    step = config['period'] / samples
    values = [envelope_at(step * i, offset, config) for i in range(samples + 1)]
    return (min(values), max(values))


def spatial_offset(point, center, config, identifier=''):
    direction = config['direction']
    if direction == '四周扩散':
        distance = math.hypot(point[0] - center[0], point[2] - center[2])
        offset = -distance * config['delay']
    elif direction in FLOW_VECTORS:
        offset=-sum(p*d for p,d in zip(point,FLOW_VECTORS[direction]))*config['delay']
    else:
        offset = {'向车头': -1, '向车尾': 1, '同步': 0}[direction] * point[2] * config['delay']
    if config['mode'] == '百花齐放':
        fraction = int(hashlib.sha256(identifier.encode()).hexdigest()[:12], 16) / (16 ** 12)
        offset += fraction * config['period']
    return offset % config['period']
