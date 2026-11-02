"""Blender projects for editing real BigWorld geometry, with staged export."""
from pathlib import Path
from datetime import datetime
import os
import subprocess
import shutil
import zipfile
from .common import ROOT, settings, safe_join, write_json, read_json, title_name
from .wotdata import load_index, Assets
from .modpack import pack, digest


def blender_command(cfg=None):
    cfg = cfg or settings()
    exe = Path(cfg.get("blender", ""))
    if not exe.is_file():
        raise ValueError("尚未配置 Blender，请在设置中选择 blender.exe")
    if not (ROOT / "tools/wot_toolkit/__init__.py").is_file():
        raise ValueError("WOT 模型插件缺失，请运行 tools_setup.py")
    return str(exe)


def ensure_addon():
    source = ROOT / 'tools/wot_toolkit'
    target = ROOT / 'tools/blender_user/scripts/addons/wot_toolkit'
    if not (source / '__init__.py').is_file():
        raise ValueError('WOT 模型插件缺失，请运行 tools_setup.py')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    if not (target / '__init__.py').is_file():
        raise ValueError('WOT 模型插件安装不完整：' + str(target))
    return target


def blender_env():
    ensure_addon()
    env = os.environ.copy()
    env["BLENDER_USER_CONFIG"] = str(ROOT / "tools/blender_user/config")
    env["BLENDER_USER_SCRIPTS"] = str(ROOT / "tools/blender_user/scripts")
    env["TEMP"] = env["TMP"] = str(ROOT / ".cache/blender")
    for path in (env["BLENDER_USER_CONFIG"], env["BLENDER_USER_SCRIPTS"], env["TEMP"]):
        Path(path).mkdir(exist_ok=True, parents=True)
    return env


