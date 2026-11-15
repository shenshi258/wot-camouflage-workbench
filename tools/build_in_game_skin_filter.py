"""Build a normally loaded .wotmod and region-specific installation ZIPs.

No installation or game launch is performed. Native resources are not bundled;
the game plugin prepares its own cache after the user saves in-game choices.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'game_mods/local_skin_filter'
VERSION='2.1.2'


def digest(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def compile27(source,target,client,module):
    helper=r'''import ctypes,sys
d=ctypes.PyDLL(sys.argv[1]);ctypes.c_int.in_dll(d,'Py_NoSiteFlag').value=1
d.Py_Initialize();d.PyRun_SimpleString.argtypes=[ctypes.c_char_p]
source,target,module,library=sys.argv[2:]
script="import marshal,sys\nsys.path[:]=[u%s]\n"%ascii(library)
script+="src=open(u%s,'rb').read()\n"%ascii(source)
script+="code=compile(src,%s,'exec')\n"%ascii(module)
script+="open(u%s,'wb').write('\\x03\\xf3\\x0d\\x0a\\x00\\x00\\x00\\x00'+marshal.dumps(code))\n"%ascii(target)
sys.exit(bool(d.PyRun_SimpleString(script.encode('ascii'))))
'''
    run=subprocess.run([sys.executable,'-c',helper,str(client/'win64/python27.dll'),str(source.resolve()),str(target.resolve()),module,str(client/'res/packages/scripts.pkg')+'/scripts/common/Lib'],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45,creationflags=0x08000000)
    if run.returncode:raise RuntimeError(run.stdout.decode('utf-8','replace'))


def stored(z,name,data):
    info=zipfile.ZipInfo(name,(2026,11,15,0,0,0));info.compress_type=zipfile.ZIP_STORED;z.writestr(info,data)


def main():
    p=argparse.ArgumentParser();p.add_argument('--eu',type=Path,required=True);p.add_argument('--asia',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'standalone/local_skin_filter'))
    from client_catalog import ClientCatalog
    from client_api import check
    from client_pyc import Reader,walk
    records=[]
    for realm,client in [('EU',a.eu),('ASIA',a.asia)]:
        with ClientCatalog(client).scan()as catalog:
            if catalog.realm!=realm:raise ValueError('Selected client realm mismatch: '+realm)
            api=check(catalog)
            # Read each installed client's native WULF view interfaces; no browser API is used.
            ui_api={}
            for file,method,args in [
              ('gui/impl/pub/window_impl.pyc','__init__',{b'self',b'wndFlags'}),
              ('gui/impl/pub/view_impl.pyc','_onLoading',{b'self'})]:
                raw=catalog.read('scripts/client/'+file);reader=Reader(raw);reader.pos=8
                methods=[c for c in walk(reader.obj())if c.name==method.encode('ascii')]
                if not any(args.issubset(set(c.varnames[:c.argcount]))for c in methods):raise ValueError('Native WULF API changed')
                ui_api[file]=hashlib.sha256(raw).hexdigest()
            if catalog.version.split()[0]!='v.2.4.1.1':raise ValueError('Native resource registration is verified for 2.4.1.1 only')
            for font in ('WarheliosZHCN-Medium.ttf','WarheliosZHCN-Bold.ttf'):
                if ('gui/gameface/fonts/'+font).lower()not in catalog.index:raise ValueError('Native CJK font missing: '+font)
            records.append(dict(path=str(client.resolve()),realm=realm,version=catalog.version,appearance_api=api,
              selector_ui='native_gameface',selector_ui_api=ui_api,
              paths_xml_sha256=digest(client/'paths.xml'),version_xml_sha256=digest(client/'version.xml'),
              python27_sha256=digest(client/'win64/python27.dll'),actual_user_launch_confirmed=False))
    # These builds share verified appearance interfaces. The plugin reads each
    # client's own native resources and own vehicle list, not another realm's files.
    assert [x['sha256']for x in records[0]['appearance_api']]==[x['sha256']for x in records[1]['appearance_api']]
    modules=('__init__','catalog','packed_xml','runtime','gameface')
    candidates=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'.cache',prefix='filter20_compile_')as folder:
        work=Path(folder)
        for region in records:
            realm=region['realm'];client=Path(region['path']);out=a.output/realm;out.mkdir(exist_ok=False)
            target=out/('local.skin_filter_'+VERSION+'.wotmod')
            with zipfile.ZipFile(target,'x')as z:
                meta=ET.Element('root')
                for k,v in [('id','local.skin_filter'),('version',VERSION),('name','In-game local skin filter EU ASIA - pending tests')]:ET.SubElement(meta,k).text=v
                stored(z,'meta.xml',ET.tostring(meta,encoding='utf-8',xml_declaration=True))
                for name in modules:
                    compiled=work/(realm+'_'+name+'.pyc');compile27(SOURCE/(name+'.py'),compiled,client,'local_skin_filter2/'+name+'.py')
                    stored(z,'res/scripts/client/gui/mods/local_skin_filter/'+name+'.pyc',compiled.read_bytes())
                stored(z,'res/gui/gameface/mods/local_skin_filter/Selector.html',(SOURCE/'selector.html').read_bytes())
                stored(z,'res/gui/gen_resources/local.skin_filter.json',(SOURCE/'selector_resources.json').read_bytes())
                entry=work/'mod_entry.py';entry.write_bytes((SOURCE/'mod_entry.py.txt').read_bytes())
                compiled=work/(realm+'_entry.pyc');compile27(entry,compiled,client,'local_skin_filter2/mod_entry.py')
                stored(z,'res/scripts/client/gui/mods/mod_zz_local_skin_filter.pyc',compiled.read_bytes())
            with zipfile.ZipFile(target)as z:
                assert z.testzip()is None
                assert all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist())
            result=dict(tool='In-game local skin filter '+VERSION,artifact=dict(path=str(target.resolve()),sha256=digest(target),bytes=target.stat().st_size),
                client=region,file_validation=dict(status='passed',zip_crc=True,stored_only=True,private_python_namespace=True,
                      native_resource_payloads=False),offline_validation=dict(status='not_tested'),
                whole_vehicle_loading=dict(status='not_tested'),in_game_tested=False,
                baseline=dict(user_confirmed_working=False,agent_in_game_observed=False),
                anti_cheat=dict(official_review='not_reviewed',zero_false_positive_guarantee=False))
            record=out/'验证记录.json';record.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');candidates.append(str(record.resolve()))
            print(realm,region['version'],target,digest(target),target.stat().st_size)
    (a.output/'候选记录索引.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
