"""Eight original layered loop animations; CPU-only background media authoring.

Reuse the established straight-alpha 5/2 rendering recipe. All motion is a
periodic function of phase; lifespan emitters fade at both wrapped endpoints.
No game resources, shaders or attachment scripts are changed by this tool.
"""
import hashlib,io,json,math,random,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_anime_presets as b
from wotcamo import ae_effects as ae,ae_presets as presets
from wotcamo.common import ROOT

W,H,N,FPS=b.W,b.H,b.N,b.FPS
T=math.tau
OUT=ROOT.parents[1]/'交付/视觉增强特效预设_新增8款'
CACHE=ROOT/'.cache/visual_presets'


def xy(x,y):return x/W,y/H

class Canvas(b.Canvas):
    def finish(self):
        rgba=np.asarray(self.image.resize((W,H),Image.Resampling.LANCZOS),dtype=np.float32)/255
        energy=rgba[:,:,:3]*rgba[:,:,3:]
        light=Image.fromarray(np.uint8(np.clip(energy,0,1)*255),'RGB')
        soft=np.asarray(light.filter(ImageFilter.GaussianBlur(1.8)),dtype=np.float32)/255
        wide=np.asarray(light.filter(ImageFilter.GaussianBlur(5.5)),dtype=np.float32)/255
        contribution=np.clip(energy*.95+soft*.65+wide*.35,0,.97)
        alpha=contribution.max(2,keepdims=True)
        straight=np.divide(contribution,alpha,out=np.zeros_like(contribution),where=alpha>0)
        return Image.fromarray(np.uint8(np.concatenate([straight,alpha],axis=2)*255+.5),'RGBA')


def halo(c,cx,cy,rx,ry,rgb,alpha):
    for j in range(24,0,-1):
        scale=j/24
        c.polygon([xy(cx+rx*scale*math.cos(T*k/80),cy+ry*scale*math.sin(T*k/80)) for k in range(81)],rgb,alpha*(1-scale)**1.5)


def ellipse(c,cx,cy,rx,ry,angle,rgb,alpha=180,width=.8,start=0,span=1):
    pts=[]
    for i in range(81):
        a=start+T*span*i/80;x=rx*math.cos(a);y=ry*math.sin(a)
        pts.append(xy(cx+x*math.cos(angle)-y*math.sin(angle),cy+x*math.sin(angle)+y*math.cos(angle)))
    c.line(pts,rgb,width,alpha)


def ribbon(c,points,width,first,last,alpha=180):
    """Tapered, shaded quads form a real band rather than a constant-width line."""
    for i,(p,q) in enumerate(zip(points,points[1:])):
        u=(i+.5)/(len(points)-1);dx=q[0]-p[0];dy=q[1]-p[1];length=max(math.hypot(dx,dy),1e-6)
        nx=-dy/length;ny=dx/length;half=width*math.sin(math.pi*u)**.7
        c.polygon([xy(p[0]+nx*half,p[1]+ny*half),xy(q[0]+nx*half,q[1]+ny*half),
                   xy(q[0]-nx*half,q[1]-ny*half),xy(p[0]-nx*half,p[1]-ny*half)],b.mix(first,last,u),alpha)


def butterfly(c,cx,cy,size,angle,phase,pink,blue):
    flap=.35+.65*abs(math.sin(T*phase))
    for sign in (-1,1):
        for lower in (False,True):
            pts=[];count=25
            for i in range(count):
                a=T*i/(count-1);r=math.sin(math.pi*i/(count-1))**.55
                x=sign*(.12+.9*r*(.8+.2*math.cos(a)))*size*flap
                y=(.22 if lower else -.31)*size+math.sin(a)*size*(.4 if lower else .65)
                if lower:x*=.78
                pts.append(xy(cx+x*math.cos(angle)-y*math.sin(angle),cy+x*math.sin(angle)+y*math.cos(angle)))
            c.polygon(pts,pink if sign<0 else blue,150 if lower else 185)
            c.line(pts,pink if sign>0 else blue,.55,225)
    c.line([xy(cx-math.sin(angle)*size*.55,cy+math.cos(angle)*size*.55),
            xy(cx+math.sin(angle)*size*.6,cy-math.cos(angle)*size*.6)],b.color('#FFF0FF'),.7,230)


