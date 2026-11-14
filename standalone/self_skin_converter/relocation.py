"""Plan and check isolated resource paths; does not write or install mods."""
import copy
import hashlib
import re
import xml.etree.ElementTree as ET
from resource_graph import game_path

RESOURCE = re.compile(r'^vehicles/([^/]+)/([^/]+)/(.+)$', re.I)
SAFE_TOKEN = re.compile(r'^[a-f0-9]{12,32}$')


def make_mapping(names, token):
    """Map source vehicle resources into a private namespace for one input.

    This is only a plan. It does not imply references embedded in binary data
    or game model-selection rules have been handled.
    """
    if not SAFE_TOKEN.fullmatch(token):
        raise ValueError('隔离标识无效')
    mapping={}
    output=set()
    for name in names:
        path=game_path(name)
        if not path:raise ValueError('资源路径无效')
        m=RESOURCE.fullmatch(path)
        if not m:continue
        nation,vehicle,tail=m.groups()
        dest='vehicles/%s/%s/_self_%s/%s'%(nation,vehicle,token,tail)
        if path.casefold() in mapping or dest.casefold() in output:raise ValueError('隔离资源路径冲突')
        mapping[path.casefold()]=dest;output.add(dest.casefold())
    return mapping


def token_for(source_digest):
    if not re.fullmatch(r'[0-9a-fA-F]{64}',source_digest):raise ValueError('输入哈希无效')
    return hashlib.sha256(('own-skin-v1:'+source_digest.lower()).encode('ascii')).hexdigest()[:20]


def rewrite_xml(root,mapping):
    """Rewrite exact XML leaf resource values, including extensionless visuals.

    The caller must separately check that every binary resource and every
    referenced client resource is accounted for before any game export.
    """
    result=copy.deepcopy(root);changed=0
    visual_stems={};model_stems={}
    for old,new in mapping.items():
        if old.endswith('.model'):
            model_stems[old[:-6]]=new[:-6]
        for suffix in ('.visual_processed','.visual'):
            if old.endswith(suffix):
                stem=old[:-len(suffix)];target=new[:-len(suffix)]
                if stem in visual_stems and visual_stems[stem].casefold()!=target.casefold():
                    raise ValueError('模型 visual 引用存在歧义')
                visual_stems[stem]=target
    for node in result.iter():
        if len(node) or not node.text:continue
        value=game_path(node.text)
        if not value:continue
        replacement=mapping.get(value.casefold())
        if replacement is None and node.tag in ('nodefullVisual','nodelessVisual'):
            replacement=visual_stems.get(value.casefold())
        if replacement is None and node.tag=='parent':
            replacement=model_stems.get(value.casefold())
        if replacement:
            node.text=replacement;changed+=1
    return result,changed


def serialize_xml(root):
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
