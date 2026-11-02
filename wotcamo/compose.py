from pathlib import Path
import hashlib
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def scan_materials(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"素材文件夹不存在：{folder}")
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"))


def seed_for(name, seed):
    # Shared normalized layout between standard and HD counterparts.
    name = name.replace("_hd.dds", ".dds")
    return (int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) + seed) % 2**32


def field(w, h, rng, n=12):
    small = Image.fromarray(rng.integers(0, 256, (n, n), dtype=np.uint8))
    return np.asarray(small.resize((w, h), Image.Resampling.BICUBIC), dtype=np.float32) / 255


def rgb(code):
    return np.array([int(code[i:i+2], 16) for i in (1, 3, 5)], dtype=np.float32)


def auto_position(ao, w, h, count):
    if ao is None:
        return (.5, .5)
    a = np.asarray(ao.convert("RGB").resize((128, 128)), dtype=np.float32).mean(axis=2)
    candidates = []
    for y in range(16, 113, 16):
        for x in range(16, 113, 16):
            score = float(np.mean(a[y-12:y+12, x-12:x+12] > 24))
            candidates.append((score, -abs(x-64)-abs(y-64), x, y))
    candidates.sort(reverse=True)
    _, _, x, y = candidates[(count * 5) % len(candidates)]
    return x / 128, y / 128


def compose_am(original, ao, recipe, material_dir, name):
    arr = np.asarray(original.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    rng = np.random.default_rng(seed_for(name, recipe.seed))
    noise = field(w, h, rng)
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    if recipe.pattern == "tiger":
        wave = np.sin((x*.8 + y*.55 + (noise-.5)*.32 + (field(w, h, rng, 6)-.5)*.4) * recipe.pattern_scale * math.tau)
        mask = np.clip((wave-.35)*5, 0, 1)
    elif recipe.pattern == "spots":
        mask = np.clip((field(w, h, rng, 28)-.59)*12, 0, 1)
    else:
        mask = np.zeros((h, w), dtype=np.float32)
    color = rgb(recipe.base_color)[None, None, :] * (1-mask[..., None]) + rgb(recipe.accent_color)[None, None, :] * mask[..., None]
    lum = np.asarray(original.convert("L"), dtype=np.float32) / 255
    shade = .68 + lum*.42
    result = color * shade[..., None]
    if recipe.wear:
        wear_mask = np.clip((noise-.38)*1.5, 0, 1) * recipe.wear
        result = result*(1-wear_mask[..., None]) + np.array([57, 50, 42], dtype=np.float32)*wear_mask[..., None]
    arr[..., :3] = np.clip(result, 0, 255).astype(np.uint8)
    image = Image.fromarray(arr)
    decal_mask = Image.new("L", (w, h))
    root = Path(material_dir).resolve()
    for i, filename in enumerate(recipe.decals):
        if Path(filename).name != filename or not (root / filename).resolve().is_relative_to(root):
            raise ValueError("贴花文件名必须位于素材目录内")
        with Image.open(root / filename) as source:
            decal = source.convert("RGBA")
        placements = [p for p in recipe.decal_placements if p.get("file") == filename and (not p.get("texture") or p["texture"] in name)]
        if not placements:
            if any(p.get("file") == filename and p.get("texture") for p in recipe.decal_placements):
                continue
            px, py = auto_position(ao, w, h, i)
            placements = [{"x": px, "y": py, "scale": .16}]
        for p in placements:
            size = max(1, int(min(w, h)*p.get("scale", .16)))
            d = decal.copy()
            d.thumbnail((size, size), Image.Resampling.LANCZOS)
            if p.get("rotation"):
                d = d.rotate(float(p["rotation"]), expand=True, resample=Image.Resampling.BICUBIC)
            pos = (int(p.get("x", .5)*w-d.width/2), int(p.get("y", .5)*h-d.height/2))
            image.alpha_composite(d, dest=pos)
            decal_mask.paste(d.getchannel("A"), pos, d.getchannel("A"))
    image.putalpha(original.convert("RGBA").getchannel("A"))
    return image, decal_mask


def derive(original, kind, fourcc, recipe, mask=None):
    a = np.asarray(original.convert("RGBA")).copy()
    if kind == "AO":
        if recipe.ao_clean:
            a[..., 1:3] = 255
        if recipe.block_official_camo and fourcc in ('DXT3','DXT5','BC7','RGBA8','BGRA8'):
            a[..., 3] = 0
    elif kind == "GMM":
        if recipe.gmm_specular is not None:
            a[..., 0] = recipe.gmm_specular
        if recipe.gmm_brightness is not None:
            a[..., 1] = recipe.gmm_brightness
        if recipe.block_official_camo:
            a[..., 2] = 0
        if recipe.emissive and mask is not None:
            m = np.asarray(mask.resize(original.size)) > 127
            a[m, 1] = 200
    elif kind == "ANM" and recipe.normal_strength is not None:
        a[..., 1] = np.clip(128 + (a[..., 1].astype(np.float32)-128)*recipe.normal_strength, 0, 255)
        a[..., 3] = a[..., 0]
    return Image.fromarray(a)


def demo_materials(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    font_path = Path("C:/Windows/Fonts/arialbd.ttf")
    font = ImageFont.truetype(str(font_path), 156) if font_path.exists() else ImageFont.load_default()
    number = Image.new("RGBA", (256, 256))
    d = ImageDraw.Draw(number)
    d.rounded_rectangle((12, 12, 244, 244), radius=30, fill=(30, 38, 44, 220), outline="white", width=7)
    d.text((128, 128), "07", font=font, fill="white", anchor="mm")
    number.save(folder / "number_07.png")
    badge = Image.new("RGBA", (256, 256))
    d = ImageDraw.Draw(badge)
    for i in range(5):
        t = i*math.tau/5
        cx, cy = 128+42*math.cos(t), 118+42*math.sin(t)
        d.ellipse((cx-42, cy-42, cx+42, cy+42), fill="#d67b9b", outline="#f9e4b8", width=4)
    d.ellipse((100, 92, 156, 148), fill="#f0c15d")
    badge.save(folder / "badge_rose.png")
