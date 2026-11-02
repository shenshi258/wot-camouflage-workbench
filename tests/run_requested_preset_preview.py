"""Exercise a delivered preset through the real local WebView2 preview, without a game launch."""
import json
import subprocess
import sys
import copy,queue,threading
from wotcamo import ae_effects as ae,ae_presets,preview3d
from wotcamo.common import ROOT

if '--hidden' in sys.argv:
    sys.path.insert(0,str(ROOT/'tools/preview_webview_stable'))
    import webview
    original_create=webview.create_window
    def hidden_window(*args,**kwargs):
        kwargs['hidden']=True
        return original_create(*args,**kwargs)
    webview.create_window=hidden_window

index=int(sys.argv[1]);records,issues=ae_presets.scan();assert len(records)==4 and not issues
record=records[index];folder=ROOT/'.cache/preset_browser'/str(index);folder.mkdir(parents=True,exist_ok=True)
metadata,clip=ae_presets.load(record['path'],folder/'assets')
project=ae.source_project(ROOT.parents[1]/'改造区/Pz70_水星野侧面流星_R1/原始涂装.wotmod',folder/'source')
values=ae.config(metadata['config'])
session=preview3d.Session(project,'D:/wot/World_of_Tanks_EU',launch=False,effect=(clip,values))
if '--armor' in sys.argv or '--deform' in sys.argv:
    if '--armor' in sys.argv:(folder/'armor_check').write_text('run click-to-surface and slider roundtrip',encoding='utf-8')
    if '--deform' in sys.argv:(folder/'deform_check').write_text('run drag and fresh plane roundtrip',encoding='utf-8')
    def bridge():
        try:
            while not session.closed:
                try:event=session.events.get(timeout=.1)
                except queue.Empty:continue
                if event['type']=='bodyselect':
                    project['ae_selection']=event['selection'];project['ae_surface_origin']=dict(source_sha256=project['source_sha256'],point=event['point'])
                    values.update(placement='surface_glow',plane='auto',mirror=False)
                elif event['type']=='effectparams':values.update(event['values'])
                elif event['type']=='effectplane':values.update(ae.new_plane_config(clip,values,session.effect))
                else:continue
                session.update_effect(clip,values)
                (folder/'armor_project.json').write_text(json.dumps(dict(project=project,clip=clip,config=values),ensure_ascii=False),encoding='utf-8')
        except Exception as error:(folder/'bridge_error.txt').write_text(repr(error),encoding='utf-8')
    threading.Thread(target=bridge,daemon=True).start()
if '--size' in sys.argv:(folder/'size_check').write_text('independent axes',encoding='utf-8')
log=(folder/'worker.log').open('wb')
session.worker=subprocess.Popen([sys.executable,'-m','wotcamo.preview3d_assets',str(session.folder)],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:
    preview3d.viewer(session.url,smoke=str(folder))
    result=json.loads((folder/'browser_report.json').read_text(encoding='utf-8'))
    assert not result.get('error') and result.get('ready') and not result.get('errors'),result
    effect=result['ae_effect'];assert effect['frames']==clip['frames'] and effect['tested_frames']==[0,1,clip['frames']-1,1]
    print(json.dumps(dict(name=record['name'],frames=effect['frames'],tested_frames=effect['tested_frames'],fps=result['fps'],errors=result['errors']),ensure_ascii=False),flush=True)
finally:session.close();log.close()
