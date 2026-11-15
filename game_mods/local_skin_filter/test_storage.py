"""Exercise disk sharing on isolated files, never on the installed game."""
import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path


@unittest.skipUnless(os.name=='nt','NTFS cache utility is Windows-only')
class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name);self.cache=self.root/'res_mods/2.4.1.1/vehicles/_lsf2'
        (self.root/'version.xml').write_text('<root/>')
        (self.root/'paths.xml').write_text('<root><Paths><Path>./res_mods/2.4.1.1</Path></Paths></root>')
        self.report=self.root/'report.json';self.files=[]
        for car in('aaaaaaaaaaaa','bbbbbbbbbbbb'):
            base='vehicles/_lsf2/111111111111/'+car+'/cccccccccccc/'
            relative=base+'dddddddddddddddd/Hull_hd.dds';data=b'full-resolution-resource'*400
            path=self.root/'res_mods/2.4.1.1'/relative;path.parent.mkdir(parents=True);path.write_bytes(data)
            record=dict(schema=3,fingerprint='1'*64,base=base,resources=[dict(destination=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())])
            (path.parent.parent/'ready.json').write_text(json.dumps(record))
            self.files.append(path)

    def tearDown(self):self.temporary.cleanup()

    def run_tool(self,apply=False):
        script=Path(__file__).with_name('optimize_cache.ps1')
        args=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-GameRoot',str(self.root),'-ReportPath',str(self.report)]
        if apply:args+=['-Apply']
        process=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45,creationflags=0x08000000)
        self.assertEqual(process.returncode,0,process.stdout.decode('utf-8','replace'))
        return json.loads(self.report.read_text('utf-8-sig'))

    def test_preview_leaves_resources_separate(self):
        report=self.run_tool();self.assertEqual(report['estimated_releasable_bytes'],self.files[0].stat().st_size)
        self.assertEqual(report['linked_files'],0);self.assertNotEqual(self.files[0].stat().st_ino,self.files[1].stat().st_ino)

    def test_sharing_preserves_bytes_and_second_run_is_idempotent(self):
        before=self.files[0].read_bytes();report=self.run_tool(True)
        self.assertEqual(report['linked_files'],1);self.assertEqual(report['released_file_bytes'],len(before))
        self.assertEqual(self.files[0].stat().st_ino,self.files[1].stat().st_ino)
        for path in self.files:self.assertEqual(path.read_bytes(),before)
        again=self.run_tool(True);self.assertEqual(again['released_file_bytes'],0);self.assertEqual(again['already_shared_files'],1)

    def test_corrupt_content_is_never_shared(self):
        self.files[1].write_bytes(b'x'*self.files[1].stat().st_size)
        report=self.run_tool(True);self.assertEqual(report['linked_files'],0);self.assertTrue(report['skipped'])
        self.assertNotEqual(self.files[0].stat().st_ino,self.files[1].stat().st_ino)

    def test_outside_path_is_rejected_and_original_is_preserved(self):
        marker=self.files[1].parent.parent/'ready.json';record=json.loads(marker.read_text())
        original=self.root/'outside.dds';original.write_bytes(self.files[0].read_bytes())
        record['resources'][0]['destination']='../outside.dds';marker.write_text(json.dumps(record))
        report=self.run_tool(True);self.assertEqual(report['linked_files'],0);self.assertTrue(report['skipped'])
        self.assertEqual(original.read_bytes(),self.files[0].read_bytes())