def butterflies(t):
    c=Canvas();pink=b.color('#FF91D0');blue=b.color('#8EE9FF');white=b.color('#FFF0FF')
    for j in range(2):
        points=[(22+340*u,72+24*math.sin(T*(u+.15*j+.07*math.sin(T*t)))) for u in np.linspace(0,1,100)]
        ribbon(c,points,1.0,pink,blue,45)
    for i in range(5):
        phase=(t+i/5)%1;cx=25+334*phase;cy=72+26*math.sin(T*(phase+i*.11))
        size=10+5*(.5+.5*math.sin(T*i/5));opacity=b.fade(phase)
        # A separate transparent layer gives the whole butterfly one envelope.
        layer=Canvas();butterfly(layer,cx,cy,size,.35*math.cos(T*phase),3*t+i*.3,pink,blue)
        a=layer.image.getchannel('A').point(lambda v:round(v*opacity));layer.image.putalpha(a)
        c.image.alpha_composite(layer.image)
        for k in range(10):
            p=(phase-.006*k)%1;x=25+334*p;y=72+26*math.sin(T*(p+i*.11))
            c.dot(x/W,y/H,.6+(9-k)*.055,white,110*(1-k/10)*opacity)
    b.specks(c,t,2626,[pink,blue,white],23)
    return c.finish()


def flower(t):
    c=Canvas();pink=b.color('#FF8FD3');blue=b.color('#9CE8FF');gold=b.color('#FFEBC0')
    cx,cy=192,72
    halo(c,cx,cy,64,58,pink,32)
    for layer in range(3):
        radius=49-layer*12;rotation=(.08 if layer%2 else -.06)*math.sin(T*t)+layer*.24
        for k in range(8):
            a=T*k/8+rotation;pts=[]
            for u in np.linspace(0,1,41):
                r=radius*math.sin(math.pi*u);side=radius*.24*math.sin(T*u)
                pts.append(xy(cx+r*math.cos(a)-side*math.sin(a),cy+r*math.sin(a)+side*math.cos(a)))
            rgb=b.mix(pink,blue,(k%4)/3)
            c.polygon(pts,rgb,45+layer*16);c.line(pts+[pts[0]],rgb,1.0,180+layer*20)
            c.line([xy(cx,cy),xy(cx+radius*.86*math.cos(a),cy+radius*.86*math.sin(a))],gold,.5,105)
    ellipse(c,cx,cy,13,13,0,gold,230,1)
    c.star(.5,.5,6,gold,190+45*math.sin(T*t)**2,math.pi/4)
    for side in (-1,1):
        points=[(cx+side*(38+u*130),cy+21*math.sin(math.pi*u+T*t)*u) for u in np.linspace(0,1,70)]
        ribbon(c,points,1.5,pink,blue,90)
        for j in range(6):
            phase=(t+j/6)%1;r=58+phase*102;a=.2*math.sin(T*(t+j/6))
            c.star((cx+side*r)/W,(cy+25*math.sin(T*(phase+.14*j)))/H,1.3+2*b.fade(phase),gold,210*b.fade(phase),a)
    return c.finish()


def gravity(t):
    c=Canvas();violet=b.color('#BE9AFF');blue=b.color('#70DAFF');white=b.color('#EAF9FF')
    halo(c,192,72,82,30,violet,28)
    for k in range(4):
        radius=45+k*5;ellipse(c,192,72,radius,radius*.32,-.24,violet if k%2 else blue,120+k*25,1.1)
    rng=random.Random(2828)
    for i in range(70):
        phase=rng.random();r=rng.uniform(43,69);a=T*(t+phase);x=r*math.cos(a);y=r*.31*math.sin(a)
        cx=192+x*math.cos(-.24)-y*math.sin(-.24);cy=72+x*math.sin(-.24)+y*math.cos(-.24)
        c.dot(cx/W,cy/H,rng.uniform(.5,1.4),b.mix(violet,white,(math.sin(a)+1)/2),95+150*(math.sin(a)+1)/2)
        ellipse(c,192,72,r,r*.31,-.24,blue,80,.65,start=a-.13,span=.018)
    ellipse(c,192,72,29,41,.37,violet,150,.8,start=T*t,span=.7)
    ellipse(c,192,72,29,41,.37,white,210,.8,start=T*t+math.pi,span=.11)
    for sign in (-1,1):
        points=[(192+sign*(38+137*u),72+sign*(7+12*u)+8*math.sin(T*(u-t))*u) for u in np.linspace(0,1,85)]
        ribbon(c,points,1.2,white,violet,110)
    b.specks(c,t,2899,[violet,blue,white],28)
    return c.finish()


