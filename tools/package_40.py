"""Persistent image/GIF elements, node animation and reviewed effect exports."""
from package_34 import main

if __name__=='__main__':
    main(version='4.0',label='',ui_count=55,preset_count=36,
         extra_guide='在 AE 编辑器打开“图片 / GIF 素材库…”导入并复用自己的元素，再用“动画节点 / 关键帧…”制作画布内的移动、旋转、缩放和透明动画。先播放预览，再应用；工程与预设保留原素材和节点。最多 128 帧，超限请缩短时长或降低帧率。\n升级请保留“程序/素材库”。普通三维贴图使用 GIF 首帧，完整动画在 AE 中制作。普通贴面距离可独立调整；旧流星素材可能含透明帧段，游戏内闪烁尚未确认修复。\n',
         extra_tests=('tests.test_ae_pattern','tests.test_meteor_preset','tests.test_ae_media','tests.test_asset_library','tests.test_paint3d','tests.test_paint_layers','tests.test_vehicle_scope',
                      'tests.test_ae_animation','tests.test_ae_animation_pipeline','tests.test_ae_preset_nodes','tests.test_ae_thin','tests.test_light_review310','tests.test_light_dependency_gate310',
                      'tests.test_light_bounds','tests.test_light_build_review','tests.test_light_directions','tests.test_light_effects','tests.test_light_palette','tests.test_light_preview','tests.test_light_select','tests.test_light_support','tests.test_light_vertex_formats','tests.test_light_wheels','tests.test_light_v213'),
         runtime_packages=(('cv2','opencv-python-headless'),),
         extra_evidence=('.cache/gif_library410/browser_result.json','.cache/gif_library410/native_dialog_result.json','.cache/gif_library410/图片GIF素材库.png','.cache/nodes310_动画节点.png',
                         'E:/wot 3d/改造区/AE闪烁复核_20261117/最终光效原生像素检查.json'),
         web_markers=('AE_COPY_PASTE_AND_FIT_HANDLERS_OK','MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK','AE_LIVE_TINT_INPUT_AND_STALE_REFRESH_OK','ASSET_LIBRARY_BROWSER_IMPORT_SEARCH_PERSIST_AND_PAINT_EXPORT_OK','UI_LIBRARY_THEMES_COMPACT_LAYOUT_AND_LAST_SELECTION_OK','PAINT_SCOPE_EXPORT_AND_PERSISTED_SELECTION_OK','GIF_LIBRARY_ANIMATION_AND_STATIC_PAINT_OK'))
