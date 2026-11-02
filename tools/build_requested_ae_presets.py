"""Convert the user's three reference clips and the original meteor into portable presets.

This authors media only. It neither builds/installs a vehicle mod nor starts the game.
Dark-background footage is converted to straight alpha for SRCALPHA/ONE blending.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import ae_effects as ae, ae_presets as presets, preview3d_assets as assets
from wotcamo.common import ROOT

WORKSPACE=ROOT.parents[1]
VIDEO=Path('E:/QQ消息/Tencent Files/3042975954/nt_qq/nt_data/Video/2026-10/Ori')
ORIGINAL=WORKSPACE/'改造区/Pz70_水星野侧面流星_R1'
OUT=ROOT/'.cache/requested_presets'
REPORT=[]


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def decode_video(path,fps):
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened():raise ValueError('无法打开视频：'+str(path))
    native=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output_count=round(count/native*fps)
    wanted={min(count-1,round(i*native/fps)) for i in range(output_count)}
    frames=[]
    for index in range(count):
        ok=cap.grab()
        if not ok:break
        if index in wanted:
            ok,bgr=cap.retrieve()
            if not ok:raise ValueError('视频帧解码失败。')
            rgb=cv2.cvtColor(cv2.resize(bgr,(320,180),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2RGB)
            frames.append(rgb.astype(np.float32)/255)
    cap.release()
    if len(frames)!=output_count:raise ValueError('视频没有解码出预期帧数。')
    return np.stack(frames),dict(path=str(path),sha256=digest(path),frames=count,fps=native,
                                seconds=count/native,dimensions=[width,height])


def loop_overlap(frames,fps):
    """Overlap end/start without a black interruption; last/first remain adjacent samples."""
    count=min(round(.4*fps),len(frames)//6)
    blend=(.5-.5*np.cos(np.linspace(0,math.pi,count,dtype=np.float32)))[:,None,None,None]
    tail=frames[-count:]*(1-blend)+frames[:count]*blend
    return np.concatenate([frames[count:-count],tail]),count/fps


def straight_frames(contributions):
    output=[]
    worst=0.
    for contribution in contributions:
        rgb=np.clip(contribution,0,1)
        alpha=rgb.max(axis=2,keepdims=True)
        straight=np.divide(rgb,alpha,out=np.zeros_like(rgb),where=alpha>0)
        rgba=np.uint8(np.clip(np.concatenate([straight,alpha],axis=2),0,1)*255+.5)
        recovered=rgba[:,:,:3].astype(float)/255*(rgba[:,:,3:].astype(float)/255)
        worst=max(worst,float(np.max(np.abs(recovered-rgb))))
        output.append(Image.fromarray(rgba,'RGBA'))
    return output,worst


def save(name,description,frames,fps,source,*,width=3.2,brightness=1.,loop_note=''):
    folder=OUT/name;folder.mkdir(parents=True,exist_ok=True)
    clip=ae.pack_frames(frames,folder/'atlas.png')
    values=ae.config(dict(fps=fps,width=width,brightness=brightness,blend='add'))
    data,payload=presets.encode(name,description,clip,values)
    target=presets.store(data,payload)
    recovered,restored=presets.load(target,folder/'roundtrip')
    preview=ae.preview_data(restored,values)
    assert preview['frames']==len(frames) and preview['blendSrc']==5 and preview['blendDst']==2
    assert restored['atlas_sha256']==clip['atlas_sha256']
    assert 1<=len(frames)<=128 and max(clip['size'])<=4096
    seam=np.abs(np.asarray(frames[-1],dtype=float)-np.asarray(frames[0],dtype=float)).mean()
    step=[np.abs(np.asarray(b,dtype=float)-np.asarray(a,dtype=float)).mean() for a,b in zip(frames,frames[1:])]
    # Export a checkerboard animation so transparency and repeat boundaries can be reviewed.
    yy,xx=np.indices((frames[0].height,frames[0].width));shade=np.where((xx//12+yy//12)%2,42,64)
    previews=[]
    for frame in frames:
        rgba=np.asarray(frame,dtype=float);rgb=rgba[:,:,:3]*(rgba[:,:,3:]/255)*brightness
        previews.append(Image.fromarray(np.uint8(np.clip(rgb+shade[:,:,None],0,255)),'RGB'))
    previews[0].save(folder/'预览.gif',save_all=True,append_images=previews[1:],duration=round(1000/fps),loop=0,disposal=2)
    frames[len(frames)//2].save(folder/'透明帧.png')
    row=dict(name=name,path=str(target),sha256=digest(target),bytes=target.stat().st_size,
             fps=fps,frames=len(frames),seconds=len(frames)/fps,frame_size=clip['frame_size'],atlas_size=clip['size'],
             source=source,description=description,loop=loop_note,seam_mean_rgba=seam,
             adjacent_mean_rgba=float(np.mean(step)),gif=str(folder/'预览.gif'),
             in_game_tested=False,whole_vehicle_loading=dict(status='not_tested',reason='Media preset only; no final vehicle package or game test.'))
    REPORT.append(row);print(json.dumps({k:row[k] for k in ('name','frames','fps','seconds','bytes')},ensure_ascii=False),flush=True)


def videos():
    rows=[('54a5367013ebe7e74ec86a5903b21a5f',15,'01 蓝青粒子涌流',
           '蓝青粒子扩散与水平镜头光；从提供的视频分离灰蓝底色，柔和重叠衔接循环。',True),
          ('2b256d1e4cff1773808d48016341a9af',24,'02 紫蓝流星雨',
           '斜向流星、紫蓝星芒与稀疏彩色闪点；保留原视频的出场和消退节奏。',False),
          ('e8f3d4f624605102d59dafd20a2c0b1b',24,'03 彩色星云光点',
           '彩色光点漂浮于紫色雾光中；紫色云雾作为特效保留，柔和重叠衔接循环。',False)]
    for key,fps,name,description,remove_base in rows:
        print('Decoding '+key,flush=True)
        frames,source=decode_video(VIDEO/(key+'.mp4'),fps)
        if remove_base:
            # The matte is a nearly stationary blue-grey gradient. Estimate it
            # from dark edge samples across time, retaining the central flare.
            edge=np.concatenate([frames[:,:12],frames[:,-12:]],axis=1)
            base=np.percentile(edge,15,axis=(0,1)).astype(np.float32)[None,None,:,:]
            frames=np.maximum(frames-base,0)
        intensity=frames.max(axis=3,keepdims=True)
        gate=np.clip((intensity-2/255)/(6/255),0,1)
        frames*=gate*gate*(3-2*gate)
        frames,overlap=loop_overlap(frames,fps)
        rgba,error=straight_frames(frames)
        source['alpha_reconstruction_max_error']=error
        source['conversion']='straight RGB = contribution / max(RGB); alpha = max(RGB); native SRCALPHA/ONE'
        source['background']='edge-estimated grey-blue matte removed' if remove_base else 'black to alpha; coloured emission preserved'
        save(name,description,rgba,fps,source,loop_note='End/start cosine overlap %.3fs'%overlap)


def meteor():
    name='04 蓝白侧面流星（最早款）'
    texture=Image.open(ORIGINAL/'流星贴图.png').convert('RGBA')
    rgba=np.asarray(texture,dtype=np.float32)/255
    rgba[:,:,:3]*=rgba[:,:,3:]
    seq=ET.parse(ORIGINAL/'unpacked/res/particles/ba_pz70_swim_meteor_r1/left.seq').getroot()
    tracks=[]
    for obj in seq.findall('sequenceObject')[1:]:
        tracks.append({track.findtext('name'):track.findall('frame') for track in obj.findall('track') if track.findtext('name') in ('position','scale')})
    fps=25;count=120;times=np.arange(count)/fps
    samples=[{key:assets.evaluate_track(value,times) for key,value in track.items()} for track in tracks]
    assert all(np.isfinite(values).all() for sample in samples for values in sample.values())
    # Use the original sprite plane and native sequence interpolation in an
    # orthographic side projection, baking only motion into a reusable atlas.
    width,height=384,108;frames=[]
    source_points=np.float32([[0,0],[texture.width-1,0],[0,texture.height-1]])
    world=[]
    for u,v in [(0,0),(1,0),(0,1)]:
        along=(u-.16)*1.25;across=(v-.5)*.46
        world.append([0,along*.12+across*.993,along*.993-across*.12])
    world=np.array(world)
    for index in range(count):
        contribution=np.zeros((height,width,3),dtype=np.float32)
        for sample in samples:
            points=world*sample['scale'][index]+sample['position'][index]
            projected=np.c_[((3.6-points[:,2])/7.1)*(width-1),((.8-points[:,1])/1.95)*(height-1)].astype(np.float32)
            matrix=cv2.getAffineTransform(source_points,projected)
            warped=cv2.warpAffine(rgba[:,:,:3],matrix,(width,height),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            contribution+=warped
        frames.append(np.clip(contribution,0,1))
    output,error=straight_frames(np.stack(frames))
    source=dict(texture=str(ORIGINAL/'流星贴图.png'),texture_sha256=digest(ORIGINAL/'流星贴图.png'),
                sequence=str(ORIGINAL/'unpacked/res/particles/ba_pz70_swim_meteor_r1/left.seq'),
                sequence_sha256=digest(ORIGINAL/'unpacked/res/particles/ba_pz70_swim_meteor_r1/left.seq'),
                alpha_reconstruction_max_error=error,note='Original left-side 3-sprite sequence baked to RGBA; R2 alpha-additive blending retained.')
    save(name,'最早蓝白流星的原贴图与三条错时运动，4.8 秒循环；按原生序列烘焙为透明动画，可用于任意车型。',
         output,fps,source,width=7.1,brightness=2.2,loop_note='Original native sequence period, 4.8s; no overlap retiming.')


def overview():
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',14)
    page=Image.new('RGB',(1080,700),'#f5f5f7');draw=ImageDraw.Draw(page)
    for i,row in enumerate(REPORT):
        x=24+(i%2)*532;y=20+(i//2)*340
        draw.rounded_rectangle((x,y,x+508,y+320),radius=12,fill='white')
        draw.text((x+16,y+12),row['name'],font=font,fill='#1d1d1f')
        im=Image.open(Path(row['gif']).parent/'透明帧.png').convert('RGBA')
        # Show the actual additive composite on a dark stage, not an opaque screenshot.
        rgb=np.asarray(im,dtype=float);contribution=rgb[:,:,:3]*(rgb[:,:,3:]/255)* (2.2 if i==3 else 1)
        comp=Image.fromarray(np.uint8(np.clip(contribution+np.array([20,25,35]),0,255)))
        comp.thumbnail((476,236));page.paste(comp,(x+16,y+52+(236-comp.height)//2))
        draw.text((x+16,y+294),'%d 帧 · %g FPS · %.2f 秒循环 · 透明素材'%(row['frames'],row['fps'],row['seconds']),font=small,fill='#64748b')
    page.save(OUT/'四款AE预设总览.png')


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    videos();meteor();overview()
    (OUT/'制作与验证记录.json').write_text(json.dumps(dict(presets=REPORT,in_game_tested=False),ensure_ascii=False,indent=2),encoding='utf-8')
    print('FOUR_PRESETS_READY',flush=True)
