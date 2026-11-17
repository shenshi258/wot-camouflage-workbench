"""Real controls for reusable elements and editable timeline nodes."""
import copy,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from wotcamo import ae_animation,asset_library
from wotcamo.ae_gui import AEImporter
from wotcamo.ae_animation_gui import AnimationDialog
from wotcamo.ae_library_gui import AssetLibraryDialog


class AENodesGUITests(unittest.TestCase):
    def setUp(self):
        self.app=AEImporter();self.app.geometry('1080x700');self.app.update()
        self.addCleanup(self.app.close)

    def test_node_settings_copy_restore_without_changing_vehicle_or_original_clip(self):
        values=self.app.collect();values['animation']=dict(duration=2,canvas_scale=2,nodes=[dict(time=0,x=-20),dict(time=2,x=20)])
        original_clip=object();self.app.clip=original_clip;self.app.source.set('original.wotmod')
        self.app.restore_settings(values);self.assertEqual(len(self.app.collect()['animation']['nodes']),2)
        self.assertIn('2 个节点',self.app.animation_note.get());self.assertIs(self.app.clip,original_clip)
        copied=[]
        with patch.object(self.app,'clipboard_clear'),patch.object(self.app,'clipboard_append',side_effect=copied.append):self.app.copy_settings()
        self.app.set_animation(None)
        with patch.object(self.app,'clipboard_get',return_value=copied[0]):self.app.paste_settings()
        self.assertEqual(self.app.collect()['animation'],ae_animation.normalize(values['animation']))
        self.assertEqual(self.app.source.get(),'original.wotmod');self.assertIs(self.app.clip,original_clip)

    def test_node_editor_preview_is_separate_and_apply_saves_the_same_nodes(self):
        original=ae_animation.normalize(None);before=copy.deepcopy(original);applied=[];previews=[]
        dialog=AnimationDialog(self.app,original,24,applied.append,previews.append)
        dialog.example();dialog.preview();self.assertEqual(len(previews),1);self.assertEqual(applied,[])
        self.assertEqual(original,before);self.assertGreaterEqual(len(previews[0]['nodes']),2)
        dialog.apply();self.assertEqual(applied,previews);self.assertFalse(dialog.winfo_exists())

    def test_node_editor_limits_and_actions_fit_in_a_small_window(self):
        dialog=AnimationDialog(self.app,None,24,lambda value:None);self.addCleanup(lambda:dialog.destroy() if dialog.winfo_exists() else None)
        dialog.geometry('760x510');self.app.update();dialog.example();dialog.parameters['duration'].set('60');dialog.refresh()
        self.assertTrue(dialog.apply_button.instate(['disabled']));self.assertIn('128',dialog.status.get())
        dialog.parameters['duration'].set('2');dialog.refresh();self.app.update()
        self.assertTrue(dialog.apply_button.instate(['!disabled']))
        for button in (dialog.apply_button,dialog.preview_button,dialog.cancel_button):
            self.assertTrue(button.winfo_ismapped());self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),dialog.winfo_rooty()+dialog.winfo_height())
        for widget,provider in dialog.hover_help.providers.items():
            spec=provider(None);self.assertTrue(spec.title);self.assertTrue(spec.body)
        dialog.hover_help.delay=0
        dialog.hover_help.schedule(dialog.apply_button,dialog.hover_help.providers[dialog.apply_button](None),100,100)
        self.app.update();self.assertIsNotNone(dialog.hover_help._window)
        dialog.hover_help.hide()

    def test_library_cancel_and_callback_false_preserve_the_original_store(self):
        with tempfile.TemporaryDirectory() as folder:
            store=asset_library.Library(Path(folder)/'library');buffer=io.BytesIO();Image.new('RGBA',(20,10),(250,60,80,128)).save(buffer,format='PNG')
            item=store.import_image(buffer.getvalue(),'元素.png','自制')['item'];selected=[]
            dialog=AssetLibraryDialog(self.app,lambda value:selected.append(value)or False,store=store)
            dialog.select_item(item);dialog.use_selected();self.assertTrue(dialog.winfo_exists())
            self.assertEqual(selected[0]['id'],item['id']);dialog.destroy()
            self.assertEqual(store.image(item['id'])[0],buffer.getvalue())

    def test_library_still_is_loaded_as_one_frame_and_can_receive_nodes(self):
        with tempfile.TemporaryDirectory() as folder:
            store=asset_library.Library(Path(folder));buffer=io.BytesIO();Image.new('RGB',(48,24),(200,60,30)).save(buffer,format='PNG')
            item=store.import_image(buffer.getvalue(),'元素.png')['item'];self.app.source.set('vehicle.wotmod')
            with patch('wotcamo.asset_library.Library',return_value=store),patch.object(self.app,'job',side_effect=lambda work,done:done(work())):
                self.assertTrue(self.app.use_library_item(item))
            self.assertEqual(self.app.clip['frames'],1);self.assertEqual(self.app.collect()['blend'],'alpha')
            self.assertEqual(self.app.source.get(),'vehicle.wotmod');self.assertEqual(store.image(item['id'])[0],buffer.getvalue())

    def test_regular_surface_distance_has_its_own_enabled_control_and_help(self):
        self.app.placement.set('贴面播放');self.app.update()
        self.assertTrue(self.app.fields['surface_lift'].instate(['!disabled']))
        self.assertTrue(self.app.fields['lift'].instate(['disabled']))
        self.app.values['surface_lift'].set('.02');self.assertEqual(self.app.collect()['surface_lift'],.02)
        self.assertIn(self.app.fields['surface_lift'],self.app.hover_help.providers)
        self.app.placement.set('贴面发光');self.app.update()
        self.assertTrue(self.app.fields['surface_lift'].instate(['disabled']))
        self.assertTrue(self.app.fields['lift'].instate(['!disabled']))
