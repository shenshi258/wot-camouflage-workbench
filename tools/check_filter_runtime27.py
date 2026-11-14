"""Run final delivered pyc with API doubles and the actual native cosmetic getter.

This uses a separate offline Python 2 helper, never a running game process.
It is not evidence of Compound loading, visual output, fair-play approval or
compatibility with arbitrary third-party hooks.
"""
import argparse,hashlib,json,subprocess,sys,zipfile
from pathlib import Path

PROBE=r'''
import sys,marshal
sys.path[:]=[LIB]
import types,collections
def mod(name):
 m=types.ModuleType(name);m.__path__=[];sys.modules[name]=m;return m
for name in('vehicle_systems','vehicle_systems.model_assembler','vehicle_systems.CompoundAppearance','vehicle_appearance','vehicle_appearance.common_tank_appearance','gui','gui.modsSettingsApi'):mod(name)
class Obj(object):pass
player=Obj();player.playerVehicleID=1;player.team=1;player.isObserver=lambda:False
player.arena=Obj();player.arena.vehicles={1:{'team':1},2:{'team':2},3:{'team':1}}
mod('BigWorld').player=lambda:player
Parts=collections.namedtuple('Parts','chassis hull turret gun')
class Names(object):ALL=('chassis','hull','turret','gun')
# Run only this pure native selector function, not the complete game module.
root=marshal.loads(open(NATIVE,'rb').read()[8:])
def codes(c):
 yield c
 for v in c.co_consts:
  if isinstance(v,types.CodeType):
   for child in codes(v):yield child
native_code=next(c for c in codes(root)if c.co_name=='getPartModelsFromDesc')
native=types.FunctionType(native_code,dict(TankPartNames=Names,VehiclePartsTuple=Parts,__builtins__=__import__('__builtin__').__dict__),'getPartModelsFromDesc')
assembler=sys.modules['vehicle_systems.model_assembler'];assembler.getPartModelsFromDesc=native
sys.modules['vehicle_systems'].model_assembler=assembler
collision=lambda *a:'native collisions';assembler.getCollisionModelsFromDesc=collision
class Common(object):
 def prerequisites(self,vID,vInfo,renderMode):
  self._CommonTankAppearance__vID=vID;self.desc=vInfo;self.params=renderMode
  return assembler.getPartModelsFromDesc(vInfo,renderMode)
class Compound(Common):
 def _CompoundAppearance__requestModelsRefresh(self):return assembler.getPartModelsFromDesc(self.desc,self.params)
sys.modules['vehicle_appearance.common_tank_appearance'].CommonTankAppearance=Common
sys.modules['vehicle_systems.CompoundAppearance'].CompoundAppearance=Compound
class API(object):
 def __init__(self):self.settings={};self.callbacks={}
 def getModSettings(self,link,template):return self.settings.get(link)
 def registerCallback(self,link,callback):self.callbacks[link]=callback
 def setModTemplate(self,link,template,callback):
  values={'enabled':template['enabled']}if'enabled'in template else{}
  for row in template.get('column1',[])+template.get('column2',[]):values[row['varName']]=row['value']
  self.settings[link]=values;self.callbacks[link]=callback;return values
api=API();sys.modules['gui.modsSettingsApi'].g_modsSettingsApi=api
env={};exec marshal.loads(open(INP,'rb').read()[8:])in env
assert env['_installed']
hook=Common.__dict__['prerequisites'];env['init']();assert Common.__dict__['prerequisites']is hook
assert assembler.getCollisionModelsFromDesc is collision
class States(object):
 def __init__(self,a,b,c):self.paths={'undamaged':a,'destroyed':b,'exploded':c}
 def getPathByStateName(self,state):return self.paths[state]
paths=env['MODEL_PATHS'];desc=Obj()
for part in Names.ALL:
 matches=[p for p in paths if'/normal/lod0/'+part in p and'/_skins/'not in p]
 assert matches,part
 p=matches[0];crashes=[p for p in paths if'/crash/lod0/'+part in p]
 dead=crashes[0]if crashes else p
 spec=Obj();spec.models=States(p,dead,dead);spec.modelsSets={'default':spec.models,'official_style':spec.models};setattr(desc,part,spec)
params=Obj();params.skin='official_style';params.state='undamaged'
def mapped(result):return Parts(*(paths.get(p,p)for p in result))
for cycle in range(100):
 for state in('undamaged','destroyed','exploded'):
  params.state=state;original=native(desc,params)
  for ident in(1,3,999):assert Common().prerequisites(ident,desc,params)==original
  enemy=Compound();assert enemy.prerequisites(2,desc,params)==mapped(original)
  assert enemy._CompoundAppearance__requestModelsRefresh()==mapped(original)
  assert native(desc,params)==original
  assert type(enemy._CompoundAppearance__requestModelsRefresh())is Parts
  settings=api.settings[env['LINK']]
  settings['enemies']=False;settings['allies']=True;api.callbacks[env['LINK']](env['LINK'],settings)
  assert enemy._CompoundAppearance__requestModelsRefresh()==original
  assert Common().prerequisites(3,desc,params)==mapped(original)
  settings['enabled']=False;api.callbacks[env['LINK']](env['LINK'],settings)
  assert Common().prerequisites(3,desc,params)==original
  settings.update(enabled=True,enemies=True,allies=False);api.callbacks[env['LINK']](env['LINK'],settings)
  player.playerVehicleID=2;assert enemy._CompoundAppearance__requestModelsRefresh()==original;player.playerVehicleID=1
  player.isObserver=lambda:True;assert enemy._CompoundAppearance__requestModelsRefresh()==original;player.isObserver=lambda:False
  assert env['_contexts']==[]
assert assembler.getCollisionModelsFromDesc is collision
open(OUT,'w').write('PASS: final delivered Python 2.7 pyc, actual native cosmetic getter with API doubles; 100 x 3 normal/destroyed/exploded cycles, official-style selection, own/enemy/ally/unknown, switches, refresh, owner change, observers, immutable descriptor and collision getter, idempotent init. No game process or Compound rendering tested.\n')
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();record=json.loads(a.record.read_text('utf-8'));target=Path(record['artifact']['path']);client=Path(record['client']['path'])
    with target.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record['artifact']['sha256']
    a.output.mkdir(parents=True,exist_ok=True);delivered=a.output/'delivered.pyc';native=a.output/'native_selector.pyc'
    with zipfile.ZipFile(target)as z:delivered.write_bytes(z.read('res/scripts/client/gui/mods/mod_zz_local_skin_filter.pyc'))
    with zipfile.ZipFile(client/'res/packages/scripts.pkg')as z:native.write_bytes(z.read('scripts/client/vehicle_systems/tankStructure.pyc'))
    out=a.output/'结果.txt';src=a.output/'probe_py27.txt';code=PROBE
    for key,value in [('LIB',str(client/'res/packages/scripts.pkg')+'/scripts/common/Lib'),('NATIVE',str(native)),('INP',str(delivered)),('OUT',str(out))]:code=code.replace(key,'u'+ascii(value))
    src.write_text(code,encoding='ascii')
    helper="import ctypes,sys;d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1;d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p];sys.exit(bool(d.PyRun_SimpleString(open(sys.argv[2],'rb').read())))"
    run=subprocess.run([sys.executable,'-c',helper,str(client/'win64/python27.dll'),str(src)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45,creationflags=0x08000000)
    if run.returncode:raise RuntimeError(run.stdout.decode('utf-8','replace'))
    print(out.read_text(),end='')


if __name__=='__main__':main()
