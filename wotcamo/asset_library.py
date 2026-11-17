"""User-owned image/GIF elements with byte-preserved copies and thumbnails."""
import base64,hashlib,io,json,math,re,tempfile,threading,uuid
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,UnidentifiedImageError
from .common import ROOT,atomic_write

MAX_BYTES=8*1024*1024
MAX_PIXELS=25000000
MAX_GIF_FRAMES=512
MAX_GIF_TOTAL_PIXELS=128*1024*1024
MAX_ASSETS=1000
FORMATS={'PNG':('image.png','image/png'),'JPEG':('image.jpg','image/jpeg'),'WEBP':('image.webp','image/webp'),'GIF':('image.gif','image/gif')}
ID=re.compile(r'[a-f0-9]{64}')
TRASH_ID=re.compile(r'[a-f0-9]{64}_[0-9]{8}T[0-9]{12}_[a-f0-9]{8}')
_lock=threading.RLock()


def label(value,limit,default=''):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):raise ValueError('素材名称或分类无效。')
    return value.strip() or default


class Library:
    def __init__(self,root=None):
        self.root=Path(root) if root is not None else ROOT/'素材库/图片元素'
        if root is None and not self.root.resolve().is_relative_to(ROOT.resolve()):raise ValueError('素材库目录不能指向程序目录之外。')

    def safe_path(self,*parts):
        result=self.root.joinpath(*parts)
        if not result.resolve().is_relative_to(self.root.resolve()) or result.resolve()==self.root.resolve():raise ValueError('素材路径无效。')
        return result

    def asset(self,key):
        if not isinstance(key,str) or not ID.fullmatch(key):raise ValueError('素材编号无效。')
        return self.safe_path(key)

    def record(self,key):
        path=self.asset(key)/'record.json'
        if not path.resolve().is_relative_to(self.asset(key).resolve()) or path.stat().st_size>16384:raise ValueError('素材记录无效。')
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('schema')!=1 or data.get('id')!=key or data.get('format') not in FORMATS:raise ValueError('素材记录损坏。')
        label(data['name'],100);label(data['category'],40)
        if not all(type(data.get(k)) is int and data[k]>0 for k in ('width','height','bytes')):raise ValueError('素材尺寸无效。')
        if data['format']=='GIF':
            frames=data.get('frames');duration=data.get('duration');delays=data.get('durations_ms')
            if type(frames) is not int or not 1<=frames<=MAX_GIF_FRAMES or not isinstance(duration,(int,float)) or isinstance(duration,bool) or not math.isfinite(duration) or duration<=0:raise ValueError('GIF 播放记录无效。')
            if not isinstance(delays,list) or len(delays)!=frames or not all(type(value) is int and 0<value<=655350 for value in delays) or not math.isclose(sum(delays)/1000,duration,abs_tol=1e-8):raise ValueError('GIF 帧延时记录无效。')
        return data

    def list(self):
        records=[];issues=0
        with _lock:
            if self.root.is_dir():
                for folder in self.root.iterdir():
                    if not ID.fullmatch(folder.name):continue
                    try:
                        row=self.record(folder.name)
                        records.append({key:row[key] for key in ('id','name','category','width','height','bytes','format','frames','duration') if key in row})
                    except (OSError,ValueError,KeyError,TypeError):issues+=1
        return dict(items=sorted(records,key=lambda row:(row['category'].casefold(),row['name'].casefold(),row['id'])),issues=issues)

    def import_image(self,raw,name,category='未分类'):
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:raise ValueError('单份图片或 GIF 不能超过 8 MB。')
        source_name=str(name).replace('\\','/').rsplit('/',1)[-1]
        title=label(Path(source_name).stem[:100],100,'未命名素材');category=label(category,40,'未分类')
        key=hashlib.sha256(raw).hexdigest()
        with _lock:
            if self.asset(key).exists():return dict(item=self.record(key),duplicate=True)
            if len(self.list()['items'])>=MAX_ASSETS:raise ValueError('素材库最多 1000 项，请先移出不需要的素材。')
            animation={}
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    kind=image.format
                    if kind not in FORMATS or image.width*image.height>MAX_PIXELS:raise ValueError('请选择不超过 2500 万像素的 PNG、JPG、WebP 或 GIF。')
                    frames=getattr(image,'n_frames',1)
                    if kind=='GIF':
                        if frames>MAX_GIF_FRAMES or max(image.size)>4096 or image.width*image.height*frames>MAX_GIF_TOTAL_PIXELS:
                            raise ValueError('GIF 最多 512 帧、4096 像素边长及 1.28 亿累计像素，请先缩小或截短。')
                        delays=[];disposals=[]
                        image.seek(0);preview=image.convert('RGBA')
                        # Read every frame in order to validate disposal/compositing
                        # and truncated data. Only the thumbnail is decoded/stored;
                        # the original GIF remains byte-for-byte unchanged.
                        for index in range(frames):
                            image.seek(index);image.load()
                            delay=image.info.get('duration',100)
                            if type(delay) is not int or delay<0 or delay>655350:raise ValueError('GIF 帧延时无效。')
                            disposal=getattr(image,'disposal_method',0)
                            if disposal not in (0,1,2,3):raise ValueError('GIF 帧清除方式无效。')
                            delays.append(delay or 100);disposals.append(disposal)
                        animation=dict(frames=frames,duration=sum(delays)/1000,durations_ms=delays,disposals=disposals)
                    elif frames>1:raise ValueError('动态素材请使用 GIF；当前不接收动态 WebP 或 APNG。')
                    # 只为缩略图校正方向；原文件副本按字节保留，供贴图导出复用。
                    else:preview=ImageOps.exif_transpose(image).convert('RGBA')
            except (OSError,UnidentifiedImageError,Image.DecompressionBombError,EOFError,IndexError) as error:raise ValueError('图片或 GIF 不完整，无法读取。') from error
            width,height=preview.size;preview.thumbnail((160,160),Image.Resampling.LANCZOS)
            thumbnail=io.BytesIO();preview.save(thumbnail,format='PNG');thumb=thumbnail.getvalue()
            record=dict(schema=1,id=key,name=title,category=category,width=width,height=height,bytes=len(raw),format=kind,
                        source_name=source_name[:255],created=datetime.now(timezone.utc).isoformat(),thumb_sha256=hashlib.sha256(thumb).hexdigest())
            record.update(animation)
            self.root.mkdir(parents=True,exist_ok=True)
            # 三件文件齐全后才把临时目录提交为素材，列表不会看见半份导入。
            with tempfile.TemporaryDirectory(prefix='.import_',dir=self.root) as temporary:
                scratch=Path(temporary)
                (scratch/FORMATS[kind][0]).write_bytes(raw);(scratch/'thumb.png').write_bytes(thumb)
                (scratch/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                try:scratch.replace(self.asset(key))
                except FileExistsError:return dict(item=self.record(key),duplicate=True)
            return dict(item=record,duplicate=False)

    def import_file(self,path,category='未分类'):
        """Read a user-selected local file after checking its size."""
        path=Path(path)
        if not path.is_file() or not 0<path.stat().st_size<=MAX_BYTES:raise ValueError('请选择不超过 8 MB 的本地图片或 GIF。')
        return self.import_image(path.read_bytes(),path.name,category)

    def import_payload(self,data):
        if not isinstance(data,dict) or not {'name','image'}<=set(data)<= {'name','image','category'} or not isinstance(data['image'],str):raise ValueError('导入内容无效。')
        if not isinstance(data['name'],str) or len(data['name'])>255:raise ValueError('文件名无效。')
        if len(data['image'])>4*((MAX_BYTES+2)//3):raise ValueError('单份图片或 GIF 不能超过 8 MB。')
        try:raw=base64.b64decode(data['image'],validate=True)
        except (ValueError,TypeError):raise ValueError('图片内容无效。')
        return self.import_image(raw,data['name'],data.get('category','未分类'))

    def image(self,key,thumbnail=False):
        with _lock:
            record=self.record(key);folder=self.asset(key)
            name='thumb.png' if thumbnail else FORMATS[record['format']][0]
            path=folder/name
            if not path.resolve().is_relative_to(folder.resolve()) or path.stat().st_size>(512*1024 if thumbnail else MAX_BYTES):raise ValueError('素材文件无效。')
            raw=path.read_bytes();expected=record['thumb_sha256'] if thumbnail else key
            if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('素材副本已变化，请移出该项后重新导入。')
            return raw,'image/png' if thumbnail else FORMATS[record['format']][1]

    def edit(self,key,name,category):
        with _lock:
            row=self.record(key);row.update(name=label(name,100,'未命名素材'),category=label(category,40,'未分类'))
            atomic_write(self.asset(key)/'record.json',json.dumps(row,ensure_ascii=False,indent=2).encode('utf-8'))
            return row

    def remove(self,key):
        """移动副本到库内回收站；不触及外部原图或已经烘焙的贴图。"""
        with _lock:
            self.record(key)
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            token=key+'_'+stamp+'_'+uuid.uuid4().hex[:8]
            trash=self.safe_path('回收站');trash.mkdir(exist_ok=True)
            destination=self.safe_path('回收站',token)
            self.asset(key).rename(destination)
            return token

    def restore(self,token):
        if not isinstance(token,str) or not TRASH_ID.fullmatch(token):raise ValueError('回收项无效。')
        with _lock:
            key=token[:64];source=self.safe_path('回收站',token);target=self.asset(key)
            if target.exists():raise ValueError('这份素材已在库中，回收项继续保留。')
            if not source.is_dir():raise ValueError('回收项已不存在。')
            source.rename(target)
            return self.record(key)

    def action(self,data):
        if not isinstance(data,dict):raise ValueError('素材操作无效。')
        if data.get('action')=='edit' and set(data)=={'action','id','name','category'}:return dict(item=self.edit(data['id'],data['name'],data['category']))
        if data.get('action')=='remove' and set(data)=={'action','id'}:return dict(trash_id=self.remove(data['id']))
        if data.get('action')=='restore' and set(data)=={'action','trash_id'}:return dict(item=self.restore(data['trash_id']))
        raise ValueError('素材操作无效。')
