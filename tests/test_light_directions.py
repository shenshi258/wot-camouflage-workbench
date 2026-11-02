import copy,json,tempfile,unittest,zipfile
from pathlib import Path
import numpy as np
from wotcamo import light_recipe as recipe,light_assets as mesh,light_effects as engine,light_delivery

class LightDirectionTests(unittest.TestCase):
    def setUp(self):
        self.v=np.array([[-1,-1,0,0,0,1,0,0],[1,-1,0,0,0,1,1,0],[1,1,0,0,0,1,1,1],[-1,1,0,0,0,1,0,1]],float)
        self.ids=np.array([0,1,2,0,2,3]);self.identity=np.eye(4)
    def test_new_directions_use_unit_vectors_and_reverse_propagation(self):
        for name,vector in recipe.FLOW_VECTORS.items():
            self.assertAlmostEqual(np.linalg.norm(vector),1)
            raw=copy.deepcopy(engine.DEFAULT_RECIPE);raw['流水方向']=name;c=recipe.validate_config(raw)
            t=np.array(vector)*.1;actual=recipe.spatial_offset(t,[0,0,0],c)
            self.assertAlmostEqual(actual,(-.1*c['delay'])%c['period'])
        self.assertEqual(recipe.FLOW_VECTORS['向上'],(0,1,0));self.assertEqual(recipe.FLOW_VECTORS['偏右下'],(2**-.5,-2**-.5,0))
    def test_every_direction_subdivides_the_relevant_axis_and_preserves_area_uvs(self):
        original=mesh.area(self.v,self.ids)
        for name,vector in recipe.FLOW_VECTORS.items():
            bands=mesh.split_for_direction(self.v,self.ids,name,self.identity)
            self.assertGreater(len(bands),5)
            self.assertAlmostEqual(sum(mesh.area(v,i) for v,i,c in bands),original,places=8)
            for vertices,ids,coordinate in bands:
                self.assertTrue(np.allclose(vertices[:,6:8],(vertices[:,:2]+1)/2))
                point=mesh.flow_phase_point(vertices,coordinate,name,self.identity)
                self.assertAlmostEqual(float(point@vector),coordinate,places=8)
    def test_anchor_transform_is_applied_to_direction_projection(self):
        angle=np.pi/2;m=np.eye(4);m[0,0]=m[1,1]=0;m[0,1]=1;m[1,0]=-1
        bands=mesh.split_for_direction(self.v,self.ids,'向上',m)
        for vertices,ids,coordinate in bands:
            projected=(np.c_[vertices[:,:3],np.ones(len(vertices))]@m)[:,1]
            self.assertLessEqual(np.ptp(projected),.200001)
    def test_outer_zip_preserves_exact_installable_package_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'lights.wotmod'
            with zipfile.ZipFile(target,'w',zipfile.ZIP_STORED) as z:z.writestr('res/example',b'unchanged')
            report=dict(artifact=dict(sha256=engine.digest(target)),embedded_project=dict(enabled=True))
            (root/'验证记录.json').write_text(json.dumps(report));(root/'使用说明.txt').write_text('test')
            result=light_delivery.bundle(target,report)
            with zipfile.ZipFile(result['path']) as z:self.assertEqual(z.read(target.name),target.read_bytes())
            self.assertTrue(result['embedded_editable_project'])

class LightDirectionUITests(unittest.TestCase):
    def setUp(self):
        from wotcamo.light_gui import LightMaker
        self.app=LightMaker();self.app.withdraw();self.app.update()
    def tearDown(self):self.app.destroy()
    def test_direction_buttons_are_light_flow_choices(self):
        for direction,button in self.app.direction_buttons:
            button.invoke();self.assertEqual(self.app.read_form()['流水方向'],direction)
        self.assertEqual({name for name,b in self.app.direction_buttons},set(recipe.FLOW_VECTORS))
        self.assertTrue(self.app.auto_bundle.get());self.assertTrue(self.app.embed_check.winfo_exists())

if __name__=='__main__':unittest.main()
