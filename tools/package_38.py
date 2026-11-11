"""User-importable persistent thumbnail library, integrated into model paint."""
from package_34 import main

if __name__=='__main__':
    main(version='3.8',label='自定义缩略图素材库版',ui_count=46,preset_count=36,
         extra_guide='“涂装制作 → 管理图片素材库”可自行批量导入 PNG / JPG / WebP，按名称和分类搜索、改名或移出。三维贴图中点击“图片素材库”，选中缩略图后点“使用素材”，再点模型放置。\n个人图片副本保存在“程序/素材库/图片元素”；升级时请保留并复制“素材库”文件夹。单次最多导入 128 张，库内最多 1000 项。\n',
         extra_tests=('tests.test_ae_pattern','tests.test_meteor_preset','tests.test_ae_media','tests.test_asset_library','tests.test_paint3d','tests.test_paint_layers'),
         runtime_packages=(('cv2','opencv-python-headless'),),
         extra_evidence=('.cache/library38_browser_result.json','.cache/图片素材库_缩略图验证.png','.cache/三维贴图_自导入素材库验证.png','.cache/素材库_UI复核_经典_800x600.png','.cache/素材库_UI复核_玻璃_800x600.png'),
         web_markers=('AE_COPY_PASTE_AND_FIT_HANDLERS_OK','MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK','AE_LIVE_TINT_INPUT_AND_STALE_REFRESH_OK','ASSET_LIBRARY_BROWSER_IMPORT_SEARCH_PERSIST_AND_PAINT_EXPORT_OK','UI_LIBRARY_THEMES_COMPACT_LAYOUT_AND_LAST_SELECTION_OK'))
