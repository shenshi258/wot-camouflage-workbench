from pathlib import Path, PurePosixPath
import json
import os
import re
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def settings():
    cfg = read_json(ROOT / "config/settings.json")
    for key in ("wot_root", "blender", "result_dir", "materials_dir", "index_file"):
        if cfg.get(key):
            p = Path(cfg[key])
            cfg[key] = str(p if p.is_absolute() else ROOT / p)
    return cfg


def safe_join(root, relative):
    relative = str(relative).replace("\\", "/")
    p = PurePosixPath(relative)
    if p.is_absolute() or ".." in p.parts or ":" in relative or not relative:
        raise ValueError(f"不安全的资源路径：{relative}")
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError(f"资源越出目标目录：{relative}")
    return target


def title_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    if not value or value.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        raise ValueError("请输入有效作品名称")
    return value[:100]
