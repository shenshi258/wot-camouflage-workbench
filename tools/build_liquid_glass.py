"""Produce two original straight-alpha glass-inspired looping AE presets."""
import ctypes,hashlib,io,json,math,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets
from wotcamo.common import ROOT

W,H,S,N,FPS=384,144,2,96,24
OUT=ROOT.parents[1]/'交付/液态玻璃AE预设_新增2款'
TAU=math.tau

def render(which,t):
    """Shaded translucent forms simulate glass; they do not refract the game scene."""
    phase=TAU*(t%1);size=(W*S,H*S);image=Image.new('RGBA',size)
    def layer(draw_fn):
        part=Image.new('RGBA',size);draw_fn(ImageDraw.Draw(part));image.alpha_composite(part)
    def pt(x,y):return (round(x*S),round(y*S))
    def ellipse(cx,cy,rx,ry,fill,outline=None,width=1):
        layer(lambda d:d.ellipse((*pt(cx-rx,cy-ry),*pt(cx+rx,cy+ry)),fill=fill,outline=outline,width=width*S))
    def line(points,color,width=1):
        layer(lambda d:d.line([pt(*p) for p in points],fill=color,width=width*S,joint='curve'))
    if which==0:
        for i,(x,y,r) in enumerate([(57,76,17),(105,54,11),(148,87,14),(202,57,21),(252,91,12),(304,61,16),(347,88,9)]):
            y+=5*math.sin(phase+i*.9);x+=3*math.sin(phase+i*.7)
            ellipse(x,y,r,r*.78,(107,210,255,38),(141,225,255,140),1)
            ellipse(x-r*.16,y-r*.19,r*.66,r*.43,(188,239,255,23))
            points=[(x+r*.77*math.cos(a),y+r*.6*math.sin(a)) for a in np.linspace(3.5,5.0,20)]
            line(points,(255,255,255,220),2)
            ellipse(x-r*.35,y-r*.3,1.3,1,(255,255,255,210))
        for j in range(3):
            points=[(x,115+j*3+3*math.sin(x/38+phase+j)) for x in range(18,367,3)]
            line(points,(159,231,255,45-j*8),1)
    else:
        for j in range(3):
            top=[];bottom=[]
            for x in range(14,371,3):
                u=(x-14)/356;envelope=math.sin(math.pi*u)**.7
                center=63+j*12+11*math.sin(TAU*u-phase+j*.7)
                thickness=(6+j*1.4)*envelope
                top.append((x,center-thickness));bottom.append((x,center+thickness))
            polygon=[pt(*p) for p in top+bottom[::-1]]
            layer(lambda d,p=polygon,j=j:d.polygon(p,fill=[(120,216,255,35),(163,203,255,33),(207,235,255,35)][j]))
            line(top,(192,241,255,135-j*20),1)
            line(bottom,(107,191,255,95-j*15),1)
        for i in range(7):
            x=39+i*51;y=67+10*math.sin(phase+i*.8);r=3+(i%3)
            ellipse(x,y,r,r*.72,(177,237,255,60),(235,253,255,150),1)
        p=(math.sin(phase)+1)/2;x=38+308*p;y=60+11*math.sin(TAU*((x-14)/356)-phase)
        ellipse(x,y,5,2,(255,255,255,125))
    return image.resize((W,H),Image.Resampling.LANCZOS)

SPECS=[('34 液态玻璃水滴',0,4.0,'半透明水滴和柔和水纹，适合水着、蓝白或清爽二次元涂装。'),
       ('35 液态玻璃流带',1,4.2,'三层柔软玻璃质感流带与细小水珠，适合长侧裙和角色周边。')]

def note(spec):
    return '\n'.join(['用途：'+spec[3],'摆放：车体侧面、侧裙或角色周边；可拖动位置并分别调整长宽。',
        '配色：默认冰蓝透明，可在播放与透明中调整特效颜色及着色强度。',
        '形状：透明高光和轮廓模拟玻璃，贴面受选区裁剪；需要两侧时勾选左右双侧。',
        '显示：普通透明混合；这是动画模拟，不会实时折射或模糊车身底图。',
        '检查：预览与游戏光照、遮挡可能不同；游戏整车和效果待实测。'])

