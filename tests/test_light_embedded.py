"""Complete engineering snapshots, integrity failure and bounded rebuild size."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from wotcamo import light_assets as mesh, light_effects as engine, light_recovery, light_embedded
from test_light_wheels import ring, fixture_visual


class EmbeddedProjectTests(unittest.TestCase):
    def setUp(self):
        (engine.ROOT/'.cache').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=engine.ROOT/'.cache');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'original.wotmod'
        vertices,indices=ring();visual=fixture_visual(vertices,indices)
        second=copy.deepcopy(visual.find('renderSet'))
        second.find('geometry/vertices').text='second_vertices';second.find('geometry/primitive').text='second_indices'
        for p in second.findall('.//property'):
            if p.text=='diffuseMap':p.find('Texture').text='other.dds'
        visual.append(second)
        sections=mesh.sections(mesh.primitives(vertices,indices.ravel()))
        other=vertices.copy();other[:,0]+=2
        sections.update({'second_'+k:v for k,v in mesh.sections(mesh.primitives(other,indices.ravel())).items()})
        self.visual='res/vehicles/test/TestTank/normal/lod0/chassis.visual_processed'
        coloured=bytearray(mesh.dds(True));coloured[136:140]=b'\x00\xf8\x00\xf8'
        with zipfile.ZipFile(self.source,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.visual,mesh.xml(visual))
            z.writestr(self.visual.replace('.visual_processed','.primitives_processed'),mesh.packed_sections(sections))
            z.writestr('res/wheel.dds',bytes(coloured));z.writestr('res/other.dds',mesh.dds(True))
        self.project=engine.scan(self.source,self.root/'scan')
        self.assertEqual(len(self.project['lights']),2)
        self.project['lights'][0]['selected']=True
        self.project['lights'][1]['selected']=False
        self.project['recipe']['峰值倍率']=2.7
        self.project['lights'][1]['配方']=dict(copy.deepcopy(engine.DEFAULT_RECIPE),峰值倍率=4.3)
        self.project['baseline_user_confirmed']=True

    def build(self,project=None,enabled=None):
        with patch.object(engine,'client_info',return_value={'root':str(self.root/'client')}), \
             patch.object(engine,'compile27',side_effect=lambda s,t,c:t.write_bytes(b'offline only')), \
             patch.object(engine,'audit_package',return_value={'status':'fixture_only'}):
            return engine.build(project or self.project,self.root/'client',self.root/'out','embedded',embed_recoverable=enabled)

    def content(self,path):
        with zipfile.ZipFile(path) as z:
            name=light_recovery.manifests(z.namelist())[0]
            data=json.loads(z.read(name))
            backup=z.read(data['embedded_project']['path']) if 'embedded_project' in data else None
            return name,data,backup

    def altered(self,path,change_meta=None,change_backup=None):
        name,data,backup=self.content(path)
        if change_backup:
            backup=change_backup(backup)
            data['embedded_project'].update(sha256=hashlib.sha256(backup).hexdigest(),bytes=len(backup))
        if change_meta:change_meta(data['embedded_project'])
        output=self.root/'altered.wotmod'
        with zipfile.ZipFile(path) as a,zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as b:
            for n in a.namelist():
                raw=json.dumps(data).encode() if n==name else backup if n.endswith('/'+light_embedded.FILENAME) else a.read(n)
                b.writestr(n,raw)
        return output

    def test_default_contains_verified_snapshot_and_untouched_original_textures(self):
        target,report=self.build();name,data,backup=self.content(target)
        self.assertTrue(report['embedded_project']['enabled'])
        self.assertEqual(hashlib.sha256(backup).hexdigest(),data['embedded_project']['sha256'])
        with zipfile.ZipFile(io.BytesIO(backup)) as z:
            self.assertEqual(set(z.namelist()),light_embedded.ENTRIES)
            self.assertEqual(z.read('source.wotmod'),self.source.read_bytes())
            saved=json.loads(z.read('project.json'))
            self.assertEqual(saved['recipe']['峰值倍率'],2.7)
            self.assertEqual(saved['lights'][1]['配方']['峰值倍率'],4.3)
            self.assertEqual(saved['geometry_sha256'],{x['id']:engine.geometry_digest(x) for x in self.project['lights']})
        with zipfile.ZipFile(target) as z:
            audit=light_embedded.audit(z,name,data)
            self.assertEqual(audit['status'],'passed');self.assertEqual(audit['lights'],2)
            self.assertTrue(all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist()))

    def test_import_prefers_original_groups_choices_and_recipes_over_final_meshes(self):
        target,_=self.build();before=engine.digest(target)
        restored=engine.scan(target,self.root/'restore')
        self.assertTrue(restored['embedded_restore']['restored_completely'])
        self.assertNotIn('recovery',restored)
        self.assertEqual(restored['source_sha256'],engine.digest(self.source))
        self.assertEqual(Path(restored['source']).read_bytes(),self.source.read_bytes())
        self.assertEqual(restored['recipe'],self.project['recipe'])
        for a,b in zip(self.project['lights'],restored['lights']):
            self.assertEqual(a['id'],b['id']);self.assertEqual(a['selected'],b['selected'])
            self.assertEqual(a.get('配方'),b.get('配方'))
            np.testing.assert_array_equal(a['_vertices'],b['_vertices'])
            np.testing.assert_array_equal(a['_indices'],b['_indices'])
        self.assertFalse(restored['baseline_user_confirmed'])
        self.assertTrue(restored['embedded_restore']['historical_baseline_user_confirmed'])
        self.assertEqual(engine.digest(target),before)

    def test_restore_and_regenerate_do_not_nest_previous_finished_packages(self):
        first,_=self.build();restored=engine.scan(first,self.root/'restore1')
        restored['recipe']['峰值倍率']=3.1
        second,_=self.build(restored);_,data,backup=self.content(second)
        with zipfile.ZipFile(io.BytesIO(backup)) as z:self.assertEqual(z.read('source.wotmod'),self.source.read_bytes())
        with zipfile.ZipFile(second) as z:self.assertEqual(len([n for n in z.namelist() if n.endswith('/'+light_embedded.FILENAME)]),1)
        self.assertLess(second.stat().st_size,first.stat().st_size+5000)
        third=engine.scan(second,self.root/'restore2')
        self.assertEqual(third['recipe']['峰值倍率'],3.1)
        self.assertEqual(third['source_sha256'],self.project['source_sha256'])

    def test_toggle_off_writes_no_embedded_snapshot(self):
        target,report=self.build(enabled=False);_,data,backup=self.content(target)
        self.assertFalse(report['embedded_project']['enabled'])
        self.assertNotIn('embedded_project',data);self.assertIsNone(backup)
        with zipfile.ZipFile(target) as z:self.assertFalse(any(n.endswith('.wotlights') for n in z.namelist()))
        recovered=engine.scan(target,self.root/'legacy')
        self.assertIn('recovery',recovered);self.assertNotIn('embedded_restore',recovered)

    def test_legacy_recovery_excludes_verified_old_embedded_snapshot(self):
        target,_=self.build()
        with zipfile.ZipFile(target) as archive:
            manifest=light_recovery.manifests(archive.namelist())[0]
            old=light_recovery.read_manifest(archive,manifest)['embedded_project']['path']
        recovered=light_recovery.recover(target,self.root/'direct_recovery',lambda _: None)
        _, excluded=light_recovery.retained(recovered,[x for x in recovered['lights'] if x.get('selected')])
        self.assertIn(old,excluded)

    def test_choice_survives_standalone_project_save_and_load(self):
        self.project['embed_recoverable']=False
        path=self.root/'saved.wotlights';engine.save_project(self.project,path)
        loaded=engine.load_project(path,self.root/'loaded')
        self.assertFalse(loaded['embed_recoverable'])
        target,report=self.build(loaded)
        self.assertFalse(report['embedded_project']['enabled'])

    def test_corrupt_backup_does_not_silently_downgrade_to_partial_recovery(self):
        target,_=self.build()
        altered=self.altered(target,change_meta=lambda d:d.update(sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'内嵌工程校验失败'):engine.scan(altered,self.root/'restore')

    def test_embedded_reference_cannot_escape_its_maker_folder(self):
        target,_=self.build()
        altered=self.altered(target,change_meta=lambda d:d.update(path='../../private.wotlights'))
        with self.assertRaisesRegex(ValueError,'引用或校验记录无效'):engine.scan(altered,self.root/'restore')

    def test_geometry_mismatch_is_detected_even_when_outer_hash_is_updated(self):
        target,_=self.build()
        def tamper(raw):
            data=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(raw)) as a,zipfile.ZipFile(data,'w') as b:
                for n in a.namelist():
                    content=a.read(n)
                    if n=='project.json':
                        saved=json.loads(content);saved['geometry_sha256']={};content=json.dumps(saved).encode()
                    b.writestr(n,content)
            return data.getvalue()
        altered=self.altered(target,change_backup=tamper)
        with self.assertRaisesRegex(ValueError,'几何校验不一致'):engine.scan(altered,self.root/'restore')

    def test_missing_snapshot_entry_is_rejected(self):
        target,_=self.build()
        def tamper(raw):
            data=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(raw)) as a,zipfile.ZipFile(data,'w') as b:
                for n in a.namelist():
                    if n!='source.wotmod':b.writestr(n,a.read(n))
            return data.getvalue()
        altered=self.altered(target,change_backup=tamper)
        with self.assertRaisesRegex(ValueError,'条目不完整'):engine.scan(altered,self.root/'restore')

    def test_depth_limit_stops_recursive_project_import(self):
        target,_=self.build()
        with self.assertRaisesRegex(ValueError,'嵌套过深'):
            engine.scan(target,self.root/'restore',_embedded_depth=light_embedded.MAX_DEPTH)

    def test_streamed_snapshot_resource_remains_zip32_stored_and_no_duplicates(self):
        target,_=self.build()
        self.assertEqual(engine.check_game_zip(target)['format'],'ZIP32_STORED')
        with zipfile.ZipFile(target) as z:self.assertEqual(len(z.namelist()),len(set(z.namelist())))

    def test_embedding_legacy_recovery_preserves_current_state_without_claiming_lost_original(self):
        legacy,_=self.build(enabled=False)
        partial=engine.scan(legacy,self.root/'partial')
        target,_=self.build(partial,enabled=True)
        restored=engine.scan(target,self.root/'restored')
        self.assertEqual(restored['embedded_restore']['source_kind'],'finished_package_recovery')
        self.assertEqual(restored['source_sha256'],engine.digest(legacy))
        self.assertIn('recovery',restored)
        self.assertEqual([x['id'] for x in partial['lights']],[x['id'] for x in restored['lights']])

    def test_failed_snapshot_creation_does_not_publish_an_installable_package(self):
        with patch.object(engine,'save_project',side_effect=OSError('injected disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):self.build()
        self.assertFalse(list((self.root/'out').rglob('*.wotmod')))

    def test_oversize_streamed_backup_stops_before_target_is_written(self):
        blob=self.root/'backup.bin';blob.write_bytes(b'test')
        target=self.root/'oversize.wotmod'
        with patch.object(zipfile,'ZIP64_LIMIT',100):
            with self.assertRaisesRegex(ValueError,'取消.*嵌入可恢复工程'):
                engine.write_game_archive(self.source,target,added_files={'res/test.wotlights':blob})
        self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
