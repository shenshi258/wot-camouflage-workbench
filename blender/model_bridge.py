"""Executed by the bundled Blender; UI and conversion stay in the workspace."""
from pathlib import Path
from datetime import datetime
import json
import sys
import traceback
import xml.etree.ElementTree as ET
import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--")+1:]
PROJECT_FILE = Path(ARGS[0]).resolve()
PROJECT = PROJECT_FILE.parent
META = json.loads(PROJECT_FILE.read_text(encoding="utf-8"))
ROOT = Path(META["workspace"])
sys.path.insert(0, str(ROOT / "tools"))
import addon_utils
addon = addon_utils.enable("wot_toolkit", default_set=True)
if addon is None:
    raise RuntimeError("WoT toolkit activation failed")
from wot_toolkit import import_bw_primitives_textured as importer
from wot_toolkit.export_bw_primitives import BigWorldModelExporter
from wot_toolkit.common.XmlUnpacker import XmlUnpacker


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class WorkspaceFinder:
    """Resolve extracted files before falling back to read-only game packages."""
    def __init__(self):
        from wot_toolkit.file_finder import WoTFileFinder
        self.fallback = WoTFileFinder()
        self.last_found_pkg = None

    def find(self, target_file, base_dir, internal_path, **kwargs):
        rel = str(internal_path).replace("\\", "/")
        near = Path(base_dir) / Path(target_file).name
        if near.is_file():
            return str(near)
        candidate = (PROJECT / "source/res" / rel).resolve()
        if candidate.is_relative_to((PROJECT / "source/res").resolve()) and candidate.is_file():
            return str(candidate)
        return self.fallback.find(target_file, base_dir, internal_path, **kwargs)


def load_native(path_str, base_path, finder, context, is_data=False):
    found = finder.find(path_str, base_path, path_str, context_pkg=context.get("last_pkg"))
    if not found:
        return None
    try:
        image = bpy.data.images.load(str(found), check_existing=True)
        if is_data:
            image.colorspace_settings.name = "Non-Color"
        image.pack()
        return image
    except Exception:
        return None


importer.load_image_safe = load_native
addon._global_finder = WorkspaceFinder()
bpy.context.preferences.addons["wot_toolkit"].preferences.wot_game_path = META["wot_root"]
# The toolkit's quick-export targets its configured game root. Redirect its
# preference to a staging client after imports, so every export stays local.


def roots():
    return [o for o in bpy.data.objects if o.get("workbench_model") == META["model"]]


def bounds(meshes):
    points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    return [[min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]]


def active_diffuse():
    for mat in bpy.data.materials:
        if mat.use_nodes:
            node = mat.node_tree.nodes.get("diffuseMap")
            if node is not None and node.type == 'TEX_IMAGE':
                mat.node_tree.nodes.active = node


def render_preview(meshes):
    from mathutils import Vector
    box = bounds(meshes)
    center = (Vector(box[0])+Vector(box[1]))/2
    span = max(Vector(box[1])-Vector(box[0]))
    camera = bpy.data.objects.get("Preview Camera")
    if camera is None:
        camera_data = bpy.data.cameras.new("Preview Camera")
        camera = bpy.data.objects.new("Preview Camera", camera_data)
        bpy.context.scene.collection.objects.link(camera)
    camera_data = camera.data
    camera.location = center + Vector((1.2, -1.5, 1.05))*span
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = span*1.35
    scene = bpy.context.scene
    active_diffuse()
    scene.camera = camera
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = 'WORLD'
    scene.world.color = (.055, .065, .085)
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(PROJECT / "preview.png")
    bpy.ops.render.render(write_still=True)