def doctor_addon(cfg=None):
    command = blender_command(cfg)
    code = "import addon_utils; a=addon_utils.enable('wot_toolkit',default_set=False); assert a is not None, 'WoT toolkit activation failed'; print('WOT_ADDON_OK')"
    try:
        result = subprocess.run([command, '--background', '--factory-startup', '--python-exit-code', '1', '--python-expr', code],
                                env=blender_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding='utf-8', errors='replace', timeout=60,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('Blender 插件自检无法完成：' + str(error)) from error
    if result.returncode or 'WOT_ADDON_OK' not in result.stdout:
        raise ValueError('Blender 插件加载失败：' + result.stdout[-1800:])
    return 'WoT 模型插件加载成功'


def run_blender(project, action, cfg=None, log=print):
    project = Path(project).resolve()
    if project.is_dir():
        project = project / "project.json"
    args = [blender_command(cfg), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(ROOT / "blender/model_bridge.py"), "--", str(project), action]
    result = subprocess.run(args, env=blender_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    logfile = project.parent / f"blender_{action}.log"
    logfile.write_text(result.stdout, encoding="utf-8")
    if result.returncode or f"[workbench] {action} done" not in result.stdout:
        raise RuntimeError(f"Blender {action} 失败，日志：{logfile}\n{result.stdout[-2200:]}")
    log(f"Blender {action} 完成；日志 {logfile}")
    return project.parent


def create(tank, model=None, cfg=None, log=print):
    cfg = cfg or settings()
    blender_command(cfg)
    idx = load_index(cfg)
    entries = idx["vehicles"].get(tank)
    if not entries:
        raise ValueError("车型不在索引内")
    candidates = sorted(p for p in entries if p.lower().endswith(".model") and "/normal/lod0/" in p and "/_skins/" not in p)
    model = model or next((p for p in candidates if Path(p).name.lower() == "hull.model"), next(iter(candidates), None))
    if model not in entries or not model.lower().endswith(".model"):
        raise ValueError("请选择索引内的 .model 文件")
    project = ROOT / "projects" / (title_name(tank.replace("/", "_") + "_" + Path(model).stem) + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    project.mkdir(parents=True)
    source = project / "source/res"
    # All assets for the chosen variant: retain untouched LODs as references.
    skin_base = model.split("/normal/")[0] if "/normal/" in model else str(Path(model).parent.parent).replace("\\", "/")
    extracted = []
    with Assets(cfg["wot_root"]) as assets:
        for rel, entry in entries.items():
            if not rel.startswith(skin_base + "/") or ("/_skins/" not in model and "/_skins/" in rel):
                continue
            if Path(rel).suffix.lower() not in (".model", ".visual_processed", ".primitives_processed", ".visual", ".primitives", ".vt", ".dds"):
                continue
            data = assets.read(rel, entry)
            dest = safe_join(source, rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            extracted.append({"path": rel, "sha256": digest(data)})
    write_json(project / "project.json", {"schema": 1, "tank": tank, "model": model, "game_version": idx["version"], "wot_root": cfg["wot_root"], "workspace": str(ROOT), "files": extracted, "geometry_scope": "single selected part and LOD", "blend": "edit.blend"})
    log(f"提取 {len(extracted)} 个模型及贴图资源；创建真实网格编辑工程")
    run_blender(project, "create", cfg, log)
    return project


def open_project(project, cfg=None):
    cfg = cfg or settings()
    project = Path(project).resolve()
    if project.is_file():
        project = project.parent
    if not (project / "edit.blend").is_file():
        raise ValueError("工程没有 edit.blend，请先创建工程")
    # A visible window is intentional: this is the editor the user requested.
    return subprocess.Popen([blender_command(cfg), str(project / "edit.blend"), "--python", str(ROOT / "blender/model_bridge.py"), "--", str(project / "project.json"), "open"], env=blender_env())


def export(project, cfg=None, log=print, title=None):
    """Export the saved model, validate it, then build a named install package."""
    cfg = cfg or settings()
    project = Path(project).resolve()
    if project.is_file():
        project = project.parent
    meta = read_json(project / "project.json")
    package_title=title_name(title if title is not None else meta.get('package_title',Path(meta['model']).stem+'_模型修改'))
    if load_index(cfg)["version"] != meta["game_version"]:
        raise ValueError("客户端版本已变化，请重新创建模型工程")
    run_blender(project, "export", cfg, log)
    output = project / read_json(project / "last_export.json")["output"]
    results = read_json(output / "model_validation.json")
    if not results.get("roundtrip_ok"):
        raise ValueError("模型导出回读未通过")
    files = [{"path": p.relative_to(output / "res").as_posix(), "sha256": digest(p.read_bytes()), "bytes": p.stat().st_size} for p in sorted((output / "res").rglob("*")) if p.is_file()]
    if not files:
        raise ValueError("没有模型导出产物")
    report={"complete": False, "type": "model", "tank": meta["tank"], "title": package_title, "game_version": meta["game_version"], "files": files, "validation": results, "in_game_tested": False, "whole_vehicle_loading": {"status": "not_tested"}, "warnings": ["仅覆盖所选部件和 LOD；其他距离的 LOD 需分别编辑。", "回读验证不等于游戏实机验证；请先在车库检查，再进训练房。"]}
    write_json(output/'report.json',report)
    package=pack(output, package_title)
    # Verify the final named archive, not just the loose export directory.
    with zipfile.ZipFile(package) as z:
        if z.testzip() or set(z.namelist())!={'meta.xml',*('res/'+f['path'] for f in files)}:raise ValueError('模型包文件校验失败。')
        for f in files:
            name='res/'+f['path']
            if z.getinfo(name).compress_type!=zipfile.ZIP_STORED or digest(z.read(name))!=f['sha256']:raise ValueError('模型包内容与导出结果不一致。')
    report.update(complete=True,artifact=dict(path=str(package),sha256=digest(package.read_bytes()),bytes=package.stat().st_size))
    write_json(output/'report.json',report)
    meta['package_title']=package_title;write_json(project/'project.json',meta)
    log(f"模型回读通过，安装包已生成：{output}")
    return output


def apply_textures(project, texture_output, cfg=None, log=print):
    from .modpack import checked_files
    cfg = cfg or settings()
    project = Path(project).resolve()
    if project.is_file():
        project = project.parent
    meta = read_json(project / "project.json")
    report, files = checked_files(texture_output)
    if report.get("type") != "textures" or report["tank"] != meta["tank"] or report["game_version"] != meta["game_version"]:
        raise ValueError("请选择与当前模型同车型、同版本的涂装产物")
    from .pipeline import verify
    verify(texture_output, cfg, log)
    for rel, data in files:
        dest = safe_join(project / "paint/res", rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    meta["texture_root"] = "paint/res"
    write_json(project / "project.json", meta)
    run_blender(project, "apply_textures", cfg, log)
    log("已将涂装应用到保存的模型工程；重新打开 Blender 可查看")
    return project
