"""Disposable image library and synthetic model for a real browser check."""
import base64,json,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_paint3d import Paint3DTests
from wotcamo import preview3d

fixture=Paint3DTests();fixture.setUp();sessions=[]
try:
    preview3d.ROOT=fixture.root
    library_root=fixture.root/'library'
    library=preview3d.Session(None,None,launch=False,library_only=True,library_root=library_root);sessions.append(library)
    paint=preview3d.Session(fixture.project,str(fixture.client),launch=False,paint={'title':'素材库验证'},library_root=library_root);sessions.append(paint)
    paint.worker=subprocess.Popen([sys.executable,'-B','-m','wotcamo.preview3d_assets',str(paint.folder)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
    files=[]
    specs=[('橙色警示',(255,140,40)),('冰蓝十字',(120,220,255)),('粉色流线',(255,100,170)),('紫色六角',(175,130,255)),('青色线条',(60,220,180)),('金色边框',(255,220,100)),('白色标记',(240,245,255)),('蓝色几何',(80,140,255))]
    for index,(name,colour) in enumerate(specs):
        image=Image.new('RGBA',(100,80));draw=ImageDraw.Draw(image)
        if index%3==0:draw.polygon([(50,8),(92,68),(8,68)],fill=(*colour,230))
        elif index%3==1:
            draw.rounded_rectangle((38,8,62,72),radius=7,fill=(*colour,240));draw.rounded_rectangle((15,28,85,52),radius=7,fill=(*colour,240))
        else:
            for y in (17,35,53):draw.line([(12,y+8),(88,y)],fill=(*colour,220),width=6)
        path=fixture.root/(name+'.png');image.save(path)
        files.append(dict(name=path.name,image=base64.b64encode(path.read_bytes()).decode()))
    ready=ROOT/'.cache/library38_browser_ready.json'
    ready.write_text(json.dumps(dict(library_url=library.url,paint_url=paint.url,files=files,stop=str(fixture.root/'stop_test')),ensure_ascii=False),encoding='utf-8')
    print('LIBRARY_BROWSER_READY',flush=True)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline and not (fixture.root/'stop_test').exists():time.sleep(.1)
finally:
    for session in sessions:session.close()
    fixture.doCleanups()
