"""Local app integration check, with the same viewer used by the workbench."""
import json,subprocess,sys,time
from pathlib import Path
from wotcamo import preview3d
from wotcamo.common import ROOT

surface='--surface' in sys.argv or '--visible' in sys.argv
folder=ROOT/('.cache/surface_visible' if '--visible' in sys.argv else '.cache/final_integration_v2' if surface else '.cache/ae_integration')
data=json.loads((folder/('surface_session.json' if surface else 'session_input.json')).read_text(encoding='utf-8'))
session=preview3d.Session(data['project'],'D:/wot/World_of_Tanks_EU',launch=False,effect=(data['clip'],data['config']))
(folder/'preview_url.txt').write_text(session.url,encoding='utf-8')
log=(folder/'preview_worker.log').open('wb')
worker=subprocess.Popen([sys.executable,'-m','wotcamo.preview3d_assets',str(session.folder)],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
session.worker=worker
try:
    print(session.url,flush=True)
    preview3d.viewer(session.url,smoke=str(folder))
finally:session.close();log.close()
