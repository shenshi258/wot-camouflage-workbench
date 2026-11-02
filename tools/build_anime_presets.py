"""Original deterministic looping sprites for anime skins. No GUI/GPU/game use.

All emitters are periodic functions of phase. Moving particles cross the outer
frame with zero opacity, so the last/first frame have the same temporal spacing
as adjacent frames. Source RGB is straight alpha for the workbench's 5/2 blend.
"""
import ctypes,hashlib,io,json,math,random,sys,zipfile
from ctypes import wintypes
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae,ae_presets as presets
from wotcamo.common import ROOT

WORKSPACE=ROOT.parents[1]
OUT=WORKSPACE/'交付/二次元特效预设_新增12款'
CACHE=ROOT/'.cache/anime_presets'
W,H,S,N,FPS=384,144,2,96,24
TAU=math.tau

def background():
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.SetPriorityClass.restype=wintypes.BOOL
    assert k.SetPriorityClass(wintypes.HANDLE(-1),0x00100000)

def color(hex_value):return tuple(int(hex_value[i:i+2],16) for i in (1,3,5))
def mix(a,b,t):return tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))
def fade(t):return math.sin(math.pi*t)**2
def point(x,y):return round(x*W*S,5),round(y*H*S,5)

class Canvas:
    def __init__(self):
        self.image=Image.new('RGBA',(W*S,H*S));self.draw=ImageDraw.Draw(self.image)
    def line(self,points,rgb,width=1,alpha=255):
        self.draw.line([point(x,y) for x,y in points],fill=(*rgb,round(max(0,min(255,alpha)))),width=max(1,round(width*S)),joint='curve')
    def dot(self,x,y,r,rgb,alpha=255):
        px,py=point(x,y);r*=S;self.draw.ellipse((px-r,py-r,px+r,py+r),fill=(*rgb,round(max(0,min(255,alpha)))))
    def polygon(self,points,rgb,alpha=255):self.draw.polygon([point(x,y) for x,y in points],fill=(*rgb,round(max(0,min(255,alpha)))))
    def star(self,x,y,r,rgb,alpha=255,angle=0):
        pts=[]
        for i in range(8):
            a=angle+TAU*i/8;length=r if i%2==0 else r*.22
            pts.append((x+math.cos(a)*length/W,y+math.sin(a)*length/H))
        self.polygon(pts,rgb,alpha)
    def curve(self,x,y,size,angle,kind,rgb,alpha=255):
        points=[]
        for i in range(65):
            t=TAU*i/64
            if kind=='heart':xx=16*math.sin(t)**3/17;yy=-(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))/17
            elif kind=='petal':
                # Notched tear-shaped sakura petal, rather than a plain ellipse.
                radius=(.78+.18*math.cos(t))*(1-.25*math.exp(-((t-math.pi)/.2)**2))
                xx=radius*math.cos(t);yy=.5*radius*math.sin(t)
            else:xx=math.cos(t);yy=.36*math.sin(t)
            xx*=size;yy*=size
            points.append((x+(xx*math.cos(angle)-yy*math.sin(angle))/W,y+(xx*math.sin(angle)+yy*math.cos(angle))/H))
        self.polygon(points,rgb,alpha)
    def finish(self):
        original=self.image.resize((W,H),Image.Resampling.LANCZOS)
        rgba=np.asarray(original,dtype=np.float32)/255
        energy=rgba[:,:,:3]*rgba[:,:,3:]
        light=Image.fromarray(np.uint8(np.clip(energy,0,1)*255),'RGB')
        soft=np.asarray(light.filter(ImageFilter.GaussianBlur(1.5)),dtype=np.float32)/255
        wide=np.asarray(light.filter(ImageFilter.GaussianBlur(4.5)),dtype=np.float32)/255
        contribution=np.clip(energy*.83+soft*.48+wide*.24,0,.97)
        alpha=contribution.max(2,keepdims=True)
        straight=np.divide(contribution,alpha,out=np.zeros_like(contribution),where=alpha>0)
        return Image.fromarray(np.uint8(np.concatenate([straight,alpha],axis=2)*255+.5),'RGBA')

