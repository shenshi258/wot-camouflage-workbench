"""Local GIF/video sampling to the existing straight-alpha AE atlas format."""
import bisect,math
from pathlib import Path
import numpy as np
from PIL import Image,UnidentifiedImageError
from . import ae_effects as ae

VIDEO_SUFFIXES={'.mp4','.mov','.webm','.avi','.mkv','.m4v'}
ALPHA_MODES={'保留画面 / GIF 透明':'preserve','黑底转透明（光效）':'black'}
MAX_FILE_BYTES=2*1024**3
MAX_GIF_BYTES=128*1024**2
MAX_GIF_FRAMES=4096
MAX_GIF_PIXELS=512*1024**2


def local_file(path):
    p=Path(path)
    if not p.is_file():raise ValueError('请选择本地 GIF 或视频文件。')
    if p.suffix.lower() not in VIDEO_SUFFIXES|{'.gif'}:raise ValueError('支持 GIF、MP4、MOV、WEBM、AVI、MKV、M4V。')
    limit=MAX_GIF_BYTES if p.suffix.lower()=='.gif' else MAX_FILE_BYTES
    if not 0<p.stat().st_size<=limit:raise ValueError('素材过大或为空；GIF 最多 128 MB，视频最多 2 GB。')
    return p


def video_capture(path):
    try:import cv2
    except ImportError as error:raise ValueError('当前程序缺少视频读取组件，请使用完整便携包。') from error
    cap=cv2.VideoCapture(str(path),cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release();raise ValueError('无法读取视频，请尝试 MP4（H.264）或 AVI 格式。')
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,1)
    return cv2,cap


def probe(path):
    p=local_file(path)
    if p.suffix.lower()=='.gif':
        try:
            with Image.open(p) as image:
                if image.format!='GIF':raise ValueError('文件内容不是 GIF。')
                width,height=image.size;count=image.n_frames
                if max(width,height)>4096 or count>MAX_GIF_FRAMES or width*height*count>MAX_GIF_PIXELS:
                    raise ValueError('GIF 分辨率或帧数过大，请先缩小或截短素材。')
                durations=[]
                for i in range(count):
                    image.seek(i)
                    milliseconds=float(image.info.get('duration',100))
                    # GIF 的零延时没有统一播放约定，此处按常见的 100 ms 处理。
                    durations.append(milliseconds/1000 if milliseconds>0 else .1)
        except (OSError,UnidentifiedImageError,EOFError) as error:raise ValueError('GIF 不完整或无法读取。') from error
        duration=sum(durations);kind='gif';native_fps=count/duration
    else:
        cv2,cap=video_capture(p)
        try:
            native_fps=float(cap.get(cv2.CAP_PROP_FPS));count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if not math.isfinite(native_fps) or native_fps<=0 or count<=0:raise ValueError('无法识别视频时长，请先转换为 MP4 或 AVI。')
            if max(width,height)>8192 or width*height>4096**2:raise ValueError('视频分辨率过大，请缩小后导入。')
            duration=count/native_fps;durations=None;kind='video'
        finally:cap.release()
    if width<1 or height<1 or not math.isfinite(duration) or not 0<duration<=24*3600:raise ValueError('素材尺寸或时长无效。')
    return dict(kind=kind,name=p.name,width=width,height=height,frames=count,duration=duration,native_fps=native_fps,durations=durations)


def plan(info,start,end,fps):
    values=[]
    for value in (start,end,fps):
        if isinstance(value,bool):raise ValueError('时间和帧率请填写数值。')
        try:number=float(value)
        except (TypeError,ValueError):raise ValueError('时间和帧率请填写数值。')
        if not math.isfinite(number):raise ValueError('时间和帧率必须是有限数值。')
        values.append(number)
    start,end,fps=values
    if not 1<=fps<=60:raise ValueError('导入帧率范围为 1～60 FPS。')
    if not 0<=start<end or end>info['duration']+1e-6:raise ValueError('请填写素材时长内的有效开始、结束时间。')
    end=min(end,info['duration'])
    count=math.ceil((end-start)*fps-1e-6)
    if not 1<=count<=ae.MAX_FRAMES:
        raise ValueError('当前片段需要 %d 帧，最多 128 帧；请缩短片段或降低帧率。'%count)
    return dict(start=start,end=end,fps=fps,frames=count,seconds=count/fps,times=[min(end-1e-9,start+i/fps) for i in range(count)])


def defaults(info):
    end=info['duration'] if info['duration']<=128 else min(4.,info['duration'])
    fps=max(1.,min(24.,info['native_fps'],math.floor(128/end)))
    return dict(start=0.,end=end,fps=fps)


def black_to_alpha(image):
    rgba=np.asarray(image.convert('RGBA'),dtype=np.float32)/255
    rgb=rgba[:,:,:3];peak=rgb.max(2,keepdims=True)
    straight=np.divide(rgb,peak,out=np.zeros_like(rgb),where=peak>0)
    # RGB×Alpha 的光能保持；不把暗尾迹预乘两次，也不改原有透明边缘。
    return Image.fromarray(np.uint8(np.concatenate((straight,rgba[:,:,3:]*peak),axis=2)*255+.5))


def import_media(path,destination,*,start=0,end=None,fps=24,alpha_mode='preserve'):
    p=local_file(path);info=probe(p)
    if alpha_mode not in ALPHA_MODES.values():raise ValueError('背景处理方式无效。')
    selected=plan(info,start,info['duration'] if end is None else end,fps);frames=[];original_size=(info['width'],info['height'])
    if info['kind']=='gif':
        ends=np.cumsum(info['durations']).tolist()
        # 顺序 seek 保留 GIF 的 disposal/compositing 语义，不能把增量帧当完整图片。
        with Image.open(p) as image:
            for time in selected['times']:
                index=min(info['frames']-1,bisect.bisect_right(ends,time+1e-9))
                image.seek(index);frame=image.convert('RGBA');frame.thumbnail((512,512),Image.Resampling.LANCZOS)
                frames.append(black_to_alpha(frame) if alpha_mode=='black' else frame)
    else:
        cv2,cap=video_capture(p)
        try:
            for time in selected['times']:
                # FFmpeg 在解码器中处理旋转元数据；按时间 seek，避免先解码整个长视频。
                if not cap.set(cv2.CAP_PROP_POS_MSEC,time*1000):raise ValueError('视频无法定位到所选片段，请转换为 MP4 后重试。')
                ok,bgr=cap.read()
                if not ok:raise ValueError('所选片段解码不完整，请缩短结束时间或转换视频格式。')
                h,w=bgr.shape[:2]
                if not frames:original_size=(w,h)
                scale=min(1.,512/max(w,h))
                if scale<1:bgr=cv2.resize(bgr,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA)
                frame=Image.fromarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)).convert('RGBA')
                frames.append(black_to_alpha(frame) if alpha_mode=='black' else frame)
        finally:cap.release()
    clip=ae.pack_frames(frames,destination,allow_opaque=alpha_mode=='preserve')
    ratio=min(1.,4096/max(original_size))
    clip['frame_size']=[max(1,round(value*ratio)) for value in original_size]
    # 原始路径不进入可移走的工程/预设，只保留必要的导入说明。
    clip['import_info']=dict(kind=info['kind'],source_name=info['name'],source_size=list(original_size),start=selected['start'],end=selected['end'],fps=selected['fps'],frames=selected['frames'],alpha_mode=alpha_mode)
    return clip
