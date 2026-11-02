"""Legacy tangent-space vertex support, based on native format declarations."""
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from wotcamo import light_assets as mesh,light_effects as engine


def legacy_vertices(fmt=b'xyznuviiiwwtb',weights=(6,0,0,255,0)):
    data=fmt.ljust(64,b'\0')+struct.pack('<I',3)
    for i in range(3):
        common=struct.pack('<3fI2f',i*.5,i*.25,i*.1,511<<22,.1+i*.2,.8-i*.1)
        if fmt in (b'xyznuviiiww',b'xyznuviiiwwtb'):common+=bytes(weights)
        if fmt in (b'xyznuvtb',b'xyznuviiiwwtb'):common+=struct.pack('<II',0x12345678,0xabcdef01)
        data+=common
    return data


class VertexFormatTests(unittest.TestCase):
    def test_37_byte_rows_keep_xyz_normal_uv_and_skin(self):
        data=legacy_vertices();vertices,skin=mesh.vertex_data(data)
        self.assertEqual(len(data),68+3*37)
        np.testing.assert_allclose(vertices[:,:3],[[0,0,0],[.5,.25,.1],[1,.5,.2]],atol=1e-7)
        np.testing.assert_allclose(vertices[:,3:6],[[0,1,0]]*3)
        np.testing.assert_allclose(vertices[:,6:8],[[.1,.8],[.3,.7],[.5,.6]],atol=1e-7)
        self.assertEqual(skin,[(6,0,0,255,0)]*3)

    def test_tb_does_not_change_the_existing_29_byte_decode(self):
        a,sa=mesh.vertex_data(legacy_vertices(b'xyznuviiiww'))
        b,sb=mesh.vertex_data(legacy_vertices())
        np.testing.assert_array_equal(a,b);self.assertEqual(sa,sb)

    def test_static_tb_is_not_mistaken_for_float_normals(self):
        vertices,skin=mesh.vertex_data(legacy_vertices(b'xyznuvtb'))
        np.testing.assert_allclose(vertices[:,3:6],[[0,1,0]]*3)
        self.assertEqual(skin,[])

    def test_rigid_and_multibone_rules_still_apply(self):
        vertices,skin=mesh.vertex_data(legacy_vertices())
        nodes=['unused','unused2','Blend'];matrices={key:np.eye(4) for key in nodes+['W_R0']}
        anchor,kind,_=engine.attachment(vertices,skin,np.array([[0,1,2]]),nodes,matrices,{'Blend':'W_R0'},'chassis')
        self.assertEqual((anchor,kind),('W_R0','node'))
        vertices,skin=mesh.vertex_data(legacy_vertices(weights=(0,3,0,128,127)))
        with self.assertRaisesRegex(ValueError,'多骨骼'):
            engine.attachment(vertices,skin,np.array([[0,1,2]]),nodes,matrices,{'Blend':'W_R0'},'chassis')

    def test_corrupt_buffer_has_a_useful_length_error(self):
        for data in (legacy_vertices()[:-1],legacy_vertices()+b'\0'):
            with self.assertRaisesRegex(ValueError,'xyznuviiiwwtb 顶点长度不匹配'):
                mesh.vertex_data(data)
        with self.assertRaisesRegex(ValueError,'数据头不完整'):mesh.vertex_data(b'bad')

    def test_unknown_layout_names_the_format(self):
        data=b'not_a_supported_layout'.ljust(64,b'\0')+struct.pack('<I',0)
        with self.assertRaisesRegex(mesh.UnsupportedVertexFormat,'not_a_supported_layout'):
            mesh.vertex_data(data)

    def fixture(self,root,fmt):
        source=root/'synthetic.wotmod'
        vertices=np.array([[0,0,0,0,1,0,0,0],[1,0,0,0,1,0,1,0],[0,0,1,0,1,0,0,1]],float)
        visual=ET.fromstring(mesh.effect_visual('tank_equipment_glow','wheel.dds',vertices,1,'test/'))
        scene=visual.find('node')
        for parent,name in ((scene,'W_R0'),):
            node=ET.SubElement(parent,'node');ET.SubElement(node,'identifier').text=name
            node.append(ET.fromstring(ET.tostring(scene.find('transform'))))
        for name in ('A','B','Blend'):
            node=ET.SubElement(visual.find('node/node'),'node');ET.SubElement(node,'identifier').text=name
            node.append(ET.fromstring(ET.tostring(scene.find('transform'))))
        rs=visual.find('renderSet');rs.find('node').text='A'
        ET.SubElement(rs,'node').text='B';ET.SubElement(rs,'node').text='Blend'
        material=visual.find('.//material');material.find('fx').text='shaders/std_effects/glow_skinned.fx'
        for p in material.findall('property'):material.remove(p)
        mesh.prop(material,'diffuseMap','Texture','wheel.dds')
        sections=mesh.sections(mesh.primitives(vertices,np.array([0,1,2])))
        sections['vertices']=legacy_vertices(fmt)
        base='res/vehicles/american/A179_Test/normal/lod0/Chassis'
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(base+'.visual_processed',mesh.xml(visual))
            z.writestr(base+'.primitives_processed',mesh.packed_sections(sections))
            z.writestr('res/wheel.dds',mesh.dds(True))
        return source

    def test_scanner_extracts_new_format_as_supported_rigid_light(self):
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            root=Path(tmp);source=self.fixture(root,b'xyznuviiiwwtb')
            before=source.read_bytes();project=engine.scan(source,root/'work')
            self.assertTrue(project['lights']);self.assertFalse(project['scan_issues'])
            self.assertTrue(all(x['supported'] for x in project['lights']))
            self.assertEqual(project['lights'][0]['anchor'],'W_R0')
            self.assertEqual(source.read_bytes(),before)

    def test_scan_error_distinguishes_found_glow_from_no_glow(self):
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            root=Path(tmp);source=self.fixture(root,b'future_layout')
            with self.assertRaises(ValueError) as error:engine.scan(source,root/'work')
            self.assertIn('已找到 1 组发光材质',str(error.exception))
            self.assertIn('future_layout',str(error.exception))
            self.assertNotIn('没有找到可提取',str(error.exception))


if __name__=='__main__':unittest.main()