def specks(c,t,seed,palette,count=32,drift=1):
    rng=random.Random(seed)
    for i in range(count):
        x=rng.random();base=rng.uniform(.2,.85);phase=rng.random();r=rng.uniform(.5,1.7)
        v=(phase+t*drift)%1;opacity=fade(v)*(.6+.4*math.sin(TAU*(t*2+phase))**2)
        c.dot((x+.14*math.sin(TAU*(t+phase)))%1,base+.06*math.sin(TAU*(t*2+x)),r,palette[i%len(palette)],220*opacity)

def petals(t):
    c=Canvas();rng=random.Random(72);pink=color('#FF85BB');cream=color('#FFD4E8')
    for i in range(23):
        p=rng.random();x=rng.random();size=rng.uniform(3,7);speed=rng.choice([1,2]);v=(p+t*speed)%1
        y=-.12+v*1.24;xx=x+.06*math.sin(TAU*(t+p))
        c.curve(xx,y,size,TAU*(t+p),'petal',mix(pink,cream,rng.random()),220*fade(v))
        c.line([(xx-size/W*.35,y),(xx+size/W*.45,y)],cream,.5,100*fade(v))
    specks(c,t,21,[pink,cream],14);return c.finish()

def hearts(t):
    c=Canvas();rng=random.Random(44);pink=color('#FF7CC7');violet=color('#DA9FFF')
    for i in range(16):
        phase=rng.random();x=rng.uniform(.08,.92);v=(phase+t)%1;y=1.12-v*1.25
        x+=.045*math.sin(TAU*(t+phase));size=rng.uniform(3.5,7.5)*(1+.12*math.sin(TAU*(t*2+phase)))
        c.curve(x,y,size,.16*math.sin(TAU*(t+phase)),'heart',mix(pink,violet,rng.random()),230*fade(v))
    specks(c,t,31,[pink,color('#FFE4F1')],25);return c.finish()

def galaxy(t):
    c=Canvas();palette=[color('#83D5FF'),color('#C29AFF'),color('#F5CBFF')];rng=random.Random(83)
    for i in range(42):
        x=rng.uniform(.03,.97);y=rng.uniform(.18,.83);phase=rng.random();radius=rng.uniform(1,4)
        a=(.22+.78*math.sin(TAU*(t+phase))**4)
        c.star(x+.014*math.sin(TAU*(t+phase)),y,radius,palette[i%3],245*a,math.pi/4 if i%4==0 else 0)
    for j in range(3):
        phase=(t+j/3)%1;x=-.1+phase*1.2;y=.25+j*.2
        c.line([(x-.1,y+.09),(x,y)],palette[j],1,180*fade(phase))
    return c.finish()

def aurora(t):
    c=Canvas();palette=[color('#56EBC9'),color('#73CEFF'),color('#B899FF')]
    for band in range(3):
        for layer in range(5):
            pts=[]
            for i in range(101):
                x=.02+.96*i/100;y=.5+.16*math.sin(TAU*(x*1.2-t+band*.12))+.035*layer+.022*math.sin(TAU*(x*3+t))
                pts.append((x,y))
            c.line(pts,palette[band],1.1,95-layer*12)
    specks(c,t,68,palette,24);return c.finish()

def holo(t):
    c=Canvas();cyan=color('#78EAFF');pink=color('#FF91D1')
    for i in range(20):
        x=.04+i*.048;y=.47+.07*math.sin(TAU*(i/8+t));a=45+110*math.sin(TAU*(t-i/24))**8
        c.line([(x,y-.13),(x+.018,y-.18)],cyan,.7,a)
        c.line([(x,y+.13),(x+.018,y+.08)],pink,.7,a)
    v=t%1;x=-.15+1.3*v
    for j in range(7):c.line([(x-j*.008,.16),(x+.1-j*.008,.84)],mix(cyan,pink,j/7),1.1,(175-j*20)*fade(v))
    for y in (.26,.74):c.line([(.05,y),(.95,y)],cyan,.7,60)
    return c.finish()

