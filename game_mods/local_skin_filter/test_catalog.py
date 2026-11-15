"""Offline tests; they do not establish native Compound/visual compatibility."""
import hashlib,json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from .catalog import Catalog,Paused,path,rewrite,parse,within,find_root,encode_xml


class CatalogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'res/packages').mkdir(parents=True);self.files={}
        self.version('EU')
        (self.root/'paths.xml').write_text('<root><Paths><Path cacheSubdirs="true">./res_mods/2.4.1.1</Path><Package>./res/packages/base.pkg</Package></Paths></root>')
        self.base='vehicles/german/G197_Test/';texture='vehicles/common/base.dds'
        for state in('normal','crash'):
            for part in('Chassis','Hull','Turret_01','Gun_01'):
                stem=self.base+state+'/lod0/'+part
                self.files[stem+'.model']=('<root><nodefullVisual>'+stem+'</nodefullVisual></root>').encode()
                self.files[stem+'.visual_processed']=('<root><Texture>'+texture+'</Texture><fx>shaders/native.fx</fx></root>').encode()
                self.files[stem+'.primitives_processed']=b'untouched native mesh'
        self.files[texture]=b'native DDS';self.files['shaders/native.10.dx11.fxo']=b'native shader'
        self.files['shaders/native.11.dx11.fxo']=b'native shader'
        self.files['scripts/item_defs/vehicles/germany/list.xml']=b'<root><G197_Test><shortUserString>#vehicles:test</shortUserString></G197_Test></root>'
        self.pkg();self.catalog=Catalog(str(self.root)).scan();self.addCleanup(self.catalog.close)
    def version(self,realm):
        (self.root/'version.xml').write_text('<root><version>v.2.4.1.1 #1</version><meta><realm>'+realm+'</realm></meta></root>')
    def pkg(self):
        with zipfile.ZipFile(self.root/'res/packages/base.pkg','w')as z:
            for k,v in self.files.items():z.writestr(k,v)
    def test_eu_asia_each_detect_own_client_without_hardcoded_install_path(self):
        self.assertEqual(self.catalog.realm,'EU');self.assertEqual(len(self.catalog.cars),1)
        self.assertEqual(self.catalog.cars[0]['localization'],'#vehicles:test')
        self.version('ASIA');other=Catalog(str(self.root)).scan();self.addCleanup(other.close)
        self.assertEqual(other.realm,'ASIA');self.assertNotEqual(other.fingerprint,self.catalog.fingerprint)
    def test_other_regions_and_other_versions_are_disabled(self):
        self.version('CN')
        with self.assertRaisesRegex(ValueError,'Supported clients'):Catalog(str(self.root))
        (self.root/'version.xml').write_text('<root><version>v.3.0.0.0 #1</version><meta><realm>EU</realm></meta></root>')
        with self.assertRaisesRegex(ValueError,'Supported clients'):Catalog(str(self.root))
    def test_client_root_discovery_handles_game_root_and_win64_startup(self):
        for cwd in(self.root,self.root/'win64'):
            with patch('os.getcwd',return_value=str(cwd)):
                self.assertEqual(find_root(),str(self.root))
    def test_cache_writes_only_own_private_namespace_and_original_files_unchanged(self):
        original={p:p.read_bytes()for p in self.root.rglob('*')if p.is_file()}
        record=self.catalog.prepare('german/g197_test')
        self.assertEqual(record['whole_vehicle_loading']['status'],'not_tested');self.assertEqual(len(record['models']),8)
        for row in record['resources']:
            self.assertTrue(row['destination'].startswith('vehicles/_lsf2/'))
            data=Path(self.catalog.absolute(row['destination'])).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
            if row['source'].endswith('.primitives_processed'):self.assertEqual(data,b'untouched native mesh')
            if row['source'].endswith('.visual_processed'):
                self.assertIn(b'<fx>shaders/native.fx</fx>',data);self.assertIn(b'vehicles/_lsf2/',data)
        for p,data in original.items():self.assertEqual(p.read_bytes(),data)
        self.assertIsNotNone(self.catalog.load_ready('german/g197_test'))
    def test_sidecar_files_remain_adjacent_after_path_shortening(self):
        record=self.catalog.prepare('german/g197_test');mapping={r['source']:r['destination']for r in record['resources']}
        for source,destination in mapping.items():
            if source.endswith('.visual_processed'):
                primitive=source.replace('.visual_processed','.primitives_processed')
                self.assertEqual(destination.replace('.visual_processed','.primitives_processed'),mapping[primitive])
    def test_corrupted_cache_is_not_reused(self):
        record=self.catalog.prepare('german/g197_test')
        Path(self.catalog.absolute(record['resources'][0]['destination'])).write_bytes(b'corrupted')
        self.assertIsNone(self.catalog.load_ready('german/g197_test'))
    def test_partial_build_or_cancel_has_no_ready_marker(self):
        with self.assertRaises(Paused):self.catalog.prepare('german/g197_test',cancel=lambda:True)
        self.assertIsNone(self.catalog.load_ready('german/g197_test'))
    def test_unresolved_dependency_stops_preparation(self):
        self.catalog.index.pop('vehicles/common/base.dds')
        with self.assertRaisesRegex(ValueError,'Missing dependency'):self.catalog.prepare('german/g197_test')
        self.assertIsNone(self.catalog.load_ready('german/g197_test'))
    def test_cache_manifest_cannot_redirect_to_public_or_outside_paths(self):
        for value in('vehicles/german/G197_Test/normal/hull.model','../escape','C:/escape'):
            with self.assertRaises(ValueError):self.catalog.absolute(value)
        record=self.catalog.prepare('german/g197_test');marker=Path(self.catalog.absolute(record['base']+'ready.json'))
        record['resources'][0]['destination']='vehicles/german/G197_Test/normal/hull.model'
        marker.write_text(json.dumps(record));self.assertIsNone(self.catalog.load_ready('german/g197_test'))
    def test_mod_overrides_are_never_a_baseline_source(self):
        file=self.root/'res_mods/2.4.1.1/vehicles/common/base.dds';file.parent.mkdir(parents=True);file.write_bytes(b'custom mod')
        record=self.catalog.prepare('german/g197_test')
        row=next(r for r in record['resources']if r['source']=='vehicles/common/base.dds')
        self.assertEqual(Path(self.catalog.absolute(row['destination'])).read_bytes(),b'native DDS')
        self.assertEqual(file.read_bytes(),b'custom mod')
    def test_packed_scalar_carriage_return_survives_plain_xml_roundtrip(self):
        from xml.etree import ElementTree as ET
        root=ET.Element('root');node=ET.SubElement(root,'property');node.text='property\r\n  >'
        restored=parse(encode_xml(root));self.assertEqual(restored.findtext('property'),node.text)
    def test_override_scan_identifies_only_existing_stock_paths_and_skips_private_cache(self):
        self.assertIsNone(path(b'res/vehicles/unknown/\xa3'))
        mods=self.root/'mods/2.4.1.1';mods.mkdir(parents=True)
        with zipfile.ZipFile(mods/'skin.wotmod','w')as z:
            z.writestr('res/'+self.base+'normal/lod0/Hull.model',b'custom')
            z.writestr('res/scripts/client/gui/mods/mod_unknown.py',b'raise RuntimeError("never execute")')
            z.writestr('res/vehicles/german/Custom/normal/lod0/Hull.model',b'custom')
        self.catalog.mod_roots=[str(mods)]
        self.assertEqual(self.catalog.scan_overrides(),{'german/g197_test'})
        self.assertEqual(self.catalog.read(self.base+'normal/lod0/Hull.model'),self.files[self.base+'normal/lod0/Hull.model'])


if __name__=='__main__':unittest.main()
