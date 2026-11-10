"""Deterministic transparent meteor rain; baked RGB, no new native shader mode."""
import colorsys,hashlib,io,json,math,random,sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets as presets
from wotcamo.common import ROOT

NAME='36 彩色流星雨'
W,H,N,FPS=384,144,96,24
DESCRIPTION='\n'.join((
    '用途：多彩流星斜向划过，带有细长渐变尾迹和柔光星点，4 秒无缝循环。',
    '摆放：车体侧面或角色背后的横向留白；独立平面可保留完整图案，贴面会沿选区裁切。',
    '配色：0% 着色保留彩虹原色；输入色号或取色会启用着色，100% 统一为所选颜色，中间值混入新颜色。',
    '形状：建议等比完整；先调位置及宽度，再按需要裁剪或变形。',
    '显示：96 帧 / 24 FPS；透明软边，默认亮度 1 倍。高亮度可能冲淡颜色。',
    '检查：原文件保留，颜色随预设及工程保存；生成后再安装。实际客户端与游戏内效果待实测。'))


def render(phase):
    # 在 2 倍分辨率计算加法光能，再还原 straight alpha；透明区没有黑底。
    phase=float(phase)%1
    yy,xx=np.mgrid[:H*2,:W*2].astype(np.float32);xx/=2;yy/=2
    energy=np.zeros((*xx.shape,3),np.float32)
    rng=random.Random(36036)
    for i in range(24):
        start=rng.random();lane=rng.uniform(28,116);length=rng.uniform(18,46);width=rng.uniform(.65,1.05)
        p=(phase+start)%1;envelope=math.sin(math.pi*p)**2
        cx=W+65-p*(W+130);cy=lane+(p-.5)*120
        # 尾迹方向与运动方向相反，头部和尾部均使用连续软边。
        dx,dy=.975,-.222
        along=(xx-cx)*dx+(yy-cy)*dy;across=-(xx-cx)*dy+(yy-cy)*dx
        tail=np.exp(-np.maximum(along,0)/length)*np.exp(-.5*(across/width)**2)*np.clip(along+1,0,1)
        head=np.exp(-((xx-cx)**2+(yy-cy)**2)/2.2)
        glow=np.exp(-((xx-cx)**2+(yy-cy)**2)/22)*.12
        hue=(i/24+.07*math.sin(math.tau*phase))%1
        first=np.array(colorsys.hsv_to_rgb(hue,.82,1),np.float32)
        last=np.array(colorsys.hsv_to_rgb((hue+.14)%1,.85,1),np.float32)
        mix=np.clip(along/(length*2),0,1)[...,None]
        energy+=envelope*((first*(1-mix)+last*mix)*tail[...,None]*1.2+first*(head+glow)[...,None])
        cross=np.exp(-((xx-cx)/2.4)**2-((yy-cy)/.28)**2)+np.exp(-((xx-cx)/.28)**2-((yy-cy)/2.4)**2)
        energy+=envelope*cross[...,None]*first*.17
    for i in range(22):
        x=rng.uniform(6,W-6);y=rng.uniform(8,H-8);offset=rng.random()
        alpha=.06+.14*math.sin(math.tau*(phase+offset))**2
        rgb=np.array(colorsys.hsv_to_rgb((i/22+.1)%1,.65,1),np.float32)
        energy+=rgb*np.exp(-((xx-x)**2+(yy-y)**2)/.65)[...,None]*alpha
    # 对光能降采样后再拆分 RGB/Alpha，避免半透明边缘二次预乘。
    light=Image.fromarray(np.uint8(np.clip(energy,0,.97)*255+.5)).resize((W,H),Image.Resampling.LANCZOS)
    energy=np.asarray(light,dtype=np.float32)/255
    alpha=energy.max(2,keepdims=True)
    rgb=np.divide(energy,alpha,out=np.zeros_like(energy),where=alpha>0)
    return Image.fromarray(np.uint8(np.concatenate((rgb,alpha),axis=2)*255+.5))


def composite(frame):
    rgba=np.asarray(frame,dtype=np.float32)/255
    yy,xx=np.mgrid[:H,:W];shade=np.where((xx//16+yy//16)%2,18,25)
    background=np.stack((shade*.75,shade*.95,shade*1.4),axis=2)/255
    return Image.fromarray(np.uint8(np.clip(rgba[:,:,:3]*rgba[:,:,3:]+background,0,1)*255+.5))


def main():
    cache=ROOT/'.cache/meteor36';cache.mkdir(parents=True,exist_ok=True)
    frames=[render(i/N) for i in range(N)]
    clip=ae.pack_frames(frames,cache/'atlas.png')
    values=ae.config(dict(fps=FPS,width=4,brightness=1,blend='add',fit_mode='contain'))
    data,payload=presets.encode(NAME,DESCRIPTION,clip,values)
    target=presets.library_file(NAME)
    if target.exists():
        old,old_atlas=presets.read(target)
        if old!=data or old_atlas!=Path(clip['atlas']).read_bytes():
            if '--rebuild' not in sys.argv:raise RuntimeError('预设已存在且内容不同；请先核对原文件。')
            previous=target.read_bytes();backup=cache/(hashlib.sha256(previous).hexdigest()+'.aepreset')
            if not backup.exists():backup.write_bytes(previous)
            target.write_bytes(payload)
    else:target.write_bytes(payload)
    media=ROOT/'预设/AE预览';media.mkdir(exist_ok=True)
    previews=[composite(frame).quantize(colors=128) for frame in frames]
    durations=[10*(round((i+1)*100/FPS)-round(i*100/FPS)) for i in range(N)]
    previews[0].save(media/(NAME+'.gif'),save_all=True,append_images=previews[1:],duration=durations,loop=0,disposal=2)
    composite(frames[32]).save(media/(NAME+'.png'))
    variants=[composite(frames[32]),composite(ae.colorize_rgba(frames[32],dict(tint_color='#00C8FF',tint_strength=100))),composite(ae.colorize_rgba(frames[32],dict(tint_color='#FF2080',tint_strength=100)))]
    sheet=Image.new('RGB',(W,H*3))
    for i,im in enumerate(variants):sheet.paste(im,(0,i*H))
    sheet.save(cache/'彩色与改色对照.png')
    arrays=[np.asarray(frame,dtype=np.float32) for frame in frames]
    steps=[float(np.abs(a-b).mean()) for a,b in zip(arrays,arrays[1:]+arrays[:1])]
    assert np.abs(np.asarray(render(1),dtype=float)-arrays[0]).max()==0
    assert steps[-1]<=3*np.median(steps)
    report=dict(name=NAME,file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),frames=N,fps=FPS,
        last_to_first_step=steps[-1],median_adjacent_step=float(np.median(steps)),endpoint_equal=True,
        in_game_tested=False,actual_running_client='not_confirmed',whole_vehicle_loading={'status':'not_tested'})
    (media/'彩色流星雨离线检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('METEOR_PRESET_READY',target,flush=True)


if __name__=='__main__':main()