def lightning(t):
    c=Canvas();palette=[color('#B08AFF'),color('#73DEFF')]
    for j in range(3):
        rng=random.Random(150+j);pts=[];opacity=(.18+.82*math.sin(TAU*(t*3+j/3))**8)
        for i in range(28):
            x=.04+i*.92/27;y=.38+j*.12+.055*math.sin(TAU*(i*.37+t*2))+rng.uniform(-.05,.05)
            pts.append((x,y))
        c.line(pts,palette[j%2],1.2,235*opacity)
        c.line(pts,color('#F1E9FF'),.4,150*opacity)
        for index in (8,18):
            x,y=pts[index];c.line([(x,y),(x+.02,y-.08),(x+.06,y-.12)],palette[j%2],.7,140*opacity)
    specks(c,t,7,palette,16);return c.finish()

def feathers(t):
    c=Canvas();gold=color('#FFD57E');white=color('#FFF0CA');rng=random.Random(53)
    for i in range(13):
        phase=rng.random();x=rng.uniform(.05,.95);v=(phase+t)%1;y=1.12-v*1.25;angle=.4*math.sin(TAU*(t+phase))+.7
        size=rng.uniform(5,9);a=210*fade(v)
        c.curve(x,y,size,angle,'feather',mix(gold,white,.75),a)
        axis=(math.cos(angle)*size/W,math.sin(angle)*size/H)
        c.line([(x-axis[0],y-axis[1]),(x+axis[0],y+axis[1])],gold,.7,a)
        for k in (-.5,0,.5):c.line([(x+axis[0]*k,y+axis[1]*k),(x+axis[0]*k-.006,y+axis[1]*k+.025)],gold,.45,a)
    specks(c,t,18,[gold,white],22);return c.finish()

def magic(t):
    c=Canvas();blue=color('#86B4FF');purple=color('#D4A4FF');cx,cy=.5,.5
    for r in (37,44,51):
        pts=[(cx+math.cos(TAU*i/160)*r/W,cy+math.sin(TAU*i/160)*r/H) for i in range(161)]
        c.line(pts,blue if r!=44 else purple,.7,135)
    for i in range(12):
        angle=TAU*(i/12+t);r=48
        x=cx+math.cos(angle)*r/W;y=cy+math.sin(angle)*r/H
        c.star(x,y,2.7,purple,220,angle)
    for j in range(2):
        pts=[]
        for i in range(7):
            angle=-TAU*t*(1 if j==0 else -1)+i*TAU/3
            pts.append((cx+math.cos(angle)*30/W,cy+math.sin(angle)*30/H))
        c.line(pts,blue if j==0 else purple,.8,185)
    c.star(cx,cy,8,blue,130+80*math.sin(TAU*t)**2,math.pi/4)
    specks(c,t,101,[blue,purple],20);return c.finish()

def music(t):
    c=Canvas();pink=color('#FF97D8');cyan=color('#72E5F2');rng=random.Random(81)
    for i in range(12):
        x=.06+i*.08;phase=rng.random();y=.53+.12*math.sin(TAU*(t+phase));a=120+100*math.sin(TAU*(t+phase))**2;rgb=pink if i%2 else cyan
        c.dot(x,y,2.7,rgb,a);c.line([(x+.007,y),(x+.007,y-.13)],rgb,1,a)
        if i%3:c.line([(x+.007,y-.13),(x+.027,y-.09)],rgb,1,a)
    pts=[(.03+i*.94/140,.76+.025*math.sin(TAU*(i/14-t*3))) for i in range(141)]
    c.line(pts,cyan,.7,105);return c.finish()

