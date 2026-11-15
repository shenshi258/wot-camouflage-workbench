import collections,types,unittest
from .runtime import Controller,MODES,LINK,variable,team_scope,install_hooks,wrap_context,_contexts


class Event:
    def __init__(self):self.items=[]
    def __iadd__(self,fn):self.items.append(fn);return self
    def __isub__(self,fn):self.items.remove(fn);return self


class API:
    def __init__(self):self.storage={};self.settings={};self.templates={};self.callbacks={};self.onSettingsChanged=Event();self.onWindowOpened=Event()
    def getModData(self,key,version,default):return self.storage.get(key,default)
    def saveModData(self,key,version,value):self.storage[key]=value
    def getModSettings(self,key,template):return self.settings.get(key)if self.templates.get(key)==template else None
    def registerCallback(self,key,callback):self.callbacks[key]=callback;self.onSettingsChanged+=callback
    def setModTemplate(self,key,template,callback):
        self.templates[key]=template;values={'enabled':template['enabled']}if'enabled'in template else{}
        for row in template.get('column1',[])+template.get('column2',[]):
            if 'varName'in row:values[row['varName']]=row['value']
        self.settings[key]=values;self.registerCallback(key,callback);return values


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.api=API();self.player=types.SimpleNamespace(playerVehicleID=1,team=1,isObserver=lambda:False,
             arena=types.SimpleNamespace(vehicles={1:{'team':1},2:{'team':2},3:{'team':1}}))
        self.world=types.SimpleNamespace(player=lambda:self.player,callback=lambda *args:1,cancelCallback=lambda *a:None)
        self.notices=[];self.rm=types.SimpleNamespace(isFile=lambda path:True,purge=lambda p:None)
        self.c=Controller(self.api,self.world,self.rm,notify=self.notices.append)
        self.car='german/g197_test';self.other='french/f10_test'
        self.source='vehicles/german/G197_Test/normal/lod0/Hull.model';self.dest='vehicles/_lsf2/private/Hull.model'
        self.parts=collections.namedtuple('Parts','chassis hull turret gun')(self.source,self.source,self.source,self.source)
        self.desc=types.SimpleNamespace(type=types.SimpleNamespace(name='germany:G197_Test'))
        self.c.ready[self.car]={self.source.lower():self.dest}
    def test_per_vehicle_four_modes_apply_independently_to_both_teams(self):
        for mode in range(4):
            self.c.rules={self.car:mode,self.other:0}
            for scope in(0,1,2):
                result=self.c.select(self.desc,self.parts,scope)
                if scope and mode in(scope,3):self.assertEqual(result.hull,self.dest)
                else:self.assertIs(result,self.parts)
        self.assertEqual(self.parts.hull,self.source)
    def test_another_vehicle_keeps_its_own_independent_rule(self):
        self.c.rules={self.car:1,self.other:2};desc=types.SimpleNamespace(type=types.SimpleNamespace(name='france:F10_Test'))
        self.assertIs(self.c.select(desc,self.parts,1),self.parts)
    def test_master_disabled_uncached_car_and_unknown_model_keep_identity(self):
        self.c.rules[self.car]=3;self.c.enabled=False;self.assertIs(self.c.select(self.desc,self.parts,1),self.parts)
        self.c.enabled=True;self.c.ready.clear();self.assertIs(self.c.select(self.desc,self.parts,1),self.parts)
    def test_scope_never_selects_own_vehicle_observer_unknown_or_special_modes(self):
        for ident,expected in((1,0),(2,1),(3,2),(999,0)):self.assertEqual(team_scope(self.world,ident),expected)
        self.player.playerVehicleID=0;self.assertEqual(team_scope(self.world,2),0);self.player.playerVehicleID=1
        self.player.isObserver=lambda:True;self.assertEqual(team_scope(self.world,2),0)
        self.player.isObserver=lambda:False;self.player.team=0;self.assertEqual(team_scope(self.world,2),0)
    def test_rules_and_disabled_master_persist_across_restart_and_label_change(self):
        self.c.on_global(LINK,{'enabled':False});self.c.rules[self.car]=2;self.c.persist()
        again=Controller(self.api,self.world,self.rm);self.assertFalse(again.enabled);self.assertEqual(again.rules[self.car],2)
        again.refresh_main();again.progress='new status';again.refresh_main();self.assertFalse(again.enabled)
        self.assertEqual(len(self.api.onSettingsChanged.items),1)
    def test_vehicle_controls_use_saved_rules_and_reject_invalid_modes(self):
        cars=[dict(key=self.car,nation='german',code='G197_Test',label='Test',localization=None)]
        self.c.rules[self.car]=2;self.c.catalog=types.SimpleNamespace(cars=cars);self.c.register_cars()
        row=self.api.templates[LINK+'_german']['column1'][0]
        self.assertEqual(row['value'],2);self.assertEqual(len(row['options']),4)
        callback=self.api.callbacks[LINK+'_german'];callback(LINK+'_german',{variable(self.car):True})
        self.assertEqual(self.c.rules[self.car],0)
    def test_worker_results_are_deferred_during_battle_and_missing_live_mount_bypasses(self):
        self.c.events.put(('ready',self.car,dict(models={self.source.lower():self.dest},resources=[dict(destination=self.dest)])))
        self.c.ready.clear();self.c.busy=True;self.c.poll();self.assertFalse(self.c.ready)
        self.player.arena=None;self.rm.isFile=lambda p:False;self.c.poll();self.assertFalse(self.c.ready)
        self.assertIn('重启',self.notices[-1])
    def test_preparation_does_not_start_in_battle(self):
        self.c.catalog=object();self.c.rules={self.car:1};self.c.ready.clear();calls=[];self.c.prepare=calls.append
        self.c.poll();self.assertEqual(calls,[])
        self.player.arena=None;self.c.poll();self.assertEqual(calls,[self.car])
    def test_native_getter_type_descriptor_and_collision_getter_are_preserved(self):
        c=self.c;c.rules[self.car]=1;parts=self.parts;desc=self.desc
        assembler=types.SimpleNamespace(getPartModelsFromDesc=lambda *a:parts,getCollisionModelsFromDesc=lambda *a:'native')
        collision=assembler.getCollisionModelsFromDesc
        class Common:
            def prerequisites(a,vID,vInfo,renderMode):a._CommonTankAppearance__vID=vID;return assembler.getPartModelsFromDesc(vInfo,renderMode)
        class Compound(Common):
            def _CompoundAppearance__requestModelsRefresh(a):return assembler.getPartModelsFromDesc(desc,None)
        install_hooks(c,assembler,Common,Compound)
        self.assertIs(Common().prerequisites(1,desc,None),parts)
        enemy=Compound();self.assertEqual(enemy.prerequisites(2,desc,None).hull,self.dest)
        self.assertEqual(enemy._CompoundAppearance__requestModelsRefresh().hull,self.dest)
        self.assertIs(type(enemy._CompoundAppearance__requestModelsRefresh()),type(parts))
        self.assertIs(assembler.getCollisionModelsFromDesc,collision);self.assertEqual(parts.hull,self.source)
        self.assertEqual(_contexts,[])
    def test_nested_context_and_native_exception_unwind(self):
        seen=[];inner=wrap_context(lambda a:seen.append(_contexts[-1]),lambda *a:0)
        def outer(a):seen.append(_contexts[-1]);inner(a);seen.append(_contexts[-1]);raise ValueError('native failure')
        with self.assertRaisesRegex(ValueError,'native failure'):wrap_context(outer,lambda *a:1)(None)
        self.assertEqual(seen,[1,0,1]);self.assertEqual(_contexts,[])


if __name__=='__main__':unittest.main()
