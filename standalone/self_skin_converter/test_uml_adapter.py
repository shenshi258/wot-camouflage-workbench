import tempfile,unittest,zipfile,json
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from uml_adapter import restrict,build


class UMLTests(unittest.TestCase):
    def test_only_npc_flag_changes_and_disabled_whitelist_animation_are_retained(self):
        raw=b'<root><models><custom><enabled>False</enabled><swapNPC>True</swapNPC><whitelist>R1</whitelist><animation><duration>1.25</duration></animation></custom></models></root>'
        changed,rows=restrict(raw);tree=ET.fromstring(changed)
        self.assertEqual(tree.findtext('models/custom/swapNPC'),'False')
        self.assertEqual(tree.findtext('models/custom/enabled'),'False')
        self.assertEqual(tree.findtext('models/custom/whitelist'),'R1')
        self.assertEqual(tree.findtext('models/custom/animation/duration'),'1.25')
        self.assertEqual(rows[0]['old_swapNPC'],'True')

    def test_missing_flag_is_added_to_each_profile(self):
        changed,rows=restrict(b'<root><models><one><enabled>True</enabled></one><two/></models></root>')
        self.assertEqual(len(rows),2)
        self.assertEqual([n.text for n in ET.fromstring(changed).findall('.//swapNPC')],['False','False'])

    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        source=root/'uml.wotmod';model='vehicles/test/Custom/normal/lod0/hull'
        profile='<root><models><custom><swapNPC>True</swapNPC><hull><undamaged>'+model+'.model</undamaged></hull></custom></models></root>'
        with zipfile.ZipFile(source,'w')as z:
            z.writestr('res/scripts/client/mods/UMLprofiles/custom.xml',profile)
            z.writestr('res/'+model+'.model','<root><nodefullVisual>'+model+'</nodefullVisual></root>')
            z.writestr('res/'+model+'.visual_processed','<root/>')
            z.writestr('res/'+model+'.primitives_processed',b'geometry')
        return root,source,SimpleNamespace(root=root/'client',index={},version='test',realm='test')

    def test_profile_output_keeps_non_profile_entries_byte_identical(self):
        root,source,catalog=self.fixture();original=source.read_bytes()
        target,record=build(source,catalog.root,root/'output',catalog)
        self.assertEqual(source.read_bytes(),original)
        self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested')
        with zipfile.ZipFile(source)as before,zipfile.ZipFile(target)as after:
            for name in before.namelist():
                if name.endswith('custom.xml'):continue
                self.assertEqual(before.read(name),after.read(name))

    def test_global_stock_or_unknown_script_is_rejected(self):
        root,source,catalog=self.fixture()
        catalog.index={'vehicles/test/custom/stock.model':('pkg','entry')}
        with self.assertRaisesRegex(ValueError,'公共目录'):build(source,catalog.root,root/'output',catalog)
        catalog.index={}
        with zipfile.ZipFile(source,'a')as z:z.writestr('res/scripts/client/gui/mods/unknown.pyc',b'unknown')
        with self.assertRaisesRegex(ValueError,'脚本'):build(source,catalog.root,root/'output',catalog)


if __name__=='__main__':unittest.main()