def crystals(t):
    c=Canvas();palette=[b.color(x) for x in ('#8DEEFF','#C1A4FF','#FFB4E3')];white=b.color('#EEFCFF')
    for i,(cx,cy,size) in enumerate([(192,70,30),(135,78,18),(245,77,20),(87,64,12),(293,61,13)]):
        cy+=5*math.sin(T*(t+i*.17));sway=3*math.sin(T*(t+i*.2))
        top=(cx+sway,cy-size);right=(cx+size*.42,cy);bottom=(cx-sway,cy+size);left=(cx-size*.42,cy);center=(cx,cy-2)
        c.polygon([xy(*p) for p in (top,right,center)],palette[i%3],150)
        c.polygon([xy(*p) for p in (top,center,left)],palette[(i+1)%3],100)
        c.polygon([xy(*p) for p in (left,center,bottom)],palette[(i+2)%3],80)
        c.polygon([xy(*p) for p in (center,right,bottom)],palette[i%3],120)
        c.line([xy(*p) for p in (top,right,bottom,left,top)],white,.8,220)
        c.line([xy(*p) for p in (top,center,bottom)],white,.6,160)
        c.line([xy(*left),xy(*right)],white,.5,130)
        c.star(top[0]/W,top[1]/H,2.2,white,150+80*math.sin(T*(t+i*.17))**4,math.pi/4)
    for j in range(3):
        points=[(26+332*u,98-j*5+9*math.sin(T*(u+t)+j*.4)) for u in np.linspace(0,1,80)]
        ribbon(c,points,.7,palette[j],white,80)
    b.specks(c,t,2929,palette+[white],23)
    return c.finish()


def bubbles(t):
    c=Canvas();blue=b.color('#86E8FF');pink=b.color('#D9B6FF');white=b.color('#EDFFFF');rng=random.Random(3030)
    for j in range(4):
        points=[(15+354*u,83+j*5+9*math.sin(T*(u+t)+j*.75)+4*math.sin(T*(2*u-t))) for u in np.linspace(0,1,95)]
        ribbon(c,points,.65,blue,pink,65)
    for i in range(15):
        phase=(t+rng.random())%1;cx=rng.uniform(30,354)+6*math.sin(T*(t+i*.21));cy=128-phase*112;r=rng.uniform(5,16)
        opacity=b.fade(phase)
        ellipse(c,cx,cy,r,r,0,b.mix(blue,pink,i%3/2),185*opacity,.9)
        ellipse(c,cx,cy,r*.83,r*.83,0,white,225*opacity,1,start=math.pi*1.06,span=.22)
        c.dot((cx-r*.35)/W,(cy-r*.5)/H,.75,white,200*opacity)
        ellipse(c,cx,111,r*1.35,r*.16,0,blue,60*opacity,.6)
    b.specks(c,t,3011,[blue,white],15)
    return c.finish()


def blades(t):
    c=Canvas();red=b.color('#FF537E');pink=b.color('#FFB6E1');white=b.color('#FFF1DB')
    for j in range(3):
        p=(t+j/3)%1;opacity=b.fade(p)**.7
        points=[]
        for u in np.linspace(0,1,110):
            a=-2.7+u*2.15;points.append((195+137*math.cos(a)+22*math.sin(T*p),76+51*math.sin(a)+j*13))
        ribbon(c,points,2.5+1.4*math.sin(math.pi*p),red,pink,190*opacity)
        c.line([xy(x,y-1.2) for x,y in points],white,.55,200*opacity)
        for k in range(4):
            c.line([xy(x,y+3+k*2) for x,y in points[::2]],red,.6,70*opacity*(1-k/5))
    rng=random.Random(3131)
    for i in range(30):
        phase=(t+rng.random())%1;cx=35+phase*315;cy=rng.uniform(42,110)-12*math.sin(math.pi*phase)
        c.line([xy(cx,cy),xy(cx-3,cy+1)],pink,.65,180*b.fade(phase))
    for i in range(6):
        p=(t+i/6)%1;c.curve(.15+.7*p,.24+.11*math.sin(T*(p+i*.3)),3,.3*math.sin(T*t),'petal',pink,110*b.fade(p))
    return c.finish()


