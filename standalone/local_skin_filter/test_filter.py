"""Behavioral checks; synthetic API doubles do not establish engine compatibility."""
import collections,hashlib,json,sys,tempfile,types,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from client_catalog import ClientCatalog
from filter_builder import build,vanilla_plan,scan_overrides


def runtime():
    modules={name:types.ModuleType(name)for name in('BigWorld','vehicle_systems','vehicle_systems.model_assembler',
      'vehicle_systems.CompoundAppearance','vehicle_appearance','vehicle_appearance.common_tank_appearance',
      'gui','gui.modsSettingsApi')}
    player=types.SimpleNamespace(playerVehicleID=1,team=1,isObserver=lambda:False,
                                arena=types.SimpleNamespace(vehicles={1:{'team':1},2:{'team':2},3:{'team':1}}))
    modules['BigWorld'].player=lambda:player
    parts=collections.namedtuple('Parts','chassis hull turret gun')
    source='vehicles/test/tank/normal/lod0/hull.model';dest='vehicles/_local_skin_filter/private/hull.model'
    original=parts(source,source,source,'unknown.model')
    assembler=modules['vehicle_systems.model_assembler'];assembler.getPartModelsFromDesc=lambda *a,**k:original
    assembler.getCollisionModelsFromDesc=lambda *a:object()
    modules['vehicle_systems'].model_assembler=assembler
    class Common:
        def prerequisites(self,vID,vInfo=None,renderMode=None):
            self._CommonTankAppearance__vID=vID
            return assembler.getPartModelsFromDesc(vInfo,renderMode)
    class Compound(Common):
        def _CompoundAppearance__requestModelsRefresh(self):return assembler.getPartModelsFromDesc(None,None)
    modules['vehicle_appearance.common_tank_appearance'].CommonTankAppearance=Common
    modules['vehicle_systems.CompoundAppearance'].CompoundAppearance=Compound
    class API:
        def __init__(self):self.callbacks={};self.settings={};self.templates={}
        def getModSettings(self,link,template):return self.settings.get(link)
        def registerCallback(self,link,callback):self.callbacks[link]=callback
        def setModTemplate(self,link,template,callback):
            values={'enabled':template['enabled']}if 'enabled'in template else{}
            for row in template.get('column1',[])+template.get('column2',[]):values[row['varName']]=row['value']
            self.settings[link]=values;self.templates[link]=template;self.callbacks[link]=callback;return values
    api=API();modules['gui.modsSettingsApi'].g_modsSettingsApi=api
    code=Path(__file__).with_name('filter_runtime.py.txt').read_text('ascii')
    code=code.replace('__MODEL_PATHS__',repr({source:dest})).replace('__VEHICLES__',repr([{'key':'test/tank','label':'Tank','var':'car_one'}]))
    env={'basestring':str}
    with patch.dict(sys.modules,modules):exec(compile(code,'runtime','exec'),env)
    return types.SimpleNamespace(env=env,api=api,player=player,assembler=assembler,Common=Common,Compound=Compound,
                                 original=original,source=source,dest=dest,modules=modules)


