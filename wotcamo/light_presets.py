"""Editable JSON presets. Importing a preset never executes code."""
import copy
import json
import shutil
from pathlib import Path
from .common import ROOT, write_json
from . import light_recipe

LIBRARY_PATH = ROOT / '预设/我的灯效预设.json'
DESCRIPTIONS = {'流水渐变':'颜色按方向平滑传播，亮度保持稳定。',
    '百花齐放':'各灯段错开颜色和呼吸，相位由灯段名称稳定生成。',
    '动态呼吸':'整体同步渐亮渐暗，可同时缓慢换色。','波浪':'明暗波沿所选方向传播。',
    '跑马灯':'窄亮带追逐移动，亮灯比例控制亮带宽度。','流水呼吸':'旧版原生呼吸叠加颜色流水。'}

# Styling presets reuse the supported export modes; no unverified shader modes.
NEW_PRESETS = (
    ('赛博霓虹','波浪',['#00E5FF','#FF00CC','#7433FF'],'向车头',.8,2.4,2.4,.04,.8,.3,'青、品红与紫色组成高反差霓虹波浪。'),
    ('极光漫游','流水渐变',['#00FFC8','#32A8FF','#8968FF','#C4FFB5'],'向车尾',3,4,1.8,.2,.8,.3,'青绿与冷紫缓慢漂移，保持柔和亮度。'),
    ('熔岩脉冲','动态呼吸',['#FF2500','#FF7300','#FFD34D'],'同步',1,3,2.4,.03,0,.3,'红橙金同步起伏，呈现熔岩般的热色脉冲。'),
    ('冰蓝心跳','动态呼吸',['#168BFF','#CCF5FF'],'同步',2,2,2,.02,0,.3,'冰蓝与霜白在同步呼吸中交替。'),
    ('樱花星河','百花齐放',['#FFB8DE','#FF65B8','#AD82FF'],'同步',2,4,1.8,.18,.4,.3,'粉色与淡紫错相闪耀，适合装饰灯和轮灯。'),
    ('彩虹追光','跑马灯',['#FF3030','#FFD020','#30FF80','#00D9FF','#9933FF','#FF00CC'],'向车头',.6,1.8,2.5,.015,.7,.22,'六色窄亮带沿车身追逐移动。'),
    ('深海涟漪','波浪',['#0838FF','#00C2FF','#00FFD5'],'四周扩散',2,4,2,.04,1.2,.3,'深蓝到青绿的明暗波按部件局部范围向外扩散。'),
    ('紫电疾行','跑马灯',['#7433FF','#E2C2FF','#00D9FF'],'向车尾',.6,1.2,2.6,.015,.6,.16,'紫电与冷白窄亮带快速反向追逐。'),
    ('日落余晖','流水渐变',['#FF5B35','#FFB347','#FF69B4','#893CFF'],'向车尾',3,4,1.8,.2,.6,.3,'橙金、玫红和紫色缓慢流动。'),
    ('薄荷糖霜','流水渐变',['#ADFFE2','#B8E7FF','#EECFFF'],'向车头',2,3,1.6,.3,.6,.3,'浅薄荷、冰蓝与薰衣草的柔和渐变。'),
    ('玫瑰金呼吸','动态呼吸',['#FF729E','#FFD6A5'],'同步',3,6,1.8,.12,0,.3,'暖粉与香槟金缓慢同步呼吸。'),
    ('翡翠流星','跑马灯',['#15FF81','#B6FF35','#D8FFF0'],'向车头',1,2,2.2,.02,.8,.28,'绿色追光搭配浅色尾段，突出移动亮带。'),
    ('星际巡航','波浪',['#265BFF','#994DFF','#00E5FF'],'向车尾',1.5,3,2.2,.06,1,.3,'蓝紫青波浪从前向后依次传播。'),
    ('金色能量环','波浪',['#FF9D00','#FFE88C'],'四周扩散',2,4,2.2,.04,1,.3,'金色明暗波由各部件的局部中心扩散。'),
    ('霓虹花火','百花齐放',['#FF00CC','#00FFD5','#FFD020','#7F45FF'],'同步',.8,2.4,2.5,.03,.4,.3,'多段独立错相，形成密集多彩的闪耀效果。'),
    ('双色交响','动态呼吸',['#FF2675','#24CFFF'],'同步',1,2,2.2,.06,0,.3,'玫红与电光蓝同步交替，轮廓清晰。'),
)

