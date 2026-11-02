from pathlib import Path
from datetime import datetime, timezone
import re
import zipfile
import xml.etree.ElementTree as ET
from .common import read_json, write_json, safe_join

NATIONS = {"american", "british", "chinese", "czech", "french", "german", "italy", "japan", "poland", "russian", "swedish"}
TEXTURE = re.compile(r"_(AM|AO|GMM|ANM)(_hd)?\.dds$", re.I)


def game_version(root):
    if not str(root or "").strip():
        raise ValueError("请先选择实际游戏客户端目录。")
    tree = ET.parse(Path(root) / "paths.xml")
    versions = [re.search(r"res_mods/([^/]+)", (e.text or "").replace("\\", "/")) for e in tree.iter("Path")]
    versions = [x.group(1) for x in versions if x]
    if len(set(versions)) != 1 or not re.fullmatch(r"[\d.]+", versions[0]):
        raise ValueError("无法从 paths.xml 唯一确定 res_mods 版本")
    return versions[0]


def packages_stamp(root):
    return [[p.name, p.stat().st_size, p.stat().st_mtime_ns] for p in sorted((Path(root) / "res/packages").glob("*.pkg"))]


def index(root, path, log=print):
    if not str(root or "").strip():
        raise ValueError("请先选择实际游戏客户端目录。")
    root = Path(root).resolve()
    stamp = packages_stamp(root)
    if not stamp:
        raise ValueError("客户端目录下找不到 res/packages/*.pkg")
    vehicles = {}
    excluded = set()
    for i, (name, _, _) in enumerate(stamp):
        with zipfile.ZipFile(root / "res/packages" / name) as z:
            for item in z.infolist():
                rel = item.filename.replace("\\", "/")
                parts = rel.split("/")
                if len(parts) < 4 or parts[0] != "vehicles" or parts[1] not in NATIONS:
                    continue
                if not re.match(r"[A-Za-z]+\d", parts[2]):
                    excluded.add("/".join(parts[1:3]))
                    continue
                if item.is_dir():
                    continue
                if any(p in ("..", "") for p in parts) or ":" in rel:
                    raise ValueError(f"资源包包含非法路径：{rel}")
                key = "/".join(parts[1:3])
                vehicles.setdefault(key, {})[rel] = {"pkg": name, "size": item.file_size, "crc": item.CRC}
        if i % 30 == 0:
            log(f"扫描资源包 {i+1}/{len(stamp)}")
    write_json(path, {"schema": 1, "wot_root": str(root), "version": game_version(root), "created": datetime.now(timezone.utc).isoformat(), "packages": stamp, "vehicles": vehicles})
    log(f"索引完成：{len(vehicles)} 台车型 / {len(stamp)} 个资源包")
    if excluded:
        log("未按车型目录命名规则收录 %d 个目录（可能包含共享资源），示例：%s" % (len(excluded), "、".join(sorted(excluded)[:5])))
    return vehicles


def load_index(cfg):
    data = read_json(cfg["index_file"])
    if Path(data["wot_root"]).resolve() != Path(cfg["wot_root"]).resolve() or data["version"] != game_version(cfg["wot_root"]) or data["packages"] != packages_stamp(cfg["wot_root"]):
        raise ValueError("客户端路径或资源版本已变化，请先重建车型索引")
    return data


class Assets:
    def __init__(self, root):
        self.root = Path(root)
        self.opened = {}

    def read(self, rel, entry):
        name = entry["pkg"]
        if Path(name).name != name:
            raise ValueError("索引包含非法资源包路径")
        if name not in self.opened:
            self.opened[name] = zipfile.ZipFile(self.root / "res/packages" / name)
        return self.opened[name].read(rel)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for z in self.opened.values():
            z.close()


def texture_kind(rel):
    m = TEXTURE.search(rel)
    return m.group(1).upper() if m else None


def peer_texture(rel, kind):
    return TEXTURE.sub(lambda m: "_" + kind + (m.group(2) or "") + ".dds", rel)
