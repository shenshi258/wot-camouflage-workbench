import argparse
from pathlib import Path
import sys
from .common import ROOT, settings, read_json
from . import wotdata, pipeline, modpack, models
from .compose import demo_materials


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="WOT 本地涂装与模型工作流")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="扫描本机客户端，重建车型索引")
    sub.add_parser("doctor", help="检查运行环境")
    sub.add_parser("demo", help="生成演示素材")
    ls = sub.add_parser("list", help="搜索车型")
    ls.add_argument("--query", default="")
    ls.add_argument("--limit", type=int, default=30)
    b = sub.add_parser("build", help="制作涂装")
    b.add_argument("--tank", required=True)
    b.add_argument("--materials", default=str(ROOT / "materials/demo"))
    b.add_argument("--prompt", default="沙漠黄底色 + 白色虎纹 + 中度做旧，贴上 number_07.png")
    b.add_argument("--title", default="我的涂装")
    b.add_argument("--out")
    b.add_argument("--recipe")
    b.add_argument("--derive", action="store_true")
    b.add_argument("--pack", action="store_true")
    b.add_argument("--install", action="store_true")
    b.add_argument("--no-install", action="store_true", help="默认就不安装；保留交接文档参数兼容")
    for name in ("verify", "install", "rollback", "pack"):
        s = sub.add_parser(name)
        s.add_argument("path")
    m = sub.add_parser("model-create", help="提取真实模型，创建 Blender 工程")
    m.add_argument("--tank", required=True)
    m.add_argument("--model", help="索引内 vehicles/.../*.model 路径")
    for name in ("model-open", "model-export"):
        s = sub.add_parser(name)
        s.add_argument("project")
    a = p.parse_args()
    cfg = settings()
    try:
        if a.command == "index":
            wotdata.index(cfg["wot_root"], cfg["index_file"])
        elif a.command == "doctor":
            import PIL, numpy
            print("Python:", sys.version.split()[0], "Pillow:", PIL.__version__, "numpy:", numpy.__version__)
            print("客户端:", cfg["wot_root"], "版本:", wotdata.game_version(cfg["wot_root"]))
            print("Blender:", models.blender_command(cfg))
            print("插件:", models.doctor_addon(cfg))
            idx = wotdata.load_index(cfg)
            print("索引:", len(idx["vehicles"]), "台车型")
        elif a.command == "demo":
            demo_materials(ROOT / "materials/demo")
        elif a.command == "list":
            idx = wotdata.load_index(cfg)
            rows = [t for t in idx["vehicles"] if a.query.lower() in t.lower()]
            print("\n".join(sorted(rows)[:a.limit]))
            print(f"共 {len(rows)} 条")
        elif a.command == "build":
            if a.install and a.no_install:
                raise ValueError("--install 和 --no-install 不能同时指定")
            out = pipeline.build(a.tank, a.materials, a.prompt, a.title, cfg, a.out, a.derive, a.pack, a.recipe)
            pipeline.verify(out, cfg)
            if a.install:
                modpack.install(out, cfg["wot_root"])
        elif a.command == "verify":
            pipeline.verify(a.path, cfg)
        elif a.command == "install":
            pipeline.verify(a.path, cfg)
            modpack.install(a.path, cfg["wot_root"])
        elif a.command == "rollback":
            modpack.rollback(a.path, wot_root=cfg["wot_root"])
        elif a.command == "pack":
            print(modpack.pack(a.path, read_json(Path(a.path) / "report.json")["title"]))
        elif a.command == "model-create":
            print(models.create(a.tank, a.model, cfg))
        elif a.command == "model-open":
            models.open_project(a.project, cfg)
        elif a.command == "model-export":
            print(models.export(a.project, cfg))
    except Exception as e:
        print(f"操作失败：{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
