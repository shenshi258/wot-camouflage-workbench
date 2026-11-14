import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def runtime():
    code=Path(__file__).with_name('game_runtime_template.py.txt').read_text('ascii')
    code=code.replace('__MODEL_MAP__',"{'stock.model':'private.model'}").replace('__INSIGNIA__','[]').replace('__TOKEN__','test')
    env={};exec(compile(code.rsplit('\ninstall()',1)[0],'<own runtime>','exec'),env)
    return env


class OwnRuntimeTests(unittest.TestCase):
    def descriptor(self):
        class States:
            def __init__(self,a,b,c):self.undamaged=a;self.destroyed=b;self.exploded=c
        def part():
            states=States('stock.model','dead','exploded')
            return SimpleNamespace(modelsSets={'default':states},models=states,emblemSlots=())
        return SimpleNamespace(**{name:part()for name in('chassis','hull','turret','gun')})

    def test_only_identity_matters_with_no_camouflage_or_style_equipped(self):
        env=runtime();stock=self.descriptor();outfit=SimpleNamespace(modelsSet='default',style=None)
        own=SimpleNamespace(_CommonTankAppearance__typeDesc=stock,_CommonTankAppearance__vID=10)
        enemy=SimpleNamespace(_CommonTankAppearance__typeDesc=stock,_CommonTankAppearance__vID=20)
        wrapper=env['_make_wrapper'](lambda appearance,cd:outfit)
        with patch.dict(sys.modules,{'BigWorld':SimpleNamespace(player=lambda:SimpleNamespace(playerVehicleID=10))}):
            wrapper(own,None);wrapper(enemy,None)
        self.assertEqual(own._CommonTankAppearance__typeDesc.hull.models.undamaged,'private.model')
        self.assertIs(enemy._CommonTankAppearance__typeDesc,stock)
        self.assertEqual(stock.hull.models.undamaged,'stock.model')

    def test_unknown_player_fails_closed_and_prior_own_copy_is_restored(self):
        env=runtime();stock=self.descriptor();outfit=SimpleNamespace(modelsSet='default')
        own=SimpleNamespace(_CommonTankAppearance__typeDesc=stock,_CommonTankAppearance__vID=10)
        player=SimpleNamespace(playerVehicleID=10);wrapper=env['_make_wrapper'](lambda appearance,cd:outfit)
        with patch.dict(sys.modules,{'BigWorld':SimpleNamespace(player=lambda:player)}):
            wrapper(own,None);del player.playerVehicleID;wrapper(own,None)
        self.assertIs(own._CommonTankAppearance__typeDesc,stock)

    def test_hangar_rebuild_keeps_original_and_respects_new_vehicle_descriptor(self):
        env=runtime();stock=self.descriptor();new=self.descriptor();outfit=SimpleNamespace(modelsSet='default')
        appearance=SimpleNamespace(_HangarVehicleAppearance__vDesc=stock,_HangarVehicleAppearance__outfit=outfit)
        seen=[];wrapper=env['_make_hangar_wrapper'](lambda obj:seen.append(obj._HangarVehicleAppearance__vDesc))
        wrapper(appearance);wrapper(appearance)
        self.assertEqual(stock.hull.models.undamaged,'stock.model')
        self.assertEqual(seen[-1].hull.models.undamaged,'private.model')
        appearance._HangarVehicleAppearance__vDesc=new;wrapper(appearance)
        self.assertIs(getattr(appearance,env['STATE_KEY'])[0],new)
        self.assertEqual(new.hull.models.undamaged,'stock.model')

    def test_native_failure_is_not_swallowed_by_the_wrapper(self):
        env=runtime()
        def original(appearance,cd):raise ValueError('native error')
        with self.assertRaisesRegex(ValueError,'native error'):env['_make_wrapper'](original)(SimpleNamespace(),None)


if __name__=='__main__':unittest.main()
