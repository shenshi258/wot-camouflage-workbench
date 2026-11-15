"""Exercise final .wotmod modules in each client's separate Python 2 helper.

Uses native packages, native cosmetic getter code and UI/engine API doubles.
Writes caches only in the requested workspace evidence directory, never in the
installed game. This is not game rendering, compatibility or anti-cheat approval.
"""
import argparse,hashlib,json,subprocess,sys,zipfile
from pathlib import Path

PROBE=r'''
import sys,marshal
sys.path[:]=[EXTRACT,LIB]
import os,json,types,collections,time,threading,hashlib,urllib2
def mod(name,paths=None):
 m=types.ModuleType(name);m.__path__=paths or[];sys.modules[name]=m;return m
gui=mod('gui',[os.path.join(EXTRACT,'gui')]);mods=mod('gui.mods',[os.path.join(EXTRACT,'gui','mods')]);gui.mods=mods
from gui.mods.local_skin_filter import catalog,runtime
root=CLIENT;out=OUTPUT
c=catalog.Catalog(root).scan()
assert c.realm in('EU','ASIA')and len(c.cars)>1000
c.resmods=os.path.join(out,'cache')
record=c.prepare('german/g197_pz_kpfw_neu')
assert c.load_ready('german/g197_pz_kpfw_neu')['models']==record['models']
with open(os.path.join(out,'native_cache_record.json'),'wb')as f:f.write(json.dumps(record,ensure_ascii=True,sort_keys=True))
class Obj(object):pass
class Event(object):
 def __init__(self):self.items=[]
 def __iadd__(self,fn):self.items.append(fn);return self
 def __isub__(self,fn):self.items.remove(fn);return self
class API(object):
 def __init__(self):self.data={};self.settings={};self.templates={};self.callbacks={};self.onSettingsChanged=Event();self.onWindowOpened=Event()
 def getModData(self,key,version,default):return self.data.get(key,default)
 def saveModData(self,key,version,value):self.data[key]=value
 def getModSettings(self,key,template):return self.settings.get(key)if self.templates.get(key)==template else None
 def registerCallback(self,key,fn):self.callbacks[key]=fn;self.onSettingsChanged+=fn
 def setModTemplate(self,key,template,fn):
  values={'enabled':template['enabled']}if'enabled'in template else{}
  for row in template.get('column1',[])+template.get('column2',[]):
   if'varName'in row:values[row['varName']]=row['value']
  self.templates[key]=template;self.settings[key]=values;self.registerCallback(key,fn);return values
api=API();player=Obj();player.playerVehicleID=1;player.team=1;player.arena=None;player.isObserver=lambda:False
world=Obj();world.player=lambda:player;world.callback=lambda *args:1;world.cancelCallback=lambda *args:None
rm=Obj();rm.isFile=lambda name:os.path.isfile(c.absolute(name));rm.purge=lambda p:None
notices=[];ctl=runtime.Controller(api,world,rm,notify=notices.append,localize=lambda key:u'\u6d4b\u8bd5\u8f66\u578b'.encode('utf-8'));ctl.catalog=c
ctl.refresh_main();ctl.register_cars()
assert len(ctl.ui_rows)==len(c.cars)
assert any(u'\u6d4b\u8bd5\u8f66\u578b'in row['label']for row in ctl.ui_rows)
ctl.on_global(runtime.LINK,{'enabled':False});ctl.refresh_main();ctl.progress='different status';ctl.refresh_main()
assert ctl.enabled is False
ctl.on_global(runtime.LINK,{'enabled':True});ctl.publish(record['vehicle'],record);assert record['vehicle']in ctl.ready
urls=[];ctl.browser=urls.append;ctl.open_selector();assert urls and ctl.panel.server.server_address[0]=='127.0.0.1'
client=urllib2.build_opener(urllib2.ProxyHandler({}))
request=urllib2.Request(ctl.panel.origin+'/api/state',headers={'X-LSF-Key':ctl.panel.token})
snapshot=json.loads(client.open(request,timeout=3).read());assert len(snapshot['cars'])==len(c.cars)
with open(os.path.join(out,'selector_delivered.html'),'wb')as f:f.write(ctl.panel.html)
html_sha256=hashlib.sha256(ctl.panel.html).hexdigest()
request=urllib2.Request(ctl.panel.origin+'/api/command',data=json.dumps({'kind':'all_enemies'}),headers={'X-LSF-Key':ctl.panel.token})
answer=json.loads(client.open(request,timeout=3).read());ctl.busy=True;ctl.poll();assert all(ctl.rules[row['key']]==1 for row in c.cars)
ctl.panel.stop();ctl.panel=None
Parts=collections.namedtuple('Parts','chassis hull turret gun')
class Names(object):ALL=('chassis','hull','turret','gun')
native_root=marshal.loads(open(NATIVE,'rb').read()[8:])
def codes(code):
 yield code
 for value in code.co_consts:
  if isinstance(value,types.CodeType):
   for child in codes(value):yield child
native_code=next(code for code in codes(native_root)if code.co_name=='getPartModelsFromDesc')
native=types.FunctionType(native_code,dict(TankPartNames=Names,VehiclePartsTuple=Parts,__builtins__=__import__('__builtin__').__dict__),'getPartModelsFromDesc')
assembler=Obj();assembler.getPartModelsFromDesc=native;collision=lambda *args:'native collisions';assembler.getCollisionModelsFromDesc=collision
class Common(object):
 def prerequisites(self,vID,vInfo,renderMode):
  self._CommonTankAppearance__vID=vID;self.desc=vInfo;self.params=renderMode
  return assembler.getPartModelsFromDesc(vInfo,renderMode)
class Compound(Common):
 def _CompoundAppearance__requestModelsRefresh(self):return assembler.getPartModelsFromDesc(self.desc,self.params)
original_prereq=Common.__dict__['prerequisites'];original_refresh=Compound.__dict__['_CompoundAppearance__requestModelsRefresh']
runtime.install_hooks(ctl,assembler,Common,Compound)
class States(object):
 def __init__(self,a,b,c):self.paths={'undamaged':a,'destroyed':b,'exploded':c}
 def getPathByStateName(self,state):return self.paths[state]
mapping=record['models'];desc=Obj();desc.type=Obj();desc.type.name='germany:G197_Pz_Kpfw_Neu'
for part in Names.ALL:
 p=next(p for p in mapping if'/normal/lod0/'+part in p and'/_skins/'not in p)
 dead=next((p for p in mapping if'/crash/lod0/'+part in p),p)
 style=p.replace('/lod0/','/lod1/');style=style if style in mapping else p
 component=Obj();component.models=States(p,dead,dead);component.modelsSets={'default':component.models,'style':States(style,dead,dead)}
 setattr(desc,part,component)
params=Obj();params.skin='style';params.state='undamaged';default_params=Obj();default_params.skin='default';default_params.state='undamaged'
assert native(desc,params)!=native(desc,default_params)
player.arena=Obj();player.arena.vehicles={1:{'team':1},2:{'team':2},3:{'team':1}}
player.playerVehicleID=0;assert runtime.team_scope(world,2)==0;player.playerVehicleID=1
car=record['vehicle'];arena=player.arena;ticket=10
for cycle in range(100):
 for state in('undamaged','destroyed','exploded'):
  params.state=state;original=native(desc,params);protected=Parts(*(mapping.get(p,p)for p in original))
  for mode in(0,1,2,3):
   player.arena=None;ticket+=1;ctl.apply_command(ticket,{'kind':'rules','keys':[car],'mode':mode});player.arena=arena;assert ctl.rules[car]==mode
   assert Common().prerequisites(1,desc,params)==original
   enemy=Compound();ally=Compound()
   assert enemy.prerequisites(2,desc,params)==(protected if mode in(1,3)else original)
   assert ally.prerequisites(3,desc,params)==(protected if mode in(2,3)else original)
   assert enemy._CompoundAppearance__requestModelsRefresh()==(protected if mode in(1,3)else original)
   assert type(enemy._CompoundAppearance__requestModelsRefresh())is Parts
   assert native(desc,params)==original and assembler.getCollisionModelsFromDesc is collision
   assert runtime._contexts==[]
ctl.on_global(runtime.LINK,{'enabled':False});assert Common().prerequisites(2,desc,params)==native(desc,params)
again=runtime.Controller(api,world,rm);assert again.enabled is False and again.rules[car]==3
# Exercise the actual entry pyc, idempotent initialization and background catalog
# lifecycle using fresh framework doubles. No callbacks are automatically fired.
assembler.getPartModelsFromDesc=native;Common.prerequisites=original_prereq;setattr(Compound,'_CompoundAppearance__requestModelsRefresh',original_refresh)
vs=mod('vehicle_systems');vs.model_assembler=assembler;sys.modules['vehicle_systems.model_assembler']=assembler
mod('vehicle_systems.CompoundAppearance').CompoundAppearance=Compound
mod('vehicle_appearance');mod('vehicle_appearance.common_tank_appearance').CommonTankAppearance=Common
sys.modules['BigWorld']=world;sys.modules['ResMgr']=rm
fresh_api=API();mod('gui.modsSettingsApi').g_modsSettingsApi=fresh_api
menu=[];menu_api=Obj();menu_api.addModification=lambda **kw:menu.append(kw);mod('gui.modsListApi').g_modsListApi=menu_api
browser_ctrl=Obj();opened=[];browser_ctrl.load=lambda **kw:opened.append(kw)
# Use the real game dispatcher. A plain mock that appends on load() would hide
# the precise 2.1 bug: adisp_async returns a callable without starting it.
adisp_errors=[];debug=mod('debug_utils')
debug.LOG_ERROR=lambda *args:adisp_errors.append('error')
debug.LOG_WRAPPED_CURRENT_EXCEPTION=lambda *args:adisp_errors.append('exception')
class SoftException(Exception):pass
mod('soft_exception').SoftException=SoftException
adisp=mod('adisp');exec marshal.loads(open(ADISP,'rb').read()[8:])in adisp.__dict__
@adisp.adisp_async
def deferred_browser(callback=None,**kwargs):
 opened.append(kwargs);callback('local_skin_filter_selector')
browser_ctrl.load=deferred_browser
unused=browser_ctrl.load(url='http://127.0.0.1/protocol-test')
assert callable(unused)and not opened
mod('skeletons');mod('skeletons.gui');mod('skeletons.gui.game_control').IBrowserController=object()
messages=mod('gui.SystemMessages');messages.pushMessage=lambda *a,**kw:None;messages.SM_TYPE=Obj();messages.SM_TYPE.Information=1;gui.SystemMessages=messages
helpers=mod('helpers');helpers.i18n=Obj();helpers.i18n.makeString=lambda value:value
helpers.dependency=Obj();helpers.dependency.instance=lambda interface:browser_ctrl
player.arena=None;original_getcwd=os.getcwd;os.getcwd=lambda:root
entry={};exec marshal.loads(open(ENTRY,'rb').read()[8:])in entry
assert runtime._installed and runtime._controller is not None
hook=Common.__dict__['prerequisites'];entry['init']();assert hook is Common.__dict__['prerequisites']
event=runtime._controller.events.get(timeout=30);assert event[0]=='catalog';runtime._controller.events.put(event);runtime._controller.poll()
os.getcwd=original_getcwd
assert runtime._controller.catalog.realm==c.realm and not runtime._controller.ready
assert len(menu)==1 and menu[0]['lobby']is True and menu[0]['login']is False
menu[0]['callback']();assert opened and opened[0]['useBrowserWindow']is True and opened[0]['showActionBtn']is False
assert not adisp_errors,adisp_errors
runtime.fini();assert runtime._controller.stopped
result=dict(status='passed',realm=c.realm,version=c.version,vehicle_count=len(c.cars),cache_resources=len(record['resources']),
 model_paths=len(record['models']),cycles=100,modes=4,states=3,entry_pyc_executed=True,
 default_and_distinct_style_models=True,utf8_localization=True,own_kept=True,collision_getter_unchanged=True,
 selector_loopback_verified=True,selector_html_sha256=html_sha256,game_browser_call_verified=True,
 native_adisp_contract_verified=True,legacy_unawaited_call_reproduced=True,
 preparation_output=out,game_process_started=False,whole_vehicle_loading=dict(status='not_tested'))
with open(os.path.join(out,'native_result.json'),'wb')as f:f.write(json.dumps(result,sort_keys=True))
c.close();runtime._controller.catalog.close()
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    record=json.loads(a.record.read_text('utf-8'));target=Path(record['artifact']['path']);client=Path(record['client']['path']);a.output.mkdir(parents=True,exist_ok=True)
    with target.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record['artifact']['sha256']
    extracted=a.output/'extracted';extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(target)as z:
        for info in z.infolist():
            if not info.filename.endswith('.pyc'):continue
            rel=info.filename.removeprefix('res/scripts/client/');dest=extracted/rel
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(info))
    native=a.output/'native_selector.pyc'
    adisp=a.output/'native_adisp.pyc'
    with zipfile.ZipFile(client/'res/packages/scripts.pkg')as z:
        native.write_bytes(z.read('scripts/client/vehicle_systems/tankStructure.pyc'))
        adisp.write_bytes(z.read('scripts/client_common/adisp.pyc'))
    code=PROBE
    for name,value in [('EXTRACT',extracted),('LIB',str(client/'res/packages/scripts.pkg')+'/scripts/common/Lib'),('CLIENT',client),
       ('OUTPUT',a.output.resolve()),('NATIVE',native.resolve()),('ADISP',adisp.resolve()),('ENTRY',(extracted/'gui/mods/mod_zz_local_skin_filter.pyc').resolve())]:
        code=code.replace(name,'u'+ascii(str(value)))
    source=a.output/'probe_py27.txt';source.write_text(code,encoding='ascii')
    helper="import ctypes,sys;d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1;d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p];sys.exit(bool(d.PyRun_SimpleString(open(sys.argv[2],'rb').read())))"
    run=subprocess.run([sys.executable,'-c',helper,str(client/'win64/python27.dll'),str(source.resolve())],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000)
    (a.output/'native_stdout.txt').write_bytes(run.stdout)
    if run.returncode:raise RuntimeError(run.stdout.decode('utf-8','replace'))
    result=json.loads((a.output/'native_result.json').read_text());result['artifact_sha256']=record['artifact']['sha256']
    (a.output/'native_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
