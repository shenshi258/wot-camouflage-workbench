"""Read-only native API evidence for the cosmetic filter prototype."""
import sys,zipfile,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone/self_skin_converter'))
from client_catalog import ClientCatalog
from xdis.load import load_module
from xdis.bytecode import Bytecode
from xdis import get_opcode_module
from xdis.version_info import PythonImplementation
OUT=ROOT/'.cache/enemy_filter';OUT.mkdir(exist_ok=True,parents=True)
opc=get_opcode_module((2,7),PythonImplementation.CPython)
def walk(c,p=''):
 name=c.co_name.decode()if isinstance(c.co_name,bytes)else c.co_name
 yield p+'/'+name,c
 for v in c.co_consts:
  if hasattr(v,'co_code'):yield from walk(v,p+'/'+name)
with ClientCatalog('D:/wot/World_of_Tanks_EU').scan()as catalog:
 with zipfile.ZipFile(catalog.root/'res/packages/scripts.pkg')as z:
  names=('scripts/client/Vehicle.pyc','scripts/client/Avatar.pyc',
   'scripts/client/vehicle_systems/model_assembler.pyc',
   'scripts/client/vehicle_systems/tankStructure.pyc',
   'scripts/client/vehicle_systems/CompoundAppearance.pyc',
   'scripts/client_common/vehicle_appearance/common_tank_appearance.pyc')
  for name in names:
   p=OUT/Path(name).name;p.write_bytes(z.read(name));code=load_module(str(p))[3]
   rows=[]
   for qual,c in walk(code):
    if ('team'in c.co_names and 'vehicles'in c.co_names) or qual.rsplit('/',1)[-1] in('getPartModelsFromDesc','prerequisites','__requestModelsRefresh','attachModels','prepareCompoundAssembler'):
     rows.append(qual+'\n'+Bytecode(c,opc).dis())
   p.with_suffix('.native.txt').write_text('\n'.join(rows),encoding='utf-8')
   print(p.name,[(q,len(c.co_code))for q,c in walk(code)if 'team'in c.co_names and 'vehicles'in c.co_names][:20])
 vehicles=collections.Counter()
 for key in catalog.index:
  parts=key.split('/')
  if len(parts)>3 and parts[0]=='vehicles'and '/normal/lod0/'in key and key.endswith('.model'):vehicles['/'.join(parts[1:3])]+=1
 print('Pz70 variants',[(v,n)for v,n in vehicles.items()if 'g197'in v])
 prefix=next(v for v in vehicles if 'g197'in v)
 files=[v for k,(_,v)in catalog.index.items()if k.startswith('vehicles/'+prefix+'/')]
 print('Vehicle',prefix,'entries',len(files),'suffixes',collections.Counter(Path(n).suffix for n in files))
 print('models',sum(n.endswith('.model')for n in files),'shared refs will be resolved during build')
