from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape
import hashlib
import uuid
import zipfile
from .common import ROOT, read_json, write_json, safe_join, atomic_write, settings
from .wotdata import game_version


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pack(output, title):
    output = Path(output)
    target = output / f"{title}.wotmod"
    tree = output / "res"
    files = sorted(p for p in tree.rglob("*") if p.is_file())
    if not files:
        raise ValueError("没有可打包的资源")
    meta = f'<?xml version="1.0" encoding="UTF-8"?><root><id>local.wotworkbench.{escape(title)}</id><version>1.0.0</version><name>{escape(title)}</name><description>Local texture/model workbench</description></root>'
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("meta.xml", meta)
        for p in files:
            z.write(p, "res/" + p.relative_to(tree).as_posix())
    return target


def checked_files(output):
    output = Path(output)
    report = read_json(output / "report.json")
    if not report.get("complete"):
        raise ValueError("构建未完成，禁止安装")
    expected = {r["path"]: r["sha256"] for r in report["files"]}
    actual = {p.relative_to(output / "res").as_posix() for p in (output / "res").rglob("*") if p.is_file()}
    if set(expected) != actual:
        raise ValueError("输出资源清单发生变化，请重新构建或校验")
    values = []
    for rel, sha in expected.items():
        data = safe_join(output / "res", rel).read_bytes()
        if digest(data) != sha:
            raise ValueError(f"文件内容发生变化：{rel}")
        if not rel.startswith("vehicles/"):
            raise ValueError("只允许安装 vehicles/ 下的涂装和模型")
        values.append((rel, data))
    return report, values


def install(output, wot_root, log=print):
    report, values = checked_files(output)
    version = game_version(wot_root)
    if report["game_version"] != version:
        raise ValueError("产物与当前客户端版本不一致，请重新构建")
    target = Path(wot_root).resolve() / "res_mods" / version
    backup = ROOT / "backups" / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    manifest = {"target": str(target), "version": version, "output": str(Path(output).resolve()), "state": "installing", "files": []}
    # Journal every file before changing it, so interrupted installs are recoverable.
    try:
        for rel, data in values:
            dest = safe_join(target, rel)
            existing = dest.read_bytes() if dest.exists() else None
            if existing is not None:
                atomic_write(safe_join(backup / "original", rel), existing)
            manifest["files"].append({"path": rel, "existed": existing is not None, "original_sha256": digest(existing) if existing is not None else None, "installed_sha256": digest(data)})
            write_json(backup / "manifest.json", manifest)
            atomic_write(dest, data)
        manifest["state"] = "installed"
        write_json(backup / "manifest.json", manifest)
    except Exception:
        # Journal remains available even if a disk failure also prevents rollback.
        rollback(backup, log, check_conflicts=False, wot_root=wot_root)
        raise
    log(f"安装完成，回滚记录：{backup}")
    return backup


def rollback(backup, log=print, check_conflicts=True, wot_root=None):
    backup = Path(backup).resolve()
    if not backup.is_relative_to((ROOT / "backups").resolve()):
        raise ValueError("请使用本工作区生成的备份记录")
    m = read_json(backup / "manifest.json")
    target = Path(m["target"]).resolve()
    if target.name != m["version"] or target.parent.name != "res_mods":
        raise ValueError("备份安装目标无效")
    selected = wot_root if wot_root is not None else settings()["wot_root"]
    if not str(selected or "").strip():
        raise ValueError("请先选择备份对应的实际游戏客户端目录。")
    selected_root = Path(selected).resolve()
    if target != selected_root / "res_mods" / m["version"]:
        raise ValueError("备份属于其他客户端，请先切换到备份对应的游戏目录。")
    if m["state"] == "rolled_back":
        raise ValueError("此安装记录已经回滚")
    # Preflight conflicts and backup integrity before making any changes.
    for f in m["files"]:
        p = safe_join(target, f["path"])
        current = digest(p.read_bytes()) if p.exists() else None
        if check_conflicts and current not in (f["installed_sha256"], f["original_sha256"]):
            raise ValueError(f"安装后文件被其他工具修改，未回滚：{f['path']}")
        if f["existed"] and digest(safe_join(backup / "original", f["path"]).read_bytes()) != f["original_sha256"]:
            raise ValueError("备份文件校验失败")
    for f in reversed(m["files"]):
        p = safe_join(target, f["path"])
        if f["existed"]:
            atomic_write(p, safe_join(backup / "original", f["path"]).read_bytes())
        elif p.exists():
            # Only an individual file created by this installation is removed.
            p.unlink()
    m["state"] = "rolled_back"
    write_json(backup / "manifest.json", m)
    log("已恢复安装前状态")