def portal(t):
    c=Canvas();blue=b.color('#79E6FF');purple=b.color('#C1A2FF');white=b.color('#EDFAFF')
    cx,cy=192,72
    halo(c,cx,cy,64,50,blue,25)
    for j in range(3):
        phase=(t+j/3)%1;r=15+phase*43;alpha=155*b.fade(phase)
        pts=[xy(cx+math.cos(T*k/6+math.pi/6)*r,cy+math.sin(T*k/6+math.pi/6)*r*.8) for k in range(7)]
        c.line(pts,blue if j%2 else purple,1.2,alpha)
    for i in range(12):
        a=T*(i/12+.04*math.sin(T*t))
        ellipse(c,cx,cy,56,45,0,blue if i%2 else purple,215,1.4,start=a,span=.045)
        r=63;c.line([xy(cx+r*math.cos(a),cy+r*.8*math.sin(a)),xy(cx+(r+4)*math.cos(a),cy+(r+4)*.8*math.sin(a))],white,.8,140)
    for sign in (-1,1):
        points=[(cx+sign*(60+u*112),cy+12*math.sin(T*(u-t))*u) for u in np.linspace(0,1,80)]
        ribbon(c,points,1.5,blue,purple,110)
        c.star((cx+sign*145)/W,.5,5,white,180+50*math.sin(T*t)**2,math.pi/4)
    c.star(.5,.5,4,white,220,math.pi/4);b.specks(c,t,3232,[blue,purple],20)
    return c.finish()


def fireworks(t):
    c=Canvas();palette=[b.color(x) for x in ('#FF97D4','#8EEAFF','#FFE4AA')];white=b.color('#FFF2F9');rng=random.Random(3333)
    for i in range(5):
        phase=(t+i/5)%1;cx=55+i*68;cy=57+15*math.sin(i*2.1);radius=3+33*(1-(1-phase)**2)
        opacity=b.fade(phase)**.5
        for k in range(22):
            a=T*k/22+.14*i;end=(cx+radius*math.cos(a),cy+radius*math.sin(a)+phase**2*18)
            points=[]
            for u in np.linspace(.35,1,8):
                points.append((cx+radius*u*math.cos(a),cy+radius*u*math.sin(a)+phase**2*18*u*u))
            ribbon(c,points,.8,palette[i%3],white,185*opacity)
            c.dot(end[0]/W,end[1]/H,.7,palette[i%3],235*opacity)
        c.star(cx/W,cy/H,2.5,white,140*opacity,math.pi/4)
    for i in range(30):
        p=(t+rng.random())%1;x=rng.uniform(25,359);y=48+78*p
        c.star(x/W,y/H,rng.uniform(.7,1.7),palette[i%3],170*b.fade(p),.6*math.sin(T*t))
    return c.finish()


SPECS=[
 ('26 星蝶双轨巡游',butterflies,4.2,'星蝶沿双重柔光曲线飞行，翼片扇动与星尘拖尾组成轻盈层次。','长侧裙或角色周边；保留两条曲线的横向空间。','0% 保留粉蓝双色；20～40% 可偏向底图，高强度会统一翼色。','蝴蝶翼片较细，避免把纵向压得过扁。'),
 ('27 琉璃花镜绽放',flower,3.6,'三层琉璃花瓣、细金花脉与两侧流动星枝，适合精致浅色主题。','角色身后或炮塔侧面；中心花朵建议避开人物面部。','粉蓝与淡金原色更有层次；低强度着色适合配合现有底图。','中心花朵适合保持比例；两侧星枝可按装甲范围裁剪。'),
 ('28 深空引力星环',gravity,4.0,'倾斜星环、近远不同亮度的轨道粒子与长条星流，适合深色科幻涂装。','车体侧面或炮塔留白；中心环与两端尾流一起摆放。','蓝紫原色有冷暖层次；冰蓝或紫晶可做单色版本。','环的倾斜与椭圆是设计效果，保留默认比例后再微调。'),
 ('29 幻彩水晶棱镜',crystals,4.0,'多面水晶缓慢悬浮，棱线高光、彩色切面和底部光带组成晶透效果。','角色周围、规则装甲板或长侧裙中段。','0% 保留多色折光；统一着色可做冰蓝、紫晶或粉晶。','中心水晶较高，裁剪时先检查最高和最低位置。'),
 ('30 月潮泡影流光',bubbles,4.2,'虹彩气泡逐渐升起，月白反光与水纹光带组成轻柔水下氛围。','水着角色周围或蓝白侧裙，适合大面积低干扰点缀。','保留蓝紫原色较柔和；冰蓝、薄荷或淡粉也可。','泡影轮廓需要纵向空间，建议先用完整素材再裁边。'),
 ('31 绯樱弧刃残光',blades,4.4,'渐细弧刃、亮边与多层残影交替流动，配以粉色花瓣和细碎火星。','长侧裙、刀剑主题角色周边或装甲边缘。','绯红与樱粉较鲜明；可改冰蓝或紫晶作为能量弧。','弧刃两端有尖细收束，裁剪前看完整循环。'),
 ('32 极光星门回廊',portal,4.0,'逐层扩展的六角星门、分段辉环与双侧极光带，适合科技魔法主题。','角色身后、徽记区域或炮塔侧面。','蓝紫原色有空间层次；低强度调色更易保留分层。','六角环宜保持长宽比例，横向尾带可独立裁短。'),
 ('33 梦色花火星瀑',fireworks,4.5,'五组错峰花火逐渐绽开，细亮尾丝与落星覆盖长条装甲。','长侧裙、偶像或庆典主题角色周围。','粉蓝金原色适合庆典；也可统一为樱粉、冷白或金色。','多点绽放会改变画面重心，放置前先观看一整轮。'),
]


