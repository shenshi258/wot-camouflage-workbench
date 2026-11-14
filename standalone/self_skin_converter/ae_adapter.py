"""Accept only AE scripts identical in behavior to the audited own-vehicle template.

Input bytecode is parsed as data, never imported or executed by the converter.
Filename/line-number metadata may differ; instructions, names and constants must
match the known template. Unknown script families remain unsupported.
"""
import hashlib
import json
import re
import tempfile
from pathlib import Path
from client_pyc import Code,Reader

MANIFEST=re.compile(r'^res/particles/(ae_import_[0-9a-f]{12})/manifest\.json$')


def code_signature(raw):
    if len(raw)>256000 or raw[:4]!=b'\x03\xf3\r\n':raise ValueError('AE 脚本格式不受支持。')
    reader=Reader(raw);reader.pos=8
    try:root=reader.obj()
    except (ValueError,IndexError,AssertionError,RecursionError)as error:
        raise ValueError('AE 脚本无法静态读取。')from error
    if not isinstance(root,Code)or reader.pos!=len(raw):raise ValueError('AE 脚本有额外数据。')
    def value(item):
        if isinstance(item,Code):
            return ('code',item.argcount,item.nlocals,item.stacksize,item.flags,item.code,
                value(item.consts),value(item.names),value(item.varnames),value(item.freevars),value(item.cellvars),item.name)
        if isinstance(item,(tuple,list)):return tuple(value(x)for x in item)
        if isinstance(item,dict):return tuple(sorted((value(k),value(v))for k,v in item.items()))
        return item
    return value(root)


def analyse(archive,nation,vehicle,client,compiler):
    manifests=[n for n in archive.namelist()if MANIFEST.fullmatch(n)]
    if not manifests:return {},[],None
    if len(manifests)!=1:raise ValueError('同一输入内有多套 AE 工程，暂不能确认脚本关系。')
    name=manifests[0];prefix=MANIFEST.fullmatch(name)[1]
    info=archive.getinfo(name)
    if info.file_size>4_000_000:raise ValueError('AE 工程记录过大。')
    manifest=json.loads(archive.read(name))
    rigs=manifest.get('models')
    if manifest.get('kind')!='ae_import'or not isinstance(rigs,list)or not 1<=len(rigs)<=8:
        raise ValueError('AE 工程记录无法确认。')
    for rig in rigs:
        if not isinstance(rig,dict)or set(rig)!={'id','part','anchor','anchor_kind','sequence'}:
            raise ValueError('AE 挂载结构不在已适配范围。')
        if rig['part']not in('chassis','hull','turret','gun')or rig['anchor_kind']not in('part','bone'):
            raise ValueError('AE 挂载部件无法确认。')
        if any(not isinstance(rig[k],str)or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',rig[k])for k in('id','anchor')):
            raise ValueError('AE 挂点名称无法确认。')
        if not re.fullmatch(r'particles/'+prefix+r'/effect_\d+\.seq',str(rig['sequence'])):
            raise ValueError('AE 序列路径不属于当前工程。')
        if 'res/'+rig['sequence']not in archive.namelist():raise ValueError('AE 序列缺失。')
    script='res/scripts/client/gui/mods/mod_'+prefix+'.pyc'
    if script not in archive.namelist():raise ValueError('AE 挂载脚本缺失。')
    source=Path(__file__).with_name('ae_runtime_template.py.txt').read_text('ascii')
    source=source.replace('RIGS = []','RIGS = '+repr(rigs)).replace('__VEHICLE_TYPE__',vehicle)
    source=source.replace('CustomVehicle.LightMaker','CustomVehicle.AEImport')
    with tempfile.TemporaryDirectory(prefix='ae_scope_')as folder:
        src=Path(folder)/'known.py';compiled=Path(folder)/'known.pyc';src.write_text(source,encoding='ascii')
        compiler(src,compiled,client);expected=compiled.read_bytes()
    raw=archive.read(script)
    if code_signature(raw)!=code_signature(expected):
        raise ValueError('AE 脚本与已核对的仅本车挂载逻辑不匹配，需要专门适配。')
    allowed=('.json','.model','.visual_processed','.primitives_processed','.seq','.dds','.png')
    extras={}
    for entry in archive.infolist():
        if entry.is_dir():continue
        if entry.filename.startswith('res/particles/'+prefix+'/'):
            if not entry.filename.lower().endswith(allowed):raise ValueError('AE 附加资源类型不受支持：'+entry.filename)
            extras[entry.filename]=archive.read(entry)
    # Emit known source, not input bytecode. The template already guards local
    # ownership, colour-pass hiding, restoration and attachment cleanup.
    extras[script]=expected
    record=dict(path=script,sha256=hashlib.sha256(raw).hexdigest(),adapter='verified_ae_own_vehicle',
                input_bytecode_executed=False,sequence_and_material_resources_preserved=True)
    return extras,[record],source