def create():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    before = set(bpy.data.objects)
    source = PROJECT / "source/res" / META["model"]
    result = importer.load_bw_primitive_textured(bpy.context.scene.collection, source, True, finder=WorkspaceFinder(), context={"last_pkg": None})
    objects = list(set(bpy.data.objects)-before)
    meshes = [o for o in objects if o.type == "MESH"]
    if result != {"FINISHED"} or not meshes or not any(len(o.data.vertices) for o in meshes):
        text = bpy.data.texts.get("BW_Import_Debug_Log")
        raise RuntimeError("No valid geometry imported\n" + (text.as_string() if text else ""))
    armatures = [o for o in objects if o.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one component armature, found {len(armatures)}")
    arm = armatures[0]
    arm["workbench_model"] = META["model"]
    arm["bw_export_filename"] = source.stem
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.shading.type = "SOLID"
                area.spaces.active.shading.color_type = "TEXTURE"
                area.spaces.active.region_3d.view_distance = max(max(o.dimensions) for o in meshes)*2.5
                area.spaces.active.region_3d.view_location = sum((o.matrix_world @ sum((__import__('mathutils').Vector(c) for c in o.bound_box), __import__('mathutils').Vector()) / 8 for o in meshes), __import__('mathutils').Vector()) / len(meshes)
    bpy.context.scene["workbench_project"] = str(PROJECT_FILE)
    bpy.context.preferences.view.language = "zh_HANS"
    bpy.context.preferences.view.use_translate_interface = True
    original_bounds = bounds(meshes)
    render_preview(meshes)
    bpy.ops.wm.save_as_mainfile(filepath=str(PROJECT / "edit.blend"))
    dump(PROJECT / "import_report.json", {"meshes": len(meshes), "vertices": sum(len(o.data.vertices) for o in meshes), "triangles": sum(len(o.data.polygons) for o in meshes), "materials": len(bpy.data.materials), "model": META["model"], "bounds": original_bounds})


def export():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    components = roots()
    if len(components) != 1:
        raise RuntimeError("Keep the imported component root; parent new meshes to it before exporting")
    arm = components[0]
    meshes = [o for o in arm.children if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh remains under the model root")
    nodes = {}
    addon.get_nodes_by_empty(arm, nodes)
    output = PROJECT / "exports" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = output / "res" / META["model"]
    dest.parent.mkdir(parents=True)
    info = {"export_models": True, "export_textures": False, "root_matrix": arm.matrix_world.copy(), "original_filename": dest.stem, "nodes": nodes, "export_vcolors": True}
    exporter = BigWorldModelExporter()
    exporter.export(meshes, str(dest.with_suffix(".temp_model")), info)
    expected = [dest, dest.with_suffix(".visual_processed"), dest.with_suffix(".primitives_processed")]
    if not all(p.is_file() and p.stat().st_size > 20 for p in expected):
        raise RuntimeError("Model exporter did not produce all three files")
    generated_model = ET.parse(dest).getroot()
    # Preserve the original parent/extent LOD chain and all model metadata.
    source = PROJECT / "source/res" / META["model"]
    try:
        original = ET.fromstring(source.read_bytes())
    except ET.ParseError:
        with source.open("rb") as f:
            original = XmlUnpacker().read(f)
    if original is None:
        raise RuntimeError("Cannot decode original model descriptor")
    node = original.find("nodefullVisual")
    if node is None:
        node = original.find("nodelessVisual")
    if node is None:
        node = ET.SubElement(original, "nodefullVisual")
    node.text = str(Path(META["model"]).with_suffix("")).replace("\\", "/")
    new_box = generated_model.find("visibilityBox")
    if new_box is not None:
        old_box = original.find("visibilityBox")
        if old_box is not None:
            original.remove(old_box)
        original.append(new_box)
    ET.ElementTree(original).write(dest, encoding="utf-8", xml_declaration=True)
    before = set(bpy.data.objects)
    collection = bpy.data.collections.new("EXPORT_VALIDATION")
    bpy.context.scene.collection.children.link(collection)
    result = importer.load_bw_primitive_textured(collection, dest, True, finder=WorkspaceFinder(), context={"last_pkg": None})
    imported = list(set(bpy.data.objects)-before)
    new_meshes = [o for o in imported if o.type == "MESH"]
    count = sum(len(o.data.vertices) for o in new_meshes)
    if result != {"FINISHED"} or not new_meshes or count < 3:
        raise RuntimeError("Exported model cannot be read back")
    for obj in new_meshes:
        if not obj.data.uv_layers:
            raise RuntimeError("Exported geometry lost UV coordinates")
        if not obj.data.materials:
            raise RuntimeError("Exported geometry lost materials")
    expected_bounds, actual_bounds = bounds(meshes), bounds(new_meshes)
    error = max(abs(expected_bounds[i][j]-actual_bounds[i][j]) for i in range(2) for j in range(3))
    if not all(__import__('math').isfinite(x) for row in actual_bounds for x in row) or error > .02:
        raise RuntimeError(f"Exported mesh dimensions differ from edited mesh: {error}")
    validation = {"roundtrip_ok": True, "meshes": len(new_meshes), "vertices": count, "polygons": sum(len(o.data.polygons) for o in new_meshes), "selected_model": META["model"], "edited_bounds": expected_bounds, "exported_bounds": actual_bounds, "bounds_max_error": error, "original_lod_chain_preserved": True, "in_game_tested": False}
    dump(output / "model_validation.json", validation)
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)
    render_preview(meshes)
    import shutil
    shutil.copyfile(PROJECT / "preview.png", output / "preview.png")
    dump(PROJECT / "last_export.json", {"output": str(output.relative_to(PROJECT))})


def apply_textures():
    paint = PROJECT / META["texture_root"]
    replacements = {}
    changed = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or node.image is None:
                continue
            ref = mat.get("bw_tex_" + node.name)
            if not ref:
                continue
            candidate = (paint / str(ref)).resolve()
            if not candidate.is_relative_to(paint.resolve()) or not candidate.is_file():
                continue
            key = (str(candidate), node.image.colorspace_settings.name)
            if key not in replacements:
                image = bpy.data.images.load(str(candidate), check_existing=False)
                image.colorspace_settings.name = key[1]
                image.pack()
                replacements[key] = image
            node.image = replacements[key]
            changed += 1
    if not changed:
        raise RuntimeError("No generated texture matches the selected model materials")
    active_diffuse()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'SOLID'
                area.spaces.active.shading.color_type = 'TEXTURE'
    render_preview([o for o in roots()[0].children if o.type == 'MESH'])
    bpy.ops.wm.save_as_mainfile(filepath=str(PROJECT / "edit.blend"))
    dump(PROJECT / "texture_preview_report.json", {"replaced_image_nodes": changed})


class WORKBENCH_OT_save(bpy.types.Operator):
    bl_idname = "workbench.save_project"
    bl_label = "保存模型工程"
    def execute(self, context):
        bpy.ops.wm.save_as_mainfile(filepath=str(PROJECT / "edit.blend"))
        return {"FINISHED"}


class WORKBENCH_PT_panel(bpy.types.Panel):
    bl_label = "WOT 本地模型工作流"
    bl_idname = "WORKBENCH_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "WOT工作流"
    def draw(self, context):
        layout = self.layout
        layout.label(text=Path(META["model"]).name)
        layout.label(text="Tab：编辑网格；G/R/S：移动/旋转/缩放")
        layout.label(text="新增网格请设为原部件骨架的子物体")
        layout.operator("workbench.save_project", icon="FILE_TICK")
        layout.label(text="保存后回工作台点击“导出模型并校验”")
        layout.label(text="当前工程只修改所选部件和 LOD")


for cls in (WORKBENCH_OT_save, WORKBENCH_PT_panel):
    bpy.utils.register_class(cls)

action = ARGS[1]
if action == "create":
    create()
elif action == "export":
    bpy.ops.wm.open_mainfile(filepath=str(PROJECT / "edit.blend"))
    export()
elif action == "smoke_edit":
    bpy.ops.wm.open_mainfile(filepath=str(PROJECT / "edit.blend"))
    # Exercise actual vertex editing and retain the result as a separate demo.
    mesh = next(o for o in roots()[0].children if o.type == "MESH")
    for v in mesh.data.vertices:
        v.co.z *= 1.015
    bpy.ops.wm.save_as_mainfile(filepath=str(PROJECT / "edit.blend"))
elif action == "apply_textures":
    bpy.ops.wm.open_mainfile(filepath=str(PROJECT / "edit.blend"))
    apply_textures()
elif action != "open":
    raise ValueError(action)
if action in ("create", "open"):
    staging = PROJECT / "sandbox_client"
    staging.mkdir(exist_ok=True)
    (staging / "version.xml").write_text(f"<root><version>v.{META['game_version']} #0</version></root>")
    bpy.context.preferences.addons["wot_toolkit"].preferences.wot_game_path = str(staging)
print(f"[workbench] {action} done", flush=True)
