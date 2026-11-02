"""Reuse verified 33-item GIFs and build the 35-item source-based gallery."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];workspace=ROOT.parents[1]
old=workspace/'交付/全部33款特效预览';out=workspace/'交付/全部35款特效预览'
if out.exists():raise RuntimeError('目标预览目录已存在')
out.mkdir();(out/'单款动画').mkdir()
old_manifest=json.loads((old/'预览制作与检查记录.json').read_text(encoding='utf-8'))
import sys
sys.path.insert(0,str(ROOT))
from wotcamo import ae_presets
records,issues=ae_presets.scan(ROOT/'预设/AE特效');assert len(records)==35 and not issues
lookup={r['name']:r for r in records}
for entry in old_manifest['effects']:
    source=lookup[entry['name']]['path']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==entry['preset_sha256']
    shutil.copy2(old/entry['gif'],out/entry['gif'])
for name in ('34 液态玻璃水滴','35 液态玻璃流带'):
    shutil.copy2(workspace/'交付/液态玻璃AE预设_新增2款/动画预览'/(name+'.gif'),out/'单款动画'/(name+'.gif'))
cache=ROOT/'.cache';(cache/'encoder_download').mkdir(exist_ok=True);(cache/'encoder').mkdir(exist_ok=True)
src=workspace/'projects/wot_workbench_31_visual33/.cache'
for item in (src/'encoder_download').glob('*.whl'):shutil.copy2(item,cache/'encoder_download'/item.name)
shutil.copy2(src/'encoder/ffmpeg.exe',cache/'encoder/ffmpeg.exe')
path=ROOT/'tools/build_all_effect_previews.py';s=path.read_text(encoding='utf-8')
s=s.replace('33款','35款').replace('33 款','35 款').replace('3.1 ·','3.2 ·').replace('ALL_33_PREVIEWS_READY','ALL_35_PREVIEWS_READY')
start=s.index('    previous,issues=ae_presets.scan(');end=s.index("    wheels=list(",start)
s=s[:start]+"    records,issues=ae_presets.scan(ROOT/'预设/AE特效');assert len(records)==35 and not issues\n"+s[end:]
s=s.replace("else '视觉增强新款'","else '视觉增强新款' if number<=33 else '液态玻璃'")
s=s.replace('min((page+1)*9,33)','min((page+1)*9,35)').replace("(1280,2740)","(1280,3000)")
s=s.replace('<button data-filter="视觉增强新款">新增 8 款</button>','<button data-filter="视觉增强新款">视觉增强</button><button data-filter="液态玻璃">液态玻璃</button>')
s=s.replace('素材均由 .aepreset 原图集重新读取，不复用旧版抽帧 GIF。','总览视频从各预设的原图集读取；逐款 GIF 复用已校验的完整循环预览。')
s=s.replace('未打开窗口或游戏，未安装模组。','未启动游戏，未安装模组。')
path=(ROOT/'tools/build_gallery_35.py');path.write_text(s,encoding='utf-8')
print('PREPARED_35_GALLERY',len(records))
