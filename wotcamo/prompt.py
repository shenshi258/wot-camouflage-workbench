"""Deterministic Chinese recipe parser; no cloud service or API key required."""
from dataclasses import dataclass, field, asdict
import re

COLORS = {"沙漠黄": "#c7a76b", "军绿": "#58613d", "橄榄绿": "#667044", "白色": "#e8e6df", "黑色": "#272b30", "粉色": "#e7a9c3", "蓝色": "#5682b5", "红色": "#b94843", "紫色": "#8963ad", "灰色": "#7a8087", "黄色": "#d9b84c"}


@dataclass
class Recipe:
    prompt: str = ""
    base_color: str = "#c7a76b"
    accent_color: str = "#e8e6df"
    pattern: str = "tiger"
    pattern_scale: float = 8.0
    wear: float = 0.18
    seed: int = 7
    parts: list = field(default_factory=lambda: ["all"])
    decals: list = field(default_factory=list)
    decal_placements: list = field(default_factory=list)
    ao_clean: bool = False
    block_official_camo: bool = False
    gmm_specular: int | None = None
    gmm_brightness: int | None = None
    normal_strength: float | None = None
    emissive: bool = False

    def to_dict(self):
        return asdict(self)

    def validate(self):
        if self.pattern not in ("solid", "tiger", "spots"):
            raise ValueError("pattern 只能为 solid/tiger/spots")
        if not 0 <= self.wear <= 1 or not 1 <= self.pattern_scale <= 64:
            raise ValueError("做旧须为 0~1，图案密度须为 1~64")
        for value in (self.base_color, self.accent_color):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError("颜色须使用 #RRGGBB")
        for v in (self.gmm_specular, self.gmm_brightness):
            if v is not None and not 0 <= v <= 255:
                raise ValueError("材质通道值须为 0~255")
        if self.normal_strength is not None and not 0 <= self.normal_strength <= 2:
            raise ValueError("normal_strength 须为 0~2")
        for p in self.decal_placements:
            if not 0 <= p.get("x", .5) <= 1 or not 0 <= p.get("y", .5) <= 1 or not .005 <= p.get("scale", .16) <= 1:
                raise ValueError("贴花 x/y 须为 0~1，scale 须为 0.005~1")
        return self


def parse(text, materials):
    r = Recipe(prompt=text)
    colors = re.findall(r"#[0-9a-fA-F]{6}|" + "|".join(COLORS), text)
    if colors:
        r.base_color = COLORS.get(colors[0], colors[0])
    if len(colors) > 1:
        r.accent_color = COLORS.get(colors[1], colors[1])
    r.pattern = "spots" if any(x in text for x in ("斑点", "豹纹")) else "tiger" if any(x in text for x in ("虎纹", "斑马")) else "solid"
    r.wear = .35 if "重度做旧" in text else .18 if "中度做旧" in text else .07 if "轻度做旧" in text else 0
    r.ao_clean = "洗车" in text
    r.block_official_camo = "屏蔽官方涂装" in text
    r.emissive = "发光" in text
    for word, values in {"哑光": (130, 40), "高光": (200, 110), "金属": (160, 200)}.items():
        if word in text:
            r.gmm_specular, r.gmm_brightness = values
    if "凹凸减弱" in text:
        r.normal_strength = .5
    if "凹凸增强" in text:
        r.normal_strength = 1.5
    parts = {"车体": "hull", "炮塔": "turret", "炮管": "gun", "底盘": "chassis"}
    r.parts = [v for k, v in parts.items() if k in text] or ["all"]
    if materials:
        r.decals = [p.name for p in materials if p.name.lower() in text.lower()]
    return r.validate()
