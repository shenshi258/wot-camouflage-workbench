import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from wotcamo import light_assets as mesh, light_effects as engine, light_recipe


class LightMakerTests(unittest.TestCase):
    def test_zip64_locals_are_rejected_and_repack_preserves_payload(self):
        import zipfile
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            source=Path(tmp)/'forced.wotmod';target=Path(tmp)/'normal.wotmod'
            with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
                with z.open('res/example.bin','w',force_zip64=True) as f:f.write(b'unchanged payload')
            with self.assertRaisesRegex(ValueError,'ZIP64'):
                engine.check_game_zip(source)
            info=engine.write_game_archive(source,target,added={'res/new.bin':b'new resource'})
            self.assertFalse(info['zip64'])
            with zipfile.ZipFile(source) as a,zipfile.ZipFile(target) as b:
                self.assertEqual(a.read('res/example.bin'),b.read('res/example.bin'))
                self.assertEqual(b.read('res/new.bin'),b'new resource')

    def test_client_root_accepts_root_mods_and_version_subdirectory(self):
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            root=Path(tmp)/'World_of_Tanks_ASIA';root.mkdir()
            (root/'version.xml').write_text('<root/>')
            (root/'paths.xml').write_text('<root/>')
            for sub in ('','mods','res_mods/2.4.1.0'):
                folder=root/sub;folder.mkdir(parents=True,exist_ok=True)
                self.assertEqual(engine.resolve_client_root(folder),root.resolve())

    def test_invalid_client_path_has_actionable_message(self):
        for path in ('',str(engine.ROOT/'.cache/not_a_game_client')):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'version.xml.*paths.xml'):
                engine.resolve_client_root(path)

    def config(self,changes=None):
        recipe=copy.deepcopy(engine.DEFAULT_RECIPE);recipe.update(changes or {})
        return light_recipe.validate_config(recipe)

    def test_multibone_is_rejected(self):
        vertices=np.zeros((3,8));ids=np.array([[0,1,2]])
        skin=[(0,3,0,128,127)]*3
        matrices={'A':np.eye(4),'B':np.eye(4),'parent':np.eye(4)}
        with self.assertRaisesRegex(ValueError,'多骨骼'):
            engine.attachment(vertices,skin,ids,['A','B'],matrices,{'A':'parent','B':'parent'},'chassis')

    def test_rigid_component_uses_its_actual_bone(self):
        vertices=np.zeros((3,8));ids=np.array([[0,1,2]])
        bone=np.eye(4);bone[3,:3]=[1,2,3]
        anchor,kind,transform=engine.attachment(vertices,[(3,3,3,255,0)]*3,ids,
            ['unused','WheelBlendBone'],{'unused':np.eye(4),'WheelBlendBone':bone,'Wheel':np.eye(4)},
            {'WheelBlendBone':'Wheel'},'chassis')
        self.assertEqual((anchor,kind),('Wheel','node'));np.testing.assert_allclose(transform,bone)

    def test_gun_cannot_use_static_part_alias(self):
        with self.assertRaisesRegex(ValueError,'Gun'):
            engine.attachment(np.zeros((3,8)),[(0,0,0,255,0)]*3,np.array([[0,1,2]]),['bone'],
                {'bone':np.eye(4),'gun':np.eye(4)},{'bone':'gun'},'gun')

    def test_gun_recoil_node_under_inclination_keeps_its_own_frame(self):
        matrices={'Scene Root':np.eye(4),'Gun':np.eye(4),'G':np.eye(4),'Blend':np.eye(4)}
        matrices['G'][3,2]=3
        parents={'Scene Root':None,'Gun':'Scene Root','G':'Gun','Blend':'G'}
        anchor,kind,transform=engine.attachment(np.zeros((3,8)),[(0,0,0,255,0)]*3,np.array([[0,1,2]]),['Blend'],matrices,parents,'gun')
        self.assertEqual((anchor,kind),('G','node'))
        np.testing.assert_allclose(transform@matrices['G'],matrices['Blend'])

    def test_glow_skinned_is_recognized_without_accepting_pbs(self):
        self.assertIn('shaders/std_effects/glow_skinned.fx',engine.GLOW_EFFECTS)
        self.assertNotIn('shaders/std_effects/PBS_tank_skinned.fx',engine.GLOW_EFFECTS)

    def test_connected_components_keep_uv_seams(self):
        v=np.zeros((6,8));v[:,:3]=[[0,0,0],[1,0,0],[0,1,0],[0,0,0],[0,1,0],[-1,0,0]]
        groups=engine.components(v,np.array([[0,1,2],[3,4,5]]))
        self.assertEqual(groups,[[0,1]])

    def test_clipping_preserves_surface_and_uv(self):
        v=np.array([[0,0,0,0,1,0,0,0],[1,0,2,0,1,0,1,1],[0,0,2,0,1,0,0,1]],float)
        ids=np.array([[0,1,2]])
        bands=mesh.split_bands(v,ids,False)
        self.assertAlmostEqual(sum(mesh.area(a,b) for a,b,c in bands),mesh.area(v,ids))
        for a,b,c in bands:np.testing.assert_allclose(a[:,7],a[:,2]/2)

    def test_configuration_rejects_nan_and_invalid_colors(self):
        for changes in [{'每色秒数':float('nan')},{'暗相系数':2},{'颜色':[{'名称':'X','RGB':'#GG0000'}]},{'流水方向':'不确定'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.config(changes)

    def test_native_keyframe_seams_for_varied_palette_sizes(self):
        for count in (1,3,5):
            c=self.config({'颜色':[{'名称':str(i),'RGB':[i/max(1,count-1),.4,1]} for i in range(count)],'每色秒数':1.3})
            for offset in (0,.125,c['period']-.01):
                track=light_recipe.colour_track('light',offset,c);frames=track.findall('frame')
                self.assertEqual(float(frames[0].findtext('startTime')),0)
                self.assertAlmostEqual(float(frames[-1].findtext('startTime')),c['period'])
                np.testing.assert_allclose(list(map(float,frames[0].findtext('value').split())),list(map(float,frames[-1].findtext('value').split())),atol=1e-9)
                np.testing.assert_allclose(list(map(float,frames[0].findtext('outTangent').split())),list(map(float,frames[-1].findtext('inTangent').split())),atol=1e-9)

    def test_indices_roundtrip_and_empty_retained_set(self):
        ids=np.array([[0,1,2],[2,3,0]])
        vb=np.zeros((4,8));vb[:,4]=1
        sections=mesh.sections(mesh.primitives(vb,ids.ravel()))
        sections['keep']=mesh.make_ib(ids[:1],4)
        geo=ET.fromstring('<geometry><primitive>keep</primitive><primitiveGroup>0</primitiveGroup></geometry>')
        recovered,_=engine.read_indices(sections,geo,geo.find('primitiveGroup'))
        np.testing.assert_array_equal(recovered,ids[:1])

    def light(self,identifier):
        return dict(id=identifier,visual='res/vehicles/t/normal/lod0/gun.visual_processed',anchor='Gun',
                    anchor_kind='node',texture='a.dds',material='m',component=0,triangles=1,supported=True,
                    selected=True,source_triangle_ids=[0],_vertices=np.zeros((3,8)),
                    _indices=np.array([[0,1,2]]),_preview=np.zeros((3,3)),vehicle='t',nation='n',part='gun')

    def test_model_recipe_requires_one_recipe_per_model(self):
        lights=[self.light('a'),self.light('b')]
        self.assertIsNone(engine.model_recipe(lights))
        lights[0]['配方']=copy.deepcopy(engine.DEFAULT_RECIPE)
        with self.assertRaisesRegex(ValueError,'配方不一致'):
            engine.model_recipe(lights)
        lights[1]['配方']=copy.deepcopy(engine.DEFAULT_RECIPE)
        self.assertIsNotNone(engine.model_recipe(lights))
        same=engine.model_recipes(lights)
        self.assertEqual(len(same),1)

    def test_project_keeps_overrides_and_rejects_invalid_ones(self):
        import zipfile
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            source=Path(tmp)/'input.wotmod';source.write_bytes(b'demo package bytes')
            project=dict(schema=1,source=str(source),source_sha256=engine.digest(source),
                         lights=[self.light('a'),self.light('b')],scan_issues=[],
                         recipe=copy.deepcopy(engine.DEFAULT_RECIPE),baseline_user_confirmed=False)
            project['lights'][0]['配方']=copy.deepcopy(engine.DEFAULT_RECIPE)
            target=Path(tmp)/'demo.wotlights'
            engine.save_project(project,target)
            with zipfile.ZipFile(target) as z:
                saved=json.loads(z.read('project.json'))
            self.assertEqual(saved['lights'][0]['配方'],project['lights'][0]['配方'])
            self.assertNotIn('配方',saved['lights'][1])
            broken=Path(tmp)/'broken.wotlights'
            project['lights'][1]['配方']={'颜色':[]}
            with self.assertRaises(ValueError):
                engine.save_project(project,broken)
            self.assertFalse(broken.exists())


if __name__=='__main__':unittest.main()
