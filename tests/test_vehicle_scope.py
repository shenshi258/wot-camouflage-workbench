import io
import sys
import tempfile
import types
import unittest
import zipfile
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from wotcamo import vehicle_scope as scope, light_effects as engine, light_assets as mesh
from test_light_wheels import ring, fixture_visual


class ScopePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.client=self.root/'client';self.client.mkdir()
        (self.client/'res/packages').mkdir(parents=True)
        with zipfile.ZipFile(self.client/'res/packages/shaders.pkg','w') as z:z.writestr('fixture',b'')
        (self.client/'version.xml').write_text('<root><version>2.4.1.1</version><meta><realm>CN</realm></meta></root>')
        (self.client/'paths.xml').write_text('<root><Path>res_mods/2.4.1.1</Path></root>')
        self.prefix='vehicles/test/TestTank/';self.base=self.prefix+'normal/lod0/hull'
        vertices,indices=ring();visual=fixture_visual(vertices,indices)
        visual.find('.//fx').text='shaders/std_effects/PBS_tank.fx'
        for prop in visual.findall('.//property'):
            if (prop.text or '').strip()=='diffuseMap':prop.find('Texture').text=self.prefix+'skin_AM.dds'
        model=ET.Element('root');ET.SubElement(model,'nodefullVisual').text=self.base
        self.source=self.root/'source.wotmod'
        self.entries={'res/'+self.base+'.model':mesh.xml(model),
            'res/'+self.base+'.visual_processed':mesh.xml(visual),
            'res/'+self.base+'.primitives_processed':mesh.primitives(vertices,indices.ravel()),
            'res/'+self.prefix+'skin_AM.dds':b'original-texture'}
        with zipfile.ZipFile(self.source,'w',zipfile.ZIP_STORED) as z:
            for name,raw in self.entries.items():z.writestr(name,raw)
        self.compiler=patch.object(engine,'compile27',side_effect=lambda source,target,client:Path(target).write_bytes(b'\x03\xf3\r\n'+b'compiled fixture'))
        self.compiler.start();self.addCleanup(self.compiler.stop)

    def test_private_archive_keeps_original_and_all_model_dependencies(self):
        original=engine.digest(self.source);target=self.root/'private.wotmod'
        report=scope.archive(self.source,target,self.client,'test/TestTank','self',
            {self.prefix+'skin_AM.dds':b'edited-texture'})
        self.assertEqual(engine.digest(self.source),original)
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        self.assertGreater(report['groups_checked'],0)
        with zipfile.ZipFile(target) as z:
            self.assertFalse(any(n.startswith('res/'+self.prefix) for n in z.namelist()))
            private=report['model_paths'][(self.base+'.model').lower()]
            model=engine.xml(z.read('res/'+private));visual=model.findtext('nodefullVisual')
            self.assertTrue(visual.startswith(report['namespace']))
            self.assertEqual(z.read('res/'+visual+'.primitives_processed'),self.entries['res/'+self.base+'.primitives_processed'])
            tree=engine.xml(z.read('res/'+visual+'.visual_processed'))
            texture=tree.find('.//Texture').text
            self.assertTrue(texture.startswith(report['namespace']))
            self.assertEqual(z.read('res/'+texture),b'edited-texture')
            self.assertIn('res/'+report['runtime'],z.namelist())
            self.assertTrue(all(n.compress_type==zipfile.ZIP_STORED for n in z.infolist()))

    def test_global_archive_keeps_shared_model_paths_and_does_not_add_script(self):
        target=self.root/'global.wotmod'
        report=scope.archive(self.source,target,self.client,'test/TestTank','all',
            {self.prefix+'skin_AM.dds':b'edited-texture'})
        self.assertEqual(report,{'value':'all'})
        with zipfile.ZipFile(target) as z:
            self.assertEqual(z.read('res/'+self.prefix+'skin_AM.dds'),b'edited-texture')
            for name,raw in self.entries.items():
                if name.endswith('.dds'):continue
                self.assertEqual(z.read(name),raw)
            self.assertFalse(any(n.endswith('.pyc') for n in z.namelist()))

    def test_self_rejects_shared_overrides_and_scripts_instead_of_leaking_globally(self):
        for name in ('res/scripts/client/gui/mods/third_party.pyc','res/vehicles/shared/shared.dds'):
            with self.subTest(name=name):
                target=self.root/'unsafe.wotmod'
                with zipfile.ZipFile(self.source,'a') as z:z.writestr(name,b'not-supported')
                with self.assertRaisesRegex(ValueError,'普通涂装'):
                    scope.archive(self.source,target,self.client,'test/TestTank','self')
                self.assertFalse(target.exists())

    def test_folder_keeps_editable_source_outside_installed_resources(self):
        out=self.root/'folder';tree=out/'res'
        for name,raw in self.entries.items():
            dest=tree/name[4:];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        report=scope.folder(out,self.client,'test/TestTank')
        self.assertEqual((out/'source_res'/self.base).with_suffix('.model').read_bytes(),self.entries['res/'+self.base+'.model'])
        self.assertFalse((tree/self.base).with_suffix('.model').exists())
        self.assertTrue((tree/report['runtime']).is_file())

    def test_invalid_scope_is_not_silently_treated_as_global(self):
        for value in ('own','SELF',None,True,[]):
            with self.subTest(value=value),self.assertRaises(ValueError):scope.validate(value)

    def test_full_texture_build_pack_and_verify_use_private_files_and_keep_editable_source(self):
        from wotcamo import pipeline,dds,modpack
        from PIL import Image
        reference=io.BytesIO();Image.new('RGBA',(16,16),(70,90,110,255)).save(reference,format='DDS',pixel_format='DXT1')
        resources=dict(self.entries);texture=self.prefix+'skin_AM.dds';resources['res/'+texture]=reference.getvalue()
        package=self.client/'res/packages/vehicles_fixture.pkg'
        with zipfile.ZipFile(package,'w') as z:
            for name,raw in resources.items():z.writestr(name[4:],raw)
        (self.client/'paths.xml').write_text('<root><Path>res_mods/2.4.1.1</Path><Package>res/packages/vehicles_fixture.pkg</Package></root>')
        index={'version':'2.4.1.1','vehicles':{'test/TestTank':{n[4:]:{'pkg':package.name} for n in resources}}}
        materials=self.root/'materials';materials.mkdir()
        cfg={'wot_root':str(self.client),'index_file':'fixture','result_dir':str(self.root/'result')}
        with patch('wotcamo.pipeline.load_index',return_value=index):
            out=pipeline.build('test/TestTank',materials,'沙漠黄底色 + 白色虎纹','自己',cfg,
                               do_pack=True,scope='self',log=lambda text:None)
            result=pipeline.verify(out,cfg,log=lambda text:None)
        report,values=modpack.checked_files(out)
        self.assertGreater(result['mips_decoded'],0)
        self.assertEqual(report['application_scope']['value'],'self')
        self.assertTrue((out/'source_res'/texture).is_file())
        self.assertTrue(all(n.startswith(report['application_scope']['namespace']) or n==report['application_scope']['runtime'] for n,raw in values))
        self.assertTrue(any(n==report['application_scope']['runtime'] for n,raw in values))
        # An accidentally retained global override must fail the install preflight.
        dest=out/'res'/texture;dest.parent.mkdir(parents=True);dest.write_bytes(reference.getvalue())
        with self.assertRaisesRegex(ValueError,'资源清单'):modpack.checked_files(out)


