import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from wotcamo import light_effects as engine, light_support as support


class LightSupportTests(unittest.TestCase):
    def setUp(self):
        cache=engine.ROOT/'.cache';cache.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=cache);self.base=Path(self.tmp.name)
        self.root=self.base/'client';self.root.mkdir()
        (self.root/'version.xml').write_text('<root><version>v.2.4.1.0 #1</version><meta><realm>TEST</realm></meta></root>')
        (self.root/'paths.xml').write_text('<root><Paths><Path>./res_mods/2.4.1.0</Path><Path mask="*.wotmod" root="res">./mods/2.4.1.0</Path></Paths></root>')
        self.layout=support.client_layout(self.root)
        self.closed=patch.object(support,'ensure_game_closed');self.closed.start()
        self.app=patch.object(support,'ROOT',self.base/'app');self.app.start()
        self.package=self.base/'output.wotmod'
        self.vehicle='res/vehicles/german/TestTank/normal/lod0/chassis.visual_processed'
        self.resource='res/particles/light_maker_new/manifest.json'
        with zipfile.ZipFile(self.package,'w',zipfile.ZIP_STORED) as z:
            z.writestr(self.vehicle,b'new chassis')
            z.writestr(self.resource,json.dumps({'coverage':[{'source':self.vehicle}]}))

    def tearDown(self):
        self.app.stop();self.closed.stop();self.tmp.cleanup()

    def test_unfinished_build_is_rejected_before_install_changes(self):
        staged=self.package.with_suffix('.wotmod.building')
        staged.write_bytes(self.package.read_bytes())
        with self.assertRaisesRegex(ValueError,'中间文件不能安装'):
            support.install_mod(staged,self.root)
        self.assertFalse(self.layout['mods'].exists())
        self.assertFalse((self.root/'light_maker_backups').exists())

    def test_install_backs_up_only_overlapping_resources_and_restores(self):
        mods=self.layout['mods'];mods.mkdir(parents=True)
        old=mods/'old.wotmod'
        with zipfile.ZipFile(old,'w') as z:z.writestr(self.vehicle,b'old chassis')
        old_bytes=old.read_bytes()
        other=mods/'unrelated.wotmod'
        with zipfile.ZipFile(other,'w') as z:z.writestr('res/vehicles/other/OtherTank/file',b'keep')
        other_bytes=other.read_bytes()
        loose=self.layout['res_mods']/self.vehicle[4:];loose.parent.mkdir(parents=True);loose.write_bytes(b'loose chassis')
        (self.root/'game.log').write_text('before test\n')
        result=support.install_mod(self.package,self.root)
        self.assertFalse(old.exists());self.assertFalse(loose.exists())
        self.assertEqual(Path(result['target']).read_bytes(),self.package.read_bytes())
        self.assertEqual(other.read_bytes(),other_bytes)
        self.assertEqual(result['conflicts_backed_up'],2)
        self.assertTrue(support.marker_path(self.root).exists())
        support.restore_install(result['backup'])
        self.assertEqual(old.read_bytes(),old_bytes);self.assertEqual(loose.read_bytes(),b'loose chassis')
        self.assertFalse(Path(result['target']).exists());self.assertEqual(other.read_bytes(),other_bytes)

    def test_failed_install_rolls_back_moved_conflicts(self):
        mods=self.layout['mods'];mods.mkdir(parents=True)
        old=mods/'old.wotmod'
        with zipfile.ZipFile(old,'w') as z:z.writestr(self.vehicle,b'old')
        before=old.read_bytes();replace=support.os.replace
        def fail_once(a,b):
            if str(a).endswith('.installing'):raise OSError('simulated final placement failure')
            return replace(a,b)
        with patch.object(support.os,'replace',side_effect=fail_once):
            with self.assertRaises(OSError):support.install_mod(self.package,self.root)
        self.assertEqual(old.read_bytes(),before)
        self.assertEqual(list(mods.glob('light_maker_*.wotmod')),[])

    def test_restore_does_not_overwrite_package_changed_after_install(self):
        result=support.install_mod(self.package,self.root)
        Path(result['target']).write_bytes(b'changed by another program')
        with self.assertRaisesRegex(ValueError,'修改'):
            support.restore_install(result['backup'])
        self.assertEqual(Path(result['target']).read_bytes(),b'changed by another program')

    def test_recorded_failed_package_and_wrong_realm_are_not_installed(self):
        report={'artifact':{'sha256':engine.digest(self.package)},'whole_vehicle_loading':{'status':'failed'}}
        record=self.base/'验证记录.json';record.write_text(json.dumps(report),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'失败'):support.install_mod(self.package,self.root)
        report['whole_vehicle_loading']['status']='not_tested';report['environment']={'realm':'OTHER'}
        record.write_text(json.dumps(report),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'区服'):support.install_mod(self.package,self.root)
        self.assertFalse(self.layout['mods'].exists())

    def test_escaped_mount_is_rejected(self):
        (self.root/'paths.xml').write_text('<root><Path mask="*.wotmod">mods/../../outside</Path><Path>res_mods/2.4.1.0</Path></root>')
        with self.assertRaises(ValueError):support.client_layout(self.root)

    def test_backup_with_external_restore_path_is_rejected(self):
        result=support.install_mod(self.package,self.root)
        p=Path(result['backup']);data=json.loads(p.read_text(encoding='utf-8'));data['target']='../outside.wotmod';p.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):support.restore_install(p)

    def test_latest_launch_and_multiline_sensitive_data_filter(self):
        log=self.root/'game.log'
        log.write_text('[2026-10-26 10:00:00] [WinMain] Command line: game\n[ERROR] old failure\n'
                       '[2026-10-26 11:00:00] [WinMain] Command line: game\n'
                       '[2026-10-26 11:00:01] [ERROR] auth token=SECRET_VALUE\n  secret continuation\n'
                       '[2026-10-26 11:00:02] [ERROR] [Compound] Chassis.model Compound building failed!\n'
                       '[2026-10-26 11:00:03] type="crash" exception code="3221225477"\n',encoding='utf-8')
        path,summary=support.export_logs(client=self.root,output_dir=self.base/'logs')
        with zipfile.ZipFile(path) as z:
            payload='\n'.join(z.read(n).decode('utf-8-sig') for n in z.namelist())
        self.assertNotIn('SECRET_VALUE',payload);self.assertNotIn('secret continuation',payload)
        self.assertNotIn('old failure',payload);self.assertIn('Compound building failed',payload)
        self.assertEqual(len(summary['crashes']),1)

    def test_marked_range_and_log_rotation(self):
        log=self.root/'game.log';log.write_text('[ERROR] before marker\n',encoding='utf-8')
        support.mark_test(self.root)
        with log.open('a',encoding='utf-8') as f:f.write('[ERROR] after marker\n')
        path,summary=support.export_logs(client=self.root,output_dir=self.base/'logs')
        self.assertEqual(summary['logs'][0]['range'],'since_test_marker')
        with zipfile.ZipFile(path) as z:self.assertNotIn('before marker',z.read('错误与灯效摘录.txt').decode('utf-8-sig'))
        log.write_text('[ERROR] rotated log\n',encoding='utf-8')
        path,summary=support.export_logs(client=self.root,output_dir=self.base/'logs')
        self.assertNotEqual(summary['logs'][0]['range'],'since_test_marker')

    def test_manual_log_export_needs_no_game_installation(self):
        log=self.base/'game.log';log.write_text('[ERROR] a resource failed\n')
        path,summary=support.export_logs(files=[log],output_dir=self.base/'logs')
        self.assertTrue(path.exists());self.assertNotIn('client',summary)


if __name__=='__main__':unittest.main()
