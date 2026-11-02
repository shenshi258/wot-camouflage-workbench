"""Local-only 3D preview session, asset worker and independent WebView2 window."""
import argparse
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit

from .common import ROOT
from . import preview3d_assets as assets
from . import __version__, APP_NAME


class Session:
    def __init__(self,project,client,launch=True,paint=None,effect=None):
        self.token=secrets.token_urlsafe(24);self.events=queue.Queue();self.metrics={};self.closed=False
        self.paint=paint;self.project=project;self.client=client;self._paint_lock=threading.Lock()
        self.folder=ROOT/'.cache/preview3d_sessions'/secrets.token_hex(12);self.folder.mkdir(parents=True)
        self.state={};self._signature=None;self._revision=-1;self.worker=None;self.viewer=None
        self.effect=None
        if effect:self.update_effect(*effect)
        self._body=None;self._ready=None;self._lock=threading.Lock()
        assets.save_snapshot(project,self.folder)
        cache=ROOT/'.cache/preview3d_models';cache.mkdir(parents=True,exist_ok=True)
        assets.write_json(self.folder/'request.json',dict(client=str(client),cache=str(cache)))
        self.update(dict(recipe=project['recipe'],lights=[dict(id=x['id'],selected=x.get('selected',False),recipe=x.get('配方')) for x in project['lights']],picked=[]))
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,code,data,kind='application/json; charset=utf-8'):
                if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
                try:
                    self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    self.end_headers();self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
            def route(self):
                if self.headers.get('Host')!='127.0.0.1:%d'%outer.server.server_port:return None
                path=unquote(urlsplit(self.path).path)
                prefix='/'+outer.token+'/'
                return path[len(prefix):] if path.startswith(prefix) else None
            def do_GET(self):
                route=self.route()
                if route is None:return self.send(404,b'Not found','text/plain')
                try:
                    if route=='status':return self.send(200,outer.status())
                    if route=='effect/atlas.png' and outer.effect:
                        file=outer.folder/'ae_atlas.png'
                    elif route.startswith('body/'):
                        info=outer.read_json('body.json')
                        if not info:return self.send(202,dict(message='loading'))
                        filename=route[5:]
                        if not re.fullmatch(r'(?:mesh_\d+\.(?:bin|idx)|texture_[a-f0-9]+\.png|scene\.json)',filename):return self.send(404,b'Not found')
                        file=Path(info['folder'])/filename
                    elif route.startswith('lamps/'):
                        match=re.fullmatch(r'lamps/(\d+)/(mesh_\d+\.(?:bin|idx)|texture_[a-f0-9]+\.png|scene\.json|animation\.bin)',route)
                        if not match:return self.send(404,b'Not found')
                        file=outer.folder/('lamps_'+match[1])/match[2]
                    else:
                        web=Path(__file__).parent/'preview_web';file=(web/(route or 'index.html')).resolve()
                        if not file.is_relative_to(web.resolve()):return self.send(404,b'Not found')
                    if not file.is_file():return self.send(404,b'Not found')
                    kind='text/javascript' if file.suffix=='.js' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                    return self.send(200,file.read_bytes(),kind)
                except (OSError,ValueError):return self.send(503,dict(message='资源正在更新'))
            def do_POST(self):
                route=self.route();origin=self.headers.get('Origin')
                if route not in ('select','bodyselect','metrics','closed','performance','paint','effectplace','effectparams','effectplane','theme') or (route=='paint' and not outer.paint) or (origin and origin!='http://127.0.0.1:%d'%outer.server.server_port):
                    return self.send(403,b'Forbidden')
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=(48*1024*1024 if route=='paint' else (250000 if route=='bodyselect' else 16384)):return self.send(413,b'Too large')
                    data=json.loads(self.rfile.read(size))
                    if not isinstance(data,dict):raise ValueError('请求参数无效。')
                    if route=='theme':
                        from . import ui_theme
                        if set(data)!={'glass'} or type(data['glass']) is not bool:raise ValueError('界面风格无效。')
                        ui_theme.save_theme_preference(data['glass'])
                        return self.send(200,dict(ok=True,glass=data['glass']))
                    elif route=='effectplane':
                        if not outer.effect or data:raise ValueError('新建平面请求无效。')
                        outer.events.put(dict(type='effectplane'))
                    elif route=='effectplace':
                        import math
                        if not outer.effect or data.get('part') not in ('hull','turret','gun'):raise ValueError()
                        point=data.get('position')
                        if not isinstance(point,list) or len(point)!=3 or not all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=30 for x in point):raise ValueError()
                        outer.events.put(dict(type='effectplace',part=data['part'],position=point))
                    elif route=='effectparams':
                        from . import ae_effects
                        allowed={'tint_color','tint_strength','uv_scale','uv_scale_x','uv_scale_y','crop_left','crop_right','crop_top','crop_bottom','x','y','z','mirror'}|set(ae_effects.WARPS)
                        move={'x','y','z'}|set(ae_effects.WARPS)
                        if not outer.effect or not data or not set(data)<=allowed:raise ValueError('只允许调整 AE 缩放、裁剪、位置与四角变形。')
                        if outer.effect['config']['placement']!='plane' and set(data)&move:raise ValueError('贴面模式只能调整缩放与裁剪，位置和变形属于独立平面。')
                        values=ae_effects.config(dict(outer.effect['config'],**data))
                        outer.events.put(dict(type='effectparams',values={key:values[key] for key in data}))
                    elif route=='select':
                        if not isinstance(data.get('id'),str) or len(data['id'])>200:raise ValueError()
                        outer.events.put(dict(type='select',id=data['id'],add=bool(data.get('add')),subtract=bool(data.get('subtract'))))
                    elif route=='bodyselect':
                        from . import area_selection
                        info=outer.read_json('body.json')
                        if not info:raise ValueError('车体尚未加载')
                        selection=area_selection.resolve(info['scene'],data.get('batches'))
                        event=dict(type='bodyselect',selection=selection)
                        if data.get('snap'):
                            import math
                            point=data.get('point')
                            if not outer.effect or data['snap'] is not True or not isinstance(point,list) or len(point)!=3 or not all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=30 for x in point):raise ValueError('吸附点无效。')
                            event.update(snap=True,point=point)
                        outer.events.put(event)
                    elif route=='paint':
                        # Only a token-scoped paint session may generate output;
                        # the worker rechecks hashes instead of trusting UV data.
                        from . import paint3d
                        info=outer.read_json('body.json')
                        if not info:raise ValueError('车体尚未加载。')
                        if not outer._paint_lock.acquire(blocking=False):raise ValueError('正在生成，请等待。')
                        try:
                            from .common import title_name
                            name=data.get('title',outer.paint['title'])
                            if not isinstance(name,str):raise ValueError('成品名称无效。')
                            target,report=paint3d.build(outer.project,outer.client,info['scene'],data,ROOT/'result/三维贴图',title_name(name))
                        finally:outer._paint_lock.release()
                        outer.events.put(dict(type='paint_complete',target=str(target),sha256=report['artifact']['sha256']))
                        return self.send(200,dict(ok=True,path=str(target),sha256=report['artifact']['sha256']))
                    elif route=='metrics':outer.metrics=data
                    elif route=='performance':
                        if data.get('value') not in ('fast','balanced','fine'):raise ValueError()
                        outer.events.put(dict(type='performance',value=data['value']))
                    elif route=='closed':outer.events.put(dict(type='closed'))
                    return self.send(200,dict(ok=True))
                except (ValueError,TypeError,OSError,KeyError) as error:
                    if route in ('paint','effectparams','bodyselect'):return self.send(400,dict(error=str(error)))
                    return self.send(400,b'Invalid request')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.server_thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True);self.server_thread.start()
        self.url='http://127.0.0.1:%d/%s/index.html'%(self.server.server_port,self.token)
        if paint:self.url+='?paint=1'
        if launch:self.launch()

    def read_json(self,name):
        try:return json.loads((self.folder/name).read_text(encoding='utf-8'))
        except (OSError,ValueError):return None

    def update_effect(self,clip,config):
        from . import ae_effects
        clip=ae_effects.colorized_clip(clip,config,self.folder/'color_cache')
        data=ae_effects.preview_data(clip,config,self.project,self.client)
        if self.effect is None or self.effect['atlas_sha256']!=data['atlas_sha256']:
            shutil.copyfile(clip['atlas'],self.folder/'ae_atlas.png')
        data['revision']=0 if self.effect is None else self.effect['revision']+1
        self.effect=data

    def status(self):
        from . import ui_theme
        with self._lock:state=dict(self.state)
        body=self.read_json('body.json');ready=self.read_json('ready.json');error=self.read_json('error.json')
        return dict(uiTheme=ui_theme.theme_preference(),body=body['scene'] if body else None,ready=ready['scene'] if ready else None,
                    readyRevision=ready['revision'] if ready else -1,state=state,
                    closed=self.closed,paintTitle=self.paint.get('title','') if self.paint else None,effect=self.effect,
                    error=error if error and (error['revision']==-1 or error['revision']>=state['revision']) else None,
                    progress=self.read_json('progress.json') or dict(message='正在读取整车资源…'))

    def update(self,state):
        state={k:v for k,v in state.items() if k!='revision'}
        signature=json.dumps({k:v for k,v in state.items() if k not in ('picked','performance')},ensure_ascii=False,sort_keys=True)
        with self._lock:
            if signature!=self._signature:
                self._signature=signature;self._revision+=1
                assets.write_json(self.folder/'state.json',dict(state,revision=self._revision))
            self.state=dict(state,revision=self._revision)

    def launch(self):
        flags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
        self.log=(self.folder/'preview.log').open('ab')
        isolation=['-s'] if sys.flags.no_user_site else []
        self.worker=subprocess.Popen([sys.executable,*isolation,'-m','wotcamo.preview3d_assets',str(self.folder)],cwd=ROOT,
                                      stdout=self.log,stderr=self.log,creationflags=flags)
        self.viewer=subprocess.Popen([sys.executable,*isolation,'-m','wotcamo.preview3d','--viewer',self.url,'--session',str(self.folder)],cwd=ROOT,
                                      stdout=self.log,stderr=self.log,creationflags=flags)

    def close(self):
        if self.closed:return
        self.closed=True;(self.folder/'stop').touch()
        for process in (self.viewer,self.worker):
            if process and process.poll() is None:
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:process.wait(timeout=1)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)
        self.server.shutdown();self.server.server_close()
        if hasattr(self,'log'):self.log.close()
        assets.write_json(self.folder/'closed.json',dict(metrics=self.metrics,revision=self._revision))
        # Only disposable files created by this session are removed. Input skins,
        # project metadata, error evidence and cached vehicle assets are retained.
        (self.folder/'geometry.npz').unlink(missing_ok=True)
        expected=(ROOT/'.cache/preview3d_sessions').resolve()
        if self.folder.resolve().is_relative_to(expected):
            for path in self.folder.glob('lamps_*'):
                if (path.is_dir() and not path.is_symlink() and re.fullmatch(r'lamps_\d+',path.name)
                        and path.resolve().is_relative_to(self.folder.resolve())):shutil.rmtree(path)


