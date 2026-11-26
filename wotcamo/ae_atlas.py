"""Lossless packing of the RGBA tiles sampled by a finished AE effect."""
import hashlib

from PIL import Image


GUTTER = 2
MAX_SIDE = 4096


def _grid(count, width, height):
    """Find the smallest power-of-two grid, keeping the native DDS layout."""
    candidates = []
    for columns in range(1, count + 1):
        rows = (count + columns - 1) // columns
        atlas_width = 1 << (columns * width - 1).bit_length()
        atlas_height = 1 << (rows * height - 1).bit_length()
        if atlas_width <= MAX_SIDE and atlas_height <= MAX_SIDE:
            candidates.append((atlas_width * atlas_height, max(atlas_width, atlas_height),
                               atlas_width, atlas_height, columns))
    if not candidates:
        return None
    _, _, atlas_width, atlas_height, columns = min(candidates)
    return (atlas_width, atlas_height), columns


def _tile_box(rect, size):
    """Recover exact texel boundaries including the original filter gutter."""
    w, h = size
    edges = (rect[0] * w - .5, rect[1] * h - .5,
             rect[2] * w + .5, rect[3] * h + .5)
    integer = tuple(map(round, edges))
    if any(abs(a - b) > 1e-7 for a, b in zip(edges, integer)):
        return None
    x, y, right, bottom = integer
    if not (GUTTER <= x < right - 1 and GUTTER <= y < bottom - 1
            and right + GUTTER <= w and bottom + GUTTER <= h):
        return None
    return x - GUTTER, y - GUTTER, right + GUTTER, bottom + GUTTER


def compact(image, rects):
    """Return an atlas, its unique UV rectangles and a model index per slot.

    Match the full tile including its gutter, so a shared frame is identical
    under linear filtering. Keep custom/legacy UV regions untouched when they
    cannot be represented as whole, equally sized tiles.
    """
    rects = [tuple(rect) for rect in rects]
    boxes = [_tile_box(rect, image.size) for rect in rects]
    extents = {(r - x, b - y) for x, y, r, b in boxes} if all(boxes) else set()
    if len(extents) != 1:
        unique = list(dict.fromkeys(rects))
        indices = {rect: i for i, rect in enumerate(unique)}
        return image, unique, [indices[rect] for rect in rects]

    cell_width, cell_height = extents.pop()
    checked = {}
    by_digest = {}
    unique_boxes = []
    unique_rects = []
    slots = []
    for rect, box in zip(rects, boxes):
        if box not in checked:
            pixels = image.crop(box).tobytes()
            digest = hashlib.sha256(pixels).digest()
            matches = by_digest.setdefault(digest, [])
            index = next((i for i in matches if image.crop(unique_boxes[i]).tobytes() == pixels), None)
            if index is None:
                index = len(unique_boxes)
                unique_boxes.append(box)
                unique_rects.append(rect)
                matches.append(index)
            checked[box] = index
        slots.append(checked[box])

    grid = _grid(len(unique_boxes), cell_width, cell_height)
    if grid is None:
        return image, unique_rects, slots
    (width, height), columns = grid
    if width * height >= image.width * image.height:
        return image, unique_rects, slots

    result = Image.new('RGBA', (width, height))
    compact_rects = []
    for i, box in enumerate(unique_boxes):
        x = (i % columns) * cell_width
        y = (i // columns) * cell_height
        result.paste(image.crop(box), (x, y))
        compact_rects.append(((x + GUTTER + .5) / width, (y + GUTTER + .5) / height,
                              (x + cell_width - GUTTER - .5) / width,
                              (y + cell_height - GUTTER - .5) / height))
    return result, compact_rects, slots
