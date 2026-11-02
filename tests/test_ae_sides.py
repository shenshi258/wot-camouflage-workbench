"""Explicit bilateral overlays preserve the original side, UVs and joint space."""
import unittest
import numpy as np
from wotcamo import ae_effects as ae

class AESidesTests(unittest.TestCase):
    def triangle(self):return np.array([[-2,0,0,-1,0,0,0,0],[-2,1,0,-1,0,0,1,0],[-2,0,1,-1,0,0,0,1]],dtype=float)
    def test_mirror_is_opt_in_and_preserves_original_side_byte_for_byte(self):
        self.assertFalse(ae.config({})['mirror']);self.assertTrue(ae.config(dict(placement='surface_glow',mirror=True))['mirror'])
        v=self.triangle();out,ids,n=ae.mirror_surface(v,[0,1,2],np.eye(4))
        np.testing.assert_array_equal(out[:3],v);self.assertEqual(n,1);self.assertEqual(ids,[0,1,2,3,4,5])
        expected=v[[0,2,1]].copy();expected[:,0]*=-1;expected[:,3]*=-1
        np.testing.assert_array_equal(out[3:],expected)
    def test_reflection_is_in_part_bind_space_not_an_offset_bone_space(self):
        v=self.triangle();matrix=np.eye(4);matrix[3,:3]=[.7,2,-3]
        out,ids,n=ae.mirror_surface(v,[0,1,2],matrix)
        original=(np.c_[v[:,:3],np.ones(3)]@matrix)[:,:3][[0,2,1]];original[:,0]*=-1
        mirrored=(np.c_[out[3:,:3],np.ones(3)]@matrix)[:,:3]
        np.testing.assert_allclose(mirrored,original);np.testing.assert_allclose(out[3:,3],[1,1,1])
    def test_selected_both_sides_does_not_get_a_second_layer(self):
        v=self.triangle();both,ids,n=ae.mirror_surface(v,[0,1,2],np.eye(4))
        again,newids,extra=ae.mirror_surface(both,ids,np.eye(4))
        self.assertEqual(extra,0);np.testing.assert_array_equal(again,both);self.assertEqual(newids,ids)
    def test_centre_crossing_triangle_is_not_doubled(self):
        v=self.triangle();v[:,0]=[-1,1,0]
        out,ids,n=ae.mirror_surface(v,[0,1,2],np.eye(4));self.assertEqual(n,0);self.assertEqual(len(out),3)
    def test_browser_checkbox_updates_boolean_var_without_a_tk_window(self):
        import queue
        from types import SimpleNamespace
        from wotcamo.ae_gui import AEImporter
        class Value:
            def set(self,value):self.value=value
        mirror=Value();events=queue.Queue();events.put(dict(type='effectparams',values=dict(mirror=True)))
        calls=[]
        app=SimpleNamespace(events=queue.Queue(),session=SimpleNamespace(events=events,viewer=None),values={},mirror=mirror,changed=lambda:calls.append('changed'))
        AEImporter._poll_once(app)
        self.assertIs(mirror.value,True);self.assertEqual(calls,['changed'])

if __name__=='__main__':unittest.main()
