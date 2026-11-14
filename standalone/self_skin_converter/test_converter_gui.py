import tempfile,unittest,threading,time
from pathlib import Path
from unittest.mock import patch
import converter_gui


class ConverterGUITests(unittest.TestCase):
    def setUp(self):
        self.app=converter_gui.App();self.app.withdraw();self.addCleanup(self.app.destroy)

    def test_empty_client_and_independent_brand_and_compact_layout(self):
        app=self.app
        self.assertEqual(app.client.get(),'')
        self.assertIn('仅本车转换器',app.title())
        app.geometry('800x600');app.deiconify();app.update()
        self.assertTrue(app.table.winfo_ismapped());self.assertTrue(app.detail.winfo_ismapped())
        self.assertLessEqual(app.detail.winfo_rooty()+app.detail.winfo_height(),app.winfo_rooty()+app.winfo_height())

    def test_add_deduplicates_paths_and_remove_after_results_uses_origin(self):
        app=self.app
        with tempfile.TemporaryDirectory()as folder:
            p=Path(folder)/'one.wotmod';q=Path(folder)/'two.zip'
            app.add_paths([p,p,q]);self.assertEqual(len(app.inputs),2)
            app.show_results([dict(path=str(q),name='inner.wotmod',status='error',error='unknown script')])
            app.table.selection_set('0');app.remove()
            self.assertEqual(app.inputs,[p.resolve()])

    def test_busy_locks_actions_and_close_waits_for_current_package(self):
        app=self.app;app.set_busy(True)
        self.assertTrue(all(str(w.cget('state'))=='disabled'for w in app.controls))
        app.close();self.assertTrue(app.cancel.is_set());self.assertTrue(app.closing)
        self.assertTrue(app.winfo_exists());app.set_busy(False)

    def test_uml_original_issues_are_visible_in_result_details(self):
        app=self.app
        app.show_results([dict(path='uml.wotmod',status='candidate',target='out.wotmod',record=dict(adapter='uml_swapNPC',
            offline_validation=dict(disabled_profiles=1),file_validation=dict(preexisting_missing_dependencies=['missing.dds'])))])
        text=app.detail.get('1.0','end')
        self.assertIn('原包有 1 项缺失依赖',text);self.assertIn('未自动开启',text);self.assertIn('尚未实测',text)

    def test_missing_client_does_not_start_conversion(self):
        app=self.app;app.add_paths([Path('one.wotmod')])
        with patch('converter_gui.messagebox.showerror')as error,patch('converter_gui.convert_many')as convert:
            app.convert()
        error.assert_called_once();convert.assert_not_called();self.assertFalse(app.busy)


if __name__=='__main__':unittest.main()
