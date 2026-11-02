"""Runtime frame observations are bounded and never mutate vehicle nodes."""
import types
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np

class Matrix:
    def __init__(self,other):self.value=np.array(other.value,copy=True)
    def invert(self):self.value=np.linalg.inv(self.value)
    def applyPoint(self,point):return tuple((np.r_[point,1.]@self.value)[:3])

class FrameDiagnosticTests(unittest.TestCase):
    def runtime(self):
        math=types.ModuleType('Math');math.Matrix=Matrix
        helpers=types.ModuleType('helpers');helpers.newFakeModel=Mock()
        vehicles=types.ModuleType('vehicle_systems');vehicles.camouflages=types.SimpleNamespace()
        modules={'BigWorld':types.ModuleType('BigWorld'),'Math':math,'helpers':helpers,
                 'AnimationSequence':types.ModuleType('AnimationSequence'),'vehicle_systems':vehicles}
        source=(Path(__file__).parents[1]/'wotcamo/light_runtime.py.txt').read_text(encoding='utf-8')
        env={}
        with patch.dict('sys.modules',modules):exec(compile(source.rsplit('\ninit()',1)[0],'<light runtime>','exec'),env)
        env['_log']=Mock()
        return env

    def test_reports_relative_frame_scale_and_enable_state_without_mutation(self):
        env=self.runtime();chassis=types.SimpleNamespace(value=np.eye(4));chassis.value[3,:3]=[100,2,50]
        anchor=types.SimpleNamespace(value=chassis.value.copy());anchor.value[3,:3]+=[1.365,.354725,1.98377]
        compound=types.SimpleNamespace(node=Mock(return_value=chassis))
        group=env['_WarpGroup'](compound,None);group.diagnostic_frames=30
        owned=types.SimpleNamespace(_node=anchor,_mount=types.SimpleNamespace(visible=True,position=(0,0,0)),
                                    _root=types.SimpleNamespace(visible=True),_key='light_000',_enabled=True,
                                    _actual_enabled=True,_detached=False)
        group.members=[lambda:owned];before=anchor.value.copy()
        group.diagnose_frames()
        env['_log'].exception.assert_not_called();call=env['_log'].info.call_args.args
        np.testing.assert_allclose(call[-3],[1.365,.354725,1.98377]);np.testing.assert_allclose(call[-2],[1,1,1])
        np.testing.assert_array_equal(anchor.value,before)
        compound.node.assert_called_once_with('chassis')

    def test_diagnostic_failure_does_not_propagate_to_effect(self):
        env=self.runtime();compound=types.SimpleNamespace(node=Mock(side_effect=ValueError('not ready')))
        group=env['_WarpGroup'](compound,None);group.diagnose_frames()
        env['_log'].exception.assert_called_once()

    def test_only_three_diagnostic_snapshots_per_group(self):
        env=self.runtime();env['BigWorld'].callback=Mock(return_value=1)
        env['FRAME_DIAGNOSTICS_ENABLED']=True
        group=env['_WarpGroup'](types.SimpleNamespace(),None);group.active.add('lamp')
        group.sync_visibility=Mock();group.diagnose_frames=Mock()
        for _ in range(240):group.tick()
        self.assertEqual(group.diagnose_frames.call_count,3)
        group.callback=None

    def test_release_runtime_does_not_collect_diagnostic_frames_by_default(self):
        env=self.runtime();env['BigWorld'].callback=Mock(return_value=1)
        group=env['_WarpGroup'](types.SimpleNamespace(),None);group.active.add('lamp')
        group.sync_visibility=Mock();group.diagnose_frames=Mock()
        for _ in range(240):group.tick()
        group.diagnose_frames.assert_not_called();self.assertEqual(group.diagnostic_frames,0)
        group.callback=None

    def test_visibility_addon_failure_does_not_override_native_result(self):
        env=self.runtime()
        class Appearance:
            compoundModel=object()
            def changeVisibility(self,value):return 'native:'+str(value)
            def changeDrawPassVisibility(self,value):raise ValueError('native failure')
        module=types.ModuleType('vehicle_systems.CompoundAppearance')
        module.CompoundAppearance=Appearance
        env['_sync_compound']=Mock(side_effect=RuntimeError('addon failure'))
        with patch.dict('sys.modules',{'vehicle_systems.CompoundAppearance':module}):
            env['_install_visibility_hooks']()
        self.assertEqual(Appearance().changeVisibility(True),'native:True')
        env['_log'].exception.assert_called_once()
        with self.assertRaisesRegex(ValueError,'native failure'):
            Appearance().changeDrawPassVisibility(False)

    def test_scope_hide_restore_and_stop_clean_up_only_own_mount(self):
        env=self.runtime();env['BigWorld'].player=Mock(return_value=None)
        env['BigWorld'].callback=Mock(return_value=1);env['BigWorld'].cancelCallback=Mock()
        compound=types.SimpleNamespace(visible=1,skipColorPass=False)
        descriptor=types.SimpleNamespace(type=types.SimpleNamespace(name='__VEHICLE_TYPE__'))
        group=env['_WarpGroup'](compound,descriptor)
        native=Mock();node=types.SimpleNamespace(attach=Mock(),detach=Mock())
        mount=types.SimpleNamespace(visible=False);root=types.SimpleNamespace(visible=False)
        owned=env['_OwnedSequence'](native,group,'lamp',root,node,mount)
        owned.setEnabled(True);owned.start()
        self.assertTrue(mount.visible);self.assertTrue(root.visible)
        compound.skipColorPass=True;env['_sync_compound'](compound)
        self.assertFalse(mount.visible);self.assertFalse(root.visible)
        native.setEnabled.assert_called_with(False)
        compound.skipColorPass=False;env['_sync_compound'](compound)
        self.assertTrue(mount.visible);native.setEnabled.assert_called_with(True)
        owned.stop();node.detach.assert_called_once_with(mount)
        native.stop.assert_called_once();env['BigWorld'].cancelCallback.assert_called_once_with(1)
        self.assertEqual(compound.visible,1)
