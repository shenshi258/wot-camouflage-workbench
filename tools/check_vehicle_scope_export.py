"""Final ordinary-skin archives and delivered Py27 selector; no game is started."""
import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wotcamo import vehicle_scope as scope,light_effects as engine


CHECK = r'''
import sys,marshal
class Obj(object):pass
def module(name):
 m=type(sys)(name);sys.modules[name]=m;return m
log=Obj();log.info=log.exception=lambda *args:None
module('logging').getLogger=lambda name:log
bw=module('BigWorld');player=Obj();player.playerVehicleID=1;bw.player=lambda:player
vs=module('vehicle_systems');assembler=Obj();vs.model_assembler=assembler
class Parts(tuple):
 _fields=('chassis','hull','turret','gun')
 def __new__(cls,*values):return tuple.__new__(cls,values)
 @property
 def hull(self):return self[1]
native=Parts('unmodified_chassis','hull_placeholder','unmodified_turret','unmodified_gun')
assembler.getPartModelsFromDesc=lambda *args,**kwargs:native
collision=lambda *args:'native-collision';assembler.getCollisionModelsFromDesc=collision
class Common(object):
 def prerequisites(self,vID,vInfo=None,renderMode=0):
  self._CommonTankAppearance__vID=vID
  if vInfo=='raise':raise ValueError('native failure')
  if vInfo=='nested':
   assert Common().prerequisites(2) is native
  return assembler.getPartModelsFromDesc(None,None)
class Compound(Common):
 def _CompoundAppearance__requestModelsRefresh(self):return assembler.getPartModelsFromDesc(None,None)
class Hangar(object):
 def _HangarVehicleAppearance__startBuild(self):return assembler.getPartModelsFromDesc(None,None)
module('vehicle_appearance');module('vehicle_appearance.common_tank_appearance').CommonTankAppearance=Common
module('vehicle_systems.CompoundAppearance').CompoundAppearance=Compound
module('gui');module('gui.hangar_vehicle_appearance').HangarVehicleAppearance=Hangar
env={};exec marshal.loads(open(INP,'rb').read()[8:])in env
assert env['_installed']
model=next(p for p in env['MODEL_PATHS']if '/normal/lod0/hull' in p)
native=Parts('unmodified_chassis',model,'unmodified_turret','unmodified_gun')
expected=env['MODEL_PATHS'][model]
getter=assembler.getPartModelsFromDesc;env['init']();assert getter is assembler.getPartModelsFromDesc
checks=0
for cycle in range(100):
 own=Compound();enemy=Compound()
 assert own.prerequisites(1).hull==expected
 assert enemy.prerequisites(2) is native
 assert own._CompoundAppearance__requestModelsRefresh().hull==expected
 assert enemy._CompoundAppearance__requestModelsRefresh() is native
 assert type(own.prerequisites(1))is Parts
 assert own.prerequisites(1,'nested').hull==expected
 assert Hangar()._HangarVehicleAppearance__startBuild().hull==expected
 assert getter(None,None)is native
 checks+=8
try:Common().prerequisites(1,'raise')
except ValueError:pass
else:raise AssertionError('native error was swallowed')
assert not env['_contexts'] and getter(None,None)is native
player.playerVehicleID=3
assert Common().prerequisites(1)is native
assert Common().prerequisites(3).hull==expected
del player.playerVehicleID
assert Common().prerequisites(1)is native
assert Hangar()._HangarVehicleAppearance__startBuild().hull==expected
assert assembler.getCollisionModelsFromDesc is collision
open(OUT,'w').write('PASS: delivered Python 2.7 bytecode; '+str(checks)+' own/enemy/hangar/refresh/nested-context checks; named tuple preserved; failed-load context restored; changed/missing player identity; collision getter unchanged; outside-context and enemy model paths remain original. API doubles only, not in-game validation.\n')
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--client',type=Path,required=True)
    p.add_argument('--tank',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    source_hash=engine.digest(args.source)
    target,record=scope.export_existing(args.source,args.output,args.client,args.tank,'self','普通涂装范围核对')
    global_target,global_record=scope.export_existing(args.source,args.output,args.client,args.tank,'all','普通涂装范围核对')
    with zipfile.ZipFile(args.source)as old,zipfile.ZipFile(global_target)as new:
        assert old.namelist()==new.namelist()
        assert all(old.read(n)==new.read(n)for n in old.namelist())
    with zipfile.ZipFile(target)as archive:
        delivered=args.output/'scope_delivered.pyc'
        delivered.write_bytes(archive.read('res/'+record['application_scope']['runtime']))
        assert not any(n.startswith('res/vehicles/'+args.tank+'/')for n in archive.namelist())
    output=args.output/'runtime_checks.txt'
    script=CHECK.replace('INP','u'+ascii(str(delivered))).replace('OUT','u'+ascii(str(output)))
    script_path=args.output/'runtime_checks_py27.txt';script_path.write_text(script,encoding='ascii')
    helper="import ctypes,sys;d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1;d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p];sys.exit(bool(d.PyRun_SimpleString(open(sys.argv[2],'rb').read())))"
    run=subprocess.run([sys.executable,'-c',helper,str(args.client/'win64/python27.dll'),str(script_path)],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,creationflags=0x08000000)
    if run.returncode:raise RuntimeError(run.stdout.decode('utf-8','replace'))
    assert engine.digest(args.source)==source_hash
    record['runtime_api_checks']=dict(status='passed',scope=output.read_text(),native_api_test_doubles=True)
    record['global_control']=dict(artifact=global_record['artifact'],all_source_entries_byte_identical=True)
    record['actual_running_client']='not_confirmed'
    record['shader_execution']='not_tested; material parameters and binary geometry retained; resource references relocated'
    (args.output/'最终范围核对.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(artifact=record['artifact'],global_artifact=global_record['artifact'],
        models=len(record['application_scope']['model_paths']),groups=record['file_validation']['groups_checked'],
        missing_dependencies=record['file_validation']['missing_dependencies'],api_checks=output.read_text().strip(),
        whole_vehicle_loading=record['whole_vehicle_loading']),ensure_ascii=False))


if __name__=='__main__':main()
