"""Prevent losing bilateral placement without creating a desktop window."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
import xml.etree.ElementTree as ET
from wotcamo import ae_effects as ae,ae_presets
from wotcamo.ae_gui import AEImporter

class Value:
    def __init__(self,value):self.value=value
    def set(self,value):self.value=value
    def get(self):return self.value

class MirrorFixTests(unittest.TestCase):
    def setUp(self):self.clip={'frame_size':[384,144]}
    def test_new_plane_preserves_the_user_choice(self):
        for mirror in (True,False):
            old=ae.config(dict(placement='plane',mirror=mirror,x=-1.82))
            new=ae.new_plane_config(self.clip,old)
            self.assertEqual(new['mirror'],mirror);self.assertEqual(new['x'],-1.82)
            self.assertEqual(len(ae.positions(new)),2 if mirror else 1)
    def test_single_sided_surface_and_reflection_fit_the_original_side(self):
        for x in (-2,2):
            original=[[x,1,-3,0,0,0,0,0],[x,3,1,0,0,0,1,1],[x,1,1,0,0,0,1,0]]
            reflected=[[-x,*p[1:]] for p in original]
            effect=dict(config={'placement':'surface_glow'},vertices=original+reflected,original_vertex_count=3,positions=[[0,0,0]],part='hull')
            c=ae.new_plane_config(self.clip,dict(mirror=True,placement='surface_glow'),effect)
            self.assertEqual(c['plane'],'side');self.assertAlmostEqual(c['x'],x+(0.006 if x>0 else -0.006))
            self.assertEqual(c['width'],4);self.assertEqual(len(ae.positions(c)),2)
    def test_selection_already_covering_both_sides_uses_first_triangle_side(self):
        first=[[-2,0,0,0,0,0,0,0],[-2,2,0,0,0,0,0,0],[-2,0,4,0,0,0,0,0]]
        opposite=[[2,*p[1:]] for p in first]
        effect=dict(config={'placement':'surface'},vertices=first+opposite,original_vertex_count=6,positions=[[0,0,0]],part='hull')
        out=ae.new_plane_config(self.clip,dict(mirror=True,placement='surface'),effect)
        self.assertEqual(out['plane'],'side');self.assertAlmostEqual(out['x'],-2.006);self.assertEqual(out['width'],4)
    def test_preview_publishes_original_vertex_count(self):
        vertices=np.array([[-2,0,0,1,0,0,0,0],[-2,1,0,1,0,0,0,1],[-2,0,1,1,0,0,1,0],[2,0,0,-1,0,0,0,0],[2,0,1,-1,0,0,1,0],[2,1,0,-1,0,0,0,1]],float)
        plan=dict(vertices=vertices,indices=list(range(6)),part='hull',matrix=np.eye(4),mirrored_triangles=1)
        clip=dict(frames=1,rects=[[0,0,1,1]],atlas_sha256='a'*64,frame_size=[384,144])
        with patch.object(ae,'validate_clip'),patch.object(ae,'geometry_plan',return_value=plan):
            preview=ae.preview_data(clip,dict(placement='surface',mirror=True),{'ae_selection':{'groups':[]}})
        self.assertEqual(preview['original_vertex_count'],3);self.assertEqual(len(preview['vertices']),6)
    def test_center_warns_before_export_but_preview_remains_editable(self):
        c=ae.config(dict(placement='plane',mirror=True,x=0))
        self.assertEqual(len(ae.positions(c)),1)
        with self.assertRaisesRegex(ValueError,'中线'):ae.validate_bilateral_placement(c)
        with patch.object(ae,'validate_clip'),patch.object(ae.engine,'client_info') as client:
            with self.assertRaisesRegex(ValueError,'中线'):ae.build({},self.clip,c,'unused','unused','unused')
            client.assert_not_called()
        for values in (dict(placement='plane',mirror=True,x=-1.82),dict(placement='plane',mirror=False,x=0),dict(placement='surface',mirror=True,x=0)):
            ae.validate_bilateral_placement(values)
    def test_new_plane_gui_keeps_checked_boolean(self):
        old=ae.config(dict(placement='plane',mirror=True,x=-1.82))
        app=SimpleNamespace(clip=self.clip,collect=lambda:old,session=None,placement=Value('独立平面'),mirror=Value(True),part=Value('车体'),plane=Value('侧面'),
                            values={k:Value(str(v)) for k,v in ae.DEFAULTS.items() if k not in ('part','plane','mirror','blend','placement')},
                            param_tabs=SimpleNamespace(select=Mock()),changed=Mock(),note=Value(''))
        AEImporter.new_plane(app);self.assertIs(app.mirror.get(),True);self.assertEqual(app.values['x'].get(),'-1.82')
    def test_center_threshold_and_surface_mode(self):
        for x in (0,1e-6,-1e-6):
            with self.assertRaises(ValueError):ae.validate_bilateral_placement(dict(mirror=True,x=x))
        for x in (1.01e-6,-1.01e-6):self.assertEqual(len(ae.positions(ae.validate_bilateral_placement(dict(mirror=True,x=x)))),2)
    def test_preset_application_preserves_bilateral_placement(self):
        current=ae.config(dict(mirror=True,x=-2,part='turret',placement='plane'))
        saved=ae.config(dict(mirror=False,x=5,brightness=2))
        output=ae_presets.apply_settings(current,saved)
        for key in ('mirror','x','part','placement'):self.assertEqual(output[key],current[key])
        self.assertEqual(output['brightness'],2)
    def test_surface_preset_preserves_mapping_but_plane_uses_preset_mapping(self):
        saved=ae.config(dict(plane='side',brightness=2))
        for mode in ('surface','surface_glow'):
            for direction in ('auto','front','top'):
                current=ae.config(dict(placement=mode,plane=direction,mirror=True))
                output=ae_presets.apply_settings(current,saved)
                self.assertEqual(output['plane'],direction);self.assertTrue(output['mirror']);self.assertEqual(output['brightness'],2)
        self.assertEqual(ae_presets.apply_settings(ae.config(dict(placement='plane',plane='top')),saved)['plane'],'side')
    def test_front_surface_remains_renderable_after_side_preset(self):
        vertices=np.array([[1,-1,2,0,0,1,0,0],[3,-1,2,0,0,1,1,0],[3,1,2,0,0,1,1,1]],float)
        record={'part':'hull','anchor':'hull','anchor_kind':'part','_anchor_matrix':np.eye(4),'_vertices':vertices,'_indices':np.array([0,1,2])}
        project={'ae_selection':{'groups':[{'triangles':[0]}]}}
        current=ae.config(dict(placement='surface',plane='auto',mirror=True))
        values=ae_presets.apply_settings(current,ae.config(dict(plane='side')))
        with patch('wotcamo.area_selection.extract_rigid_lights',return_value=[record]):
            plan=ae.surface_geometry(project,values,None)
            self.assertEqual(plan['mirrored_triangles'],1)
            with self.assertRaisesRegex(ValueError,'没有有效面积'):
                ae.surface_geometry(project,dict(values,plane='side'),None)
    def test_deformed_mirror_reflects_positions_normals_and_winding(self):
        for direction in ('side','front','top'):
            c=ae.config(dict(plane=direction,x=-1.82,width=4,mirror=True,warp_tl_z=-1,warp_tr_z=.5,warp_br_x=.2))
            vertices,indices=ae.plane_mesh(self.clip,c,[0,0,1,1]);other,other_ids=ae.reflect_plane_geometry(vertices,indices)
            left,right=ae.positions(c)
            expected=vertices[:,:3]+left;expected[:,0]*=-1
            np.testing.assert_allclose(other[:,:3]+right,expected)
            np.testing.assert_allclose(other[:,3:6],vertices[:,3:6]*[-1,1,1])
            np.testing.assert_array_equal(other[:,6:8],vertices[:,6:8])
            np.testing.assert_array_equal(np.asarray(other_ids).reshape(-1,3),np.asarray(indices).reshape(-1,3)[:,[0,2,1]])
    def test_new_plane_uses_current_pose_not_stale_preview_or_deformed_bounds(self):
        current=ae.config(dict(plane='side',x=-3,width=4,mirror=True,angle=27,uv_scale_x=1.4,uv_scale_y=.7,warp_tl_z=-2,warp_tr_z=2))
        old=ae.config(dict(current,x=-1.82));vertices,_=ae.plane_mesh(self.clip,old,[0,0,1,1])
        stale={'config':old,'vertices':vertices.tolist(),'positions':ae.positions(old),'part':'hull'}
        new=ae.new_plane_config(self.clip,current,stale)
        for key in ('x','y','z','plane','angle','width','uv_scale_x','uv_scale_y','mirror'):self.assertEqual(new[key],current[key])
        for key in ae.WARPS:self.assertEqual(new[key],0)
        for _ in range(5):new=ae.new_plane_config(self.clip,new,stale)
        self.assertEqual(new['x'],-3);self.assertEqual(new['plane'],'side')
    def test_mirrored_sequences_reference_distinct_frames_with_same_timing(self):
        clip={'frames':3};c=ae.config(dict(fps=24,mirror=True,x=-2))
        left=ET.fromstring(ae.sequence('particles/a/',clip,c,[-2,0,0]))
        right=ET.fromstring(ae.sequence('particles/a/',clip,c,[2,0,0],'frame_mirror_'))
        l=left.findall('sequenceObject')[1:];r=right.findall('sequenceObject')[1:]
        self.assertEqual(len(l),len(r))
        for a,b in zip(l,r):
            self.assertIn('/frame_',a.findtext('resource'));self.assertIn('/frame_mirror_',b.findtext('resource'))
            ta=next(t for t in a.findall('track') if t.findtext('name')=='scale');tb=next(t for t in b.findall('track') if t.findtext('name')=='scale')
            self.assertEqual(ET.tostring(ta),ET.tostring(tb))
    def test_surface_new_plane_recomputes_from_current_form_on_worker(self):
        current=ae.config(dict(placement='surface',plane='auto',mirror=True,u_offset=.4))
        effect={'config':current,'vertices':[[-3,0,0,0,0,0,0,0],[-3,1,0,0,0,0,0,0],[-3,0,2,0,0,0,0,0]],'positions':[[0,0,0]],'original_vertex_count':3,'part':'hull'}
        app=SimpleNamespace(clip=self.clip,collect=lambda:current,session=SimpleNamespace(client='client',effect={'stale':True}),project={'ae_selection':{'groups':[{'triangles':[0]}]}},
                            placement=Value('贴面播放'),mirror=Value(True),part=Value('车体'),plane=Value('自动贴合'),
                            values={k:Value(str(v)) for k,v in ae.DEFAULTS.items() if k not in ('part','plane','mirror','blend','placement')},
                            param_tabs=SimpleNamespace(select=Mock()),changed=Mock(),note=Value(''))
        app.job=lambda worker,done:done(worker())
        with patch.object(ae,'preview_data',return_value=effect) as preview:
            AEImporter.new_plane(app)
        self.assertEqual(preview.call_args.args[1]['u_offset'],.4);self.assertAlmostEqual(float(app.values['x'].get()),-3.006)
        self.assertTrue(app.mirror.get())
    def test_surface_worker_does_not_overwrite_a_new_selection(self):
        current=ae.config(dict(placement='surface',plane='auto',mirror=True))
        effect={'config':current,'vertices':[[-3,0,0,0,0,0,0,0],[-3,1,0,0,0,0,0,0],[-3,0,2,0,0,0,0,0]],'positions':[[0,0,0]],'original_vertex_count':3,'part':'hull'}
        app=SimpleNamespace(clip=self.clip,collect=lambda:current,session=SimpleNamespace(client='client'),project={'ae_selection':{'groups':[{'triangles':[0]}]}},
                            placement=Value('贴面播放'),mirror=Value(True),part=Value('车体'),plane=Value('自动贴合'),
                            values={k:Value(str(v)) for k,v in ae.DEFAULTS.items() if k not in ('part','plane','mirror','blend','placement')},
                            param_tabs=SimpleNamespace(select=Mock()),changed=Mock(),note=Value(''))
        def worker_then_changed(worker,done):
            value=worker();app.project['ae_selection']['groups'][0]['triangles']=[1];done(value)
        app.job=worker_then_changed
        with patch.object(ae,'preview_data',return_value=effect):AEImporter.new_plane(app)
        self.assertEqual(app.placement.get(),'贴面播放');self.assertIn('选区已变化',app.note.get());app.changed.assert_not_called()

if __name__=='__main__':unittest.main()