def hexagons(t):
    c=Canvas();cyan=color('#79DEFF');violet=color('#BA8FFF');radius=12
    for row in range(3):
        for col in range(13):
            x=(col*23+(row%2)*11.5+38)/W;y=(row*21+50)/H
            if x>.94:continue
            a=25+175*max(0,math.cos(TAU*(t-x)))**10
            pts=[(x+math.cos(TAU*k/6+math.pi/6)*radius/W,y+math.sin(TAU*k/6+math.pi/6)*radius/H) for k in range(7)]
            c.line(pts,mix(cyan,violet,row/3),.8,a)
    specks(c,t,40,[cyan,violet],12);return c.finish()

def comet(t):
    c=Canvas();palette=[color('#FF95D4'),color('#BB9DFF'),color('#78DFFF')]
    for j in range(3):
        v=(t+j/3)%1;head=-.1+1.2*v;y=.42+j*.12
        for k in range(34):
            d=k/34;xx=head-d*.25;yy=y+.04*math.sin(TAU*(xx*2-t))
            c.dot(xx,yy,1.7*(1-d)+.3,palette[j],220*(1-d)**2*fade(v))
        c.star(head,y+.04*math.sin(TAU*(head*2-t)),4,palette[j],240*fade(v))
    specks(c,t,65,palette,22);return c.finish()

def snow(t):
    c=Canvas();ice=color('#9BDFFF');white=color('#E8F7FF');rng=random.Random(15)
    for i in range(18):
        phase=rng.random();x=rng.random();v=(phase+t)%1;y=-.13+1.26*v;x+=.025*math.sin(TAU*(t+phase));size=rng.uniform(3,6);alpha=210*fade(v)
        for j in range(3):
            angle=j*math.pi/3+.35*math.sin(TAU*t)
            dx=math.cos(angle)*size/W;dy=math.sin(angle)*size/H
            c.line([(x-dx,y-dy),(x+dx,y+dy)],mix(ice,white,.5),.8,alpha)
            for sign in (-1,1):
                for twist in (-.65,.65):
                    px=x+dx*.6*sign;py=y+dy*.6*sign;end=angle+twist+math.pi*(sign<0)
                    c.line([(px,py),(px-math.cos(end)*size*.27/W,py-math.sin(end)*size*.27/H)],ice,.6,alpha)
    specks(c,t,22,[ice,white],20);return c.finish()

SPECS=[
 ('05 樱粉花瓣飘落',petals,'粉白、校园、偶像风；适合车体侧裙或角色背景。',3.8),
 ('06 桃心祈愿',hearts,'可爱、甜系涂装；爱心缓慢上浮，保留大部分底图。',3.4),
 ('07 蓝紫星砂银河',galaxy,'星空、科幻角色；星芒闪烁配少量斜向流星。',4.2),
 ('08 薄荷极光丝带',aurora,'蓝绿、清爽配色；适合侧裙、炮塔下缘的细流光。',4.5),
 ('09 樱蓝全息扫光',holo,'粉蓝科技风；稀疏刻线和斜向扫描光束。',4.0),
 ('10 紫晶电弧',lightning,'机甲、暗色角色；细电弧周期跳动，避免整块发白。',3.8),
 ('11 鎏金圣光羽',feathers,'金白、天使、典雅涂装；柔光羽片缓慢漂移。',3.5),
 ('12 月环魔法阵',magic,'魔法、月光、紫蓝角色；适合炮塔侧面或装甲圆徽区域。',2.4),
 ('13 糖果电音音符',music,'偶像、音乐主题；粉青音符轻摆配细音波。',4.0),
 ('14 冰蓝六角光域',hexagons,'科幻、机械风；线框六角单元依次点亮，底图仍可见。',4.2),
 ('15 梦彩彗尾流光',comet,'粉紫蓝通用配色；三路细彗尾沿车身方向流动。',4.4),
 ('16 晶蓝雪花轻落',snow,'冰雪、冬装、浅蓝角色；细雪花旋转下落。',3.8),
]

