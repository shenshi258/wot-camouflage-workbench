"""Blue Archive inspired original procedural effects; background media only.

Reuse the verified straight-alpha/soft-glow pipeline. No official artwork is
embedded, no native shader/runtime is changed, and no GUI/GPU/game is started.
"""
import hashlib,io,json,math,random,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_anime_presets as b
from wotcamo import ae_effects as ae,ae_presets as presets
from wotcamo.common import ROOT

W,H,N,FPS=b.W,b.H,b.N,b.FPS
T=math.tau
OUT=ROOT.parents[1]/'交付/碧蓝档案风格特效预设_新增9款'
CACHE=ROOT/'.cache/ba_presets'
REFERENCES=['https://bluearchive.jp/character','https://sh-anime.shochiku.co.jp/bluearchive-anime/character/','https://sh-anime.shochiku.co.jp/bluearchive-anime/news/9/']

def arc(c,x,y,r,rotation,length,rgb,alpha=220,width=1,aspect=1):
    points=[]
    for i in range(max(8,round(length*90))+1):
        a=rotation+T*length*i/max(8,round(length*90))
        points.append((x+math.cos(a)*r/W,y+math.sin(a)*r*aspect/H))
    c.line(points,rgb,width,alpha)

def square(c,x,y,size,rgb,alpha=210,filled=True):
    pts=[(x-size/W,y-size/H),(x+size/W,y-size/H),(x+size/W,y+size/H),(x-size/W,y+size/H)]
    if filled:c.polygon(pts,rgb,alpha)
    else:c.line(pts+[pts[0]],rgb,.8,alpha)

def diamond(c,x,y,size,rgb,alpha=220,rotation=0,filled=False):
    pts=[(x+math.cos(rotation+T*i/4)*size/W,y+math.sin(rotation+T*i/4)*size/H) for i in range(4)]
    if filled:c.polygon(pts,rgb,alpha)
    else:c.line(pts+[pts[0]],rgb,1,alpha)

def terminal(t):
    c=b.Canvas();blue=b.color('#73DAFF');white=b.color('#DEF7FF')
    for r in (30,37,46):
        for j in range(3):arc(c,.5,.5,r,T*(t*(1 if r!=37 else -1)+j/3),.21,blue if r!=37 else white,190 if r!=46 else 130,.9)
    triangle=[(.5,.29),(.5+24/W,.63),(.5-24/W,.63),(.5,.29)]
    c.line(triangle,white,1,200)
    for sign in (-1,1):
        x=.5+sign*.22
        c.line([(x+sign*.02,.27),(x,.27),(x,.73),(x+sign*.02,.73)],blue,1,160)
        for j in range(5):
            phase=(t+j/5)%1;xx=x+sign*(.04+j*.02)
            c.line([(xx,.43),(xx,.57)],white,.8,50+150*b.fade(phase))
    b.specks(c,t,137,[blue,white],20);return c.finish()

def arona(t):
    c=b.Canvas();blue=b.color('#77DFFF');white=b.color('#E0F8FF');x=.5;y=.44
    arc(c,x,y,29,math.pi, .5,white,230,1.2,aspect=.66)
    # Umbrella scallops, ribs and hooked handle are made as actual line shapes.
    for j in range(3):
        xx=x+(-29+j*19.333+9.666)/W
        arc(c,xx,y,9.666,0,.5,blue,220,.9,aspect=.33)
    for dx in (-13,13):c.line([(x,y-19/H),(x+dx/W,y)],blue,.7,165)
    c.line([(x,y-.03),(x,.73)],white,1.1,230)
    arc(c,x+5/W,.73,5,0,.5,white,230,1.1)
    arc(c,x,.19,18,T*t,1,blue,155,.8,aspect=.2)
    rng=random.Random(72)
    for i in range(26):
        xx=rng.uniform(.06,.94);phase=rng.random();v=(t+phase)%1;yy=-.08+v*1.16
        if abs(xx-.5)<.10 and .35<yy<.78:continue
        c.line([(xx,yy),(xx-.006,yy+.035)],blue,.8,190*b.fade(v))
    b.specks(c,t,44,[white,blue],10);return c.finish()

