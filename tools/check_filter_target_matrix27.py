"""Final-bytecode cosmetic matrix and native SD/HD resource readback.

Runs in an isolated client Python helper. Engine/appearance objects are doubles;
this does not start the game or prove native rendering or Compound acceptance.
"""
import argparse,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def audit_resources(record,output):
    """Reverse relocation and compare full target resources, including all LODs."""
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'standalone/local_skin_filter'))
    from client_catalog import ClientCatalog
    from resource_graph import parse
    from relocation import rewrite_xml
    from package_audit import visual_groups
    from tools.package_in_game_skin_filter import same_tree
    result=json.loads((output/'target_matrix.json').read_text('utf8'))
    assert result['artifact_sha256']==record['artifact']['sha256']
    cache_root=(output/'cache').resolve()
    def read(name):
        target=(cache_root/name).resolve()
        if not target.is_relative_to(cache_root):raise ValueError('Cache escaped the evidence directory')
        return target.read_bytes()
    with ClientCatalog(record['client']['path']).scan()as native:
        for target in result['targets']:
            data=json.loads((output/target['cache_record']).read_text('utf8'))
            reverse={r['destination'].lower():r['source']for r in data['resources']}
            groups=0;prior=[];xml=0;binary=0
            for row in data['resources']:
                before=native.read(row['source']);after=read(row['destination'])
                assert hashlib.sha256(before).hexdigest()==row['source_sha256']
                assert hashlib.sha256(after).hexdigest()==row['sha256']
                if row['source'].lower().endswith(('.model','.visual','.visual_processed','.mfm')):
                    restored,unused=rewrite_xml(parse(after),reverse)
                    original=parse(before)
                    # Native packages themselves mix 3dst/3Dst spellings.
                    # Compare references through the client's case-folded index;
                    # all other strings, material fields and numbers stay strict.
                    for tree in(original,restored):
                        for node in tree.iter():
                            if not len(node)and node.text and node.tag in('Texture','texture','fx','parent','nodefullVisual','nodelessVisual'):
                                node.text=node.text.lower()
                    assert same_tree(original,restored),row['source'];xml+=1
                else:assert before==after;binary+=1
                if row['source'].lower().endswith(('.visual','.visual_processed')):
                    count,errors=visual_groups(read,row['destination']);groups+=count
                    unused,baseline=visual_groups(native.read,row['source'])
                    for error in errors:
                        if error not in baseline:raise ValueError('New native mesh issue: '+str(error))
                        prior.append(dict(source=row['source'],location=error[0],issue=error[1]))
            target.update(xml_semantic_readback=xml,binary_byte_identical=binary,mesh_groups=groups,
              preexisting_mesh_issues=prior,new_mesh_issues=[],all_lod_descriptors_preserved=True)
    result['resource_readback']='passed'
    (output/'target_matrix.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result

PROBE=r'''
import sys
sys.path[:]=[EXTRACT,LIB]
import os,json,types,collections,marshal
def module(name,paths=None):
 m=types.ModuleType(name);m.__path__=paths or[];sys.modules[name]=m;return m
module('gui',[os.path.join(EXTRACT,'gui')]);module('gui.mods',[os.path.join(EXTRACT,'gui','mods')])
from gui.mods.local_skin_filter import catalog,runtime
class Obj(object):pass
class API(object):
 def getModData(self,key,version,default):return default
api=API();player=Obj();player.playerVehicleID=1;player.team=1;player.isObserver=lambda:False
player.arena=Obj();player.arena.vehicles={1:{'team':1},2:{'team':2},3:{'team':1}}
world=Obj();world.player=lambda:player
ctl=runtime.Controller(api,world,Obj())
c=catalog.Catalog(CLIENT).scan();c.resmods=os.path.join(OUTPUT,'cache');ctl.catalog=c
Parts=collections.namedtuple('Parts','chassis hull turret gun')
class Names(object):ALL=('chassis','hull','turret','gun')
def codes(code):
 yield code
 for v in code.co_consts:
  if isinstance(v,types.CodeType):
   for child in codes(v):yield child
code=next(v for v in codes(marshal.loads(open(NATIVE,'rb').read()[8:]))if v.co_name=='getPartModelsFromDesc')
native=types.FunctionType(code,dict(TankPartNames=Names,VehiclePartsTuple=Parts,__builtins__=__import__('__builtin__').__dict__))
assembler=Obj();assembler.getPartModelsFromDesc=native
collision=lambda *args:'unchanged collision';assembler.getCollisionModelsFromDesc=collision
class Common(object):
 def prerequisites(self,vID,desc,params):
  self._CommonTankAppearance__vID=vID;self.desc=desc;self.params=params
  return assembler.getPartModelsFromDesc(desc,params)
class Compound(Common):
 def _CompoundAppearance__requestModelsRefresh(self):return assembler.getPartModelsFromDesc(self.desc,self.params)
runtime.install_hooks(ctl,assembler,Common,Compound)
class States(object):
 def __init__(self,normal,dead):self.normal=normal;self.dead=dead
 def getPathByStateName(self,state):return self.normal if state=='undamaged'else self.dead
results=[]
for key in('german/g72_jagdpz_e100','czech/cz40_dbv_152'):
 record=c.prepare(key);mapping=record['models'];ctl.ready[key]=mapping
 name=key.split('/')[-1];filename='cache_'+name+'.json'
 with open(os.path.join(OUTPUT,filename),'wb')as f:f.write(json.dumps(record,sort_keys=True))
 rows={v['source'].lower():v for v in record['resources']};pairs=0
 for source,row in rows.items():
  companion=source[:-4]+'_hd.dds'
  if source.endswith('.dds')and not source.endswith('_hd.dds')and companion in c.index:
   assert companion in rows and rows[companion]['destination'].lower()==row['destination'].lower()[:-4]+'_hd.dds';pairs+=1
 styles=sorted(set(p.split('/_skins/',1)[1].split('/',1)[0]for p in mapping if '/_skins/'in p))
 native_car=next(v for v in c.cars if v['key']==key)
 desc=Obj();desc.type=Obj();desc.type.name=catalog.NATIONS[native_car['nation']]+':'+native_car['code']
 combinations=0
 for lod in range(5):
  def pick(part,state,skin='default'):
   prefix='vehicles/'+key+'/'
   if skin!='default':prefix+='_skins/'+skin+'/'
   prefix+=state+'/lod'+str(lod)+'/'
   found=sorted(p for p in mapping if p.startswith(prefix)and os.path.basename(p).split('_')[0].split('.')[0]==part)
   if found:return found[0]
   if skin!='default':return pick(part,state)
   if state!='normal':return pick(part,'normal')
   # Fixed casemates can have only a LOD0 dummy turret. Exercise the native
   # source that exists for that part, without inventing additional mesh LODs.
   for detail in range(lod-1,-1,-1):
    candidate=prefix.replace('/lod'+str(lod)+'/','/lod'+str(detail)+'/')
    found=sorted(p for p in mapping if p.startswith(candidate)and os.path.basename(p).split('_')[0].split('.')[0]==part)
    if found:return found[0]
   raise ValueError('Native part absent: '+prefix+part)
  for part in Names.ALL:
   component=Obj();component.models=States(pick(part,'normal'),pick(part,'crash'))
   component.modelsSets={s:States(pick(part,'normal',s),pick(part,'crash',s))for s in styles}
   setattr(desc,part,component)
  for skin in ['default']+styles:
   params=Obj();params.skin=skin
   for state in('undamaged','destroyed','exploded'):
    params.state=state;original=native(desc,params);protected=Parts(*(mapping[p]for p in original))
    assert runtime.car_key(desc,original)==key
    for mode in range(4):
     ctl.rules[key]=mode
     for ident,scope in((1,0),(2,1),(3,2)):
      expected=protected if scope and mode in(scope,3)else original
      appearance=Compound();assert appearance.prerequisites(ident,desc,params)==expected
      assert appearance._CompoundAppearance__requestModelsRefresh()==expected
      assert native(desc,params)==original;combinations+=1
 assert assembler.getCollisionModelsFromDesc is collision
 results.append(dict(vehicle=key,cache_record=filename,resources=len(rows),models=len(mapping),hd_pairs=pairs,
  lods=5,styles=['default']+styles,states=3,modes=4,scopes=3,combinations=combinations))
slots={};car_rows={row['key']:row for row in c.cars}
for path in c.index:
 if not path.endswith('.model')or '/normal/lod0/'not in path or '/_skins/'in path:continue
 pieces=path.split('/');key='/'.join(pieces[1:3]);part=os.path.basename(path).split('_')[0].split('.')[0]
 if key in c.overridden and part in Names.ALL:slots.setdefault(key,{})[part]=path
broad_cases=0;broad_cars=[];unsupported=[]
for key in sorted(c.overridden):
 if set(slots.get(key,{}))!=set(Names.ALL):unsupported.append(key);continue
 desc=Obj();desc.type=Obj();row=car_rows[key];desc.type.name=catalog.NATIONS[row['nation']]+':'+row['code']
 paths=[]
 for part in Names.ALL:
  normal=slots[key][part];dead=normal.replace('/normal/','/crash/');dead=dead if dead in c.index else normal
  component=Obj();component.models=States(normal,dead);component.modelsSets={};setattr(desc,part,component);paths.extend((normal,dead))
 ctl.ready[key]={p:c._destination('vehicles/_lsf2/matrix_only/',c.index[p][1])for p in paths}
 params=Obj();params.skin='default'
 for state in('undamaged','destroyed','exploded'):
  params.state=state;original=native(desc,params);protected=Parts(*(ctl.ready[key][p]for p in original))
  for mode in range(4):
   ctl.rules[key]=mode
   for ident,scope in((1,0),(2,1),(3,2)):
    expected=protected if scope and mode in(scope,3)else original
    appearance=Compound();assert appearance.prerequisites(ident,desc,params)==expected
    assert appearance._CompoundAppearance__requestModelsRefresh()==expected
    assert native(desc,params)==original;broad_cases+=1
 broad_cars.append(key)
with open(os.path.join(OUTPUT,'target_matrix.json'),'wb')as f:f.write(json.dumps(dict(status='passed',targets=results,
 installed_override_matrix=dict(vehicles=broad_cars,unsupported=unsupported,combinations=broad_cases,resource_paths='simulation only'),
 native_getter_executed=True,appearance_objects='API doubles',game_started=False,whole_vehicle_loading=dict(status='not_tested')),sort_keys=True))
c.close()
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--record',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--audit-only',action='store_true')
    a=parser.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    record=json.loads(a.record.read_text('utf8'));client=Path(record['client']['path']);artifact=Path(record['artifact']['path'])
    assert hashlib.sha256(artifact.read_bytes()).hexdigest()==record['artifact']['sha256']
    if a.audit_only:
        result=audit_resources(record,a.output)
        print(json.dumps(dict(realm=result['realm'],resource_readback=result['resource_readback'],
          override_vehicles=len(result['installed_override_matrix']['vehicles']),unsupported=result['installed_override_matrix']['unsupported'])))
        return
    extracted=a.output/'extracted';extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(artifact)as z:
        for name in z.namelist():
            if name.startswith('res/scripts/client/')and name.endswith('.pyc'):
                destination=extracted/name.removeprefix('res/scripts/client/');destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(z.read(name))
    native=a.output/'native_getter.pyc'
    with zipfile.ZipFile(client/'res/packages/scripts.pkg')as z:native.write_bytes(z.read('scripts/client/vehicle_systems/tankStructure.pyc'))
    script=PROBE
    for key,value in [('EXTRACT',extracted.resolve()),('LIB',str(client/'res/packages/scripts.pkg')+'/scripts/common/Lib'),('CLIENT',client),('OUTPUT',a.output.resolve()),('NATIVE',native.resolve())]:
        script=script.replace(key,'u'+ascii(str(value)))
    source=a.output/'probe_py27.txt';source.write_text(script,encoding='ascii')
    helper="import ctypes,sys;d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1;d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p];sys.exit(bool(d.PyRun_SimpleString(open(sys.argv[2],'rb').read())))"
    run=subprocess.run([sys.executable,'-c',helper,str(client/'win64/python27.dll'),str(source.resolve())],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,creationflags=0x08004000)
    (a.output/'native_stdout.txt').write_bytes(run.stdout)
    if run.returncode:raise RuntimeError(run.stdout.decode('utf8','replace'))
    result=json.loads((a.output/'target_matrix.json').read_text());result['artifact_sha256']=record['artifact']['sha256'];result['realm']=record['client']['realm']
    (a.output/'target_matrix.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    result=audit_resources(record,a.output)
    print(json.dumps(dict(status=result['status'],realm=result['realm'],resource_readback=result['resource_readback'],
      targets=[dict(vehicle=t['vehicle'],hd_pairs=t['hd_pairs'],combinations=t['combinations'])for t in result['targets']],
      override_vehicles=len(result['installed_override_matrix']['vehicles']),unsupported=result['installed_override_matrix']['unsupported'],
      override_combinations=result['installed_override_matrix']['combinations'],artifact_sha256=result['artifact_sha256']),ensure_ascii=False))


if __name__=='__main__':main()