class ScopeRuntimeTests(unittest.TestCase):
    def runtime(self):
        modules={name:types.ModuleType(name) for name in ('BigWorld','vehicle_systems',
            'vehicle_appearance','vehicle_appearance.common_tank_appearance',
            'vehicle_systems.CompoundAppearance','gui','gui.hangar_vehicle_appearance')}
        player=types.SimpleNamespace(playerVehicleID=1);modules['BigWorld'].player=lambda:player
        native=namedtuple('VehiclePartsTuple','chassis hull turret gun')('stock_chassis','stock_hull','stock_turret','stock_gun')
        assembler=types.SimpleNamespace(getPartModelsFromDesc=lambda *args,**kwargs:native)
        modules['vehicle_systems'].model_assembler=assembler
        class Common:
            def prerequisites(self,vID,vInfo=None,renderMode=0):
                self._CommonTankAppearance__vID=vID
                if vInfo=='raise':raise ValueError('native failure')
                return assembler.getPartModelsFromDesc(None,None)
        class Compound(Common):
            def _CompoundAppearance__requestModelsRefresh(self):return assembler.getPartModelsFromDesc(None,None)
        class Hangar:
            def _HangarVehicleAppearance__startBuild(self):return assembler.getPartModelsFromDesc(None,None)
        modules['vehicle_appearance.common_tank_appearance'].CommonTankAppearance=Common
        modules['vehicle_systems.CompoundAppearance'].CompoundAppearance=Compound
        modules['gui.hangar_vehicle_appearance'].HangarVehicleAppearance=Hangar
        text=(Path(scope.__file__).parent/'vehicle_scope_runtime.py.txt').read_text(encoding='utf-8')
        text=text.replace('MODEL_PATHS = {}',"MODEL_PATHS = {'stock_hull': 'private_hull'}")
        env={'basestring':str}
        with patch.dict(sys.modules,modules):exec(compile(text,'<scope>','exec'),env)
        return env,assembler,native,Common,Compound,Hangar,player

    def test_same_model_self_and_enemy_keep_separate_paths_and_native_tuple_type(self):
        env,assembler,native,Common,Compound,Hangar,player=self.runtime()
        own=Common().prerequisites(1);enemy=Common().prerequisites(2)
        self.assertEqual(own.hull,'private_hull');self.assertIs(type(own),type(native))
        self.assertIs(enemy,native);self.assertEqual(native.hull,'stock_hull')
        self.assertIs(assembler.getPartModelsFromDesc(None,None),native)
        self.assertEqual(env['_contexts'],[])

    def test_hangar_refresh_death_and_respawn_reselect_without_modifying_shared_descriptors(self):
        env,assembler,native,Common,Compound,Hangar,player=self.runtime()
        for vehicle_id in (1,2,1):
            appearance=Compound();appearance.prerequisites(vehicle_id)
            paths=appearance._CompoundAppearance__requestModelsRefresh()
            self.assertEqual(paths.hull,'private_hull' if vehicle_id==1 else 'stock_hull')
        self.assertEqual(Hangar()._HangarVehicleAppearance__startBuild().hull,'private_hull')
        self.assertIs(assembler.getPartModelsFromDesc(None,None),native)
        player.playerVehicleID=3
        self.assertIs(Common().prerequisites(1),native)

    def test_failed_native_build_clears_context_and_preserves_native_error(self):
        env,assembler,native,Common,Compound,Hangar,player=self.runtime()
        with self.assertRaisesRegex(ValueError,'native failure'):Common().prerequisites(1,'raise')
        self.assertEqual(env['_contexts'],[])
        self.assertIs(assembler.getPartModelsFromDesc(None,None),native)

    def test_missing_player_identity_does_not_apply_skin_to_every_vehicle(self):
        env,assembler,native,Common,Compound,Hangar,player=self.runtime()
        del player.playerVehicleID
        self.assertIs(Common().prerequisites(1),native)
        self.assertEqual(Hangar()._HangarVehicleAppearance__startBuild().hull,'private_hull')


if __name__=='__main__':unittest.main()
