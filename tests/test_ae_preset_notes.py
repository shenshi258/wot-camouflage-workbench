"""Portable annotations and main-window bounds, with no Tk window creation."""
import copy,unittest
from types import SimpleNamespace
from wotcamo import ae_presets,ae_effects as ae
from tools import preset_notes_catalog as catalog

class PresetNotesTests(unittest.TestCase):
    def record(self,description='用途：测试预设。\n摆放：车体侧面。'):
        return dict(name='测试预设',description=description,config=ae.config(dict(fps=24)),clip=dict(frames=96,frame_size=[384,144]))
    def test_all_35_annotations_have_required_guidance_and_fit_the_format(self):
        self.assertEqual(len(catalog.ROWS),35)
        for index in range(1,36):
            text=catalog.description(index);self.assertLessEqual(len(text),1000)
            for heading in ('用途：','摆放：','配色：','形状：','显示：','检查：'):self.assertIn(heading,text)
    def test_summary_is_two_lines_even_for_long_notes(self):
        text=ae_presets.summary(self.record('用途：'+'长注释'*300+'\n摆放：测试。'))
        self.assertEqual(len(text.splitlines()),2);self.assertLess(len(text),180);self.assertIn('4 秒',text)
    def test_manager_displays_full_description_and_does_not_mutate_settings(self):
        record=self.record('用途：第一行。\n摆放：第二行。\n配色：最后一行。');before=copy.deepcopy(record)
        text=ae_presets.description_text(record);self.assertIn('配色：最后一行。',text);self.assertEqual(record,before)
        self.assertIn('选择左侧预设',ae_presets.description_text(None))
    def test_main_window_uses_shared_summary_without_a_tk_root(self):
        from wotcamo.ae_gui import AEImporter
        class Value:
            def set(self,value):self.value=value
        label=Value();record=self.record();app=SimpleNamespace(selected_preset=lambda:record,preset_note=label)
        AEImporter.describe_preset(app);self.assertEqual(label.value,ae_presets.summary(record))

if __name__=='__main__':unittest.main()
