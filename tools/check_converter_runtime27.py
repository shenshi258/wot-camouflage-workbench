"""Execute the delivered own-skin selector with API doubles in a separate Py27 helper."""
import argparse,json,subprocess,sys,zipfile
from pathlib import Path

SETUP=r'''
import sys,marshal
sys.path[:]=[LIB]
import types,copy,collections
def mod(name):
 m=types.ModuleType(name);m.__path__=[];sys.modules[name]=m;return m
for name in('vehicle_appearance','vehicle_appearance.common_tank_appearance','vehicle_systems','vehicle_systems.CompoundAppearance','gui','gui.hangar_vehicle_appearance'):mod(name)
class CommonTankAppearance(object):
 def prerequisites(self,vID,vInfo,renderMode):pass
 def _prepareOutfit(self,outfitCD):return outfitCD
class CompoundAppearance(CommonTankAppearance):
 def _prepareOutfit(self,outfitCD):return CommonTankAppearance._prepareOutfit(self,outfitCD)
class HangarVehicleAppearance(object):
 def _HangarVehicleAppearance__startBuild(self):return self._HangarVehicleAppearance__vDesc
sys.modules['vehicle_appearance.common_tank_appearance'].CommonTankAppearance=CommonTankAppearance
sys.modules['vehicle_systems.CompoundAppearance'].CompoundAppearance=CompoundAppearance
sys.modules['gui.hangar_vehicle_appearance'].HangarVehicleAppearance=HangarVehicleAppearance
class Obj(object):pass
player=Obj();player.playerVehicleID=1
mod('BigWorld').player=lambda:player
mod('Math').Vector3=lambda *v:tuple(v)
env={};exec marshal.loads(open(INP,'rb').read()[8:])in env
assert env['_installed']
hook=CommonTankAppearance.__dict__['_prepareOutfit'];env['install']();assert hook is CommonTankAppearance.__dict__['_prepareOutfit']
class States(object):
 def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
class Part(object):
 def copy(self):return copy.copy(self)
Slot=collections.namedtuple('Slot','type slotId rayStart rayEnd rayUp size')
def descriptor():
 d=Obj();d.name='unknown'
 for part in('chassis','hull','turret','gun'):
  path=next(k for k in env['MODEL_MAP']if '/normal/lod0/'+part in k and '/_skins/'not in k)
  p=Part();p.modelsSets={'default':States(path,'dead.model','exploded.model')};p.models=p.modelsSets['default'];p.name='unknown';p.emblemSlots=()
  setattr(d,part,p)
 if env['INSIGNIA']:
  config=env['INSIGNIA'][0];d.name=config['vehicle'];d.turret.name=config['turret'];d.gun.name=config['gun']
  d.gun.emblemSlots=(Slot('insigniaOnGun',config['slotId'],(0,0,0),(0,0,0),(0,0,0),1),)
 return d
stock=descriptor();outfit=Obj();outfit.modelsSet='default';outfit.style=None
for cycle in range(100):
 own=CompoundAppearance();enemy=CompoundAppearance()
 setattr(own,env['TYPE_ATTR'],stock);setattr(enemy,env['TYPE_ATTR'],stock)
 own._CommonTankAppearance__vID=1;enemy._CommonTankAppearance__vID=2
 own._prepareOutfit(outfit);enemy._prepareOutfit(outfit)
 private=getattr(own,env['TYPE_ATTR'])
 assert private is not stock and getattr(enemy,env['TYPE_ATTR'])is stock
 for part in('chassis','hull','turret','gun'):
  old=getattr(stock,part);new=getattr(private,part)
  assert new is not old and new.modelsSets is not old.modelsSets
  assert new.models.undamaged==env['MODEL_MAP'][old.models.undamaged.lower()]
 if env['INSIGNIA']:
  assert private.gun.emblemSlots[0].rayEnd==tuple(env['INSIGNIA'][0]['rayEnd'])
  assert stock.gun.emblemSlots[0].rayEnd==(0,0,0)
 player.playerVehicleID=3;own._prepareOutfit(outfit);assert getattr(own,env['TYPE_ATTR'])is stock
 player.playerVehicleID=1
 hangar=HangarVehicleAppearance();hangar._HangarVehicleAppearance__vDesc=stock;hangar._HangarVehicleAppearance__outfit=outfit
 assert hangar._HangarVehicleAppearance__startBuild()is not stock
 assert hangar._HangarVehicleAppearance__startBuild()is not stock
 assert stock.hull.models.undamaged in env['MODEL_MAP']
open(OUT,'w').write('PASS: delivered Python 2.7 selector; 100 own/enemy, ownership-change, nested prepareOutfit and repeated hangar rebuild cycles; four private part/model-set copies; original descriptor and insignia slots retained; recognized insignia metadata applied to private gun only; install idempotent. API doubles only, not game execution.\n')
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--record',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();record=json.loads(args.record.read_text(encoding='utf-8'));args.output.mkdir(parents=True,exist_ok=True)
    target=Path(record['artifact']['path']);client=Path(record['client']['path'])
    import hashlib
    with target.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record['artifact']['sha256']
    with zipfile.ZipFile(target)as z:
        name=next(n for n in z.namelist()if '/mod_self_skin_'in n and n.endswith('.pyc'))
        delivered=args.output/'delivered.pyc';delivered.write_bytes(z.read(name))
    out=args.output/'结果.txt';src=args.output/'probe_py27.txt'
    code=SETUP.replace('LIB','u'+ascii(str(client/'res/packages/scripts.pkg')+'/scripts/common/Lib'))
    code=code.replace('INP','u'+ascii(str(delivered))).replace('OUT','u'+ascii(str(out)))
    src.write_text(code,encoding='ascii')
    helper="import ctypes,sys;d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1;d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p];sys.exit(bool(d.PyRun_SimpleString(open(sys.argv[2],'rb').read())))"
    run=subprocess.run([sys.executable,'-c',helper,str(client/'win64/python27.dll'),str(src)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,creationflags=0x08000000)
    if run.returncode:raise RuntimeError(run.stdout.decode('utf-8','replace'))
    print(out.read_text(),end='')


if __name__=='__main__':main()
