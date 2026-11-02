"""Audit regressions: real serialized tracks and GUI callbacks without windows."""
import copy
import queue
import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from wotcamo import ae_effects as ae, preview3d_assets as assets
from wotcamo.ae_gui import AEImporter, _preset_action_buttons, PLACEMENTS, BLENDS


class Value:
    def __init__(self,value,callback=None):self.value=value;self.callback=callback
    def get(self):return self.value
    def set(self,value):
        self.value=value
        if self.callback:self.callback()


class AEReviewFixTests(unittest.TestCase):
    def test_all_integer_fps_frame_counts_have_strict_serialized_times(self):
        # Inspect every frame track, including the first-frame loop seam.
        for fps in range(1,61):
            for count in range(2,129):
                for index in range(count):
                    times=[float(format(t,'.12g')) for t,_ in ae.frame_keys(index,count,fps)]
                    if not all(b>a for a,b in zip(times,times[1:])):
                        self.fail('Non-increasing serialized times: %r'%((fps,count,index,times),))

    def test_all_last_frame_key_times_and_midpoints_evaluate_finitely(self):
        for fps in [*range(1,61),23.976,29.97,59.94,1.000001,59.999999]:
            for count in range(2,129):
                obj=ET.Element('object')
                ae.write_track(obj,'scale',[(t,[s]*3) for t,s in ae.frame_keys(count-1,count,fps)])
                frames=obj.find('track').findall('frame')
                times=np.array([float(f.findtext('startTime')) for f in frames])
                samples=np.r_[times,(times[:-1]+times[1:])/2]
                with np.errstate(all='raise'):
                    values=assets.evaluate_track(frames,samples)
                if not np.isfinite(values).all():self.fail('Nonfinite scale: %r'%((fps,count),))

    def app(self,placement='独立平面',blend='发光叠加',plane='侧面'):
        calls=[];widget=SimpleNamespace(state=lambda value:None)
        app=SimpleNamespace(events=queue.Queue(),session=SimpleNamespace(events=queue.Queue(),viewer=None,project={}),
                            project={'source_sha256':'a'*64,'ae_surface_origin':{'point':[9,9,9]}},
                            part=Value('车体'),plane=Value(plane),blend=Value(blend),mirror=Value(True),
                            values={k:Value(str(v)) for k,v in ae.DEFAULTS.items() if k not in ('part','plane','blend','mirror','placement')},
                            selection_note=Value(''),mode_note=Value(''),plane_widgets=[widget],surface_widgets=[widget],
                            fields={'lift':widget},param_tabs=SimpleNamespace(select=lambda index:None),
                            changed=lambda:calls.append('changed'))
        app.placement=Value(placement,lambda:AEImporter.mode_changed(app))
        app.update_selection_note=lambda:AEImporter.update_selection_note(app)
        app.session.project=copy.deepcopy(app.project)
        return app,calls

    def test_ordinary_selection_preserves_all_explicit_effect_parameters(self):
        for placement in PLACEMENTS:
            for blend in BLENDS:
                app,calls=self.app(placement,blend,'正面')
                app.values['u_offset'].set('.3');app.values['v_offset'].set('-.2')
                before=AEImporter.collect(app)
                selection={'groups':[{'triangles':[1,2,3]}]}
                app.session.events.put(dict(type='bodyselect',selection=selection))
                AEImporter._poll_once(app)
                self.assertEqual(AEImporter.collect(app),before)
                self.assertEqual(app.project['ae_selection'],selection)
                self.assertEqual(app.session.project['ae_selection'],selection)
                self.assertIsNot(app.project['ae_selection'],selection)
                self.assertNotIn('ae_surface_origin',app.project)
                self.assertNotIn('ae_surface_origin',app.session.project)
                self.assertEqual(calls,['changed'])

    def test_explicit_snap_still_selects_surface_mode_and_resets_origin(self):
        for blend,expected in [('发光叠加','贴面发光'),('普通透明','贴面播放')]:
            app,_=self.app(blend=blend)
            app.values['u_offset'].set('.4');app.values['v_offset'].set('.2')
            app.session.events.put(dict(type='bodyselect',selection={'groups':[{'triangles':[0]}]},snap=True,point=[1,2,3]))
            AEImporter._poll_once(app)
            self.assertEqual(app.placement.get(),expected);self.assertEqual(app.blend.get(),blend)
            self.assertEqual(app.plane.get(),'自动贴合')
            self.assertTrue(app.mirror.get())
            for project in (app.project,app.session.project):self.assertEqual(project['ae_surface_origin']['point'],[1,2,3])
            self.assertEqual(float(app.values['u_offset'].get()),0);self.assertEqual(float(app.values['v_offset'].get()),0)

    def test_manual_surface_modes_still_apply_their_intended_defaults(self):
        app,_=self.app()
        app.placement.set('贴面播放');self.assertEqual(app.blend.get(),'普通透明')
        app.placement.set('贴面发光');self.assertEqual(app.blend.get(),'发光叠加')

    def test_action_grid_fits_the_audited_minimum_width_budget(self):
        columns={};buttons=[];invoked=[]
        parent=SimpleNamespace(columnconfigure=lambda index,**kw:columns.update({index:kw}))
        class Button:
            def __init__(self,parent,**kw):self.options=kw;buttons.append(self)
            def grid(self,**kw):self.cell=kw
        actions=[(label,lambda label=label:invoked.append(label)) for label in ('套用','导入…','导出…','删除','预设目录','关闭')]
        with patch('wotcamo.ae_gui.ttk.Button',Button):result=_preset_action_buttons(parent,actions)
        self.assertEqual(result,buttons);self.assertEqual(set(columns),{0,1,2})
        self.assertEqual({(b.cell['row'],b.cell['column']) for b in buttons},{(r,c) for r in range(2) for c in range(3)})
        self.assertTrue(all(c['weight']==1 and c['uniform']=='preset_actions' for c in columns.values()))
        # The audit measured 118px at 10pt and ~135px at 12pt per button.
        # This checks the new three-column geometry budget, without mapping Tk.
        for width in (700,780):
            for request in (118,135):
                inner=width-2*18
                self.assertLessEqual(3*max(request,120)+2*7,inner)
                self.assertGreaterEqual((inner-2*7)/3,90)
        for button in buttons:
            self.assertEqual(button.cell['sticky'],'ew');button.options['command']()
        self.assertEqual(invoked,[label for label,_ in actions])


if __name__=='__main__':unittest.main()