def composite(frame):
    yy,xx=np.indices((H,W));v=np.where((xx//12+yy//12)%2,29,20)
    bg=np.stack([v*.82,v*.95,v*1.25],axis=2)/255
    src=np.asarray(frame,dtype=np.float32)/255;a=src[:,:,3:]
    return Image.fromarray(np.uint8(np.clip(src[:,:,:3]*a+bg*(1-a),0,1)*255),'RGB')

def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    assert kernel.SetPriorityClass(ctypes.c_void_p(-1),0x40)
    OUT.mkdir();(OUT/'动画预览').mkdir();records=[];posters=[]
    for spec in SPECS:
        name,which,width,_=spec;folder=ROOT/'.cache/liquid_glass'/str(which);folder.mkdir(parents=True,exist_ok=True)
        frames=[render(which,i/N) for i in range(N)];assert render(which,0).tobytes()==render(which,1).tobytes()
        alpha=np.asarray(frames[0])[:,:,3];assert alpha.min()==0 and np.count_nonzero((alpha>0)&(alpha<200))>200
        clip=ae.pack_frames(frames,folder/'atlas.png');values=ae.config(dict(fps=FPS,width=width,brightness=1,blend='alpha'))
        meta,payload=ae_presets.encode(name,note(spec),clip,values);target=OUT/(name+'.aepreset');target.write_bytes(payload)
        recovered,png=ae_presets.read(target);assert recovered['config']['blend']=='alpha' and hashlib.sha256(png).hexdigest()==clip['atlas_sha256']
        with Image.open(io.BytesIO(png)) as src:
            tinted=ae.colorize_rgba(src,dict(values,tint_color='#FF8CCB',tint_strength=100))
            assert tinted.getchannel('A').tobytes()==src.getchannel('A').tobytes()
        previews=[composite(frame).quantize(colors=128) for frame in frames]
        durations=[10*(round((i+1)*100/FPS)-round(i*100/FPS)) for i in range(N)]
        gif=OUT/'动画预览'/(name+'.gif');previews[0].save(gif,save_all=True,append_images=previews[1:],duration=durations,loop=0,disposal=2)
        with Image.open(gif) as animation:
            total=0
            for i in range(animation.n_frames):animation.seek(i);total+=animation.info.get('duration',0)
            assert total==4000
        poster=composite(frames[N//3]);poster.save(OUT/'动画预览'/(name+'.png'));posters.append((name,poster))
        records.append(dict(name=name,sha256=hashlib.sha256(payload).hexdigest(),frames=N,fps=FPS,blend='alpha',glass_is_simulated=True,in_game_tested=False))
        print(name,'完成',flush=True)
    sheet=Image.new('RGB',(830,440),'#101827');d=ImageDraw.Draw(sheet);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    for i,(name,poster) in enumerate(posters):
        sheet.paste(poster,(28,20+i*205));d.text((435,80+i*205),name,font=font,fill='#e6f7ff')
    sheet.save(OUT/'液态玻璃预览.png')
    (OUT/'使用说明.md').write_text('# 液态玻璃 AE 特效\n\n工作台 3.2 已内置；也可在 AE 窗口通过「管理 / 导入」单独导入 .aepreset。\n\n'+ '\n\n'.join('## '+s[0]+'\n\n'+note(s) for s in SPECS)+'\n',encoding='utf-8')
    (OUT/'离线检查.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    target=OUT.with_suffix('.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in OUT.rglob('*'):
            if p.is_file():z.write(p,(Path(OUT.name)/p.relative_to(OUT)).as_posix())
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    print('GLASS_PRESETS_READY',target,hashlib.sha256(target.read_bytes()).hexdigest(),flush=True)

if __name__=='__main__':main()
