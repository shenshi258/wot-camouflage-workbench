"""Marquee selection and model grouping for the light-face preview.

The preview is a pure orthographic sketch: three panes share one scale so a
rectangle dragged on screen maps back to light faces with a plain linear test.
Everything here is numpy only, so the geometry can be tested without a GUI.
"""

import numpy as np

# axis_a, axis_b, label — identical to the preview that has shipped since v1.3.
PANES = ((2, 1, '侧面 Z/Y'), (0, 1, '正面 X/Y'), (0, 2, '俯视 X/Z'))
MARGIN_X = 24
MARGIN_TOP = 45
MAX_POINTS_PER_FACE = 250
MIN_POINTS_PER_FACE = 6


def model_key(light):
    """Identify an attachment for whole-model editing and initial grouping.

    The exporter may split this group by per-face recipe into several native
    models and sequences. Unsupported faces may lack anchor fields.
    """
    return (light.get('visual'), light.get('anchor'), light.get('anchor_kind'), light.get('texture'))


def clouds(lights):
    return [np.asarray(light['_preview'], dtype=float) for light in lights]


def bounds(lights):
    points = np.concatenate(clouds(lights))
    return points.min(0), points.max(0)


def face_sample_limit(face_count):
    """How many preview points to draw per face so hundreds of faces stay usable."""
    return int(max(MIN_POINTS_PER_FACE, min(MAX_POINTS_PER_FACE, 6000 // max(int(face_count), 1))))


class View:
    """Maps model space to canvas pixels for the three preview panes."""

    def __init__(self, lights, width, height, zoom=1.0, pan=None):
        points = np.concatenate(clouds(lights))
        self.low = points.min(0)
        self.high = points.max(0)
        self.center = (self.low + self.high) / 2
        self.width = float(max(width, 1))
        self.height = float(max(height, 1))
        self.zoom=float(np.clip(zoom,.25,20))
        self.pan=np.zeros((len(PANES),2)) if pan is None else np.asarray(pan,dtype=float).copy()
        self.panes = []
        for index, (axis_a, axis_b, label) in enumerate(PANES):
            pane_width = self.width / len(PANES)
            span_a = max(self.high[axis_a] - self.low[axis_a], .01)
            span_b = max(self.high[axis_b] - self.low[axis_b], .01)
            scale = max(min((pane_width - MARGIN_X) / span_a, (self.height - MARGIN_TOP) / span_b), 1e-9)
            self.panes.append(dict(index=index, axes=(axis_a, axis_b), label=label,
                                   width=pane_width, left=index * pane_width, scale=scale))

    def screen(self, points, pane):
        points = np.asarray(points, dtype=float)
        axis_a, axis_b = pane['axes']
        dx,dy=self.pan[pane['index']]
        x = pane['left'] + pane['width'] / 2 + (points[:, axis_a] - self.center[axis_a]) * pane['scale']*self.zoom+dx
        y = (self.height + 25) / 2 - (points[:, axis_b] - self.center[axis_b]) * pane['scale']*self.zoom+dy
        return np.c_[x, y]

    def visible(self,screen,pane):
        return ((screen[:,0]>=pane['left']+2)&(screen[:,0]<=pane['left']+pane['width']-2)
                &(screen[:,1]>=32)&(screen[:,1]<=self.height-2))

    def zoom_by(self,factor,x=None,y=None):
        if not np.isfinite(factor) or factor<=0:raise ValueError('缩放倍率必须是有限正数')
        old=self.zoom;self.zoom=float(np.clip(old*factor,.25,20));ratio=self.zoom/old
        if x is None:
            self.pan*=ratio
        else:
            pane=self.pane_at(x);index=pane['index']
            origin=np.array([pane['left']+pane['width']/2,(self.height+25)/2])
            pointer=np.array([x,y])
            self.pan[index]=pointer-origin-(pointer-origin-self.pan[index])*ratio
        return self.zoom

    def pane_at(self, x):
        index = int(min(max(x // (self.width / len(PANES)), 0), len(PANES) - 1))
        return self.panes[index]

    def hit(self, lights, rect, limit=MAX_POINTS_PER_FACE):
        """Return the ids of faces with at least one preview point inside rect."""
        x0, y0, x1, y1 = normalize_rect(rect)
        hits = []
        for light in lights:
            points = np.asarray(light['_preview'], dtype=float)
            step = max(1, len(points) // max(int(limit), 1))
            points = points[::step]
            for pane in self.panes:
                if pane['left'] > x1 or pane['left'] + pane['width'] < x0:
                    continue
                screen = self.screen(points, pane)
                inside = self.visible(screen,pane)&(screen[:, 0] >= x0) & (screen[:, 0] <= x1) & (screen[:, 1] >= y0) & (screen[:, 1] <= y1)
                if inside.any():
                    hits.append(light['id'])
                    break
        return hits

    def nearest(self, lights, x, y, limit=MAX_POINTS_PER_FACE, tolerance=12.0):
        """Pick the face whose preview point is closest to a click."""
        best = None; best_distance = tolerance ** 2
        if not 0<=x<self.width or not 32<=y<=self.height-2:return None
        pane=self.pane_at(x)
        for light in lights:
            points = np.asarray(light['_preview'], dtype=float)
            step = max(1, len(points) // max(int(limit), 1))
            points = points[::step]
            screen = self.screen(points, pane)
            screen=screen[self.visible(screen,pane)]
            if not len(screen):continue
            distance = np.square(screen[:, 0] - x) + np.square(screen[:, 1] - y)
            index = int(np.argmin(distance))
            if distance[index] < best_distance:
                best_distance = float(distance[index]); best = light['id']
        return best


def normalize_rect(rect):
    x0, y0, x1, y1 = (float(value) for value in rect)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def rect_too_small(rect, minimum=3.0):
    x0, y0, x1, y1 = normalize_rect(rect)
    return (x1 - x0) < minimum and (y1 - y0) < minimum


def expand_to_models(lights, picked):
    """Grow a face selection to every face of the models it touches."""
    keys = {model_key(light) for light in lights if light['id'] in picked}
    return {light['id'] for light in lights if model_key(light) in keys}


def model_count(lights, picked):
    return len({model_key(light) for light in lights if light['id'] in picked})


def merge(current, incoming, mode='replace'):
    """Combine the marquee hit set with the existing pick using the drag modifier."""
    current = set(current)
    incoming = set(incoming)
    if mode == 'add':
        return current | incoming
    if mode == 'subtract':
        return current - incoming
    if mode == 'toggle':
        return current ^ incoming
    return incoming


def drag_mode(shift=False, control=False):
    if control:
        return 'subtract'
    if shift:
        return 'add'
    return 'replace'
