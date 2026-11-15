# -*- coding: utf-8 -*-
"""Python 2.7/3 native-resource cache. No game API is called from worker threads.

Reads ONLY native .pkg files declared in paths.xml. Original mods remain in
place; generated files live exclusively in our private res_mods namespace.
An incomplete build is never published as ready. It cannot hide a tank.
"""
from __future__ import unicode_literals
import copy,hashlib,io,json,os,re,struct,uuid,zipfile
from xml.etree import ElementTree as ET
from .packed_xml import XmlUnpacker

XML = ('.model','.visual','.visual_processed','.mfm')
ALLOWED = XML + ('.dds','.vt','.primitives','.primitives_processed')
PREFIX = 'vehicles/_lsf2/'
NATIONS = {'german':'germany','french':'france','american':'usa','british':'uk',
           'russian':'ussr','chinese':'china','japan':'japan','czech':'czech',
           'poland':'poland','sweden':'sweden','italy':'italy'}


class Paused(Exception):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def path(value):
    if isinstance(value,bytes)and not isinstance(value,type(u'')):
        try:value=value.decode('utf-8')
        except UnicodeDecodeError:return None
    value=(value or '').strip().replace('\\','/')
    if not value or value.startswith('/')or ':'in value or '..'in value.split('/'):return None
    value='/'.join(p for p in value.split('/')if p)
    if value.lower().startswith('res/'):value=value[4:]
    return value or None


def within(base,target):
    base=os.path.normcase(os.path.realpath(base));target=os.path.normcase(os.path.realpath(target))
    return target==base or target.startswith(base+os.sep)


def parse(data):
    if data[:4]==struct.pack('<I',0x62a14e45):return XmlUnpacker().read(io.BytesIO(data))
    if b'<!DOCTYPE'in data.upper()or b'<!ENTITY'in data.upper():raise ValueError('XML entities are unsupported')
    return ET.fromstring(data)


def encode_xml(root):
    # Packed sections can contain literal CR in scalar values. Plain XML
    # normalizes raw CR/LF while reading; numeric references preserve the value.
    return ET.tostring(root,encoding='utf-8').replace(b'\r',b'&#13;')


def find_root():
    import sys
    candidates=[os.getcwd(),os.path.dirname(os.path.abspath(sys.executable))]
    for start in candidates:
        current=start
        for unused in range(4):
            if all(os.path.isfile(os.path.join(current,p))for p in('paths.xml','version.xml')):return current
            current=os.path.dirname(current)
    raise ValueError('Client paths.xml/version.xml not found')


def rewrite(root,mapping):
    root=copy.deepcopy(root);visual={};models={}
    for old,new in mapping.items():
        if old.endswith('.model'):models[old[:-6]]=new[:-6]
        for ext in('.visual','.visual_processed'):
            if old.endswith(ext):visual[old[:-len(ext)]]=new[:-len(ext)]
    for node in root.iter():
        if len(node)or not node.text:continue
        value=path(node.text)
        if not value:continue
        value=value.lower();replacement=mapping.get(value)
        if replacement is None and node.tag in('nodefullVisual','nodelessVisual'):replacement=visual.get(value)
        if replacement is None and node.tag=='parent':replacement=models.get(value)
        if replacement is not None:node.text=replacement
    return root


