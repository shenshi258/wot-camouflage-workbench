"""User-owned image elements: original copies, thumbnails and editable labels."""
import base64,hashlib,io,json,re,tempfile,threading,uuid
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,UnidentifiedImageError
from .common import ROOT,atomic_write

MAX_BYTES=8*1024*1024
MAX_PIXELS=25000000
MAX_ASSETS=1000
FORMATS={'PNG':('image.png','image/png'),'JPEG':('image.jpg','image/jpeg'),'WEBP':('image.webp','image/webp')}
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
        return data

    def list(self):
        records=[];issues=0
        with _lock:
            if self.root.is_dir():
                for folder in self.root.iterdir():
                    if not ID.fullmatch(folder.name):continue
                    try:
                        row=self.record(folder.name)
                        records.append({key:row[key] for key in ('id','name','category','width','height','bytes','format')})
                    except (OSError,ValueError,KeyError,TypeError):issues+=1
        return dict(items=sorted(records,key=lambda row:(row['category'].casefold(),row['name'].casefold(),row['id'])),issues=issues)

    def import_image(self,raw,name,category='未分类'):
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:raise ValueError('单张图片不能超过 8 MB。')
        source_name=str(name).replace('\\','/').rsplit('/',1)[-1]
        title=label(Path(source_name).stem[:100],100,'未命名素材');category=label(category,40,'未分类')
        key=hashlib.sha256(raw).hexdigest()
        with _lock:
            if self.asset(key).exists():return dict(item=self.record(key),duplicate=True)
            if len(self.list()['items'])>=MAX_ASSETS:raise ValueError('素材库最多 1000 项，请先移出不需要的素材。')
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    kind=image.format
                    if kind not in FORMATS or image.width*image.height>MAX_PIXELS:raise ValueError('请选择不超过 2500 万像素的 PNG、JPG 或 WebP 图片。')
                    if getattr(image,'n_frames',1)>1:raise ValueError('图片素材库只收静态图案；动画请使用 AE 的 GIF / 视频导入。')
                    preview=ImageOps.exif_transpose(image).convert('RGBA')
            except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as error:raise ValueError('图片无法读取。') from error
            width,height=preview.size;preview.thumbnail((160,160),Image.Resampling.LANCZOS)
            thumbnail=io.BytesIO();preview.save(thumbnail,format='PNG');thumb=thumbnail.getvalue()
            record=dict(schema=1,id=key,name=title,category=category,width=width,height=height,bytes=len(raw),format=kind,
                        source_name=source_name[:255],created=datetime.now(timezone.utc).isoformat(),thumb_sha256=hashlib.sha256(thumb).hexdigest())
            self.root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.import_',dir=self.root) as temporary:
                scratch=Path(temporary)
                (scratch/FORMATS[kind][0]).write_bytes(raw);(scratch/'thumb.png').write_bytes(thumb)
                (scratch/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                try:scratch.replace(self.asset(key))
                except FileExistsError:return dict(item=self.record(key),duplicate=True)
            return dict(item=record,duplicate=False)

    def import_payload(self,data):
        if not isinstance(data,dict) or not {'name','image'}<=set(data)<= {'name','image','category'} or not isinstance(data['image'],str):raise ValueError('导入内容无效。')
        if not isinstance(data['name'],str) or len(data['name'])>255:raise ValueError('文件名无效。')
        if len(data['image'])>4*((MAX_BYTES+2)//3):raise ValueError('单张图片不能超过 8 MB。')
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
            if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('素材文件已变化，请重新导入。')
            return raw,'image/png' if thumbnail else FORMATS[record['format']][1]

    def edit(self,key,name,category):
        with _lock:
            row=self.record(key);row.update(name=label(name,100,'未命名素材'),category=label(category,40,'未分类'))
            atomic_write(self.asset(key)/'record.json',json.dumps(row,ensure_ascii=False,indent=2).encode('utf-8'))
            return row

    def remove(self,key):
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
