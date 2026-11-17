"""Only new missing dependencies block publication of ordinary lamp rebuilds."""
import json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from wotcamo import light_assets as mesh,light_effects as engine
import test_light_build_review as fixtures
import test_light_wheels as geometry


class DependencyGateTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.client=self.root/'client';(self.client/'res').mkdir(parents=True)
        (self.client/'paths.xml').write_text('<root/>')
        for branch in('10','11'):
            path=self.client/('res/shaders/custom/emissive_playground.'+branch+'.dx11.fxo')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture dependency only')

    def build(self,project):
        with patch.object(engine,'client_info',return_value={'root':str(self.client)}),patch.object(engine,'compile27',side_effect=lambda source,target,client:target.write_bytes(b'fixture bytecode')):
            return engine.build(project,self.client,self.root/'out','dependency gate',embed_recoverable=False)

    def test_new_visual_missing_texture_keeps_failed_build_and_record_without_installable_suffix(self):
        project=fixtures.LightBuildReviewTests().project(self.root);write=engine.write_game_archive
        def omit_new_texture(source,target,changes=None,added=None,excluded=None,added_files=None):
            added=dict(added);missing=next(n for n in added if '/emission_'in n and n.endswith('.dds'))
            del added[missing]
            return write(source,target,changes,added,excluded,added_files)
        with patch.object(engine,'write_game_archive',side_effect=omit_new_texture):
            with self.assertRaisesRegex(ValueError,'新增或修改的灯效资源缺少依赖'):self.build(project)
        self.assertFalse(list((self.root/'out').rglob('*.wotmod')))
        stages=list((self.root/'out').rglob('*.building'));self.assertEqual(len(stages),1)
        record=json.loads(stages[0].with_name('验证记录.json').read_text('utf-8'))
        self.assertEqual(record['build_status'],'failed');self.assertEqual(record['file_validation']['status'],'failed')
        self.assertEqual(record['offline_validation']['status'],'failed');self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested')
        self.assertEqual(record['artifact']['path'],str(stages[0]));self.assertEqual(record['artifact']['sha256'],engine.digest(stages[0]))
        self.assertTrue(record['file_validation']['introduced_missing_dependencies'])
        self.assertTrue(all('/emission_'in name for name in record['file_validation']['introduced_missing_dependencies']))
        self.assertEqual(engine.digest(project['source']),project['source_sha256'])

    def test_original_missing_reference_is_reported_separately_and_does_not_block_rebuild(self):
        project=fixtures.LightBuildReviewTests().project(self.root);source=Path(project['source'])
        vertices,ids=geometry.ring();visual=ET.fromstring(mesh.effect_visual('legacy','external/legacy_missing.dds',vertices,len(ids),'legacy/'))
        with zipfile.ZipFile(source,'a',zipfile.ZIP_STORED)as z:
            z.writestr('res/unrelated/legacy.visual_processed',mesh.xml(visual))
            z.writestr('res/unrelated/legacy.primitives_processed',mesh.primitives(vertices,ids.ravel()))
        project['source_sha256']=engine.digest(source)
        target,record=self.build(project);audit=record['file_validation']
        self.assertTrue(target.is_file());self.assertEqual(audit['introduced_missing_dependencies'],[])
        self.assertIn('external/legacy_missing.dds',audit['preexisting_missing_dependencies'])
        self.assertEqual(audit['missing_dependency_sources']['external/legacy_missing.dds'],['res/unrelated/legacy.visual_processed'])
        self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested')

    def model_audit(self,before,after,extra=None,excluded=None):
        source=self.root/'source.wotmod';target=self.root/'candidate.building'
        with zipfile.ZipFile(source,'w',zipfile.ZIP_STORED)as z:
            z.writestr('res/old.model',before)
            for name,data in(extra or {}).items():z.writestr(name,data)
        engine.write_game_archive(source,target,changes={'res/old.model':after},excluded=excluded)
        return engine.audit_package(target,source,{'res/old.model'},self.client,excluded)

    def test_modified_resource_retaining_same_legacy_reference_is_not_new(self):
        audit=self.model_audit(b'<root><nodelessVisual>external/old</nodelessVisual></root>',
                              b'<root><nodelessVisual>external/old</nodelessVisual><extent>1</extent></root>')
        self.assertEqual(audit['introduced_missing_dependencies'],[])
        self.assertEqual(audit['preexisting_missing_dependencies'],['external/old.primitives_processed','external/old.visual_processed'])

    def test_modified_resource_new_reference_is_an_introduced_omission(self):
        audit=self.model_audit(b'<root><nodelessVisual>external/old</nodelessVisual></root>',
                              b'<root><nodelessVisual>external/new</nodelessVisual></root>')
        self.assertEqual(audit['preexisting_missing_dependencies'],[])
        self.assertEqual(audit['introduced_missing_dependencies'],['external/new.primitives_processed','external/new.visual_processed'])

    def test_removed_original_dependency_is_not_misclassified_as_a_legacy_omission(self):
        model=b'<root><nodelessVisual>external/old</nodelessVisual></root>'
        audit=self.model_audit(model,model,{'res/external/old.primitives_processed':b'original geometry'},
                              {'res/external/old.primitives_processed'})
        self.assertEqual(audit['introduced_missing_dependencies'],['external/old.primitives_processed'])
        self.assertEqual(audit['preexisting_missing_dependencies'],['external/old.visual_processed'])


if __name__=='__main__':unittest.main()