class Catalog(object):
    def __init__(self,root):
        self.root=os.path.realpath(root);self.index={};self.packages=[];self.archives={};self.cars=[];self.mod_roots=[]
        self.overridden=set();self.override_warnings=[]
        self.index_loaded=False;self.metadata_cache_hit=False
        version_raw=self._file('version.xml');paths_raw=self._file('paths.xml')
        version=parse(version_raw);self.version=(version.findtext('version')or'').strip()
        self.realm=(version.findtext('meta/realm')or'').strip()
        match=re.search(r'v\.([0-9]+(?:\.[0-9]+){3})',self.version)
        if self.realm not in('EU','ASIA')or not match or match.group(1)!='2.4.1.1':
            raise ValueError('Supported clients: Wargaming EU/ASIA 2.4.1.1')
        self.branch=match.group(1);tree=parse(paths_raw);self.resmods=None;stamps=[]
        for node in tree.findall('.//Package'):
            name=path(node.text)
            if not name:raise ValueError('Invalid native package path')
            source=os.path.join(self.root,*name.split('/'))
            if not within(self.root,source):raise ValueError('Native package outside client')
            if os.path.isfile(source):
                self.packages.append(source);info=os.stat(source);stamps.append((name,info.st_size,int(info.st_mtime)))
        for node in tree.findall('.//Paths/Path'):
            name=path(node.text)
            if name and node.get('mask')=='*.wotmod':
                source=os.path.realpath(os.path.join(self.root,*name.split('/')))
                if within(self.root,source):self.mod_roots.append(source)
            if name and node.get('mask')is None and name.lower()=='./res_mods/'+self.branch:name=name[2:]
            if name and node.get('mask')is None and name.lower()=='res_mods/'+self.branch:
                self.resmods=os.path.realpath(os.path.join(self.root,*name.split('/')))
        if not self.packages or not self.resmods or not within(self.root,self.resmods):
            raise ValueError('Native package or active res_mods path not found')
        self.fingerprint=sha(b'lsf2-cache-format-2-preserve-cr\n'+version_raw+paths_raw+json.dumps(stamps,sort_keys=True).encode('utf-8'))
        self.cache_rel=PREFIX+self.fingerprint[:12]+'/'
        self.cache_root=self.absolute(self.cache_rel)

    def _file(self,name):
        with open(os.path.join(self.root,name),'rb')as f:return f.read()

    def absolute(self,resource):
        name=path(resource)
        if not name or not name.startswith(PREFIX):raise ValueError('Not a private cache resource')
        result=os.path.realpath(os.path.join(self.resmods,*name.split('/')))
        if not within(os.path.join(self.resmods,*PREFIX.strip('/').split('/')),result):raise ValueError('Cache path escaped')
        return result

    def _override_stamp(self):
        """Stat installed overrides without reopening their ZIP directories."""
        stamps=[];seen=set()
        def add(filename):
            key=os.path.normcase(os.path.realpath(filename))
            if key in seen:return
            seen.add(key);info=os.stat(filename)
            stamps.append((os.path.relpath(filename,self.root),info.st_size,info.st_mtime))
        for folder in self.mod_roots:
            if not os.path.isdir(folder):continue
            for current,dirs,files in os.walk(folder):
                for name in files:
                    if name.lower().endswith('.wotmod'):add(os.path.join(current,name))
        vehicles=os.path.join(self.resmods,'vehicles')
        if os.path.isdir(vehicles):
            for nation in os.listdir(vehicles):
                folder=os.path.join(vehicles,nation)
                if nation.startswith('_')or not os.path.isdir(folder):continue
                for current,dirs,files in os.walk(folder):
                    for name in files:add(os.path.join(current,name))
        return sha(json.dumps(sorted(stamps),ensure_ascii=True,separators=(',',':')).encode('ascii'))

    def _metadata(self,folder,signature,save=False):
        """Cache small vehicle metadata; native model bytes are never trusted here."""
        target=os.path.join(os.path.realpath(folder),'catalog2_'+self.fingerprint+'_'+signature+'.json')
        if save:
            payload=dict(cars=self.cars,overridden=sorted(self.overridden),warnings=self.override_warnings)
            text=json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':'))
            data=dict(schema=2,fingerprint=self.fingerprint,overrides=signature,payload=text,sha256=sha(text.encode('ascii')))
            if not os.path.isdir(folder):os.makedirs(folder)
            temporary=target+'.'+uuid.uuid4().hex+'.tmp'
            try:
                with io.open(temporary,'w',encoding='ascii')as f:f.write(type(u'')(json.dumps(data,ensure_ascii=True)))
                if os.path.isfile(target):os.remove(target)
                os.rename(temporary,target)
            finally:
                if os.path.isfile(temporary):os.remove(temporary)
            return True
        if not os.path.isfile(target)or os.path.getsize(target)>5*1024*1024:return False
        with io.open(target,encoding='ascii')as f:data=json.load(f)
        if data.get('schema')!=2 or data.get('fingerprint')!=self.fingerprint or data.get('overrides')!=signature:return False
        text=data['payload']
        if sha(text.encode('ascii'))!=data['sha256']:return False
        payload=json.loads(text);cars=payload['cars'];known=set()
        if not isinstance(cars,list)or not 0<len(cars)<=5000:return False
        for car in cars:
            nation=car['nation'];code=car['code'];key=car['key']
            if nation not in NATIONS or not re.match(r'^[A-Za-z0-9_\-]+$',code)or key!=nation+'/'+code.lower()or key in known:return False
            if not isinstance(car['label'],(str,type(u'')))or len(car['label'])>250:return False
            localization=car.get('localization')
            if localization is not None and(not isinstance(localization,(str,type(u'')))or len(localization)>250):return False
            known.add(key)
        affected=payload['overridden'];warnings=payload['warnings']
        if not isinstance(affected,list)or not set(affected).issubset(known):return False
        if not isinstance(warnings,list)or not all(isinstance(v,(str,type(u'')))for v in warnings):return False
        self.cars=cars;self.overridden=set(affected);self.override_warnings=warnings
        self.metadata_cache_hit=True
        return True

    def scan(self,cache_dir=None):
        signature=None
        if cache_dir:
            try:
                signature=self._override_stamp()
                if self._metadata(cache_dir,signature):return self
            except (IOError,OSError,ValueError,KeyError,TypeError,AttributeError):pass
        self.ensure_index();self.scan_overrides()
        if cache_dir and signature:
            try:self._metadata(cache_dir,signature,save=True)
            except (IOError,OSError,ValueError,TypeError):pass
        return self

    def ensure_index(self,cancel=lambda:False):
        # Warm startup needs only the small metadata snapshot. The full native
        # dependency index is deferred to the resource preparation worker.
        if self.index_loaded:return
        found={}
        for source in self.packages:
            if cancel():raise Paused()
            with zipfile.ZipFile(source)as archive:
                for number,info in enumerate(archive.infolist()):
                    if number%1024==0 and cancel():raise Paused()
                    if info.filename.endswith('/'):continue
                    name=path(info.filename)
                    if not name:raise ValueError('Unsafe native resource path')
                    key=name.lower()
                    if key not in self.index:self.index[key]=(source,info.filename,info.CRC,info.file_size)
                    if key.startswith('vehicles/')and '/normal/lod0/'in key and key.endswith('.model'):
                        parts=name.split('/');ident='/'.join(parts[1:3]).lower()
                        found[ident]=dict(key=ident,nation=parts[1].lower(),code=parts[2],label=parts[2].replace('_',' '),localization=None)
        self.index_loaded=True
        # Localization is read from native vehicle lists, never from mod scripts.
        for nation,definition in NATIONS.items():
            name='scripts/item_defs/vehicles/'+definition+'/list.xml'
            if name.lower()not in self.index:continue
            for node in parse(self.read(name)):
                ident=nation+'/'+node.tag.lower()
                if ident in found:found[ident]['localization']=node.findtext('shortUserString')or node.findtext('userString')
        self.cars=sorted(found.values(),key=lambda row:row['key'])

    def scan_overrides(self):
        """Index stock vehicle overrides without executing mod code or copying skins.

        Selecting every enemy should not duplicate every vanilla vehicle. Cars
        with no local stock-path override already have the original appearance.
        """
        known=set(row['key']for row in self.cars);hits=set();warnings=[]
        def inspect(value):
            name=path(value)
            if not name:return
            key=name.lower();parts=key.split('/')
            if len(parts)>3 and parts[0]=='vehicles'and key in self.index and key.endswith(ALLOWED):
                vehicle='/'.join(parts[1:3])
                if vehicle in known:hits.add(vehicle)
        for folder in self.mod_roots:
            if not os.path.isdir(folder):continue
            for current,dirs,files in os.walk(folder):
                for filename in files:
                    if not filename.lower().endswith('.wotmod'):continue
                    try:
                        with zipfile.ZipFile(os.path.join(current,filename))as z:
                            for info in z.infolist():inspect(info.filename)
                    except (IOError,OSError,zipfile.BadZipfile):warnings.append(filename)
        vehicles=os.path.join(self.resmods,'vehicles')
        if os.path.isdir(vehicles):
            for nation in os.listdir(vehicles):
                nation_dir=os.path.join(vehicles,nation)
                if not os.path.isdir(nation_dir)or nation.startswith('_'):continue
                for code in os.listdir(nation_dir):
                    if (nation+'/'+code).lower()not in known:continue
                    car_dir=os.path.join(nation_dir,code)
                    for current,dirs,files in os.walk(car_dir):
                        for filename in files:inspect(os.path.relpath(os.path.join(current,filename),self.resmods))
        self.overridden=hits;self.override_warnings=warnings
        return hits

    def read(self,name):
        self.ensure_index()
        key=path(name)
        if key is None or key.lower()not in self.index:raise ValueError('Missing native resource: '+str(name))
        source,entry,unused_crc,unused_size=self.index[key.lower()]
        if source not in self.archives:self.archives[source]=zipfile.ZipFile(source)
        return self.archives[source].read(entry)

    def plan(self,vehicle,cancel=lambda:False):
        self.ensure_index(cancel)
        if vehicle not in set(c['key']for c in self.cars):raise ValueError('Unknown native vehicle')
        prefix='vehicles/'+vehicle+'/';resources={};queue=[];shaders=set()
        def add(value,owner):
            name=path(value)
            if name is None or name.lower()not in self.index:raise ValueError('Missing dependency: '+str(value)+' <- '+owner)
            key=name.lower()
            if key in resources:return
            if not key.endswith(ALLOWED):raise ValueError('Unsupported dependency: '+name)
            resources[key]=self.index[key][1]
            if key.endswith(XML):queue.append(key)
            if len(resources)>10000:raise ValueError('Resource graph too large')
        roots=[name for key,(_,name,_,_)in self.index.items()if key.startswith(prefix)and key.endswith('.model')]
        parts=set(os.path.basename(n).lower().split('_')[0].split('.')[0]for n in roots if '/normal/lod0/'in n.lower())
        if not set(('chassis','hull','turret','gun')).issubset(parts):raise ValueError('Native vehicle does not have all four parts')
        for name in roots:add(name,'root')
        while queue:
            if cancel():raise Paused()
            key=queue.pop();name=resources[key];raw=self.read(name)
            if len(raw)>32*1024*1024:raise ValueError('XML resource too large')
            root=parse(raw)
            if key.endswith(('.visual','.visual_processed')):
                ext='.visual_processed'if key.endswith('.visual_processed')else'.visual';stem=name[:-len(ext)]
                add(stem+('.primitives_processed'if ext=='.visual_processed'else'.primitives'),name)
                if (stem+'.vt').lower()in self.index:add(stem+'.vt',name)
            for node in root.iter():
                value=(node.text or '').strip()
                if not value or len(node):continue
                if node.tag=='parent':add(value if value.lower().endswith('.model')else value+'.model',name)
                elif node.tag in('nodefullVisual','nodelessVisual'):
                    stem=path(value)
                    if stem is None:raise ValueError('Invalid visual path')
                    candidates=[stem]if stem.lower().endswith(('.visual','.visual_processed'))else[stem+'.visual_processed',stem+'.visual']
                    add(next((n for n in candidates if n.lower()in self.index),candidates[0]),name)
                elif node.tag=='fx':
                    shader=path(value)
                    compiled=[shader[:-3]+'.'+n+'.dx11.fxo'for n in('10','11')]if shader and shader.lower().endswith('.fx')else[]
                    if not shader or(shader.lower()not in self.index and(not compiled or not all(n.lower()in self.index for n in compiled))):
                        raise ValueError('Native shader branches not found: '+value)
                    shaders.add(shader)
                elif node.tag in('Texture','texture')or value.lower().endswith(ALLOWED):add(value,name)
        return dict(resources=resources,shaders=sorted(shaders),roots=roots)

    def _destination(self,base,original):
        # Flatten only directory names. Keep visual/primitive/VT sidecars adjacent.
        parent,filename=original.rsplit('/',1)
        return base+sha(parent.lower().encode('utf-8'))[:16]+'/'+filename

    def prepare(self,vehicle,cancel=lambda:False,progress=lambda text:None):
        if not self.index_loaded:progress(u'正在按需建立原版资源索引…')
        self.ensure_index(cancel)
        ready=self.load_ready(vehicle)
        if ready is not None:return ready
        spec=self.plan(vehicle,cancel);key_hash=sha(vehicle.encode('utf-8'))[:12]
        base=self.cache_rel+key_hash+'/'+uuid.uuid4().hex[:12]+'/'
        mapping={key:self._destination(base,name)for key,name in spec['resources'].items()}
        if len(set(v.lower()for v in mapping.values()))!=len(mapping):raise ValueError('Private path collision')
        rows=[]
        for number,(key,name)in enumerate(sorted(spec['resources'].items())):
            if cancel():raise Paused()
            data=self.read(name);source_hash=sha(data)
            if key.endswith('.vt'):
                if data[:8]!=b'\x0b\xb0\x0b\xb0\x02\x00\x00\x00'or b'vehicles/'in data.lower()or b'vehicles\\'in data.lower():
                    raise ValueError('Unsupported VT content')
            if key.endswith(XML):
                root=rewrite(parse(data),mapping)
                for node in root.iter():
                    old=path(node.text)
                    if old and old.lower()in mapping:raise ValueError('Unrelocated native reference')
                data=encode_xml(root)
            destination=mapping[key];absolute=self.absolute(destination);folder=os.path.dirname(absolute)
            if not os.path.isdir(folder):os.makedirs(folder)
            with open(absolute,'wb')as f:f.write(data)
            with open(absolute,'rb')as f:
                if sha(f.read())!=sha(data):raise ValueError('Private resource readback mismatch')
            rows.append(dict(source=name,source_sha256=source_hash,source_crc=self.index[key][2],destination=destination,sha256=sha(data),bytes=len(data)))
            if number%20==0:progress('%s: %d/%d'%(vehicle,number+1,len(spec['resources'])))
        if cancel():raise Paused()
        result=dict(schema=2,fingerprint=self.fingerprint,vehicle=vehicle,base=base,resources=rows,
                    shaders=spec['shaders'],models={key:value for key,value in mapping.items()if key.endswith('.model')},
                    whole_vehicle_loading=dict(status='not_tested'),in_game_tested=False)
        # The readiness marker is written LAST; partial caches are never selected.
        marker=self.absolute(base+'ready.json');temp=marker+'.tmp'
        text=json.dumps(result,ensure_ascii=True,sort_keys=True)
        if not isinstance(text,type(u'')):text=text.decode('ascii')
        with io.open(temp,'w',encoding='utf-8')as f:f.write(text)
        os.rename(temp,marker)
        return result

    def load_ready(self,vehicle):
        self.ensure_index()
        base=self.cache_rel+sha(vehicle.encode('utf-8'))[:12]+'/'
        folder=self.absolute(base)
        if not os.path.isdir(folder):return None
        for generation in sorted(os.listdir(folder),reverse=True):
            if not re.match(r'^[a-f0-9]{12}$',generation):continue
            marker=self.absolute(base+generation+'/ready.json')
            if not os.path.isfile(marker)or os.path.getsize(marker)>16*1024*1024:continue
            try:
                with io.open(marker,encoding='utf-8')as f:record=json.load(f)
                if record['fingerprint']!=self.fingerprint or record['vehicle']!=vehicle or record['schema']!=2:continue
                expected=base+generation+'/'
                if record['base']!=expected or not record['resources']or len(record['resources'])>10000:continue
                models={}
                for row in record['resources']:
                    source=row['source'];key=path(source)
                    if not key or key.lower()not in self.index:raise ValueError('Cache source missing')
                    key=key.lower();destination=self._destination(expected,self.index[key][1])
                    if row['destination']!=destination or row['source_crc']!=self.index[key][2]:raise ValueError('Cache source changed')
                    absolute=self.absolute(destination)
                    if os.path.getsize(absolute)!=row['bytes']:raise ValueError('Cache resource changed')
                    with open(absolute,'rb')as f:
                        if sha(f.read())!=row['sha256']:raise ValueError('Cache resource hash changed')
                    if key.endswith('.model'):models[key]=destination
                if models!=record['models']or not models:continue
                return record
            except (ValueError,IOError,OSError,KeyError,TypeError):continue
        return None

    def close(self):
        for archive in self.archives.values():archive.close()
        self.archives.clear()