def composite(frame,gain=1):
    a=np.asarray(frame,dtype=np.float32)/255
    yy,xx=np.indices((H,W));shade=np.where((xx//12+yy//12)%2,20,29)
    bg=np.stack([shade*.82,shade*.95,shade*1.25],axis=2)/255
    return Image.fromarray(np.uint8(np.clip(a[:,:,:3]*a[:,:,3:]*gain+bg,0,1)*255),'RGB')

def main():
    background();resume='--resume' in sys.argv;OUT.mkdir(exist_ok=resume);CACHE.mkdir(parents=True,exist_ok=True);(OUT/'动画预览').mkdir(exist_ok=resume)
    report=[];posters=[]
    for name,renderer,description,width in SPECS:
        folder=CACHE/name;folder.mkdir(exist_ok=True)
        previous=OUT/(name+'.aepreset')
        if resume and previous.exists():
            metadata,atlas=presets.read(previous);frames=[]
            with Image.open(io.BytesIO(atlas)) as source:
                for rect in metadata['clip']['rects']:
                    x=round(rect[0]*source.width-.5);y=round(rect[1]*source.height-.5)
                    frames.append(source.crop((x,y,x+W,y+H)).convert('RGBA'))
        else:frames=[renderer(i/N) for i in range(N)]
        # Closure is evaluated at the actual next frame, not by duplicating the
        # first frame at the end (which would create a temporal pause).
        endpoint=renderer(1.)
        delta=np.abs(np.asarray(endpoint,dtype=float)-np.asarray(frames[0],dtype=float)).max()
        endpoint_mean=float(np.abs(np.asarray(endpoint,dtype=float)-np.asarray(frames[0],dtype=float)).mean())
        if endpoint_mean>.12:raise ValueError(name+' 不满足循环端点：'+str(endpoint_mean))
        clip=ae.pack_frames(frames,folder/'atlas.png');values=ae.config(dict(fps=FPS,width=width,brightness=1.,blend='add'))
        data,payload=presets.encode(name,description,clip,values)
        # Neutral-colour media stays importable in the previous 3.1 reader.
        data['config'].pop('tint_color',None);data['config'].pop('tint_strength',None)
        target=OUT/(name+'.aepreset')
        with zipfile.ZipFile(target,'w' if resume else 'x',zipfile.ZIP_DEFLATED) as z:
            z.writestr('preset.json',json.dumps(data,ensure_ascii=False));z.write(clip['atlas'],'atlas.png')
        recovered,loaded=presets.load(target,folder/'roundtrip');assert loaded['atlas_sha256']==clip['atlas_sha256']
        assert recovered['config']['tint_strength']==0
        # Same source alpha in every hue; check both the cached preview asset
        # and native DDS encoding path without starting an engine or WebView.
        colored=ae.colorized_clip(loaded,dict(values,tint_color='#FF70C8',tint_strength=100),folder/'color_check')
        with Image.open(colored['atlas']) as image,Image.open(loaded['atlas']) as source:
            assert image.getchannel('A').tobytes()==source.getchannel('A').tobytes()
            dds=Image.open(io.BytesIO(ae.dds(image))).convert('RGBA');assert dds.tobytes()==image.tobytes()
        previews=[composite(frame).quantize(colors=128) for frame in frames[::2]]
        gif=OUT/'动画预览'/(name+'.gif');previews[0].save(gif,save_all=True,append_images=previews[1:],duration=round(2000/FPS),loop=0,disposal=2)
        poster=composite(frames[N//3]);posters.append((name,poster,description))
        poster.save(OUT/'动画预览'/(name+'.png'))
        steps=[np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float)).mean() for a,b in zip(frames,frames[1:]+frames[:1])]
        if steps[-1]>max(.3,3*np.median(steps)):raise ValueError(name+' 循环交界变化过大')
        row=dict(name=name,file=target.name,frames=N,fps=FPS,seconds=N/FPS,frame_size=[W,H],atlas_size=clip['size'],bytes=target.stat().st_size,
                 sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source='Original procedural animation, deterministic seed and periodic motion',
                 blend='SRCALPHA/ONE',description=description,endpoint_max_delta=float(delta),endpoint_mean_delta=endpoint_mean,mean_frame_step=float(np.mean(steps)),
                 last_to_first_step=float(steps[-1]),import_roundtrip='passed',alpha_and_dds_color_parity='passed',
                 in_game_tested=False,whole_vehicle_loading=dict(status='not_tested',reason='Media preset; no vehicle package or game observation'))
        report.append(row);print(name,'OK',target.stat().st_size,flush=True)
    font_path='C:/Windows/Fonts/msyh.ttc';title_font=ImageFont.truetype(font_path,23);small_font=ImageFont.truetype(font_path,14)
    sheet=Image.new('RGB',(1280,1030),'#111929');draw=ImageDraw.Draw(sheet)
    draw.text((28,17),'二次元涂装 · 12 款可导入动态特效',font=title_font,fill='#eaf1ff')
    draw.text((28,51),'透明背景 · 4 秒循环 · 24 FPS · 支持新版自定义颜色与着色强度',font=small_font,fill='#9daec8')
    for i,(name,poster,description) in enumerate(posters):
        x=22+(i%3)*420;y=88+(i//3)*231
        draw.rounded_rectangle((x,y,x+404,y+216),radius=12,fill='#1b273b',outline='#30405b')
        sheet.paste(poster,(x+10,y+8));draw.text((x+12,y+158),name,font=ImageFont.truetype(font_path,19),fill='#edf3ff')
        draw.text((x+12,y+188),description.split('；')[0],font=small_font,fill='#b6c3d9')
    sheet.save(OUT/'12款特效总览.png')
    (OUT/'制作与验证记录.json').write_text(json.dumps(dict(presets=report,no_gui_or_game_started=True),ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'导入与配色说明.txt').write_text('二次元涂装特效预设 · 新增 12 款\n\n解压合集 ZIP，AE 窗口 → 管理 / 导入… → 导入…，选择 .aepreset 后套用。每个预设自带透明图集，4 秒循环、24 FPS。\n\n新增调色功能：AE 窗口“播放与透明”页 → 特效颜色。可选颜色、调着色强度；0% 保留素材原色，100% 统一为自定义颜色。三维工具条也可调整。调色需本次工作台更新包；本合集的中性预设本身仍可导入上一版 3.1。\n\n适用建议：\n粉白/校园：樱粉花瓣、桃心祈愿、糖果电音。\n蓝紫/科幻：星砂银河、极光丝带、全息扫光、紫晶电弧、六角光域。\n金白/圣光：鎏金圣光羽。\n魔法/冰雪：月环魔法阵、晶蓝雪花。\n通用流光：梦彩彗尾。\n\n建议贴在侧裙、炮塔下缘或角色周围，避开角色面部；先保持默认亮度，按底图再微调。左右需要同时出现时勾选“左右双侧显示”。\n动画预览为带棋盘底的参考合成图；素材本身透明，游戏曝光和泛光仍需在最终包中实测。\n\n本次不生成或安装车辆模组，不打开制作器、WebView 或游戏窗口。所有素材为程序原创动画。\n',encoding='utf-8-sig')
    target=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in OUT.rglob('*'):
            if file.is_file():z.write(file,(Path(OUT.name)/file.relative_to(OUT)).as_posix())
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    target.with_name(target.name+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print('PRESET_PACK',str(target),digest,flush=True)

if __name__=='__main__':main()