def plana(t):
    c=b.Canvas();lavender=b.color('#C7B2FF');white=b.color('#F0EAFE')
    for r in (20,31,43):diamond(c,.5,.5,r,white if r==31 else lavender,180,T*t if r!=31 else -T*t)
    for j in range(8):
        a=T*(j/8-t);x=.5+math.cos(a)*51/W;y=.5+math.sin(a)*51/H
        diamond(c,x,y,3,lavender,190,a,filled=j%2==0)
    c.star(.5,.5,7,white,170+70*math.sin(T*t)**2,math.pi/4)
    for sign in (-1,1):
        for i in range(6):
            phase=(t+i/6)%1;square(c,.5+sign*(.18+i*.038),.5+.10*math.sin(T*(t+i/6)),1.6,lavender,170*b.fade(phase))
    return c.finish()

def hoshino(t):
    c=b.Canvas();pink=b.color('#FF9BCB');blue=b.color('#7AD8FF');white=b.color('#FFE7F4')
    for j in range(4):
        phase=(t+j/4)%1;r=16+50*phase
        arc(c,.5,.63,r,0,1,b.mix(pink,blue,j/4),210*(1-phase)**1.6,1,aspect=.27)
    arc(c,.5,.31,24,0,1,pink,205,1.1,aspect=.27)
    for j in range(3):
        y=.69+j*.05
        pts=[(.06+i*.88/90,y+.018*math.sin(T*(i/35-t+j*.1))) for i in range(91)]
        c.line(pts,blue if j%2 else pink,.8,90)
    rng=random.Random(69)
    for i in range(18):
        phase=rng.random();v=(t+phase)%1;x=rng.uniform(.17,.83);y=.67-.24*math.sin(math.pi*v)
        c.dot(x,y,rng.uniform(1,2.1),blue if i%2 else white,210*b.fade(v))
    b.specks(c,t,11,[pink,blue],16);return c.finish()

def shiroko(t):
    c=b.Canvas();blue=b.color('#79EEE6');white=b.color('#DDFBFF')
    for r in (31,39):
        for j in range(4):arc(c,.5,.5,r,T*(j/4+(t if r==39 else 0))+.14,.17,blue,215 if r==31 else 150,1)
    for j in range(4):
        a=j*T/4
        c.line([(.5+math.cos(a)*18/W,.5+math.sin(a)*18/H),(.5+math.cos(a)*45/W,.5+math.sin(a)*45/H)],white,1,220)
    diamond(c,.5,.5,5,white,190,math.pi/4)
    for sign in (-1,1):
        x=.5+sign*.25
        for j in range(5):
            c.line([(x+sign*j*.02,.47),(x+sign*j*.02,.53)],blue,.9,65+150*math.sin(T*(t-j*.08))**4)
    b.specks(c,t,15,[blue,white],20);return c.finish()

def aris(t):
    c=b.Canvas();blue=b.color('#7CDAFF');white=b.color('#E3F5FF');violet=b.color('#B6A9FF')
    # Pixel sword: a stepped blade, crossguard and handle, not a blurred bar.
    bob=.025*math.sin(T*t)
    for i in range(12):
        x=.40+i*.016;y=.68-i*.034+bob
        square(c,x,y,2.3,blue,230);square(c,x+.003,y-.006,1.1,white,235)
    c.line([(.40-.022,.68-.022+bob),(.40+.025,.68+.035+bob)],violet,3,230)
    for i in range(4):square(c,.40-i*.009,.68+i*.022+bob,1.9,violet,230)
    rng=random.Random(812)
    for i in range(26):
        phase=rng.random();v=(t+phase)%1;x=rng.uniform(.08,.92);y=.91-v*.80
        size=rng.choice([1.2,1.8,2.4]);square(c,x,y,size,blue if i%2 else violet,180*b.fade(v))
        if i%5==0:
            square(c,x+size*2/W,y,size,white,120*b.fade(v));square(c,x,y+size*2/H,size,white,120*b.fade(v))
    return c.finish()

