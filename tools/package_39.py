"""Ordinary-skin scope, persistent thumbnails and media import."""
from package_34 import main

if __name__=='__main__':
    main(version='3.9',label='涂装应用范围版',ui_count=49,preset_count=36,
         extra_guide='在“涂装制作 → 应用范围”选择“所有同资源车辆”或“仅自己的车辆”；三维贴图中也有对应选项。已有普通包可点“按当前范围导出已有涂装”。仅自己模式暂不支持 UML、第三方脚本和共享覆盖包。测试前停用同款旧包；仅控制本机显示。游戏内效果待实测。\n个人图片位于“程序/素材库/图片元素”，升级请保留素材库文件夹。\n',
         extra_tests=('tests.test_ae_pattern','tests.test_meteor_preset','tests.test_ae_media','tests.test_asset_library','tests.test_paint3d','tests.test_paint_layers','tests.test_vehicle_scope'),
         runtime_packages=(('cv2','opencv-python-headless'),),
         extra_evidence=('.cache/library38_browser_result.json','.cache/图片素材库_缩略图验证.png','.cache/三维贴图_自导入素材库验证.png','.cache/素材库_UI复核_经典_800x600.png','.cache/素材库_UI复核_玻璃_800x600.png'),
         web_markers=('AE_COPY_PASTE_AND_FIT_HANDLERS_OK','MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK','AE_LIVE_TINT_INPUT_AND_STALE_REFRESH_OK','ASSET_LIBRARY_BROWSER_IMPORT_SEARCH_PERSIST_AND_PAINT_EXPORT_OK','UI_LIBRARY_THEMES_COMPACT_LAYOUT_AND_LAST_SELECTION_OK','PAINT_SCOPE_EXPORT_AND_PERSISTED_SELECTION_OK'))
