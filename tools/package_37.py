"""Portable GIF/video import with its local FFmpeg-backed decoder included."""
from package_34 import main

if __name__=='__main__':
    main(version='3.7',label='GIF视频动画导入版',ui_count=43,preset_count=36,
         extra_guide='AE 窗口点击“导入 GIF / 视频动画…”，选择片段、帧率及背景处理；导入后自动打开素材预览，可继续调色、贴面和摆放。单次最多 128 帧，只导入画面，不含音轨。\n',
         extra_tests=('tests.test_ae_pattern','tests.test_meteor_preset','tests.test_ae_media'),
         runtime_packages=(('cv2','opencv-python-headless'),),
         web_markers=('AE_COPY_PASTE_AND_FIT_HANDLERS_OK','MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK','AE_LIVE_TINT_INPUT_AND_STALE_REFRESH_OK'))
