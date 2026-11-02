"""UML preview regressions use synthetic resources, not installed game assets."""
import copy
import tempfile
import unittest
import zipfile
from pathlib import Path
from wotcamo import light_assets as mesh, light_effects, paint3d, preview3d_assets, uml_preview
from test_light_wheels import ring, fixture_visual


class UMLPreviewTests(unittest.TestCase):
    def setUp(self):
        cache=light_effects.ROOT/'.cache';cache.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=cache);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.package=self.root/'uml.wotmod'
        self.model='vehicles/test/Base_Custom/normal/lod0/'
        profile='<root><models><!--invalid--comment--><skin><enabled>False</enabled>'
        for part in ('chassis','hull','turret','gun'):
            pos='<hullPosition>0 1.25 0</hullPosition>' if part=='chassis' else ''
            profile+=f'<{part}><undamaged>{self.model}{part}.model</undamaged><destroyed>vehicles/test/Base/crash/{part}.model</destroyed>{pos}</{part}>'
        profile+='</skin></models></root>'
        verts,ids=ring()
        with zipfile.ZipFile(self.package,'w') as z:
            z.writestr('res/scripts/client/mods/UMLprofiles/model.xml',profile)
            for part in ('chassis','hull','turret','gun'):
                path=self.model+part
                z.writestr('res/'+path+'.model','<root><nodefullVisual>'+path+'</nodefullVisual></root>')
                visual=fixture_visual(verts,ids)
                if part in ('hull','turret'):
                    joint=copy.deepcopy(visual.find('node'))
                    joint.find('identifier').text='HP_turretJoint' if part=='hull' else 'HP_gunJoint'
                    joint.find('transform/row3').text='0 2 3' if part=='hull' else '0 4 5'
                    visual.find('node').append(joint)
                z.writestr('res/'+path+'.visual_processed',mesh.xml(visual))
                z.writestr('res/'+path+'.primitives_processed',mesh.primitives(verts,ids.ravel()))

    def test_profile_parts_and_joints_assemble_without_flipping(self):
        project=paint3d.project_from_package('test/Base',self.package)
        self.assertEqual(project['vehicle'],'Base_Custom');self.assertEqual(project['base_vehicle'],'Base')
        body=preview3d_assets.make_body(project,None,self.root/'body')
        self.assertEqual(body['offsets']['hull'],[0,1.25,0])
        self.assertEqual(body['offsets']['turret'],[0,2,3])
        self.assertEqual(body['offsets']['gun'],[0,4,5])
        self.assertEqual(set(body['visuals']),{'chassis','hull','turret','gun'})
        self.assertTrue(any('禁用' in w for w in body['warnings']))

    def test_unrelated_vehicle_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'当前所选车型'):
            paint3d.project_from_package('test/Other',self.package)

    def test_ambiguous_profiles_are_rejected(self):
        with zipfile.ZipFile(self.package,'a') as z:
            data=z.read('res/scripts/client/mods/UMLprofiles/model.xml').decode().replace('1.25','2.25')
            z.writestr('res/scripts/client/mods/UMLprofiles/other.xml',data)
        with zipfile.ZipFile(self.package) as z:
            with self.assertRaisesRegex(ValueError,'多套不同'):
                uml_preview.choose(z,'test','Base')
