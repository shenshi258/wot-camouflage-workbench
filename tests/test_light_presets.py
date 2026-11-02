import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from wotcamo import light_presets as presets, light_recipe as recipe, light_assets as mesh, light_effects as engine


class PresetTests(unittest.TestCase):
    def test_requested_builtins_are_valid_and_distinct(self):
        records=presets.defaults();presets.validate_library({'版本':1,'预设':records})
        curves=[]
        for name in ('流水渐变','百花齐放','动态呼吸','波浪','跑马灯'):
            config=recipe.validate_config(records[name]['配方']);self.assertEqual(config['mode'],name)
            offset=recipe.spatial_offset((0,0,1),(0,0,0),config,'test_band')
            curves.append([recipe.animated_value(t,offset,config) for t in np.linspace(0,6,37)])
        for i,a in enumerate(curves):
            for b in curves[i+1:]:self.assertGreater(np.max(np.abs(np.array(a)-b)),.05)

    def test_radial_equal_radius_and_outward_delay(self):
        config=recipe.validate_config(presets.defaults()['四周扩散']['配方'])
        center=(0,0,0)
        offsets=[recipe.spatial_offset(p,center,config,'same') for p in ((1,0,0),(-1,0,0),(0,0,1),(0,0,-1))]
        self.assertEqual(len(set(offsets)),1)
        np.testing.assert_allclose(recipe.animated_value(1,offsets[0],config),recipe.animated_value(0,0,config))

    def test_new_mode_tracks_loop_without_negative_interpolation(self):
        for name in ('流水渐变','百花齐放','动态呼吸','波浪','跑马灯'):
            config=recipe.validate_config(presets.defaults()[name]['配方'])
            frames=recipe.colour_track('test',.127,config).findall('frame')
            def vec(f,key):return np.array(list(map(float,f.findtext(key).split())))
            np.testing.assert_allclose(vec(frames[0],'value'),vec(frames[-1],'value'),atol=1e-8)
            np.testing.assert_allclose(vec(frames[0],'outTangent'),vec(frames[-1],'inTangent'),atol=1e-8)
            for a,b in zip(frames,frames[1:]):
                dt=float(b.findtext('startTime'))-float(a.findtext('startTime'))
                for u in (.2,.5,.8):
                    v=(2*u**3-3*u*u+1)*vec(a,'value')+(u**3-2*u*u+u)*dt*vec(a,'outTangent')+(-2*u**3+3*u*u)*vec(b,'value')+(u**3-u*u)*dt*vec(b,'inTangent')
                    self.assertGreaterEqual(v[:3].min(),-1e-8);self.assertLessEqual(v[:3].max(),config['peak']+1e-8)
                    self.assertEqual(v[3],1.)

    def test_common_cycle_and_legacy_config(self):
        raw=copy.deepcopy(presets.defaults()['波浪']['配方']);raw['每色秒数']=1.5
        config=recipe.validate_config(raw);self.assertEqual(config['period'],18)
        old=recipe.validate_config(engine.DEFAULT_RECIPE)
        self.assertEqual(old['mode'],'流水呼吸');self.assertEqual(old['period'],6)

    def test_radial_clipping_preserves_area_and_uv_on_grid_boundary(self):
        v=np.array([[0,0,0,0,1,0,0,0],[2,0,0,0,1,0,2,0],[0,0,2,0,1,0,0,2]],float)
        ids=np.array([[0,1,2]])
        split=mesh.split_radial(v,ids)
        self.assertGreater(len(split),3)
        self.assertAlmostEqual(sum(mesh.area(a,b) for a,b,c in split),mesh.area(v,ids))
        for a,b,c in split:np.testing.assert_allclose(a[:,6:8],a[:,[0,2]])

    def test_preset_edit_backup_and_share_roundtrip(self):
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            path=Path(tmp)/'library.json';share=Path(tmp)/'share.json'
            records=presets.defaults();presets.save(records,path)
            records['我的扩散']=copy.deepcopy(records['四周扩散']);records['我的扩散']['配方']['每米延迟秒数']=.2
            presets.save(records,path)
            self.assertTrue(path.with_suffix('.json.bak').exists())
            loaded=presets.load(path);presets.export_file({'我的扩散':loaded['我的扩散']},share)
            self.assertEqual(presets.import_file(share),{'我的扩散':records['我的扩散']})
            records['错误']=copy.deepcopy(records['我的扩散']);records['错误']['配方']['每米延迟秒数']='执行代码'
            with self.assertRaises(ValueError):presets.save(records,path)
            self.assertNotIn('错误',presets.load(path))


if __name__=='__main__':unittest.main()