def twins(t):
    c=b.Canvas();pink=b.color('#FF94C8');green=b.color('#A1F0B5');white=b.color('#E7FBEC')
    for j,sign,rgb in [(0,-1,pink),(1,1,green)]:
        x=.5+sign*.16
        diamond(c,x,.34,14,rgb,200,math.pi/4)
        for i in range(6):
            phase=(t+i/6)%1;xx=x+sign*(.06+i*.025);y=.15+phase*.72
            square(c,xx,y,2.3,rgb,210*b.fade(phase))
        for dx,dy in [(-1,0),(0,-1),(0,0),(1,0),(0,1)]:square(c,x+dx*4/W,.69+dy*4/H,1.65,rgb,230)
    # A two-colour eight-bit heart links the sister palettes.
    heart=['01100110','11111111','11111111','01111110','00111100','00011000']
    oy=.48+.025*math.sin(T*t)
    for y,row in enumerate(heart):
        for x,on in enumerate(row):
            if on=='1':square(c,.5+(x-3.5)*3.4/W,oy+(y-2.5)*3.4/H,1.55,pink if x<4 else green,215)
    b.specks(c,t,663,[pink,green,white],18);return c.finish()

def hina(t):
    c=b.Canvas();purple=b.color('#B09BFA');pink=b.color('#D8B7FF');white=b.color('#E7DDFF')
    opening=.015*math.sin(T*t)
    for sign in (-1,1):
        for j in range(7):
            start=(.5+sign*.055,.52+j*.006)
            end=(.5+sign*(.14+j*.025),.22+j*.063+opening)
            elbow=(end[0]-sign*.025,end[1]+.11)
            c.line([start,elbow,end],purple if j%2 else pink,.9,150+j*8)
            c.line([end,(end[0]-sign*.012,end[1]-.035)],white,.6,155)
    for j in range(4):arc(c,.5,.33,22,T*(t+j/4),.16,purple,205,.9,aspect=.6)
    diamond(c,.5,.51,12,pink,220)
    c.line([(.5-9/W,.28),(.5-5/W,.19),(.5,.25),(.5+5/W,.19),(.5+9/W,.28)],white,.9,230)
    b.specks(c,t,36,[purple,pink],15);return c.finish()

def trinity(t):
    c=b.Canvas();gold=b.color('#FFD79B');white=b.color('#FFF2D4')
    arc(c,.5,.36,26,0,1,gold,225,1.1,aspect=.32)
    arc(c,.5,.36,21,0,1,white,155,.8,aspect=.32)
    for sign in (-1,1):
        for j in range(6):
            pts=[]
            for i in range(31):
                u=i/30;x=.5+sign*(.055+(.24-j*.024)*u)
                y=.59-.18*math.sin(u*math.pi/2)+j*.025*u+.015*math.sin(T*t)*u
                pts.append((x,y))
            c.line(pts,white if j%2 else gold,1.2,190-j*12)
    c.star(.5,.58,5,white,155+70*math.sin(T*t)**2,math.pi/4)
    b.specks(c,t,222,[gold,white],28);return c.finish()

