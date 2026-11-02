from pathlib import Path
from datetime import datetime, timezone
import hashlib
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from . import dds
from .common import settings, safe_join, title_name, write_json, read_json
from .wotdata import Assets, load_index, texture_kind, peer_texture
from .compose import scan_materials, compose_am, derive
from .prompt import parse, Recipe
from .modpack import digest, pack


def selected(rel, recipe):
    stem = Path(rel).stem.lower()
    return "decals" not in stem and ("all" in recipe.parts or any(p in stem for p in recipe.parts))


def preview(tiles, output, title):
    cols, cell = 3, 320
    tiles = tiles[:12]
    sheet = Image.new("RGB", (cols*cell, 74+math.ceil(len(tiles)/cols)*(cell+36)), "#19212b")
    draw = ImageDraw.Draw(sheet)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    draw.text((20, 18), f"{title} · AM 贴图图集预览", font=font, fill="#ecedf0")
    for i, (name, im) in enumerate(tiles):
        x, y = i % cols*cell, 74+i//cols*(cell+36)
        im = im.convert("RGB")
        im.thumbnail((cell-16, cell-16))
        sheet.paste(im, (x+8, y))
        draw.text((x+8, y+cell-9), name[-32:], font=font, fill="#b7c7d9")
    sheet.save(output)


def build(tank, material_dir, text, title, cfg=None, out=None, derive_maps=False, do_pack=False, recipe_file=None, log=print):
    cfg = cfg or settings()
    index = load_index(cfg)
    if tank not in index["vehicles"]:
        raise ValueError(f"索引中找不到车型：{tank}")
    material_files = scan_materials(material_dir)
    recipe = Recipe(**read_json(recipe_file)).validate() if recipe_file else parse(text, material_files)
    title = title_name(title)
    # Never mix stale textures with a new build.
    output = Path(out) if out else Path(cfg["result_dir"]) / (title + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    if output.exists() and any(output.iterdir()):
        raise ValueError("输出目录非空；请选择新目录以避免旧资源混入")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "recipe.json", recipe.to_dict())
    entries = index["vehicles"][tank]
    am_paths = sorted(p for p in entries if texture_kind(p) == "AM" and selected(p, recipe))
    if not am_paths:
        raise ValueError("没有匹配部件的 AM 贴图；请检查部件名称，或尝试选择全部部件/使用配方文件。")
    report = {"complete": False, "type": "textures", "tank": tank, "title": title, "game_version": index["version"], "created": datetime.now(timezone.utc).isoformat(), "files": [], "warnings": [], "preview": "AM atlas only; not a 3D model", "in_game_tested": False, "whole_vehicle_loading": {"status": "not_tested"}}
    if not derive_maps and (recipe.ao_clean or recipe.block_official_camo or recipe.gmm_specular is not None or recipe.normal_strength is not None or recipe.emissive):
        report["warnings"].append("提示词含材质/洗车/屏蔽/发光选项，未勾选派生贴图，这些选项未应用。")
    if recipe.emissive and not recipe.decals:
        report["warnings"].append("发光仅应用到贴花区域；未指定贴花，因此未添加发光。")
    tiles = []
    with Assets(cfg["wot_root"]) as assets:
        for i, rel in enumerate(am_paths):
            log(f"[{i+1}/{len(am_paths)}] {Path(rel).name}")
            raw = assets.read(rel, entries[rel])
            original = dds.decode(raw)
            ao_path = peer_texture(rel, "AO")
            ao = dds.decode(assets.read(ao_path, entries[ao_path])) if ao_path in entries else None
            image, mask = compose_am(original, ao, recipe, material_dir, rel)
            if recipe.emissive and derive_maps:
                a = np.asarray(image).copy()
                a[np.asarray(mask) > 127, 0] = 0
                image = Image.fromarray(a)
            outputs = [(rel, image, raw)]
            if derive_maps:
                for kind in ("AO", "GMM", "ANM"):
                    peer = peer_texture(rel, kind)
                    if peer not in entries:
                        continue
                    source = assets.read(peer, entries[peer])
                    info = dds.inspect(source)
                    decoded = dds.decode(source)
                    edited = derive(decoded, kind, info.fourcc, recipe, mask)
                    if edited.tobytes() != decoded.tobytes():
                        outputs.append((peer, edited, source))
            for path, pixels, reference in outputs:
                if pixels.tobytes() == dds.decode(reference).tobytes():
                    report["warnings"].append(f"未改变的资源已跳过：{path}")
                    continue
                encoded = dds.encode_like(pixels, reference)
                if encoded == reference:
                    report["warnings"].append(f"压缩后无变化，已跳过：{path}")
                    continue
                safe_join(output / "res", path).parent.mkdir(parents=True, exist_ok=True)
                safe_join(output / "res", path).write_bytes(encoded)
                info = dds.inspect(encoded)
                report["files"].append({"path": path, "sha256": digest(encoded), "original_sha256": digest(reference), "width": info.width, "height": info.height, "format": info.format_name, "mips": info.levels, "bytes": len(encoded)})
            if "_hd.dds" not in rel and len(tiles) < 12:
                tiles.append((Path(rel).name, image.copy()))
    if not report["files"]:
        raise ValueError("没有实际改变的贴图，未生成安装产物")
    preview(tiles, output / "preview.png", title)
    report["complete"] = True
    report["count"] = len(report["files"])
    write_json(output / "report.json", report)
    if do_pack:
        pack(output, title)
    log(f"完成：{len(report['files'])} 张贴图；输出 {output}")
    for warning in report["warnings"]:
        log("提示：" + warning)
    return output


def verify(output, cfg=None, log=print):
    from .modpack import checked_files
    cfg = cfg or settings()
    report, values = checked_files(output)
    index = load_index(cfg)
    if report["game_version"] != index["version"]:
        raise ValueError("产物对应的客户端版本已变化")
    entries = index["vehicles"][report["tank"]]
    mip_count = 0
    with Assets(cfg["wot_root"]) as assets:
        for rel, data in values:
            if not rel.lower().endswith(".dds"):
                continue
            if rel not in entries:
                raise ValueError(f"原客户端找不到贴图：{rel}")
            ref = assets.read(rel, entries[rel])
            dds.verify_matches(data, ref)
            if dds.inspect(ref).fourcc == "DXT1" and texture_kind(rel) in ("AM", "AO", "GMM"):
                original_alpha = np.asarray(dds.decode(ref))[..., 3] < 128
                output_alpha = np.asarray(dds.decode(data))[..., 3] < 128
                if not np.array_equal(original_alpha, output_alpha):
                    raise ValueError(f"DXT1 透明区域与原始贴图不一致：{rel}")
            if data == ref:
                raise ValueError(f"产物包含未修改的原贴图：{rel}")
            for mip in dds.decode_mips(data):
                mip.load()
                mip_count += 1
    archives = list(Path(output).glob("*.wotmod"))
    import zipfile
    for archive in archives:
        with zipfile.ZipFile(archive) as z:
            if set(z.namelist()) != {"meta.xml", *["res/"+p for p, _ in values]}:
                raise ValueError("安装包文件清单不符")
            for rel, data in values:
                if z.getinfo("res/"+rel).compress_type != zipfile.ZIP_STORED or z.read("res/"+rel) != data:
                    raise ValueError("安装包内容或压缩方式不符")
    log(f"文件结构校验通过：{len(values)} 个文件，{mip_count} 级 mip，{len(archives)} 个安装包；游戏内整车尚未验收")
    return {"files": len(values), "mips_decoded": mip_count, "packs": len(archives)}
