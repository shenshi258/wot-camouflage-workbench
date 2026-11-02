"""Wheel export regressions. All packages here are synthetic offline fixtures."""
import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
from wotcamo import light_assets as mesh, light_effects as engine


def ring():
    vertices=[];ids=[]
    for i in range(24):
        a,b=np.array([i,i+1])*2*np.pi/24
        base=len(vertices)
        for radius,angle in ((.22,a),(.28,a),(.28,b),(.22,b)):
            y,z=radius*np.cos(angle),radius*np.sin(angle)
            vertices.append([.07,y,z,1,0,0,(y+.3)/.6,(z+.3)/.6])
        ids.extend([[base,base+1,base+2],[base,base+2,base+3]])
    return np.array(vertices),np.array(ids)


def fixture_visual(vertices,ids):
    visual=ET.fromstring(mesh.effect_visual('old_lamp','wheel.dds',vertices,len(ids),'test/'))
    material=visual.find('.//material');material.find('fx').text='shaders/std_effects/glow.fx'
    for p in material.findall('property'):material.remove(p)
    mesh.prop(material,'diffuseMap','Texture','wheel.dds')
    mesh.prop(material,'srcBlend','Int',3);mesh.prop(material,'destBlend','Int',3)
    return visual


class WheelExportTests(unittest.TestCase):
    def test_sector_clipping_keeps_surface_uv_and_bounds(self):
        vertices,ids=ring();bands=mesh.split_wheel(vertices,ids)
        self.assertEqual(len(bands),12)
        self.assertAlmostEqual(sum(mesh.area(v,i) for v,i,_ in bands),mesh.area(vertices,ids),places=10)
        for v,i,_ in bands:
            np.testing.assert_allclose(v[:,6],(v[:,1]+.3)/.6,atol=1e-12)
            np.testing.assert_allclose(v[:,7],(v[:,2]+.3)/.6,atol=1e-12)
            np.testing.assert_allclose(v[:,0],.07)
            self.assertLess(int(i.max()),len(v))

    def test_full_old_lamps_are_removed_without_touching_nodes_or_buffers(self):
        vertices,ids=ring();visual=fixture_visual(vertices,ids)
        rs=visual.find('renderSet')
        visual.append(copy.deepcopy(rs));visual.append(copy.deepcopy(rs))
        skeleton=ET.tostring(visual.find('node'))
        buffers=mesh.sections(mesh.primitives(vertices,ids.ravel()));before=copy.deepcopy(buffers)
        changed,coverage=engine.remove_selected_faces(visual,buffers,{(0,0,0):set(range(len(ids))),(1,0,0):set(range(len(ids)))})
        self.assertFalse(changed)
        self.assertEqual(len(visual.findall('renderSet')),1)
        self.assertEqual(ET.tostring(visual.find('node')),skeleton)
        self.assertEqual(buffers,before)
        self.assertTrue(all(x['suppression']=='geometry_removed' for x in coverage))

    def test_partial_selection_keeps_only_unselected_faces(self):
        vertices,ids=ring();visual=fixture_visual(vertices,ids)
        buffers=mesh.sections(mesh.primitives(vertices,ids.ravel()))
        before=buffers['vertices']
        changed,coverage=engine.remove_selected_faces(visual,buffers,{(0,0,0):{0,1}})
        geo=visual.find('.//geometry')
        retained,_=engine.read_indices(buffers,geo,geo.find('primitiveGroup'))
        self.assertTrue(changed);np.testing.assert_array_equal(retained,ids[2:])
        self.assertEqual(before,buffers['vertices'])
        self.assertEqual(coverage[0]['retained_triangles'],len(ids)-2)

    def light(self,name,visual):
        vertices,ids=ring()
        return dict(id=name,visual=visual,anchor='W_R0',anchor_kind='node',texture='res/wheel.dds',
                    selected=True,supported=True,part='chassis',vehicle='TestTank',nation='test',
                    render_set=0,geometry=0,group=0,source_triangle_ids=list(range(len(ids))),
                    _vertices=vertices,_indices=ids,_preview=vertices[:,:3],_anchor_matrix=np.eye(4))

    def lights(self):
        normal='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'
        skin='res/vehicles/test/TestTank/_skins/style/normal/lod0/chassis.visual_processed'
        return [self.light('normal',normal),self.light('skin',skin)]

    def test_exact_variant_aliases_share_one_export(self):
        lights=self.lights()
        kept,aliases=engine.deduplicate_variant_lights(lights,engine.DEFAULT_RECIPE)
        self.assertEqual(len(kept),1);self.assertEqual(aliases[0]['representative'],'normal')

    def test_distinct_frame_geometry_or_recipe_is_never_deduplicated(self):
        for change in ('frame','vertices','recipe','same_visual'):
            lights=self.lights()
            if change=='frame':lights[1]['anchor']='W_R1'
            if change=='vertices':lights[1]['_vertices'][0,1]+=.001
            if change=='recipe':lights[1]['配方']=dict(engine.DEFAULT_RECIPE,峰值倍率=4)
            if change=='same_visual':lights[1]['visual']=lights[0]['visual']
            with self.subTest(change=change):
                if change=='recipe':
                    with self.assertRaisesRegex(ValueError,'重复外观'):
                        engine.deduplicate_variant_lights(lights,engine.DEFAULT_RECIPE)
                    continue
                kept,aliases=engine.deduplicate_variant_lights(lights,engine.DEFAULT_RECIPE)
                self.assertEqual(len(kept),2);self.assertFalse(aliases)

    def test_build_writes_one_wheel_with_multiple_live_colour_tracks(self):
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            root=Path(tmp);source=root/'synthetic.wotmod';lights=self.lights()
            vertices,ids=ring();visual=fixture_visual(vertices,ids)
            with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
                for light in lights:
                    z.writestr(light['visual'],mesh.xml(visual))
                    z.writestr(light['visual'].replace('.visual_processed','.primitives_processed'),mesh.primitives(vertices,ids.ravel()))
                z.writestr('res/wheel.dds',mesh.dds(True))
            recipe=dict(copy.deepcopy(engine.DEFAULT_RECIPE),效果模式='百花齐放',流水方向='四周扩散')
            project=dict(source=str(source),source_sha256=engine.digest(source),recipe=recipe,lights=lights)
            def compile_fixture(source,target,client):target.write_bytes(b'offline fixture - not executable')
            with patch.object(engine,'client_info',return_value={'root':str(root/'client')}), \
                 patch.object(engine,'compile27',side_effect=compile_fixture), \
                 patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
                target,report=engine.build(project,root/'client',root/'out','synthetic')
            with zipfile.ZipFile(target) as z:
                manifest=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/manifest.json'))))
                self.assertEqual(len(manifest['models']),1)
                self.assertEqual(len(manifest['deduplicated_lights']),1)
                self.assertEqual(len(manifest['bands']),12)
                visual=ET.fromstring(z.read('res/'+manifest['models'][0]['sequence'][:-4]+'.visual_processed'))
                low=np.fromstring(visual.findtext('boundingBox/min'),sep=' ')
                high=np.fromstring(visual.findtext('boundingBox/max'),sep=' ')
                self.assertGreater(high[0]-low[0],.0099)
                self.assertLess(low[0],.07);self.assertGreater(high[0],.07)
                from wotcamo.light_preview import prepare
                preview=prepare(lights,recipe)
                np.testing.assert_allclose([x['offset'] for x in preview],
                                           [x['offset_seconds'] for x in manifest['bands']])
                self.assertGreater(len(set(round(x['offset_seconds'],6) for x in manifest['bands'])),1)
                seq=ET.fromstring(z.read('res/'+manifest['models'][0]['sequence']))
                self.assertEqual(len(seq.findall('.//track[property="g_tint"]')),12)
                for light in lights:
                    self.assertFalse(ET.fromstring(z.read(light['visual'])).findall('.//geometry'))
                self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')


if __name__=='__main__':unittest.main()
