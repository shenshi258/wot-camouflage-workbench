"""Cross-layer checks for per-face recipes, continuous colour and safe output."""
import copy
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from wotcamo import light_assets as mesh, light_effects as engine, light_recipe as recipe
from wotcamo import light_preview, preview3d_assets, light_presets, light_select
import test_light_wheels as fixtures


class Version21Tests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'original.wotmod'
        vertices,indices=fixtures.ring();visual=fixtures.fixture_visual(vertices,indices)
        second=copy.deepcopy(visual.find('renderSet'))
        second.find('geometry/vertices').text='second_vertices'
        second.find('geometry/primitive').text='second_indices'
        visual.append(second)
        sections=mesh.sections(mesh.primitives(vertices,indices.ravel()))
        other=vertices.copy();other[:,2]+=1.5
        sections.update({'second_'+k:v for k,v in mesh.sections(mesh.primitives(other,indices.ravel())).items()})
        self.visual='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'
        with zipfile.ZipFile(self.source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.visual,mesh.xml(visual))
            z.writestr(self.visual.replace('.visual_processed','.primitives_processed'),mesh.packed_sections(sections))
            z.writestr('res/wheel.dds',mesh.dds(True))
        self.project=engine.scan(self.source,self.root/'scan')
        self.assertEqual(len(self.project['lights']),2)
        self.assertEqual(light_select.model_key(self.project['lights'][0]),light_select.model_key(self.project['lights'][1]))
        for light in self.project['lights']:light['selected']=True
        custom=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式='流水渐变',换色曲线='匀速',
                    颜色=[{'名称':'红','RGB':'#FF0000'},{'名称':'蓝','RGB':'#0000FF'}],每色秒数=1.)
        self.project['lights'][0]['配方']=custom

    def build(self):
        with patch.object(engine,'client_info',return_value={'root':str(self.root/'client')}), \
             patch.object(engine,'compile27',side_effect=lambda s,t,c:t.write_bytes(b'offline only')), \
             patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
            return engine.build(self.project,self.root/'client',self.root/'out','fixture')

    def test_one_face_is_partitioned_in_export_and_embedded_recovery(self):
        original=engine.digest(self.source);target,report=self.build()
        with zipfile.ZipFile(target) as z:
            manifest=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/manifest.json'))))
            self.assertEqual(len(manifest['models']),2)
            self.assertEqual(manifest['per_model_recipes']['light_000']['换色曲线'],'匀速')
            self.assertNotIn('light_001',manifest['per_model_recipes'])
            self.assertEqual(manifest['model_faces']['light_000'],[self.project['lights'][0]['id']])
            self.assertEqual(manifest['model_faces']['light_001'],[self.project['lights'][1]['id']])
            self.assertEqual(len(z.read(self.visual)),len(mesh.xml(engine.xml(z.read(self.visual)))))
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        self.assertEqual(engine.digest(self.source),original)
        restored=engine.scan(target,self.root/'restored')
        self.assertEqual(restored['lights'][0]['配方'],self.project['lights'][0]['配方'])
        self.assertNotIn('配方',restored['lights'][1])

    def test_two_previews_use_same_partition_and_export_phase(self):
        offline=light_preview.prepare(self.project['lights'],self.project['recipe'])
        three=preview3d_assets.lamp_plan(self.project,{'chassis':self.visual})
        self.assertEqual([x['identifier'] for x in offline],[x['identifier'] for x in three])
        for a,b in zip(offline,three):
            self.assertAlmostEqual(a['offset'],b['phase'])
            self.assertEqual(a['config']['raw'],b['config']['raw'])
        self.assertEqual({x['config']['curve'] for x in three},{'柔和','匀速'})

    def test_duplicate_variant_is_recognized_but_adjacent_face_is_not(self):
        faces=fixtures.WheelExportTests().lights()
        aliases=engine.variant_aliases(faces)
        self.assertEqual(aliases['normal'],{'skin'});self.assertEqual(aliases['skin'],{'normal'})
        self.assertFalse(engine.variant_aliases(self.project['lights']))

    def test_reference_presets_are_valid_and_do_not_overwrite_custom_values(self):
        names={'常亮模式','呼吸模式','梦幻彩虹','一触即发','雨中漫步','涟漪扩散','繁星点点',
               '川流不息','随波逐流','如影随形','正弦光波','旋转风车','七彩瀑布','花开富贵'}
        defaults=light_presets.defaults();self.assertTrue(names<=set(defaults))
        light_presets.validate_library({'版本':1,'预设':defaults})
        custom=copy.deepcopy(defaults['梦幻彩虹']);custom['说明']='我的原有预设'
        self.assertEqual(light_presets.with_new_presets({'梦幻彩虹':custom})['梦幻彩虹'],custom)
        self.assertIn('不响应',defaults['一触即发']['说明'])
        self.assertIn('非真实',defaults['旋转风车']['说明'])

    def test_continuous_tracks_close_for_all_modes_and_keep_colour_corner_speed(self):
        raw=dict(copy.deepcopy(engine.DEFAULT_RECIPE),换色曲线='匀速',每色秒数=1.,呼吸周期秒数=4.,
                 颜色=[{'名称':'红','RGB':'#FF0000'},{'名称':'绿','RGB':'#00FF00'},{'名称':'蓝','RGB':'#0000FF'}])
        for mode in recipe.MODES:
            with self.subTest(mode=mode):
                cfg=recipe.validate_config(dict(raw,效果模式=mode))
                frames=recipe.colour_track('lamp',0,cfg).findall('frame')
                for field in ('value','inTangent','outTangent'):
                    np.testing.assert_allclose(np.fromstring(frames[0].findtext(field),sep=' '),
                                               np.fromstring(frames[-1].findtext(field),sep=' '),atol=1e-7)
                dt=0.001
                values=preview3d_assets.evaluate_track(frames,np.array([1-dt,1.,1+dt]))[:,:3]
                self.assertGreater(np.linalg.norm(values[1]-values[0])/dt,1e-4)
                self.assertGreater(np.linalg.norm(values[2]-values[1])/dt,1e-4)

    def test_all_curves_close_exactly_with_nonzero_spatial_phase(self):
        for mode in recipe.MODES:
            for curve in ('柔和','匀速'):
                raw=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式=mode,换色曲线=curve)
                cfg=recipe.validate_config(raw)
                with self.subTest(mode=mode,curve=curve):
                    frames=recipe.colour_track('lamp',.173,cfg).findall('frame')
                    self.assertEqual(frames[0].findtext('value'),frames[-1].findtext('value'))
                    self.assertEqual(frames[0].findtext('inTangent'),frames[-1].findtext('inTangent'))
                    self.assertEqual(frames[0].findtext('outTangent'),frames[-1].findtext('outTangent'))

    def test_old_palette_remains_eased_unless_continuous_is_selected(self):
        raw=copy.deepcopy(engine.DEFAULT_RECIPE)
        old=recipe.validate_config(raw);linear=recipe.validate_config(dict(raw,换色曲线='匀速'))
        old_value=recipe.color_at(old['step']*.25,0,old)[0]
        linear_value=recipe.color_at(linear['step']*.25,0,linear)[0]
        self.assertNotEqual(old_value,linear_value)
        self.assertEqual(old['curve'],'柔和')

    def test_continuous_curve_removes_repeated_colors_at_loop_boundary(self):
        raw=dict(copy.deepcopy(engine.DEFAULT_RECIPE),换色曲线='匀速',每色秒数=1.,
                 颜色=[{'名称':'红','RGB':'#FF0000'},{'名称':'红2','RGB':'#FF0000'},
                     {'名称':'蓝','RGB':'#0000FF'},{'名称':'首尾红','RGB':'#FF0000'}])
        cfg=recipe.validate_config(raw)
        self.assertEqual(len(cfg['palette']),2);self.assertEqual(cfg['palette_period'],2.)
        before=recipe.color_at(1.9,0,cfg)[0];after=recipe.color_at(.1,0,cfg)[0]
        self.assertNotEqual(before,after)

    def test_parser_rejects_bad_data_area_and_optimized_mode_still_checks(self):
        blob=bytearray(mesh.packed_sections({'test':b'abcd'}))
        table=len(blob)-4-struct.unpack_from('<I',blob,len(blob)-4)[0]
        struct.pack_into('<I',blob,table,1000)
        with self.assertRaisesRegex(ValueError,'超出数据区'):mesh.sections(bytes(blob))
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        code="from wotcamo.light_assets import sections; sections(b'\\0'*8)"
        result=subprocess.run([sys.executable,'-O','-c',code],cwd=engine.ROOT,env=env,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'ValueError',result.stderr)

    def test_failed_save_leaves_no_finished_or_temporary_project(self):
        target=self.root/'result.wotlights'
        with patch.object(zipfile.ZipFile,'testzip',side_effect=OSError('injected failure')):
            with self.assertRaisesRegex(OSError,'injected failure'):engine.save_project(self.project,target)
        self.assertFalse(target.exists());self.assertFalse(list(self.root.glob('result.wotlights.*.building')))
        self.assertTrue(self.source.exists())


if __name__=='__main__':unittest.main()
