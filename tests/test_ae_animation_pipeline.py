"""Editable nodes, material-library stills and the exact exported atlas."""
import copy,hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from PIL import Image
from wotcamo import ae_effects as ae,ae_media,ae_presets,preview3d


class AnimationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.source=self.root/'original.wotmod'
        with zipfile.ZipFile(self.source,'w') as z:z.writestr('res/vehicles/german/G197_Pz_Kpfw_Neu/test.dds',b'original')
        self.project=ae.source_project(self.source,self.root/'source');self.project['baseline_user_confirmed']=True
        self.clip=ae.pack_frames([Image.new('RGBA',(16,8),(220,30,80,180))],self.root/'input.png')
        self.values=ae.config(dict(fps=8,animation=dict(duration=1,canvas_scale=2,nodes=[dict(time=0,x=-15),dict(time=1,x=15,rotation=45,scale=.7,opacity=20)])))

    def test_still_images_accept_opaque_pixels_and_preserve_input(self):
        for extension,kind in (('png','PNG'),('jpg','JPEG'),('webp','WEBP')):
            path=self.root/('标志.'+extension);Image.new('RGB',(48,24),(200,80,20)).save(path,format=kind);before=path.read_bytes()
            clip=ae_media.import_picture(path,self.root/(extension+'.png'))
            self.assertEqual(clip['frames'],1);self.assertEqual(clip['frame_size'],[48,24]);self.assertEqual(path.read_bytes(),before)
            self.assertEqual(clip['import_info']['kind'],'image');ae.validate_clip(clip)

    def test_nodes_survive_settings_project_and_preset_without_changing_source(self):
        values=ae.decode_settings(ae.encode_settings(self.values));self.assertEqual(values,self.values)
        saved=self.root/'edit.aefx';ae.save_project(saved,self.project,self.clip,values)
        data,payload=ae_presets.encode('节点','',self.clip,values);preset=self.root/'nodes.aepreset';preset.write_bytes(payload)
        _,restored=ae_presets.load(preset,self.root/'preset');self.assertEqual(data['config']['animation'],values['animation'])
        _,clip,c=ae.load_project(saved,self.root/'reopened');self.assertEqual(c['animation'],values['animation']);self.assertEqual(clip['frames'],1)
        self.assertEqual(clip['atlas_sha256'],restored['atlas_sha256'])

    def test_prepared_atlas_is_cached_and_source_is_never_rewritten(self):
        before=Path(self.clip['atlas']).read_bytes();original=copy.deepcopy(self.clip)
        prepared=ae.playback_clip(self.clip,self.values,self.root/'cache');timestamp=Path(prepared['atlas']).stat().st_mtime_ns
        reused=ae.playback_clip(self.clip,self.values,self.root/'cache')
        self.assertEqual(reused,prepared);self.assertEqual(Path(reused['atlas']).stat().st_mtime_ns,timestamp)
        self.assertEqual(prepared['frames'],8);self.assertEqual(self.clip,original);self.assertEqual(Path(self.clip['atlas']).read_bytes(),before)
        changed=copy.deepcopy(self.values);changed['animation']['nodes'][1]['x']=25
        self.assertNotEqual(ae.playback_clip(self.clip,changed,self.root/'cache')['atlas_sha256'],prepared['atlas_sha256'])
        self.assertIs(ae.playback_clip(prepared,self.values,self.root/'cache'),prepared)

    def test_empty_node_settings_keep_original_gif_timing_and_bytes(self):
        self.assertIs(ae.playback_clip(self.clip,dict(fps=17),self.root/'none'),self.clip)
        self.assertFalse((self.root/'none').exists())
        first=ae.config({});second=ae.config({});first['animation']['nodes'].append(dict(time=0))
        self.assertEqual(second['animation']['nodes'],[])

    def test_shared_atlas_with_different_frame_order_or_aspect_never_uses_stale_cache(self):
        clip=ae.pack_frames([Image.new('RGBA',(16,8),(255,0,0,128)),Image.new('RGBA',(16,8),(0,0,255,128))],self.root/'two.png')
        normal=ae.playback_clip(clip,self.values,self.root/'shared')
        reversed_clip=copy.deepcopy(clip);reversed_clip['rects'].reverse();ae.validate_clip(reversed_clip)
        reversed_result=ae.playback_clip(reversed_clip,self.values,self.root/'shared')
        fresh=ae.playback_clip(reversed_clip,self.values,self.root/'fresh')
        self.assertEqual(reversed_result['atlas_sha256'],fresh['atlas_sha256'])
        self.assertNotEqual(reversed_result['atlas_sha256'],normal['atlas_sha256'])
        aspect=copy.deepcopy(clip);aspect['frame_size']=[16,16]
        changed=ae.playback_clip(aspect,self.values,self.root/'shared')
        self.assertEqual(changed['frame_size'],[32,32]);self.assertNotEqual(changed['atlas'],normal['atlas'])

    def test_preview_session_uses_baked_timing_and_pixels(self):
        prepared=ae.playback_clip(self.clip,self.values,self.root/'expected')
        session=preview3d.Session(None,None,launch=False,library_only=True,effect=(self.clip,self.values))
        self.addCleanup(session.close)
        self.assertEqual(session.effect['frames'],8);self.assertEqual(session.effect['period'],1)
        self.assertEqual(session.effect['atlas_sha256'],prepared['atlas_sha256'])
        actual=session.folder/('ae_atlas_'+prepared['atlas_sha256']+'.png')
        self.assertEqual(actual.read_bytes(),Path(prepared['atlas']).read_bytes())

    def test_final_game_archive_contains_the_prepared_pixels_and_node_settings(self):
        client=self.root/'client';(client/'res/packages').mkdir(parents=True)
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w') as z:z.writestr('effect',b"('SRCALPHA', 5) ('ONE', 2) ('INVSRCALPHA', 6)")
        with zipfile.ZipFile(client/'res/packages/shaders.pkg','w') as z:
            for branch in ('10','11'):z.writestr('shaders/custom/emissive_playground.'+branch+'.dx11.fxo',payload.getvalue())
        def compile_stub(source,target,client):Path(target).write_bytes(b'not-native-bytecode')
        expected=ae.playback_clip(self.clip,self.values,self.root/'reference')
        with patch.object(ae.engine,'client_info',return_value=dict(kind='synthetic')),patch.object(ae.engine,'compile27',side_effect=compile_stub),patch.object(ae.engine,'audit_package',return_value=dict(missing_dependencies=[])):
            target,report=ae.build(self.project,self.clip,self.values,str(client),self.root/'export','节点')
        with zipfile.ZipFile(target) as z:
            manifest=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/manifest.json'))))
            self.assertEqual(manifest['config']['animation'],self.values['animation']);self.assertEqual(manifest['clip']['frames'],8)
            with Image.open(io.BytesIO(z.read(next(n for n in z.namelist() if n.endswith('/atlas.dds'))))) as actual,Image.open(expected['atlas']) as image:
                self.assertEqual(actual.convert('RGBA').tobytes(),image.convert('RGBA').tobytes())
            sequence=ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('/effect_0.seq'))))
            self.assertEqual(float(sequence.findtext('duration')),1)
            self.assertEqual(z.read('res/vehicles/german/G197_Pz_Kpfw_Neu/test.dds'),b'original')
        self.assertEqual(report['whole_vehicle_loading']['status'],'not_tested');self.assertFalse(report['in_game_tested'])

    def test_frame_limit_is_explicit_and_does_not_create_partial_cache(self):
        values=copy.deepcopy(self.values);values['animation']['duration']=60
        with self.assertRaisesRegex(ValueError,'128'):ae.playback_clip(self.clip,values,self.root/'large')
        self.assertFalse(list((self.root/'large').glob('*.png')))