class RuntimeTests(unittest.TestCase):
    def setUp(self):self.r=runtime()
    def test_default_selects_enemy_and_preserves_own_ally_and_unknown(self):
        r=self.r;self.assertTrue(r.env['_installed'])
        for ident in(1,3,999):self.assertIs(r.Common().prerequisites(ident),r.original)
        result=r.Common().prerequisites(2)
        self.assertIs(type(result),type(r.original));self.assertEqual(result.hull,r.dest);self.assertEqual(result.gun,'unknown.model')
        self.assertEqual(r.original.hull,r.source)
    def test_live_settings_callback_changes_next_build_and_saves_via_api(self):
        r=self.r;values=r.api.settings['local_skin_filter'];values.update(enemies=False,allies=True)
        r.api.callbacks['local_skin_filter']('local_skin_filter',values)
        self.assertIs(r.Common().prerequisites(2),r.original);self.assertEqual(r.Common().prerequisites(3).hull,r.dest)
        values['enabled']=False;r.api.callbacks['local_skin_filter']('local_skin_filter',values)
        self.assertIs(r.Common().prerequisites(3),r.original)
    def test_vehicle_deselection_and_missing_or_malformed_values_disable(self):
        r=self.r;apply=r.env['_apply'];apply('unrelated',{'enabled':False})
        self.assertEqual(r.Common().prerequisites(2).hull,r.dest)
        apply('local_skin_filter',{'enabled':True,'enemies':True,'car_one':False})
        self.assertIs(r.Common().prerequisites(2),r.original)
        apply('local_skin_filter',{'enabled':'true','enemies':True,'car_one':True})
        self.assertIs(r.Common().prerequisites(2),r.original)
    def test_observer_and_special_teams_and_missing_player_do_not_redirect(self):
        r=self.r;r.player.isObserver=lambda:True;self.assertIs(r.Common().prerequisites(2),r.original)
        r.player.isObserver=lambda:False;r.player.team=0;self.assertIs(r.Common().prerequisites(2),r.original)
        r.player.team=1;r.player.arena.vehicles[2]['team']=3;self.assertIs(r.Common().prerequisites(2),r.original)
        r.modules['BigWorld'].player=lambda:None;self.assertIs(r.Common().prerequisites(2),r.original)
    def test_refresh_and_ownership_changes_recompute_team(self):
        r=self.r;a=r.Compound();a._CommonTankAppearance__vID=2
        self.assertEqual(a._CompoundAppearance__requestModelsRefresh().hull,r.dest)
        r.player.playerVehicleID=2;self.assertIs(a._CompoundAppearance__requestModelsRefresh(),r.original)
    def test_no_context_is_identity_and_collision_getter_untouched(self):
        r=self.r;collision=r.assembler.getCollisionModelsFromDesc
        self.assertIs(r.assembler.getPartModelsFromDesc(None,None),r.original)
        with patch.dict(sys.modules,r.modules):r.env['init']()
        self.assertIs(r.assembler.getCollisionModelsFromDesc,collision)
    def test_nested_contexts_and_native_exception_restore_stack(self):
        r=self.r;wrap=r.env['_with_context'];seen=[]
        inner=wrap(lambda a:seen.append(r.assembler.getPartModelsFromDesc(None,None)),lambda *a:False)
        def outer(a):
            seen.append(r.assembler.getPartModelsFromDesc(None,None));inner(a)
            seen.append(r.assembler.getPartModelsFromDesc(None,None));raise ValueError('native')
        with self.assertRaisesRegex(ValueError,'native'):wrap(outer,lambda *a:True)(None)
        self.assertEqual(seen[0].hull,r.dest);self.assertIs(seen[1],r.original);self.assertEqual(seen[2].hull,r.dest)
        self.assertEqual(r.env['_contexts'],[])
    def test_missing_settings_api_installs_no_hooks(self):
        r=self.r;code=Path(__file__).with_name('filter_runtime.py.txt').read_text('ascii').replace('__MODEL_PATHS__','{}').replace('__VEHICLES__','[]')
        before=r.assembler.getPartModelsFromDesc
        mods=dict(r.modules);mods['gui.modsSettingsApi']=types.ModuleType('gui.modsSettingsApi')
        with patch.dict(sys.modules,mods):env={};exec(compile(code,'runtime','exec'),env)
        self.assertFalse(env['_installed']);self.assertIs(r.assembler.getPartModelsFromDesc,before)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name);client=self.root/'client';self.client=client
        (client/'res/packages').mkdir(parents=True)
        (client/'version.xml').write_text('<root><version>v.test</version><meta><realm>EU</realm></meta></root>')
        (client/'paths.xml').write_text('<root><Package>./res/packages/base.pkg</Package></root>')
        self.prefix='vehicles/test/Tank/';self.files={}
        for part in('chassis','hull','turret','gun'):
            stem=self.prefix+'normal/lod0/'+part
            self.files[stem+'.model']=('<root><nodefullVisual>'+stem+'</nodefullVisual></root>').encode()
            self.files[stem+'.visual_processed']=b'<root><Texture>vehicles/common/base.dds</Texture><fx>shaders/native.fx</fx></root>'
            self.files[stem+'.primitives_processed']=b'original geometry'
        self.files['vehicles/common/base.dds']=b'original texture';self.files['shaders/native.10.dx11.fxo']=b'compiled'
        self.files['shaders/native.11.dx11.fxo']=b'compiled'
        self.write_pkg();self.catalog=ClientCatalog(client).scan();self.addCleanup(lambda:self.catalog.close())
    def write_pkg(self):
        with zipfile.ZipFile(self.client/'res/packages/base.pkg','w')as z:
            for k,v in self.files.items():z.writestr(k,v)
    @staticmethod
    def compiler(source,target,client):
        compile(Path(source).read_text('ascii'),'runtime','exec');Path(target).write_bytes(b'\x03\xf3\x0d\x0a'+bytes(4)+b'test')
    def test_plan_is_pristine_and_includes_shared_texture_and_lod(self):
        plan=vanilla_plan(self.catalog,['test/tank'])
        self.assertIn('vehicles/common/base.dds',plan['resources']);self.assertEqual(len(plan['roots']),4)
        self.assertEqual(plan['shaders'],['shaders/native.fx']);self.assertNotIn('shaders/native.10.dx11.fxo',plan['resources'])
    def test_missing_dependency_stops_before_output(self):
        self.catalog.index.pop('vehicles/common/base.dds')
        with self.assertRaisesRegex(ValueError,'依赖不完整'):vanilla_plan(self.catalog,['test/tank'])
    def test_unknown_vehicle_and_game_directory_output_refused(self):
        with self.assertRaisesRegex(ValueError,'存在的车型'):vanilla_plan(self.catalog,['test/unknown'])
        with self.assertRaisesRegex(ValueError,'游戏目录以外'):build(self.catalog,['test/tank'],self.client/'mods')
    def test_final_pack_contains_only_private_native_resources_and_auditable_hashes(self):
        with patch('filter_builder.check_api',return_value=[]),patch('filter_builder.audit',return_value={'groups_checked':0}):
            target,result=build(self.catalog,['test/tank'],self.root/'output',compiler=self.compiler)
        self.assertEqual(result['whole_vehicle_loading']['status'],'not_tested');self.assertFalse(result['in_game_tested'])
        rows=json.loads((target.parent/'资源清单.json').read_text('utf-8'))
        with zipfile.ZipFile(target)as z:
            self.assertIsNone(z.testzip());self.assertTrue(all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist()))
            for row in rows:
                data=z.read(row['destination']);self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
                self.assertIn('/_local_skin_filter/',row['destination'])
                if row['source'].endswith('.visual_processed'):
                    self.assertIn(b'/vehicles/common/base.dds',data);self.assertIn(b'<fx>shaders/native.fx</fx>',data)
                if row['source'].endswith('.dds'):self.assertEqual(data,b'original texture')
            self.assertNotIn('res/vehicles/common/base.dds',z.namelist())
        self.assertTrue((target.parent/'运行脚本.py').is_file())
    def test_scan_never_runs_scripts_and_distinguishes_custom_namespace(self):
        path=self.root/'input.wotmod'
        with zipfile.ZipFile(path,'w')as z:
            z.writestr('res/'+self.prefix+'normal/lod0/hull.model',b'custom')
            z.writestr('res/scripts/client/gui/mods/mod_bad.py',b'raise RuntimeError("must not execute")')
            z.writestr('res/vehicles/test/CustomTank/normal/lod0/hull.model',b'custom')
        before=path.read_bytes();result=scan_overrides(self.catalog,[path])
        self.assertEqual(set(result['vehicles']),{'test/tank'});self.assertEqual(path.read_bytes(),before)
        self.assertEqual(result['sources'][0]['script_entries'],1);self.assertTrue(result['warnings'])
    def test_custom_script_only_pack_is_not_claimed_supported(self):
        path=self.root/'uml.wotmod'
        with zipfile.ZipFile(path,'w')as z:z.writestr('res/vehicles/test/Custom/normal/lod0/hull.model',b'custom')
        result=scan_overrides(self.catalog,[path]);self.assertFalse(result['vehicles']);self.assertTrue(result['warnings'])


if __name__=='__main__':unittest.main()
