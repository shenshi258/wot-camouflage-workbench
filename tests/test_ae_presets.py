"""Preset portability, damaged-import isolation and vehicle-specific state retention."""
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from wotcamo import ae_effects as ae, ae_presets as presets


class AEPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        frames=[Image.new('RGBA',(24,12),(20*i,100,200,120)) for i in (1,2,3)]
        self.clip=ae.pack_frames(frames,self.root/'atlas.png')
        self.values=ae.config(dict(fps=12,width=3.5,angle=32,brightness=1.8,blend='alpha',x=12,part='gun'))
        self.data,self.payload=presets.encode('蓝色流星','用于不同车型',self.clip,self.values)
        self.path=presets.store(self.data,self.payload,self.root/'library')
    def tearDown(self):self.temp.cleanup()

    def rewrite(self,data=None,atlas=None,extra=None):
        result=io.BytesIO()
        with zipfile.ZipFile(result,'w') as z:
            z.writestr('preset.json',json.dumps(data or self.data))
            z.writestr('atlas.png',atlas if atlas is not None else Path(self.clip['atlas']).read_bytes())
            if extra:z.writestr(*extra)
        self.path.write_bytes(result.getvalue())

    def test_portable_asset_survives_original_removal_without_vehicle_data(self):
        expected=Image.open(self.clip['atlas']).copy();Path(self.clip['atlas']).unlink()
        data,clip=presets.load(self.path,self.root/'cache')
        self.assertTrue(np.array_equal(np.asarray(expected),np.asarray(Image.open(clip['atlas']))))
        self.assertEqual(clip['rects'],self.clip['rects']);self.assertEqual(data['config']['fps'],12)
        self.assertEqual(data['name'],'蓝色流星')
        with zipfile.ZipFile(self.path) as z:
            self.assertEqual(set(z.namelist()),{'preset.json','atlas.png'})
            self.assertNotIn('source',z.read('preset.json').decode())
        self.assertEqual(set(data['config']),set(presets.SETTINGS))

    def test_apply_retains_vehicle_mode_joint_position_and_mirror(self):
        for placement,mirror in [('plane',True),('surface',False),('surface_glow',False)]:
            current=ae.config(dict(placement=placement,mirror=mirror,part='turret',x=-2,y=.6,z=1))
            actual=presets.apply_settings(current,self.data['config'])
            for key in ('placement','mirror','part','x','y','z'):self.assertEqual(actual[key],current[key])
            for key in presets.SETTINGS:
                self.assertEqual(actual[key],current[key] if key=='plane' and placement!='plane' else self.values[key])

    def test_overwrite_keeps_backup_and_scan_ignores_backups(self):
        original=self.path.read_bytes()
        data,payload=presets.encode('蓝色流星','新版',self.clip,dict(self.values,fps=30))
        presets.store(data,payload,self.root/'library')
        self.assertEqual(self.path.with_suffix('.aepreset.bak').read_bytes(),original)
        records,issues=presets.scan(self.root/'library')
        self.assertFalse(issues);self.assertEqual(len(records),1);self.assertEqual(records[0]['config']['fps'],30)
        self.assertEqual(presets.library_file(' BLUE ',self.root),presets.library_file('blue',self.root))

    def test_invalid_asset_hash_is_rejected_before_cache_write(self):
        self.rewrite(atlas=b'broken')
        with self.assertRaisesRegex(ValueError,'哈希'):presets.load(self.path,self.root/'cache')
        self.assertFalse((self.root/'cache').exists())

    def test_fixed_names_reject_extra_entries_and_vehicle_packages(self):
        for extra in [('../outside.txt','unsafe'),('source.wotmod','vehicle'),('atlas.png','duplicate')]:
            self.rewrite(extra=extra)
            with self.assertRaises(ValueError):presets.read(self.path)

    def test_invalid_metadata_reports_file_and_preserves_original(self):
        mutations=[('schema',2),('name',''),('config',dict(self.data['config'],part='gun')),
                   ('config',dict(self.data['config'],fps=float('nan')))]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                data=copy.deepcopy(self.data);data[key]=value;self.rewrite(data)
                records,issues=presets.scan(self.root/'library')
                self.assertFalse(records);self.assertEqual(len(issues),1);self.assertTrue(self.path.exists())
        for field,value in [('frames',0),('size',[100000,100000]),('rects',[[0,0,2,1]]*3)]:
            data=copy.deepcopy(self.data);data['clip'][field]=value;self.rewrite(data)
            with self.assertRaises(ValueError):presets.read(self.path)

    def test_import_size_limits_are_checked_before_content_is_read(self):
        with patch.object(presets,'MAX_ARCHIVE',1):
            with self.assertRaisesRegex(ValueError,'过大'):presets.read(self.path)

    def test_earlier_presets_load_with_neutral_crop_and_axis_defaults(self):
        data=copy.deepcopy(self.data);data['config']={key:data['config'][key] for key in presets.BASE_SETTINGS}
        self.rewrite(data)
        loaded,clip=presets.load(self.path,self.root/'legacy')
        self.assertEqual(loaded['config']['uv_scale_x'],1);self.assertEqual(loaded['config']['crop_left'],0)
        values=dict(self.values,uv_scale_x=2,uv_scale_y=.5,crop_top=20)
        current,payload=presets.encode('新裁剪','',self.clip,values)
        path=presets.store(current,payload,self.root/'new');loaded,clip=presets.load(path,self.root/'new_cache')
        self.assertEqual(loaded['config']['crop_top'],20);self.assertEqual(loaded['config']['uv_scale_y'],.5)

    def test_atlas_format_dimensions_and_valid_pixels_are_checked(self):
        for content in (b'not an image',self.image_bytes((1,1))):
            data=copy.deepcopy(self.data)
            data['clip']['atlas_sha256']=presets.hashlib.sha256(content).hexdigest()
            self.rewrite(data,content)
            with self.assertRaises((ValueError,OSError)):presets.load(self.path,self.root/'cache')

    @staticmethod
    def image_bytes(size):
        output=io.BytesIO();Image.new('RGBA',size).save(output,format='PNG');return output.getvalue()


class AEPresetGUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from wotcamo.ae_gui import AEImporter
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.library=patch.object(presets,'LIBRARY_PATH',self.root/'library');self.library.start()
        try:self.app=AEImporter();self.app.geometry('1020x700');self.app.update()
        except tk.TclError as error:self.library.stop();self.temp.cleanup();self.skipTest(str(error))
    def tearDown(self):
        if hasattr(self,'app'):self.app.close()
        self.library.stop();self.temp.cleanup()

    def test_empty_library_and_management_do_not_create_sample_assets(self):
        self.assertTrue(self.app.preset_apply.instate(['disabled']))
        self.assertIn('还没有',self.app.preset_note.get())
        self.app.manage_presets();self.app.update()
        import tkinter as tk
        dialog=next(w for w in self.app.winfo_children() if isinstance(w,tk.Toplevel))
        self.assertTrue(dialog.winfo_ismapped());dialog.destroy()
        self.assertFalse(presets.LIBRARY_PATH.exists())

    def test_loaded_preset_updates_controls_retains_project_and_refreshes_preview(self):
        clip=ae.pack_frames([Image.new('RGBA',(32,16),(20,100,255,100))],self.root/'atlas.png')
        data,payload=presets.encode('测试流星','三帧素材',clip,ae.config(dict(fps=17,width=4,blend='add')))
        path=presets.store(data,payload)
        self.app.refresh_presets('测试流星');self.assertFalse(self.app.preset_apply.instate(['disabled']))
        self.app.placement.set('贴面发光');self.app.part.set('炮塔');self.app.values['x'].set('-3')
        project=dict(ae_selection=dict(groups=[dict(triangles=[3])]))
        self.app.project=project;self.app.source.set('原始涂装.wotmod');self.app.baseline.set(True)
        with patch.object(self.app,'changed') as changed:
            self.app.accept_preset(presets.load(path,self.root/'cache'))
        self.assertIs(self.app.project,project);self.assertEqual(self.app.source.get(),'原始涂装.wotmod')
        self.assertTrue(self.app.baseline.get());self.assertEqual(self.app.placement.get(),'贴面发光')
        self.assertEqual(self.app.part.get(),'炮塔');self.assertEqual(self.app.values['x'].get(),'-3')
        self.assertEqual(self.app.collect()['fps'],17);self.assertEqual(self.app.collect()['width'],4)
        self.assertEqual(self.app.clip['atlas_sha256'],clip['atlas_sha256']);changed.assert_called()

    def test_preset_controls_and_export_remain_visible_at_compact_size(self):
        for widget in (self.app.preset_combo,self.app.preset_apply,self.app.export_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreater(widget.winfo_height(),20)
            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),self.app.winfo_rooty()+self.app.winfo_height())


if __name__=='__main__':unittest.main()
