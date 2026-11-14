"""Read a user-selected client's vanilla resource catalog without installing mods."""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from resource_graph import game_path


class ClientCatalog:
    def __init__(self,root):
        selected=Path(root).expanduser().resolve()
        if selected.is_file():selected=selected.parent
        self.root=next((p for p in (selected,*selected.parents)
                        if (p/'paths.xml').is_file() and (p/'version.xml').is_file()),selected)
        paths_file=self.root/'paths.xml';version_file=self.root/'version.xml'
        if not paths_file.is_file() or not version_file.is_file():
            raise ValueError('请选择同时包含 paths.xml 和 version.xml 的客户端目录。')
        raw=paths_file.read_bytes()
        if len(raw)>8*1024*1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('客户端路径配置无效或过大。')
        tree=ET.fromstring(raw);self.packages=[];self.index={};self.collisions={};self.archives={}
        for node in tree.findall('.//Package'):
            value=(node.text or '').strip().replace('\\','/')
            if value.startswith('./'):value=value[2:]
            if not value or value.startswith('/') or ':' in value or '..' in value.split('/'):
                raise ValueError('客户端资源包路径不安全。')
            path=(self.root/value).resolve()
            if not path.is_relative_to(self.root):raise ValueError('客户端资源包路径越界。')
            if path.is_file():self.packages.append(path)
        if not self.packages:raise ValueError('客户端配置中没有找到可读取的资源包。')
        version=ET.parse(version_file).getroot()
        self.version=(version.findtext('version') or '').strip()
        self.realm=(version.findtext('meta/realm') or '').strip()

    def scan(self):
        """Index in paths.xml order. Duplicate paths remain explicit warnings."""
        for path in self.packages:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():continue
                    resource=game_path(info.filename)
                    if resource is None:raise ValueError('客户端资源包中包含不安全的路径。')
                    key=resource.casefold()
                    if key in self.index:
                        self.collisions.setdefault(key,[]).append(str(path))
                    else:self.index[key]=(path,info.filename)
        return self

    def read(self,resource):
        name=game_path(resource)
        if name is None:raise ValueError('资源路径无效。')
        if name.casefold() not in self.index:raise FileNotFoundError(name)
        path,entry=self.index[name.casefold()]
        if path not in self.archives:self.archives[path]=zipfile.ZipFile(path)
        return self.archives[path].read(entry)

    def vehicle_models(self,nation,vehicle):
        """List candidate models, including stock and 3D-style resources."""
        if not nation or not vehicle or any(c in nation+vehicle for c in '/\\:'):
            raise ValueError('车型名称无效。')
        prefix=('vehicles/'+nation+'/'+vehicle+'/').casefold()
        return sorted(entry for key,(_,entry) in self.index.items()
                      if key.startswith(prefix) and '/normal/lod0/' in key and key.endswith('.model'))

    def close(self):
        for archive in self.archives.values():archive.close()
        self.archives.clear()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
