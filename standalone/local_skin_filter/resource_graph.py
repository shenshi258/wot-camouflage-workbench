"""Read model and material references without extracting or converting assets."""
import io
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from XmlUnpacker import XmlUnpacker

MAX_XML = 32 * 1024 * 1024


def parse(data):
    if data[:4] == struct.pack('<I', 0x62a14e45):
        return XmlUnpacker().read(io.BytesIO(data))
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('资源 XML 包含不支持的声明')
    return ET.fromstring(data)


def game_path(value):
    value=(value or '').strip().replace('\\','/')
    if not value or value.startswith('/') or ':' in value or '..' in value.split('/'):
        return None
    # Repeated separators in game references denote the same resource, but
    # must not be used to bypass traversal or absolute-path checks.
    value='/'.join(part for part in value.split('/') if part)
    if value.lower().startswith('res/'):
        value=value[4:]
    if not value:return None
    return value


def inspect_references(path):
    """Resolve source-owned dependencies and list external references, read only.

    External references may be supplied by the client or another mod. Listing
    them is not a claim that the game can resolve or load them.
    """
    with zipfile.ZipFile(path) as archive:
        names={x.filename.casefold():x for x in archive.infolist() if not x.is_dir()}
        refs=[];issues=[];checked=0
        def add(source, kind, value):
            value=game_path(value)
            if not value:
                issues.append(dict(source=source,issue='无效或不安全的资源引用'));return
            target=names.get(('res/'+value).casefold())
            refs.append(dict(source=source,kind=kind,target=value,
                             availability='input_package' if target else 'client_or_other_mod_unverified'))
        for item in archive.infolist():
            lower=item.filename.casefold()
            if item.is_dir() or not lower.endswith(('.model','.visual','.visual_processed','.mfm')):
                continue
            if item.file_size>MAX_XML:
                issues.append(dict(source=item.filename,issue='XML 资源超过离线检查大小上限'));continue
            try:
                root=parse(archive.read(item));checked+=1
                if lower.endswith('.model'):
                    for node in root.iter():
                        if node.tag not in ('nodefullVisual','nodelessVisual','parent') or not node.text:continue
                        value=game_path(node.text)
                        if not value:add(item.filename,'visual',node.text);continue
                        if node.tag=='parent':
                            add(item.filename,'parent_model',value if value.casefold().endswith('.model') else value+'.model')
                            continue
                        if not value.casefold().endswith(('.visual','.visual_processed')):
                            candidates=[value+'.visual_processed',value+'.visual']
                            value=next((v for v in candidates if ('res/'+v).casefold() in names),candidates[0])
                        add(item.filename,'visual',value)
                else:
                    for node in root.iter():
                        if node.tag in ('Texture','texture','fx') and (node.text or '').strip():
                            add(item.filename,'shader' if node.tag=='fx' else 'texture',node.text)
                        elif node.tag=='material' and (node.text or '').strip().casefold().endswith('.mfm'):
                            add(item.filename,'material',node.text)
                    if lower.endswith('.visual_processed'):
                        add(item.filename,'primitives',item.filename[4:-len('.visual_processed')]+'.primitives_processed')
                    elif lower.endswith('.visual'):
                        add(item.filename,'primitives',item.filename[4:-len('.visual')]+'.primitives')
            except Exception as error:
                issues.append(dict(source=item.filename,issue='资源无法解析：'+str(error)[:240]))
        return dict(resources_checked=checked,references=refs,issues=issues,
                    complete=False,reason='尚未核对客户端或其他模组资源，也未执行游戏加载。')
