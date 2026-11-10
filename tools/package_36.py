"""3.6: colour-edit fixes and the additional original meteor-rain preset."""
from package_34 import main

if __name__=='__main__':
    main(version='3.6',label='彩色流星雨与调色修正版',ui_count=40,preset_count=36,
         extra_guide='AE 预设选择“36 彩色流星雨”，在“播放与透明”中调色。着色强度 0% 保留彩色原貌，100% 使用所选颜色；完整输入色号或取色会自动启用着色。动画预览见“程序/预设/AE预览”。\n',
         extra_tests=('tests.test_ae_pattern','tests.test_meteor_preset'),
         web_markers=('AE_COPY_PASTE_AND_FIT_HANDLERS_OK','MIRRORED_DRAG_BOTH_GEOMETRIES_AND_PICKED_SIDE_OK','AE_LIVE_TINT_INPUT_AND_STALE_REFRESH_OK'))