SPECS=[
 ('17 BA风格 蓝白终端环',terminal,'蓝白几何终端；适合炮塔侧面与角色周围。',3.6),
 ('18 BA风格 阿洛娜雨伞蓝空',arona,'阿洛娜配色灵感；蓝白雨伞与轻雨光点。',3.3),
 ('19 BA风格 普拉娜淡紫菱晶',plana,'普拉娜配色灵感；淡紫菱晶与数据碎片。',3.2),
 ('20 BA风格 星野粉蓝水波',hoshino,'星野粉蓝配色灵感；水波环与轻盈水滴。',4.0),
 ('21 BA风格 白子青蓝准星环',shiroko,'白子配色与光环灵感；青蓝准星及分段环。',3.4),
 ('22 BA风格 爱丽丝像素光剑',aris,'爱丽丝与像素勇者灵感；阶梯光剑和方块星点。',3.8),
 ('23 BA风格 桃绿双子双色像素',twins,'桃绿双子配色灵感；粉绿像素心与十字键。',3.8),
 ('24 BA风格 日奈紫晶翼阵',hina,'日奈配色灵感；淡紫翼形线阵与光环碎片。',3.6),
 ('25 BA风格 三一金白羽环',trinity,'三一学园风格灵感；金白羽翼与椭圆柔光环。',3.6),
]

