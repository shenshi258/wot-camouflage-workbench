"""All 33 effects: source-accurate GIF gallery plus a CPU-encoded overview video."""
import ctypes,faulthandler,hashlib,html,io,json,math,re,shutil,subprocess,sys,zipfile
from ctypes import wintypes
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_anime_presets as b
from wotcamo import ae_presets,ae_effects as ae
from wotcamo.common import ROOT

WORKSPACE=ROOT.parents[1]
OUT=WORKSPACE/'交付/全部35款特效预览_3.3'
FONT='C:/Windows/Fonts/msyh.ttc'
VW,VH,RATE,PAGE_SECONDS=1280,900,30,8


def source_frames(record):
    data,png=ae_presets.read(record['path']);clip=data['clip'];c=ae.config(data['config'])
    packed=clip['packed_frame_size'];frames=[]
    yy,xx=np.indices((144,384));shade=np.where((xx//12+yy//12)%2,20,29)
    background=np.stack([shade*.82,shade*.95,shade*1.25],axis=2)/255
    with Image.open(io.BytesIO(png)) as atlas:
        atlas=ae.colorize_rgba(atlas,c)
        for rect in clip['rects']:
            x=round(rect[0]*atlas.width-.5);y=round(rect[1]*atlas.height-.5)
            frame=atlas.crop((x,y,x+packed[0],y+packed[1])).convert('RGBA')
            frame.thumbnail((384,144),Image.Resampling.LANCZOS)
            stage=Image.new('RGBA',(384,144));stage.paste(frame,((384-frame.width)//2,(144-frame.height)//2))
            rgba=np.asarray(stage,dtype=np.float32)/255
            rgb=rgba[:,:,:3]*rgba[:,:,3:]*c['brightness']
            rgb+=background if c['blend']=='add' else background*(1-rgba[:,:,3:])
            frames.append(Image.fromarray(np.uint8(np.clip(rgb,0,1)*255),'RGB'))
    return data,frames


def group(number):return '原视频与流星' if number<=4 else '二次元系列' if number<=16 else '碧蓝档案风格' if number<=25 else '视觉增强新款' if number<=33 else '液态玻璃'


def main():
    # Idle CPU priority keeps the game ahead of this job. Keep normal memory
    # priority for the bounded frame cache to avoid repeated paging of images.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.SetPriorityClass.restype=wintypes.BOOL
    assert kernel.SetPriorityClass(wintypes.HANDLE(-1),0x40)
    trace=(ROOT/'.cache/preview_stack.log').open('w',encoding='utf-8')
    faulthandler.dump_traceback_later(45,repeat=True,file=trace)
    resume='--resume' in sys.argv
    OUT.mkdir(exist_ok=resume);animations=OUT/'单款动画';animations.mkdir(exist_ok=resume)
    records,issues=ae_presets.scan(ROOT/'预设/AE特效');assert len(records)==35 and not issues
    wheels=list((ROOT/'.cache/encoder_download').glob('*.whl'));assert len(wheels)==1
    binary=ROOT/'.cache/encoder/ffmpeg.exe';binary.parent.mkdir(exist_ok=True)
    if not binary.exists():
        with zipfile.ZipFile(wheels[0]) as z:
            assert z.testzip() is None
            entry=next(n for n in z.namelist() if n.endswith('.exe') and 'ffmpeg' in n)
            binary.write_bytes(z.read(entry))
    final=OUT/'全部35款特效动态总览.mp4';partial=OUT/'全部35款特效动态总览.partial.mp4'
    if final.exists():raise RuntimeError('总览已存在，保留原文件。')
    cmd=[str(binary),'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s:v',f'{VW}x{VH}',
         '-r',str(RATE),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','21','-threads','1',
         '-filter_threads','1','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
    title=ImageFont.truetype(FONT,28);label=ImageFont.truetype(FONT,18);small=ImageFont.truetype(FONT,14)
    catalog=[];posters=[]
    with (ROOT/'.cache/preview_video_encode.log').open('w',encoding='utf-8') as errors:
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors,creationflags=0x08000000|0x40)
        try:
            for page in range(4):
                batch=[]
                for record in records[page*9:(page+1)*9]:
                    print('READING',record['name'],flush=True)
                    data,frames=source_frames(record);fps=data['config']['fps'];count=len(frames);name=data['name'];number=int(name[:2])
                    durations=[10*(round((i+1)*100/fps)-round(i*100/fps)) for i in range(count)]
                    expected=round(count*100/fps)*10
                    gif=animations/(name+'.gif');poster=animations/(name+'.png')
                    new_gif=WORKSPACE/'交付/视觉增强特效预设_新增8款/动画预览'/(name+'.gif')
                    if not gif.exists() and number>=26:
                        # These eight GIFs were just verified as 96 complete
                        # frames at exactly 4s from the same source presets.
                        shutil.copy2(new_gif,gif)
                    if not gif.exists():
                        preview=[im.quantize(colors=128) for im in frames]
                        preview[0].save(gif,save_all=True,append_images=preview[1:],duration=durations,loop=0,disposal=2)
                    with Image.open(gif) as animated:
                        total=0;encoded=animated.n_frames
                        for i in range(encoded):animated.seek(i);total+=animated.info.get('duration',0)
                    assert total==expected,(name,total,expected)
                    frames[count//3].save(poster);posters.append((name,frames[count//3]))
                    item=dict(name=name,number=number,group=group(number),source_frames=count,fps=fps,seconds=count/fps,
                              gif='单款动画/'+gif.name,poster='单款动画/'+poster.name,gif_encoded_frames=encoded,gif_loop_ms=total,
                              original_blank_frames_and_timing_preserved=True,description=data['description'],
                              preset_sha256=hashlib.sha256(record['path'].read_bytes()).hexdigest())
                    catalog.append(item);batch.append((item,frames));print('PREVIEW',name,'OK',flush=True)
                canvas=Image.new('RGB',(VW,VH),'#101827');draw=ImageDraw.Draw(canvas)
                draw.text((32,20),'wot涂装工作台 3.3 · 全部 35 款特效',font=title,fill='#eef7ff')
                draw.text((34,66),f'第 {page+1} / 4 页   ·   编号 {page*9+1:02d}–{min((page+1)*9,35):02d}   ·   保留素材原播放速度',font=small,fill='#a6bfd7')
                for slot,(item,frames) in enumerate(batch):
                    x=28+(slot%3)*414;y=110+(slot//3)*240
                    draw.rounded_rectangle((x,y,x+402,y+224),radius=13,fill='#1b293d',outline='#35495f')
                    draw.text((x+10,y+163),item['name'],font=label,fill='#edf6ff')
                    draw.text((x+10,y+194),f"{item['source_frames']} 帧 · {item['fps']:g} FPS · {item['seconds']:.2f} 秒",font=small,fill='#a6bfd7')
                draw.text((32,865),'透明素材参考合成 · 原起止空帧保留 · 游戏光照与泛光效果未实测',font=small,fill='#93a9bf')
                for frame_index in range(PAGE_SECONDS*RATE):
                    image=canvas.copy()
                    for slot,(item,frames) in enumerate(batch):
                        at=math.floor((frame_index/RATE)*item['fps']+1e-8)%len(frames)
                        image.paste(frames[at],(38+(slot%3)*414,120+(slot//3)*240))
                    if page==0 and frame_index==RATE:image.save(OUT/'视频封面.png')
                    process.stdin.write(image.tobytes())
                (ROOT/'.cache/all_previews_progress.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
            process.stdin.close();returncode=process.wait(timeout=90)
            if returncode:raise RuntimeError((ROOT/'.cache/preview_video_encode.log').read_text(encoding='utf-8'))
        except BaseException:
            process.kill();process.wait();raise
    partial.replace(final)
    check=subprocess.run([str(binary),'-hide_banner','-v','error','-threads','1','-i',str(final),'-progress','pipe:1','-f','null','-'],
                         capture_output=True,text=True,timeout=120,creationflags=0x08000000|0x40)
    decoded=[int(x) for x in re.findall(r'^frame=(\d+)',check.stdout,re.M)]
    assert check.returncode==0 and decoded[-1]==4*PAGE_SECONDS*RATE,(check.returncode,decoded,check.stderr)
    sheet=Image.new('RGB',(1280,3000),'#101827');d=ImageDraw.Draw(sheet)
    d.text((30,20),'全部 35 款特效 · 名称总览',font=title,fill='#edf7ff')
    d.text((30,65),'打开同目录 MP4 看 32 秒动态总览；HTML 可搜索和逐款查看完整循环。',font=small,fill='#a6bfd7')
    for i,(name,poster) in enumerate(posters):
        x=24+(i%3)*420;y=106+(i//3)*236
        d.rounded_rectangle((x,y,x+402,y+222),radius=12,fill='#1b293d',outline='#35495f')
        sheet.paste(poster,(x+9,y+9));d.text((x+10,y+166),name,font=label,fill='#edf6ff')
        d.text((x+10,y+197),group(int(name[:2])),font=small,fill='#a6bfd7')
    sheet.save(OUT/'全部35款效果总览.png')
    cards=[]
    for item in catalog:
        q=lambda value:html.escape(str(value),quote=True)
        cards.append(f'''<article data-group="{q(item['group'])}" data-name="{q(item['name'])}"><img loading="lazy" width="384" height="144" src="{q(item['gif'])}" data-motion="{q(item['gif'])}" data-still="{q(item['poster'])}" alt="{q(item['name'])}"><h2>{q(item['name'])}</h2><p>{item['source_frames']} 帧 · {item['fps']:g} FPS · {item['seconds']:.2f} 秒</p><details><summary>摆放与配色说明</summary><div>{q(item['description']).replace(chr(10),'<br>')}</div></details></article>''')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>全部35款特效预览</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#1b2b40;font:15px "Microsoft YaHei UI",sans-serif}main{max-width:1320px;margin:auto;padding:30px}h1{font-size:28px;margin:0 0 10px}header p{color:#526981;line-height:1.8}video{display:block;width:100%;max-height:75vh;background:#101827;border-radius:16px}.bar{display:flex;flex-wrap:wrap;gap:10px;position:sticky;top:0;background:#f3f6faee;backdrop-filter:blur(10px);padding:18px 0;z-index:2}button,input{font:inherit;border:1px solid #ccdae9;border-radius:9px;padding:10px 14px;background:white;color:#244769}button{cursor:pointer}button.active{background:#2079de;color:white;border-color:#2079de}input{flex:1;min-width:220px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:20px}article{background:white;border:1px solid #d9e3ef;border-radius:14px;overflow:hidden;padding-bottom:16px}article img{display:block;width:100%;height:auto;background:#101827}article h2{font-size:18px;margin:16px 16px 8px}article p,details{margin:8px 16px;color:#526981}details div{line-height:1.8;font-size:14px;margin-top:12px}summary{cursor:pointer;color:#2767aa}footer{margin-top:24px;line-height:1.8;color:#526981}</style>
<main><header><h1>全部 35 款特效预览</h1><p>先看 32 秒动态总览，再按分类逐款挑选。每款动画保留素材原播放速度、完整循环及原有空帧；可在工作台继续调色、尺寸和位置。</p></header><video controls preload="metadata" poster="视频封面.png" src="全部35款特效动态总览.mp4"></video>
<nav class="bar"><button class="active" data-filter="全部">全部 35 款</button><button data-filter="原视频与流星">原视频与流星</button><button data-filter="二次元系列">二次元系列</button><button data-filter="碧蓝档案风格">碧蓝档案风格</button><button data-filter="视觉增强新款">视觉增强</button><button data-filter="液态玻璃">液态玻璃</button><input id="search" placeholder="按编号或名称搜索"><button id="motion">改看静态</button></nav><section class="grid">'''+''.join(cards)+'''</section><footer>本页完全离线，无外部图片或网络请求。贴面受装甲选区裁切；独立平面可自由放置。这里是透明素材参考合成，游戏整车、光照、遮挡与泛光未实测。</footer></main>
<script>let group='全部',moving=true;const cards=[...document.querySelectorAll('article')];function filter(){let text=document.querySelector('#search').value.trim().toLowerCase();for(const card of cards)card.hidden=!((group==='全部'||card.dataset.group===group)&&card.dataset.name.toLowerCase().includes(text));}for(const button of document.querySelectorAll('[data-filter]'))button.onclick=()=>{group=button.dataset.filter;for(const b of document.querySelectorAll('[data-filter]'))b.classList.toggle('active',b===button);filter();};document.querySelector('#search').oninput=filter;document.querySelector('#motion').onclick=event=>{moving=!moving;for(const image of document.querySelectorAll('article img'))image.src=moving?image.dataset.motion:image.dataset.still;event.target.textContent=moving?'改看静态':'播放动画';};</script></html>'''
    (OUT/'全部35款特效预览.html').write_text(page,encoding='utf-8')
    (OUT/'使用说明.txt').write_text('打开“全部35款特效动态总览.mp4”看 32 秒总览：4 页，每页 8 秒。编号和名称与工作台一致。\n打开“全部35款特效预览.html”可离线搜索、按分类筛选、切换静态／动画，并阅读摆放配色说明。单款 GIF 在“单款动画”。\n原有透明起止段保留。GIF 会合并连续相同画面，循环时长按 0.01 秒精度取整。总览视频按各自实际 FPS 取帧，最高素材 25 FPS，视频 30 FPS。\n总览视频从各预设的原图集读取；逐款 GIF 复用已校验的完整循环预览。未启动游戏，未安装模组。\n',encoding='utf-8-sig')
    result=dict(effects=catalog,video=dict(file=final.name,sha256=hashlib.sha256(final.read_bytes()).hexdigest(),fps=RATE,frames=decoded[-1],seconds=32,resolution=[VW,VH],codec='H.264',decoded_all_frames=True),
                gif_count=len(catalog),all_gif_durations_match_source=True,no_windows_or_game_started=True,
                encoder_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),in_game_tested=False)
    (OUT/'预览制作与检查记录.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    target=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in OUT.rglob('*'):
            if p.is_file():z.write(p,(Path(OUT.name)/p.relative_to(OUT)).as_posix())
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    digest=hashlib.sha256(target.read_bytes()).hexdigest();target.with_name(target.name+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print('ALL_35_PREVIEWS_READY',target,target.stat().st_size,digest,flush=True)
    faulthandler.cancel_dump_traceback_later();trace.close()


if __name__=='__main__':
    import tkinter as tk
    from unittest.mock import patch
    with patch.object(tk.Tk,'__init__',side_effect=AssertionError('禁止创建窗口')),patch.object(tk.Toplevel,'__init__',side_effect=AssertionError('禁止创建窗口')):
        main()
