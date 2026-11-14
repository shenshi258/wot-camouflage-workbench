"""Synthetic offline tests; do not imply the game can load the result."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace
from collections import namedtuple
import sys
from builder import build
from client_catalog import ClientCatalog


class BuilderTests(unittest.TestCase):
    def setUp(self):
        api=patch('builder.verify_client_api',return_value={'status':'synthetic'})
        api.start();self.addCleanup(api.stop)
        temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temp.cleanup);self.root=Path(temp.name);self.client=self.root/'client'
        (self.client/'res/packages').mkdir(parents=True)
        (self.client/'version.xml').write_text('<root><version>test</version><meta><realm>test</realm></meta></root>')
        (self.client/'paths.xml').write_text('<root><Package>./res/packages/a.pkg</Package></root>')
        self.base='vehicles/test/TestTank/normal/lod0/'
        with zipfile.ZipFile(self.client/'res/packages/a.pkg','w') as z:
            z.writestr('scripts/item_defs/vehicles/test/TestTank.xml','<root><destroyed>vehicles/test/TestTank/crash/lod0/hull.model</destroyed></root>')
            for part in ('chassis','hull','turret_01','gun_01'):
                name=self.base+part
                z.writestr(name+'.model','<root><nodefullVisual>'+name+'</nodefullVisual></root>')
                z.writestr(name+'.visual_processed','<root><property><Texture>vehicles/test/TestTank/hull_AM.dds</Texture></property></root>')
                z.writestr(name+'.primitives_processed',b'synthetic')
        self.skin=self.root/'input.wotmod'
        with zipfile.ZipFile(self.skin,'w') as z:z.writestr('res/vehicles/test/TestTank/hull_AM.dds',b'synthetic DDS')

    @staticmethod
    def fake_compile(source,target,client):
        compile(Path(source).read_text('ascii'),'runtime','exec')
        Path(target).write_bytes(b'\x03\xf3\x0d\x0a\x00\x00\x00\x00synthetic')

    def test_texture_only_candidate_is_isolated_and_marked_unverified(self):
        before=self.skin.read_bytes()
        target,result=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertEqual(self.skin.read_bytes(),before)
        self.assertEqual(result['whole_vehicle_loading']['status'],'not_tested')
        self.assertFalse(result['in_game_tested'])
        with zipfile.ZipFile(target) as z:
            self.assertIsNone(z.testzip());names=z.namelist()
            self.assertNotIn('res/vehicles/test/TestTank/hull_AM.dds',names)
            self.assertTrue(any('_self_' in n and n.endswith('hull_AM.dds') for n in names))
            self.assertTrue(any(n.endswith('.pyc') for n in names))
            visual=next(n for n in names if n.endswith('hull.visual_processed'))
            self.assertIn(b'_self_',z.read(visual))
            self.assertTrue(all(x.compress_type==zipfile.ZIP_STORED for x in z.infolist()))
        self.assertTrue((target.parent/'验证记录.json').is_file())

    def test_existing_scripts_are_not_silently_removed(self):
        with zipfile.ZipFile(self.skin,'a') as z:z.writestr('res/scripts/client/gui/mods/mod_test.pyc',b'data')
        with self.assertRaisesRegex(ValueError,'脚本'):
            build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertFalse((self.root/'output').exists())

    def test_basic_model_override_is_carried_into_private_resources(self):
        path=self.base+'hull'
        with zipfile.ZipFile(self.skin,'a') as z:
            z.writestr('res/'+path+'.model','<root><nodefullVisual>'+path+'</nodefullVisual></root>')
            z.writestr('res/'+path+'.visual_processed','<root><Texture>vehicles/test/TestTank/hull_AM.dds</Texture><flag>custom</flag></root>')
            z.writestr('res/'+path+'.primitives_processed',b'custom primitive')
        target,_=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        with zipfile.ZipFile(target) as z:
            visual=next(n for n in z.namelist() if n.endswith('hull.visual_processed'))
            self.assertIn(b'<flag>custom</flag>',z.read(visual))
            primitive=visual.replace('.visual_processed','.primitives_processed')
            self.assertEqual(z.read(primitive),b'custom primitive')

    def test_recognized_insignia_script_is_adapted_not_copied(self):
        with zipfile.ZipFile(self.skin,'a') as z:
            z.writestr('res/scripts/client/gui/mods/mod_insignia_test.pyc',b'original script')
            z.writestr('res/vehicles/test/TestTank/normal/lod0/hull.vt',bytes.fromhex('0bb00bb002000000')+b'fixture')
        config=dict(vehicle='test:TestTank',turret='Turret_1',gun='Gun_1',slotId=49000,
                    rayStart=(0.,0.,0.),rayEnd=(0.,0.,1.),rayUp=(1.,0.,0.),size=.6)
        with patch('builder.parse_insignia',return_value=[config]):
            target,record=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertEqual(record['offline_validation']['insignia_slots'],1)
        self.assertEqual(record['offline_validation']['adapted_scripts'][0]['adapter'],'insignia_slot')
        with zipfile.ZipFile(target) as z:
            self.assertNotIn('res/scripts/client/gui/mods/mod_insignia_test.pyc',z.namelist())
            self.assertTrue(any(n.endswith('hull.vt') for n in z.namelist()))

    def test_recognized_insignia_without_res_prefix_is_adapted(self):
        with zipfile.ZipFile(self.skin,'a') as z:
            z.writestr('scripts/client/gui/mods/mod_insignia_test.pyc',b'original script')
        config=dict(vehicle='test:TestTank',turret='Turret_1',gun='Gun_1',slotId=49000,
                    rayStart=(0.,0.,0.),rayEnd=(0.,0.,1.),rayUp=(1.,0.,0.),size=.6)
        with patch('builder.parse_insignia',return_value=[config]):
            target,record=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertTrue(target.exists());self.assertEqual(record['offline_validation']['insignia_slots'],1)
        self.assertTrue(record['offline_validation']['adapted_scripts'][0]['path'].startswith('scripts/'))

    def test_design_psd_is_not_silently_included_in_the_game_package(self):
        original='res/vehicles/test/TestTank/source/hull.psd'
        with zipfile.ZipFile(self.skin,'a') as z:z.writestr(original,b'design')
        target,record=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertEqual(record['offline_validation']['ignored_design_files'][0]['path'],original)
        with zipfile.ZipFile(target) as z:self.assertFalse(any(n.endswith('.psd') for n in z.namelist()))

    def test_unknown_vt_format_is_refused(self):
        with zipfile.ZipFile(self.skin,'a') as z:
            z.writestr('res/vehicles/test/TestTank/normal/lod0/hull.vt',b'unknown format')
        with self.assertRaisesRegex(ValueError,'VT'):
            build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertEqual(self.skin.exists(),True)

    def test_unrecognized_insignia_script_is_refused(self):
        with zipfile.ZipFile(self.skin,'a') as z:
            z.writestr('res/scripts/client/gui/mods/mod_insignia_test.pyc',b'unknown script')
        with self.assertRaisesRegex(ValueError,'徽记脚本'):
            build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)

    def test_source_crash_model_is_isolated_and_not_a_global_override(self):
        stem='vehicles/test/TestTank/crash/lod0/hull'
        with zipfile.ZipFile(self.skin,'a') as z:
            z.writestr('res/'+stem+'.model','<root><nodefullVisual>'+stem+'</nodefullVisual></root>')
            z.writestr('res/'+stem+'.visual_processed','<root><Texture>vehicles/test/TestTank/hull_AM.dds</Texture></root>')
            z.writestr('res/'+stem+'.primitives_processed',b'crash geometry')
        target,record=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile)
        self.assertTrue(record['offline_validation']['source_has_crash'])
        self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested')
        with zipfile.ZipFile(target) as z:
            self.assertNotIn('res/'+stem+'.model',z.namelist())
            self.assertTrue(any('_self_' in n and n.endswith('crash/lod0/hull.model') for n in z.namelist()))

    def test_siege_vehicle_is_recorded_and_requires_composite_probe(self):
        with ClientCatalog(self.client).scan() as catalog:
            real_read=catalog.read
            def read(name):
                if name.endswith('/TestTank.xml'):return b'<root><siege_mode/></root>'
                return real_read(name)
            with patch.object(catalog,'read',side_effect=read):
                target,record=build(self.skin,self.client,self.root/'output',compiler=self.fake_compile,catalog=catalog)
        self.assertTrue(target.exists())
        self.assertTrue(record['offline_validation']['dual_mode'])
        self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested')


class RuntimeTests(unittest.TestCase):
    def test_wrapper_keeps_enemy_stock_and_applies_separate_model_to_own_vehicle(self):
        code=Path(__file__).with_name('game_runtime_template.py.txt').read_text('ascii')
        code=code.replace('__MODEL_MAP__',repr({'stock.model':'isolated.model'})).replace('__INSIGNIA__','[]').replace('__TOKEN__','abc')
        code=code.rsplit('\ninstall()',1)[0]
        namespace={};exec(compile(code,'runtime','exec'),namespace)
        class States:
            def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
        def part():
            state=States('stock.model','destroyed','exploded')
            return SimpleNamespace(modelsSets={'default':state},models=state)
        stock=SimpleNamespace(**{k:part() for k in ('chassis','hull','turret','gun')})
        appearance=SimpleNamespace(_CommonTankAppearance__typeDesc=stock,_CommonTankAppearance__vID=1)
        slot=SimpleNamespace(getItemCD=lambda:1)
        outfit=SimpleNamespace(style=None,modelsSet='default',getContainer=lambda i:SimpleNamespace(slotFor=lambda kind:slot))
        wrapper=namespace['_make_wrapper'](lambda self,cd:outfit,9,4)
        player=SimpleNamespace(playerVehicleID=1)
        game=SimpleNamespace(player=lambda:player)
        with patch.dict(sys.modules,{'BigWorld':game}):wrapper(appearance,None)
        changed=appearance._CommonTankAppearance__typeDesc
        self.assertEqual(changed.hull.models.undamaged,'isolated.model')
        self.assertEqual(stock.hull.models.undamaged,'stock.model')
        player.playerVehicleID=2
        with patch.dict(sys.modules,{'BigWorld':game}):wrapper(appearance,None)
        self.assertIs(appearance._CommonTankAppearance__typeDesc,stock)

    def test_both_composite_modes_are_independent_and_keep_vehicle_mode(self):
        code=Path(__file__).with_name('game_runtime_template.py.txt').read_text('ascii')
        code=code.replace('__MODEL_MAP__',repr({'ordinary.model':'private_ordinary.model','siege.model':'private_siege.model'})).replace('__INSIGNIA__','[]').replace('__TOKEN__','abc')
        namespace={};exec(compile(code.rsplit('\ninstall()',1)[0],'runtime','exec'),namespace)
        class States:
            def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
        def part(path):
            state=States(path,'destroyed','exploded');return SimpleNamespace(modelsSets={'default':state},models=state)
        def descriptor(path):return SimpleNamespace(**{name:part(path) for name in ('chassis','hull','turret','gun')})
        class CompositeVehicleDescriptor:
            def __init__(self,normal,siege):
                self.__dict__['_CompositeVehicleDescriptor__vehicleDescr']=normal
                self.__dict__['_CompositeVehicleDescriptor__siegeDescr']=siege
                self.__dict__['_CompositeVehicleDescriptor__vehicleMode']=1
            @property
            def defaultVehicleDescr(self):return self.__dict__['_CompositeVehicleDescriptor__vehicleDescr']
            @property
            def siegeVehicleDescr(self):return self.__dict__['_CompositeVehicleDescriptor__siegeDescr']
            def __setattr__(self,name,value):
                setattr(self.defaultVehicleDescr,name,value);setattr(self.siegeVehicleDescr,name,value)
        normal=descriptor('ordinary.model');siege=descriptor('siege.model')
        original=CompositeVehicleDescriptor(normal,siege)
        clone=namespace['_clone'](original,SimpleNamespace(modelsSet='default'))
        self.assertIsNot(clone,original)
        self.assertEqual(clone.defaultVehicleDescr.hull.models.undamaged,'private_ordinary.model')
        self.assertEqual(clone.siegeVehicleDescr.hull.models.undamaged,'private_siege.model')
        self.assertEqual(normal.hull.models.undamaged,'ordinary.model')
        self.assertEqual(siege.hull.models.undamaged,'siege.model')
        self.assertEqual(clone.__dict__['_CompositeVehicleDescriptor__vehicleMode'],1)

    def test_insignia_changes_only_cloned_gun_slot(self):
        config=dict(vehicle='usa:Tank',turret='Turret_1',gun='Gun_1',slotId=49000,
                    rayStart=(0.,0.,3.),rayEnd=(0.,0.,4.),rayUp=(1.,0.,0.),size=.6)
        code=Path(__file__).with_name('game_runtime_template.py.txt').read_text('ascii')
        code=code.replace('__MODEL_MAP__',repr({'stock.model':'private.model'})).replace('__INSIGNIA__',repr([config])).replace('__TOKEN__','abc')
        namespace={};exec(compile(code.rsplit('\ninstall()',1)[0],'runtime','exec'),namespace)
        class States:
            def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
        Slot=namedtuple('Slot','type slotId rayStart rayEnd rayUp size')
        old=Slot('insigniaOnGun',49000,(0,0,0),(0,0,0),(0,0,0),1.)
        def part(name=''):
            state=States('stock.model','dead','exploded')
            return SimpleNamespace(name=name,modelsSets={'default':state},models=state,emblemSlots=(old,))
        desc=SimpleNamespace(name='usa:Tank',chassis=part(),hull=part(),turret=part('Turret_1'),gun=part('Gun_1'))
        fake_math=SimpleNamespace(Vector3=lambda *args:tuple(args))
        with patch.dict(sys.modules,{'Math':fake_math}):
            result=namespace['_clone'](desc,SimpleNamespace(modelsSet='default'))
        self.assertEqual(result.gun.emblemSlots[0].rayEnd,(0.,0.,4.))
        self.assertEqual(desc.gun.emblemSlots[0],old)

    def test_crash_and_exploded_variants_are_conditional_too(self):
        code=Path(__file__).with_name('game_runtime_template.py.txt').read_text('ascii')
        mapping={'stock.model':'private.model','dead.model':'private_dead.model','exploded.model':'private_exploded.model'}
        code=code.replace('__MODEL_MAP__',repr(mapping)).replace('__INSIGNIA__','[]').replace('__TOKEN__','abc')
        namespace={};exec(compile(code.rsplit('\ninstall()',1)[0],'runtime','exec'),namespace)
        class States:
            def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
        def part():
            state=States('stock.model','dead.model','exploded.model')
            return SimpleNamespace(modelsSets={'default':state},models=state)
        descriptor=SimpleNamespace(**{name:part() for name in ('chassis','hull','turret','gun')})
        result=namespace['_clone'](descriptor,SimpleNamespace(modelsSet='default'))
        self.assertEqual(result.hull.models.destroyed,'private_dead.model')
        self.assertEqual(result.hull.models.exploded,'private_exploded.model')
        self.assertEqual(descriptor.hull.models.destroyed,'dead.model')

    def test_missing_expected_insignia_slot_fails_closed(self):
        config=dict(vehicle='usa:Tank',turret='Turret_1',gun='Gun_1',slotId=49000,
                    rayStart=(0.,0.,3.),rayEnd=(0.,0.,4.),rayUp=(1.,0.,0.),size=.6)
        code=Path(__file__).with_name('game_runtime_template.py.txt').read_text('ascii')
        code=code.replace('__MODEL_MAP__',repr({'stock.model':'private.model'})).replace('__INSIGNIA__',repr([config])).replace('__TOKEN__','abc')
        namespace={};exec(compile(code.rsplit('\ninstall()',1)[0],'runtime','exec'),namespace)
        class States:
            def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
        def part(name=''):
            state=States('stock.model','dead','exploded')
            return SimpleNamespace(name=name,modelsSets={'default':state},models=state,emblemSlots=())
        desc=SimpleNamespace(name='usa:Tank',chassis=part(),hull=part(),turret=part('Turret_1'),gun=part('Gun_1'))
        with patch.dict(sys.modules,{'Math':SimpleNamespace(Vector3=lambda *a:a)}):
            self.assertIsNone(namespace['_clone'](desc,SimpleNamespace(modelsSet='default')))