def main():
    b.background();resume='--resume' in sys.argv;OUT.mkdir(exist_ok=resume);CACHE.mkdir(parents=True,exist_ok=True);(OUT/'动画预览').mkdir(exist_ok=resume)
    progress_path=CACHE/'progress.json';progress=json.loads(progress_path.read_text(encoding='utf-8')) if resume and progress_path.exists() else []
    report=[];posters=[]
    for name,renderer,description,width in SPECS:
        target=OUT/(name+'.aepreset');folder=CACHE/name;folder.mkdir(exist_ok=True)
        old=next((row for row in progress if row['name']==name),None)
        if resume and old and target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==old['sha256']:
            presets.read(target);report.append(old)
            with Image.open(OUT/'动画预览'/(name+'.png')) as image:posters.append((name,image.copy(),description))
            print(name,'REUSED',flush=True);continue
        frames=[renderer(i/N) for i in range(N)]
        endpoint=renderer(1.);endpoint_mean=float(np.abs(np.asarray(endpoint,dtype=float)-np.asarray(frames[0],dtype=float)).mean())
        steps=[float(np.abs(np.asarray(a,dtype=float)-np.asarray(z,dtype=float)).mean()) for a,z in zip(frames,frames[1:]+frames[:1])]
        assert endpoint_mean<.12,(name,'endpoint',endpoint_mean)
        assert steps[-1]<=max(.3,3*np.median(steps)),(name,'seam',steps[-1])
        clip=ae.pack_frames(frames,folder/'atlas.png');values=ae.config(dict(fps=FPS,width=width,brightness=1.,blend='add'))
        data,_=presets.encode(name,description,clip,values)
        for key in ('tint_color','tint_strength'):data['config'].pop(key,None)
        with zipfile.ZipFile(target,'w' if resume else 'x',zipfile.ZIP_DEFLATED) as z:
            z.writestr('preset.json',json.dumps(data,ensure_ascii=False));z.write(clip['atlas'],'atlas.png')
        restored,loaded=presets.load(target,folder/'roundtrip');assert loaded['atlas_sha256']==clip['atlas_sha256']
        original_alpha=None
        with Image.open(loaded['atlas']) as image:original_alpha=image.getchannel('A').tobytes()
        for hue in ('#78DCFF','#FF8BC8'):
            colored=ae.colorized_clip(loaded,dict(values,tint_color=hue,tint_strength=100),folder/'color_check')
            with Image.open(colored['atlas']) as image:
                assert image.getchannel('A').tobytes()==original_alpha
                assert Image.open(io.BytesIO(ae.dds(image))).convert('RGBA').tobytes()==image.tobytes()
        preview_frames=[b.composite(frame).quantize(colors=128) for frame in frames[::2]]
        durations=[10*(round((i+1)*100/(FPS/2))-round(i*100/(FPS/2))) for i in range(len(preview_frames))]
        gif=OUT/'动画预览'/(name+'.gif');preview_frames[0].save(gif,save_all=True,append_images=preview_frames[1:],duration=durations,loop=0,disposal=2)
        with Image.open(gif) as animation:
            total=0
            for i in range(animation.n_frames):animation.seek(i);total+=animation.info.get('duration',0)
            assert total==4000,(name,'gif duration',total)
        poster=b.composite(frames[N//3]);poster.save(OUT/'动画预览'/(name+'.png'));posters.append((name,poster,description))
        row=dict(name=name,file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size,
                 frames=N,fps=FPS,seconds=N/FPS,gif_loop_ms=total,frame_size=[W,H],atlas_size=clip['size'],
                 description=description,provenance='New original procedural fan-style animation; character motifs/palettes are design inspiration.',
                 endpoint_mean_delta=endpoint_mean,last_to_first_step=steps[-1],median_adjacent_step=float(np.median(steps)),
                 import_roundtrip='passed',two_colour_alpha_and_dds_checks='passed',in_game_tested=False,
                 whole_vehicle_loading=dict(status='not_tested',reason='Portable media only; no final vehicle package or game test.'))
        report.append(row);progress_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,'OK',target.stat().st_size,flush=True)
    font='C:/Windows/Fonts/msyh.ttc';large=ImageFont.truetype(font,23);small=ImageFont.truetype(font,14);label=ImageFont.truetype(font,18)
    sheet=Image.new('RGB',(1280,800),'#101b2c');draw=ImageDraw.Draw(sheet)
    draw.text((28,15),'碧蓝档案风格 · 9 款可导入动态特效',font=large,fill='#e6f5ff')
    draw.text((28,50),'光环 / 蓝白终端 / 角色配色 / 像素图案 · 透明底 · 4 秒循环 · 支持自由调色',font=small,fill='#a3bfd4')
    for i,(name,poster,description) in enumerate(posters):
        x=22+(i%3)*420;y=86+(i//3)*231
        draw.rounded_rectangle((x,y,x+404,y+216),radius=12,fill='#1a2a40',outline='#334e65')
        sheet.paste(poster,(x+10,y+8));draw.text((x+12,y+158),name.replace('BA风格 ',''),font=label,fill='#ebf5ff')
        draw.text((x+12,y+188),description.split('；')[0],font=small,fill='#b6c9da')
    sheet.save(OUT/'碧蓝档案风格9款总览.png')
    (OUT/'制作与验证记录.json').write_text(json.dumps(dict(presets=report,design_references=REFERENCES,no_gui_gpu_or_game_started=True),ensure_ascii=False,indent=2),encoding='utf-8')
    names='\n'.join(row['name'] for row in report)
    (OUT/'导入与使用说明.txt').write_text('碧蓝档案风格 · 新增 9 款透明动画预设\n\n'+names+'\n\n解压合集 ZIP，工作台 AE 窗口 → 管理 / 导入… → 导入…，选择 .aepreset 后套用。每个文件自带透明图集，24 FPS、4 秒循环。GIF 预览循环也为 4 秒。\n\n本组为围绕角色配色、光环、终端和像素元素制作的风格原创动画。官方角色资料参考：\n'+'\n'.join(REFERENCES)+'\n\n调颜色：调色版 3.1 → 播放与透明 → 特效颜色；0% 原色，100% 自定义颜色。旧版双侧显示 3.1 也可导入这些原色预设，调色需使用调色版。\n\n建议放在炮塔侧面、侧裙、徽标位置或角色周边；完整圆环建议保持横纵比例，避免把圆环拉成长椭圆。左右同时出现请勾选“左右双侧显示”。本组不会自动修改或覆盖你已有的涂装。\n\n本次只生成媒体文件并做导入、循环、透明度和 DDS 像素回读检查，未打开工作台、WebView 或游戏窗口；游戏内曝光、泛光、遮挡和最终整车效果待实测。\n',encoding='utf-8-sig')
    target=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in OUT.rglob('*'):
            if file.is_file():z.write(file,(Path(OUT.name)/file.relative_to(OUT)).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for row in report:assert hashlib.sha256(z.read(OUT.name+'/'+row['file'])).hexdigest()==row['sha256']
    with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    target.with_name(target.name+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print('BA_PRESETS_READY',str(target),target.stat().st_size,digest,flush=True)

if __name__=='__main__':main()
