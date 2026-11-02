import copy, json, zipfile
from unittest.mock import patch
from test_light_embedded import EmbeddedProjectTests
from wotcamo import light_merge, light_effects as engine, light_recovery

class MergeTests(EmbeddedProjectTests):
    def packages(self, overlap=False):
        a=copy.deepcopy(self.project);b=copy.deepcopy(self.project)
        for light in a['lights']:light['selected']=False
        for light in b['lights']:light['selected']=False
        a['lights'][0]['selected']=True;b['lights'][0 if overlap else 1]['selected']=True
        a['recipe']['峰值倍率']=2.0;b['recipe']['峰值倍率']=3.0
        for project in (a,b):
            for light in project['lights']:light.pop('配方',None)
        first,_=self.build(a);second,_=self.build(b)
        return first,second

    def test_merge_rebuilds_two_lamps_from_common_source(self):
        first,second=self.packages()
        project,info=light_merge.merge_projects([first,second],self.root/'merge')
        selected=[x for x in project['lights'] if x['selected']]
        self.assertEqual(len(selected),2)
        self.assertEqual([x['配方']['峰值倍率'] for x in selected],[2.0,3.0])
        self.assertEqual(info['shared_original_sha256'],engine.digest(self.source))
        with patch.object(engine,'client_info',return_value={'root':str(self.root/'client')}), patch.object(engine,'compile27',side_effect=lambda s,t,c:t.write_bytes(b'offline')), patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
            target,report,_,_=light_merge.build([first,second],self.root/'client',self.root/'out',self.root/'merge2','combined')
        with zipfile.ZipFile(target) as z:
            manifest=light_recovery.read_manifest(z,light_recovery.manifests(z.namelist())[0])
            self.assertEqual(len(manifest['selected_ids']),2)
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        self.assertEqual(len(report['merge']['inputs']),2)

    def test_merge_rejects_different_recipes_on_same_lamp(self):
        first,second=self.packages(overlap=True)
        with self.assertRaisesRegex(ValueError,'同一灯面'):
            light_merge.merge_projects([first,second],self.root/'merge')

    def test_merge_rejects_no_embedded_project(self):
        first,second=self.packages()
        with patch.object(light_merge.light_embedded,'metadata',return_value=None):
            with self.assertRaisesRegex(ValueError,'没有内嵌'):
                light_merge.merge_projects([first,second],self.root/'merge')

    def test_merge_rejects_different_originals(self):
        first,_=self.packages()
        changed=self.root/'other.wotmod'
        with zipfile.ZipFile(self.source) as src,zipfile.ZipFile(changed,'w',zipfile.ZIP_STORED) as out:
            for name in src.namelist():out.writestr(name,src.read(name))
            out.writestr('res/unrelated.dat',b'different baseline')
        other=engine.scan(changed,self.root/'other_scan')
        other['lights'][0]['selected']=True
        second,_=self.build(other)
        with self.assertRaisesRegex(ValueError,'原始涂装不同'):
            light_merge.merge_projects([first,second],self.root/'mixed')
