"""Update 3.2 labels and import the two reviewed, portable presets."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_presets
from wotcamo.common import ROOT

for name in ('wotcamo/gui.py','wotcamo/ae_help.py','wotcamo/workbench_help.py'):
    path=ROOT/name;data=path.read_text(encoding='utf-8')
    data=data.replace('33 款','35 款').replace('3.1 灯效','3.2 灯效').replace('灯效制作器  ·  3.1','灯效制作器  ·  3.2')
    if name.endswith('ae_help.py'):
        data=data.replace('视觉增强 8 款。','视觉增强 8 款、液态玻璃 2 款。')
    path.write_text(data,encoding='utf-8')
path=ROOT/'tests/test_unified31.py';data=path.read_text(encoding='utf-8').replace("self.assertEqual(__version__,'3.1')","self.assertEqual(__version__,'3.2')");path.write_text(data,encoding='utf-8')
path=ROOT/'tools/preset_notes_catalog.py';data=path.read_text(encoding='utf-8')
data+='\n# Original translucent glass-inspired additions in 3.2.\nROWS.extend([\n'
data+=" ('半透明水滴和水纹，适合蓝白和水着涂装。','车体侧面、侧裙或角色周围。','可调整颜色与着色强度。','调整长宽，保留水滴形状。'),\n"
data+=" ('玻璃质感流带与水珠，适合长条装甲。','长侧裙或角色背景。','默认冰蓝，可自由调色。','长宽可独立调整。')])\n"
path.write_text(data,encoding='utf-8')
path=ROOT/'tests/test_ae_preset_notes.py';data=path.read_text(encoding='utf-8').replace('test_all_33_annotations','test_all_35_annotations').replace('len(catalog.ROWS),33','len(catalog.ROWS),35').replace('range(1,34)','range(1,36)');path.write_text(data,encoding='utf-8')
out=ROOT.parents[1]/'交付/液态玻璃AE预设_新增2款'
for path in sorted(out.glob('*.aepreset')):
    data,payload=ae_presets.read(path);ae_presets.store(data,path.read_bytes(),ROOT/'预设/AE特效')
records,issues=ae_presets.scan(ROOT/'预设/AE特效');assert len(records)==35 and not issues
print('PREPARED_32',len(records))