# Named styles requested by the user. They use the maker's existing animation
# primitives, not a claim to reproduce another application's trigger or shader.
REFERENCE_PRESETS = (
    ('无级变色','无级变色',['#FF3030','#FFD020','#30FF80','#00D9FF','#8740FF','#FF30A5'],'向车头',2,2,2,1,.65,.3,'连续沿色相过渡，不叠加明暗呼吸；可自行选择色标与方向。'),
    ('常亮模式','流水渐变',['#EAFBFF'],'同步',2,2,1.8,1,0,.3,'稳定单色常亮；可在调色盘更换颜色。'),
    ('呼吸模式','动态呼吸',['#8BD7FF'],'同步',2,3,2,.08,0,.3,'单色同步渐亮渐暗。'),
    ('梦幻彩虹','动态呼吸',['#FF83C5','#FFD683','#92FFCC','#87B9FF','#BE8BFF'],'同步',1.2,3,2,.18,0,.3,'柔和彩虹连续换色，整体同步呼吸。'),
    ('一触即发','波浪',['#FF541F','#FFD367'],'向车头',1,1,2.4,.03,.45,.22,'快速暖色波浪；自动循环，不响应按键或事件触发。'),
    ('雨中漫步','百花齐放',['#398BFF','#74DEFF','#D7F7FF'],'同步',1,2,1.8,.12,.3,.3,'蓝白灯段错相闪烁，模拟雨点。'),
    ('涟漪扩散','波浪',['#25BFFF','#9CF9FF'],'四周扩散',2,3,2,.08,.9,.3,'明暗波从各部件局部中心扩散。'),
    ('繁星点点','百花齐放',['#F6FBFF','#87BCFF'],'同步',1,2,1.8,.03,.2,.3,'不同灯段错相闪耀，模拟星光。'),
    ('川流不息','流水渐变',['#05D6FF','#467AFF','#71FFD7'],'向车头',.8,2,2,1,.65,.3,'冷色灯带连续向车头换色。'),
    ('随波逐流','波浪',['#09ACFF','#8AF5FF','#1E5CFF'],'向车尾',1,2,2,.12,.8,.3,'蓝色明暗波沿车身流动。'),
    ('如影随形','动态呼吸',['#B5A2FF','#6C8AFF'],'同步',2,4,1.6,.2,0,.3,'紫蓝色同步缓慢呼吸。'),
    ('正弦光波','波浪',['#42C9FF'],'向车头',2,3,2,.1,.8,.3,'单色明暗按正弦波传播。'),
    ('旋转风车','百花齐放',['#FFEF8C','#FF8040','#FFFFFF'],'同步',1,2,2,.04,.5,.25,'多灯段错相闪动；非真实角度旋转或车轮动画。'),
    ('七彩瀑布','流水渐变',['#FF3030','#FFD020','#30FF80','#00D9FF','#8740FF','#FF30A5'],'向车尾',.5,2,2,1,.8,.3,'六色连续向车尾流动。'),
    ('花开富贵','波浪',['#FF315B','#FFAA32','#FFE790'],'四周扩散',1.5,3,2.2,.12,.8,.3,'红金色明暗波从部件局部中心扩散。'),
)


def defaults():
    def entry(mode, colors, direction='向车头', low=.08, delay=.65):
        return {'说明':DESCRIPTIONS.get(mode,'连续变色，不叠加明暗呼吸。'), '配方':{'效果模式':mode,
            '颜色':[{'名称':'颜色%d'%(i+1),'RGB':c} for i,c in enumerate(colors)],
            '每色秒数':2,'呼吸周期秒数':2,'峰值倍率':2,'暗相系数':low,
            '流水方向':direction,'每米延迟秒数':delay,'亮灯比例':.3}}
    colors=['#0838FF','#FF1A75','#FFBF0A'];rainbow=['#FF3030','#FFD020','#30FF80','#3080FF','#D040FF']
    records={'流水渐变':entry('流水渐变',colors),'百花齐放':entry('百花齐放',rainbow,'同步'),
        '动态呼吸':entry('动态呼吸',['#66BFFF'],'同步'),'波浪':entry('波浪',colors,delay=1),
        '跑马灯':entry('跑马灯',colors,low=.02,delay=1),'蓝粉黄流水呼吸':entry('流水呼吸',colors),
        '彩虹流水':entry('流水渐变',rainbow),'单色呼吸':entry('动态呼吸',['#66BFFF'],'同步'),
        '全车同步换色':entry('流水渐变',colors,'同步'),'四周扩散':entry('波浪',colors,'四周扩散',delay=1)}
    for name,mode,palette,direction,step,breath,peak,low,delay,duty,description in NEW_PRESETS + REFERENCE_PRESETS:
        record=entry(mode,palette,direction,low,delay)
        record['说明']=description
        record['配方'].update({'每色秒数':step,'呼吸周期秒数':breath,'峰值倍率':peak,'亮灯比例':duty})
        if name in ('无级变色','梦幻彩虹','川流不息','七彩瀑布'):
            record['配方']['换色曲线']='匀速'
        records[name]=record
    return records


def with_new_presets(records):
    """Expose new styles to existing libraries without overwriting saved recipes."""
    merged=copy.deepcopy(records);builtins=defaults()
    for row in NEW_PRESETS + REFERENCE_PRESETS:merged.setdefault(row[0],builtins[row[0]])
    return merged


def validate_library(data):
    if not isinstance(data,dict) or data.get('版本')!=1 or set(data)!={'版本','预设'} or not isinstance(data['预设'],dict):
        raise ValueError('预设文件应包含“版本: 1”和“预设”对象。')
    if not 1<=len(data['预设'])<=200:raise ValueError('预设库需要 1～200 个预设。')
    for name,record in data['预设'].items():
        if not isinstance(name,str) or not name.strip() or name!=name.strip() or len(name)>60:
            raise ValueError('预设名称需为 1～60 字，前后不能有空格。')
        if not isinstance(record,dict) or set(record)!={'说明','配方'} or not isinstance(record['说明'],str) or len(record['说明'])>1000:
            raise ValueError('每个预设需要“说明”和“配方”。')
        light_recipe.validate_config(record['配方'])
    return copy.deepcopy(data['预设'])


def load(path=None):
    path=Path(path or LIBRARY_PATH)
    return validate_library(json.loads(path.read_text(encoding='utf-8-sig'))) if path.exists() else defaults()


def save(records,path=None):
    path=Path(path or LIBRARY_PATH);data={'版本':1,'预设':records};validate_library(data)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():shutil.copy2(path,path.with_suffix('.json.bak'))
    write_json(path,data);return path


def import_file(path):
    return validate_library(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def export_file(records,path):
    data={'版本':1,'预设':records};validate_library(data);write_json(path,data)
