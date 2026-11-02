import io, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from wotcamo import dds, compose, light_support, modpack, models, light_effects, wotdata, pipeline
from wotcamo.common import write_json
from wotcamo.prompt import Recipe

class AuditRepairs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_dxt1_preserves_transparent_pixels_and_opaque_pixels(self):
        a=np.full((32,32,4),255,dtype=np.uint8);a[:16,:,3]=0
        buf=io.BytesIO();Image.fromarray(a).save(buf,format='DDS',pixel_format='DXT1')
        ref=buf.getvalue();out=dds.encode_like(dds.decode(ref),ref)
        self.assertTrue(np.array_equal(np.asarray(dds.decode(ref))[...,3],np.asarray(dds.decode(out))[...,3]))
        self.assertEqual(dds.inspect(ref),dds.inspect(out))

    def test_targeted_decal_only_on_selected_texture_and_preserves_alpha(self):
        Image.new('RGBA',(16,16),'red').save(self.root/'d.png')
        a=np.full((64,64,4),255,dtype=np.uint8);a[:8,:,3]=0
        recipe=Recipe(pattern='solid',wear=0,base_color='#808080',decals=['d.png'],decal_placements=[{'file':'d.png','texture':'hull','x':.5,'y':.5,'scale':.5}])
        hull,_=compose.compose_am(Image.fromarray(a),None,recipe,self.root,'hull_AM.dds')
        turret,_=compose.compose_am(Image.fromarray(a),None,recipe,self.root,'turret_AM.dds')
        h,t=np.asarray(hull),np.asarray(turret)
        self.assertGreater(int((h[...,0]>200).sum()),0);self.assertEqual(int((t[...,0]>200).sum()),0)
        np.testing.assert_array_equal(h[...,3],a[...,3]);np.testing.assert_array_equal(t[...,3],a[...,3])

    def test_mount_false_is_not_package(self):
        (self.root/'version.xml').write_text('<root><version>2.4</version></root>')
        (self.root/'paths.xml').write_text('<root><Path mask="false">res_mods/2.4.1</Path><Path mask="*.wotmod">mods/2.4.1</Path></root>')
        self.assertEqual(light_support.client_layout(self.root)['res_mods'],self.root/'res_mods/2.4.1')

    def test_rollback_rejects_other_client_without_writing(self):
        root=self.root;game=root/'gameA';other=root/'gameB';target=game/'res_mods/2.4.1'
        f=target/'vehicles/test/a.dds';f.parent.mkdir(parents=True);f.write_bytes(b'current')
        backup=root/'backups/test';backup.mkdir(parents=True)
        write_json(backup/'manifest.json',{'target':str(target),'version':'2.4.1','state':'installed','files':[{'path':'vehicles/test/a.dds','existed':False,'installed_sha256':modpack.digest(b'current'),'original_sha256':None}]})
        with patch.object(modpack,'ROOT',root):
            with self.assertRaisesRegex(ValueError,'其他客户端'):modpack.rollback(backup,wot_root=other)
        self.assertEqual(f.read_bytes(),b'current')

    def test_addon_is_installed_in_blender_scripts(self):
        addon=self.root/'tools/wot_toolkit';addon.mkdir(parents=True);(addon/'__init__.py').write_text('x=1')
        with patch.object(models,'ROOT',self.root):
            target=models.ensure_addon()
            self.assertEqual((target/'__init__.py').read_text(),'x=1')
            self.assertEqual(models.ensure_addon(),target)

    def test_sensitive_error_keeps_safe_marker_but_not_secret(self):
        lines=['[2026-10-28 10:00:00] [ERROR] token=secret Compound building failed', ' hidden continuation', '[2026-10-28 10:00:01] next']
        result=light_support.redacted_lines(lines)
        self.assertIn('Compound building failed',result[0]);self.assertNotIn('secret',str(result));self.assertNotIn('hidden continuation',str(result))

    def test_python27_compile_unicode_paths_if_available(self):
        client=Path('D:/wot/World_of_Tanks_EU')
        if not (client/'win64/python27.dll').is_file():self.skipTest('未安装对应 Python 2 DLL')
        source=self.root/'脚本.py';target=self.root/'脚本.pyc'
        source.write_text('# -*- coding: utf-8 -*-\nanswer = 42\n',encoding='utf-8')
        light_effects.compile27(source,target,client)
        self.assertEqual(target.read_bytes()[:4],b'\x03\xf3\x0d\x0a')
        source.write_text('if (\n',encoding='ascii')
        with self.assertRaisesRegex(ValueError,'编译失败'):light_effects.compile27(source,self.root/'bad.pyc',client)

    def test_index_reports_nonstandard_directories_without_assuming_vehicle(self):
        game=self.root/'game';pkg=game/'res/packages';pkg.mkdir(parents=True)
        (game/'paths.xml').write_text('<root><Path>res_mods/2.4.1</Path></root>')
        with zipfile.ZipFile(pkg/'a.pkg','w') as z:
            z.writestr('vehicles/russian/R45_IS-7/a.model','x')
            z.writestr('vehicles/russian/T-62A/a.model','x')
        logs=[];result=wotdata.index(game,self.root/'index.json',logs.append)
        self.assertIn('russian/R45_IS-7',result);self.assertTrue(any('T-62A' in s for s in logs))

    def test_synthetic_end_to_end_preserves_dxt1_alpha_and_targeted_decal(self):
        game=self.root/'game';pkg=game/'res/packages';pkg.mkdir(parents=True)
        (game/'paths.xml').write_text('<root><Path>res_mods/2.4.1</Path></root>')
        pixels=np.full((64,64,4),255,dtype=np.uint8);pixels[:16,:,3]=0
        b=io.BytesIO();Image.fromarray(pixels).save(b,format='DDS',pixel_format='DXT1');original=b.getvalue()
        rel='vehicles/russian/R45_IS-7/normal/lod0/'
        with zipfile.ZipFile(pkg/'vehicles.pkg','w') as z:
            z.writestr(rel+'hull_AM.dds',original);z.writestr(rel+'turret_AM.dds',original)
        cfg={'wot_root':str(game),'index_file':str(self.root/'data/index.json'),'result_dir':str(self.root/'result')}
        wotdata.index(game,cfg['index_file'],lambda _:None)
        mat=self.root/'mat';mat.mkdir();Image.new('RGBA',(16,16),(255,0,0,255)).save(mat/'d.png')
        recipe=Recipe(pattern='solid',wear=0,base_color='#808080',decals=['d.png'],decal_placements=[{'file':'d.png','texture':'hull','x':.5,'y':.5,'scale':.5}])
        recipe_path=self.root/'recipe.json';write_json(recipe_path,recipe.to_dict())
        out=pipeline.build('russian/R45_IS-7',mat,'','demo',cfg,do_pack=True,recipe_file=recipe_path,log=lambda _:None)
        report=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested')
        result=pipeline.verify(out,cfg,lambda _:None);self.assertEqual(result['packs'],1)
        hull=np.asarray(dds.decode((out/'res'/rel/'hull_AM.dds').read_bytes()))
        turret=np.asarray(dds.decode((out/'res'/rel/'turret_AM.dds').read_bytes()))
        self.assertTrue(np.array_equal(hull[...,3],np.asarray(dds.decode(original))[...,3]))
        self.assertTrue(np.array_equal(turret[...,3],np.asarray(dds.decode(original))[...,3]))
        self.assertGreater(int(hull[32,32,0]),int(turret[32,32,0])+50)
