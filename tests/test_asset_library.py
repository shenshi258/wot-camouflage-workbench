"""Persistent user copies and token-scoped thumbnail APIs; no game resources."""
import base64,hashlib,io,json,tempfile,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from wotcamo import asset_library as library,preview3d


class AssetLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=library.Library(self.root/'library')
        image=Image.new('RGBA',(320,100),(240,10,50,128));image.putpixel((0,0),(0,0,0,0))
        buffer=io.BytesIO();image.save(buffer,format='PNG');self.raw=buffer.getvalue()
    def payload(self,**changes):return dict(name='标志.png',category='标志',image=base64.b64encode(self.raw).decode(),**changes)

    def test_import_preserves_original_and_transparency_with_a_bounded_thumbnail(self):
        source=self.root/'原图.png';source.write_bytes(self.raw)
        row=self.store.import_image(source.read_bytes(),source.name,'标志')['item']
        self.assertEqual(source.read_bytes(),self.raw);self.assertEqual(row['id'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.store.image(row['id'])[0],self.raw)
        thumb,mime=self.store.image(row['id'],True);self.assertEqual(mime,'image/png')
        with Image.open(io.BytesIO(thumb)) as image:
            self.assertLessEqual(max(image.size),160);self.assertEqual(image.mode,'RGBA');self.assertLess(image.getchannel('A').getextrema()[0],128)
        self.assertNotIn(str(self.root),(self.store.asset(row['id'])/'record.json').read_text(encoding='utf-8'))

    def test_duplicate_reopen_and_edited_labels_persist(self):
        row=self.store.import_payload(self.payload())['item']
        self.assertTrue(self.store.import_payload(self.payload())['duplicate'])
        self.store.edit(row['id'],'<标志>','警示线')
        reopened=library.Library(self.store.root).list()
        self.assertEqual(len(reopened['items']),1);self.assertEqual(reopened['items'][0]['name'],'<标志>');self.assertEqual(reopened['items'][0]['category'],'警示线')

    def test_remove_and_restore_keep_a_recoverable_copy(self):
        row=self.store.import_payload(self.payload())['item'];token=self.store.remove(row['id'])
        self.assertEqual(self.store.list()['items'],[])
        self.assertTrue((self.store.root/'回收站'/token/'image.png').is_file())
        restored=self.store.restore(token);self.assertEqual(restored['id'],row['id'])
        self.assertEqual(self.store.image(row['id'])[0],self.raw)
        with self.assertRaises(ValueError):self.store.restore('../../outside')

    def test_invalid_files_and_requests_never_enter_the_library(self):
        for payload in ({'name':'bad','image':'!'},dict(self.payload(),path='C:/Windows'),dict(self.payload(),name=None)):
            with self.assertRaises(ValueError):self.store.import_payload(payload)
        for raw in (b'not an image',b'',b'x'*(library.MAX_BYTES+1)):
            with self.assertRaises(ValueError):self.store.import_image(raw,'bad.png')
        with patch.object(library,'MAX_PIXELS',1),self.assertRaises(ValueError):self.store.import_image(self.raw,'large.png')
        for key in ('../outside','C:/outside','a'*63,'A'*64):
            with self.assertRaises(ValueError):self.store.image(key)
        self.assertEqual(self.store.list()['items'],[])

    def gif(self):
        buffer=io.BytesIO();frames=[]
        for x,colour in ((2,(255,0,0,255)),(12,(0,255,0,255)),(22,(0,0,255,255))):
            frame=Image.new('RGBA',(36,18));frame.paste(colour,(x,4,x+6,10));frames.append(frame)
        frames[0].save(buffer,format='GIF',save_all=True,append_images=frames[1:],duration=[100,300,200],loop=0,disposal=2)
        return buffer.getvalue()

    def test_gif_original_timing_disposal_and_transparency_persist_and_restore(self):
        original=self.gif();source=self.root/'自己的动画.gif';source.write_bytes(original)
        row=self.store.import_file(source,'动画')['item'];self.assertEqual(source.read_bytes(),original)
        self.assertEqual(row['format'],'GIF');self.assertEqual(row['frames'],3)
        self.assertEqual(row['durations_ms'],[100,300,200]);self.assertEqual(row['disposals'],[2,2,2])
        self.assertAlmostEqual(row['duration'],.6)
        self.assertEqual(self.store.image(row['id']),(original,'image/gif'))
        thumb,mime=self.store.image(row['id'],True);self.assertEqual(mime,'image/png')
        with Image.open(io.BytesIO(thumb)) as image:self.assertEqual(image.getpixel((0,0))[3],0)
        listed=library.Library(self.store.root).list()['items'][0]
        self.assertEqual((listed['frames'],listed['duration']),(3,.6))
        token=self.store.remove(row['id']);self.assertEqual(self.store.list()['items'],[])
        self.store.restore(token);self.assertEqual(self.store.image(row['id'])[0],original)

    def test_gif_limits_incomplete_data_and_tampered_timing_are_rejected(self):
        original=self.gif()
        with patch.object(library,'MAX_GIF_FRAMES',2),self.assertRaisesRegex(ValueError,'GIF'):self.store.import_image(original,'large.gif')
        with patch.object(library,'MAX_GIF_TOTAL_PIXELS',100),self.assertRaisesRegex(ValueError,'GIF'):self.store.import_image(original,'large.gif')
        with self.assertRaises(ValueError):self.store.import_image(original[:len(original)//2],'broken.gif')
        self.assertEqual(self.store.list()['items'],[])
        row=self.store.import_image(original,'valid.gif')['item'];path=self.store.asset(row['id'])/'record.json'
        row['durations_ms']=[100,300,100];path.write_text(json.dumps(row),encoding='utf-8')
        self.assertEqual(self.store.list()['issues'],1)

    def test_static_schema1_records_without_animation_fields_remain_compatible(self):
        row=self.store.import_image(self.raw,'old.png')['item']
        self.assertNotIn('frames',row);self.assertNotIn('duration',row)
        reopened=library.Library(self.store.root);self.assertEqual(reopened.record(row['id'])['format'],'PNG')
        self.assertEqual(reopened.image(row['id'])[0],self.raw)

    def test_tampered_content_is_rejected_and_broken_records_are_reported(self):
        row=self.store.import_payload(self.payload())['item'];folder=self.store.asset(row['id'])
        (folder/'image.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.store.image(row['id'])
        (folder/'record.json').write_text('{}',encoding='utf-8')
        result=self.store.list();self.assertEqual(result['items'],[]);self.assertEqual(result['issues'],1)

    def test_standalone_library_needs_no_client_and_api_is_persistent_and_scoped(self):
        with patch.object(preview3d.assets,'save_snapshot') as snapshot:
            session=preview3d.Session(None,None,launch=False,library_only=True,library_root=self.store.root)
            snapshot.assert_not_called()
        base=session.url.replace('library.html','')
        def request(path,data=None,origin=None):
            req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode())
            if origin:req.add_header('Origin',origin)
            return urllib.request.urlopen(req)
        try:
            self.assertIsNone(session.worker)
            with request('library/import',self.payload()) as response:item=json.load(response)['item']
            with request('library/list') as response:self.assertEqual(json.load(response)['items'][0]['id'],item['id'])
            with request('library/image/'+item['id']) as response:self.assertEqual(response.read(),self.raw)
            with request('library/thumb/'+item['id']) as response:self.assertEqual(response.headers['Content-Type'],'image/png')
            animation=dict(name='循环.gif',category='动画',image=base64.b64encode(self.gif()).decode())
            with request('library/import',animation) as response:gif=json.load(response)['item']
            with request('library/image/'+gif['id']) as response:
                self.assertEqual(response.headers['Content-Type'],'image/gif');self.assertEqual(response.read(),self.gif())
            with self.assertRaises(urllib.error.HTTPError):request('library/import',self.payload(),origin='https://example.invalid')
            with self.assertRaises(urllib.error.HTTPError):request('library/action',dict(action='remove',id='../outside'))
            with request('library/action',dict(action='remove',id=item['id'])) as response:token=json.load(response)['trash_id']
            with request('library/action',dict(action='restore',trash_id=token)):pass
        finally:session.close()
        self.assertEqual(len(library.Library(self.store.root).list()['items']),2)

    def test_non_library_preview_does_not_expose_or_mutate_the_store(self):
        with patch.object(preview3d.assets,'save_snapshot'):
            session=preview3d.Session(dict(recipe={},lights=[]),None,launch=False,library_root=self.store.root)
        try:
            base=session.url.replace('index.html','')
            for path,data in [('library/list',None),('library/import',self.payload())]:
                req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode())
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
                self.assertEqual(error.exception.code,403)
        finally:session.close()


if __name__=='__main__':unittest.main()