def note(spec):
    name,renderer,width,purpose,placement,palette,shape=spec
    return '\n'.join(['用途：'+purpose,'摆放：'+placement,'配色：'+palette,'形状：'+shape,
                      '显示：贴面受选区裁切，独立平面可自由拖动；左右同时显示需勾选双侧。',
                      '检查：先保留默认亮度观看完整循环；游戏曝光、遮挡与整车效果未实测。'])


def main():
    b.background();resume='--resume' in sys.argv
    OUT.mkdir(exist_ok=resume);CACHE.mkdir(parents=True,exist_ok=True);(OUT/'动画预览').mkdir(exist_ok=resume)
    progress=CACHE/'progress.json';old=json.loads(progress.read_text(encoding='utf-8')) if resume and progress.exists() else []
    records=[];posters=[]
    for spec in SPECS:
        name,renderer,width,*_=spec;target=OUT/(name+'.aepreset');folder=CACHE/name;folder.mkdir(exist_ok=True)
        previous=next((r for r in old if r['name']==name),None)
        if previous and target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==previous['sha256']:
            presets.read(target);records.append(previous)
            with Image.open(OUT/'动画预览'/(name+'.png')) as im:posters.append((name,im.copy()))
            print(name,'REUSED',flush=True);continue
        frames=[renderer(i/N) for i in range(N)]
        rgba=[np.asarray(frame,dtype=np.float32) for frame in frames]
        endpoint=float(np.abs(np.asarray(renderer(1.),dtype=np.float32)-rgba[0]).mean())
        steps=[float(np.abs(a-z).mean()) for a,z in zip(rgba,rgba[1:]+rgba[:1])]
        assert endpoint<.12,(name,'endpoint',endpoint)
        assert steps[-1]<=max(.3,3*np.median(steps)),(name,'seam',steps[-1])
        assert np.percentile([np.count_nonzero(a[:,:,3]>0) for a in rgba],0)>50
        clip=ae.pack_frames(frames,folder/'atlas.png');values=ae.config(dict(fps=FPS,width=width,brightness=1.,blend='add'))
        metadata,_=presets.encode(name,note(spec),clip,values)
        for key in ('tint_color','tint_strength'):metadata['config'].pop(key,None)
        with zipfile.ZipFile(target,'w' if resume else 'x',zipfile.ZIP_DEFLATED) as z:
            z.writestr('preset.json',json.dumps(metadata,ensure_ascii=False));z.write(clip['atlas'],'atlas.png')
        recovered,loaded=presets.load(target,folder/'roundtrip');assert loaded['atlas_sha256']==clip['atlas_sha256']
        with Image.open(loaded['atlas']) as im:original=im.copy()
        for hue in ('#77DCFF','#FF8CCB'):
            im=ae.colorize_rgba(original,dict(values,tint_color=hue,tint_strength=100))
            assert im.getchannel('A').tobytes()==original.getchannel('A').tobytes()
            assert Image.open(io.BytesIO(ae.dds(im))).convert('RGBA').tobytes()==im.tobytes()
        # Every source frame is represented. Centisecond rounding sums to 4s.
        previews=[b.composite(frame).quantize(colors=128) for frame in frames]
        durations=[10*(round((i+1)*100/FPS)-round(i*100/FPS)) for i in range(N)]
        gif=OUT/'动画预览'/(name+'.gif');previews[0].save(gif,save_all=True,append_images=previews[1:],duration=durations,loop=0,disposal=2)
        with Image.open(gif) as animation:
            total=0
            for i in range(animation.n_frames):animation.seek(i);total+=animation.info.get('duration',0)
            assert total==4000 and animation.n_frames==N,(name,'gif',total,animation.n_frames)
        poster=b.composite(frames[N//3]);poster.save(OUT/'动画预览'/(name+'.png'));posters.append((name,poster))
        row=dict(name=name,file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size,
                 frames=N,fps=FPS,seconds=N/FPS,gif_frames=N,gif_loop_ms=total,frame_size=[W,H],atlas_size=clip['size'],
                 endpoint_mean_delta=endpoint,last_to_first_step=steps[-1],median_adjacent_step=float(np.median(steps)),
                 description=note(spec),original_procedural_animation=True,source_alpha_and_dds_parity='passed',
                 preset_import_roundtrip='passed',in_game_tested=False,whole_vehicle_loading=dict(status='not_tested',reason='Media preset; no final vehicle package.'))
        records.append(row);progress.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,'OK',target.stat().st_size,flush=True)
    font='C:/Windows/Fonts/msyh.ttc';title=ImageFont.truetype(font,26);label=ImageFont.truetype(font,20);small=ImageFont.truetype(font,14)
    sheet=Image.new('RGB',(1280,1020),'#101827');draw=ImageDraw.Draw(sheet)
    draw.text((30,18),'视觉增强 · 8 款全新动态特效',font=title,fill='#eaf4ff')
    draw.text((30,58),'透明底 / 多层柔光 / 独立调色 / 24 FPS · 4 秒循环 / 完整帧动画预览',font=small,fill='#a9bfd4')
    for i,(name,poster) in enumerate(posters):
        x=28+(i%2)*624;y=104+(i//2)*224
        draw.rounded_rectangle((x,y,x+598,y+205),radius=14,fill='#1a273a',outline='#34465e')
        sheet.paste(poster,(x+105,y+13));draw.text((x+20,y+165),name,font=label,fill='#eef6ff')
    sheet.save(OUT/'新增8款视觉特效总览.png')
    (OUT/'制作与验证记录.json').write_text(json.dumps(dict(presets=records,no_gui_gpu_or_game_started=True),ensure_ascii=False,indent=2),encoding='utf-8')
    guide='# 8 款视觉增强特效\n\nAE 窗口 → 管理 / 导入… → 导入…，选择单个 .aepreset 后套用。33 款整合程序包已内置本组，无需再导入。\n\n每款为透明背景、96 帧、24 FPS、4 秒循环，附完整 96 帧 GIF；GIF 为参考合成，透明素材保存在预设中。调色在「播放与透明 → 特效颜色」。同车型只启用一份涂装或 AE 特效包。\n\n'
    for spec in SPECS:guide+='## '+spec[0]+'\n\n'+note(spec).replace('\n','\n\n')+'\n\n'
    guide+='本次仅制作和检查媒体预设，未生成或安装车辆模组、未启动界面或游戏。游戏实际曝光、遮挡和整车效果未实测。\n'
    (OUT/'导入与摆放说明.md').write_text(guide,encoding='utf-8')
    target=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in OUT.rglob('*'):
            if p.is_file():z.write(p,(Path(OUT.name)/p.relative_to(OUT)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for r in records:assert hashlib.sha256(z.read(OUT.name+'/'+r['file'])).hexdigest()==r['sha256']
    digest=hashlib.sha256(target.read_bytes()).hexdigest();target.with_name(target.name+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print('VISUAL_PRESETS_READY',target,target.stat().st_size,digest,flush=True)


if __name__=='__main__':
    import tkinter as tk
    from unittest.mock import patch
    with patch.object(tk.Tk,'__init__',side_effect=AssertionError('禁止创建窗口')),patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('禁止创建窗口')):
        main()