def viewer(url,smoke=None):
    import tempfile
    profile=ROOT/'.cache/preview3d_webview'
    profile.mkdir(parents=True,exist_ok=True)
    temp=ROOT/'.cache/preview3d_temp';temp.mkdir(parents=True,exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(temp);tempfile.tempdir=str(temp)
    dependencies=ROOT/'tools/preview_webview_stable'
    if dependencies.exists():sys.path.insert(0,str(dependencies))
    try:import webview
    except ImportError as error:raise RuntimeError('三维预览窗口组件缺失，请使用完整的工作台程序。') from error
    class Api:
        def close(self):window.destroy()
    window=webview.create_window(APP_NAME+' · 三维预览',url,width=1100,height=720,min_size=(800,600),background_color='#0b111c',js_api=Api())
    if smoke:
        def test():
            report={};started=time.monotonic()
            try:
                while time.monotonic()-started<90:
                    time.sleep(.5)
                    report=window.evaluate_js('window.previewTest ? window.previewTest.report() : ({loading:true})')
                    if report.get('ready'):break
                    if report.get('error'):raise RuntimeError(str(report['error']))
                if not report.get('ready'):raise RuntimeError('三维预览加载超时：'+str(report))
                report['interaction']=window.evaluate_js('window.previewTest.exercise()')
                effect=window.evaluate_js('window.previewTest.effectState()')
                if effect.get('frames'):
                    window.evaluate_js('window.previewTest.effectSideView()')
                    fps=effect['config']['fps'];count=effect['frames']
                    indices=[0,min(1,count-1),count-1,count+min(1,count-1)]
                    observed=[window.evaluate_js('window.previewTest.effectTime(%s)'%((i+.25)/fps)) for i in indices]
                    if observed!=[i%count for i in indices]:raise RuntimeError('AE 动画帧序与导出不一致。')
                    effect['tested_frames']=observed;effect['face_click']=window.evaluate_js('window.previewTest.surfaceClickTest()')
                    if not effect['face_click'] or effect['face_click']['count']!=1:raise RuntimeError('单面点选检查失败。')
                    report['ae_effect']=effect
                    window.evaluate_js('window.previewTest.effectTime(0.25)')
                    if (Path(smoke)/'size_check').exists():
                        wanted=window.evaluate_js('window.previewTest.sizeAdjustTest()')
                        for _ in range(100):
                            time.sleep(.15);sized=window.evaluate_js('window.previewTest.effectState()')
                            if all(sized['config'].get(k)==v for k,v in wanted.items()):break
                        if not all(sized['config'].get(k)==v for k,v in wanted.items()):raise RuntimeError('独立平面长宽没有同步。')
                        c=sized['config'];clip_ratio=effect['bounds'][0][1]/effect['bounds'][0][2]
                        bounds=sized['bounds'][0]
                        if abs(bounds[2]-c['width']*2)>1e-5 or abs(bounds[1]-c['width']*clip_ratio*.5)>1e-5:raise RuntimeError('独立平面的长宽仍在联动。')
                        report['independent_size']=sized
                    if (Path(smoke)/'deform_check').exists():
                        stages=[]
                        for script,keys in [('window.previewTest.deformDragTest(26,16)',('warp_tr_x','warp_tr_y')),
                                            ("window.previewTest.deformDragTest(0,-20,'corner',1,true)",('warp_tr_z',)),
                                            ("window.previewTest.deformDragTest(23,18,'move',0)",('x','y','z')),
                                            ("window.previewTest.deformDragTest(0,-20,'move',0,true)",('x',)),
                                            ("window.previewTest.deformDragTest(-15,0,'edge',3)",('warp_tl_x','warp_bl_x'))]:
                            before=window.evaluate_js('window.previewTest.effectState()')
                            action=window.evaluate_js(script)
                            if not action:raise RuntimeError('没有可拖动的平面控制点。')
                            for _ in range(100):
                                time.sleep(.15);after=window.evaluate_js('window.previewTest.effectState()')
                                if any(abs(after['config'][key]-before['config'][key])>1e-5 for key in keys):break
                            if not any(abs(after['config'][key]-before['config'][key])>1e-5 for key in keys):raise RuntimeError('拖动未同步：'+script)
                            stages.append(dict(action=script,before=before,after=after))
                        window.evaluate_js('window.previewTest.newPlaneTest()')
                        for _ in range(100):
                            time.sleep(.15);fresh=window.evaluate_js('window.previewTest.effectState()')
                            if all(value==0 for key,value in fresh['config'].items() if key.startswith('warp_')):break
                        if any(value!=0 for key,value in fresh['config'].items() if key.startswith('warp_')):raise RuntimeError('新建流动平面未重置变形。')
                        report['deform']=dict(stages=stages,fresh=fresh)
                    if (Path(smoke)/'armor_check').exists():
                        target=window.evaluate_js('window.previewTest.armorSnapTest()')
                        if not target:raise RuntimeError('未找到可吸附的可见装甲面。')
                        for _ in range(100):
                            time.sleep(.15);snapped=window.evaluate_js('window.previewTest.effectState()')
                            if snapped['config']['placement']!='plane':break
                        if snapped['config']['placement']=='plane':raise RuntimeError('装甲吸附事件未更新到预览。')
                        wanted=window.evaluate_js('window.previewTest.armorAdjustTest()')
                        for _ in range(100):
                            time.sleep(.15);adjusted=window.evaluate_js('window.previewTest.effectState()')
                            if all(adjusted['config'].get(k)==v for k,v in wanted.items()):break
                        if not all(adjusted['config'].get(k)==v for k,v in wanted.items()):raise RuntimeError('装甲缩放与裁剪未同步。')
                        report['armor']=dict(target=target,snapped=snapped,adjusted=adjusted)
                time.sleep(5)
                report.update(window.evaluate_js('window.previewTest.report()'))
                # WebView screenshot through the WebView2 canvas, without capturing other windows.
                png=window.evaluate_js('window.previewTest.capture()')
                if png:
                    import base64
                    (Path(smoke)/'preview.png').write_bytes(base64.b64decode(png.split(',',1)[1]))
                assets.write_json(Path(smoke)/'browser_report.json',report)
            except Exception as error:assets.write_json(Path(smoke)/'browser_report.json',dict(error=str(error),report=report))
            finally:window.destroy()
        webview.start(test,gui='edgechromium',debug=False,private_mode=False,storage_path=str(profile))
    else:webview.start(gui='edgechromium',debug=False,private_mode=False,storage_path=str(profile))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--viewer',required=True);parser.add_argument('--smoke');parser.add_argument('--session')
    args=parser.parse_args()
    try:viewer(args.viewer,args.smoke)
    except Exception as error:
        if not args.smoke:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'三维预览无法启动：\n'+str(error)+'\n\n请确认已安装 Microsoft Edge WebView2 Runtime。现有二维预览仍可使用。','三维预览',16)
        raise
