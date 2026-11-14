"""Check native Python 2.7 entry points without executing any game or mod code."""
import hashlib
from client_pyc import Reader,walk

REQUIRED = {
 'scripts/client_common/vehicle_appearance/common_tank_appearance.pyc':
     {'prerequisites': ('self','vID','vInfo','renderMode')},
 'scripts/client/vehicle_systems/CompoundAppearance.pyc':
     {'__requestModelsRefresh': ('self',)},
 'scripts/client/vehicle_systems/tankStructure.pyc':
     {'getPartModelsFromDesc': ('vehicleDesc','modelsSetParams')},
}


def check(catalog):
    records=[]
    for path,methods in REQUIRED.items():
        raw=catalog.read(path)
        if raw[:4]!=b'\x03\xf3\x0d\x0a':raise ValueError('客户端脚本格式不支持：'+path)
        reader=Reader(raw);reader.pos=8;codes=list(walk(reader.obj()))
        for name,args in methods.items():
            matches=[c for c in codes if c.name==name.encode('ascii')]
            if len(matches)!=1 or matches[0].varnames[:matches[0].argcount]!=tuple(a.encode()for a in args):
                raise ValueError('客户端外观接口已变化，请等待适配：'+name)
        records.append(dict(path=path,sha256=hashlib.sha256(raw).hexdigest()))
    # Native attachModels resolves its cosmetic getter via this imported alias.
    raw=catalog.read('scripts/client/vehicle_systems/model_assembler.pyc')
    reader=Reader(raw);reader.pos=8;root=reader.obj()
    attach=[c for c in walk(root)if c.name==b'attachModels']
    if len(attach)!=1 or b'getPartModelsFromDesc'not in attach[0].names:
        raise ValueError('客户端模型选择入口已变化。')
    # PlayerAvatar.selectPlayer uses arena.vehicles[id][team] and player.team.
    raw_avatar=catalog.read('scripts/client/Avatar.pyc');reader=Reader(raw_avatar);reader.pos=8
    matches=[c for c in walk(reader.obj())if c.name==b'selectPlayer']
    if len(matches)!=1 or not {b'arena',b'vehicles',b'team',b'isObserver'}.issubset(matches[0].names):
        raise ValueError('客户端队伍元数据接口未能确认。')
    records.extend([dict(path='scripts/client/vehicle_systems/model_assembler.pyc',sha256=hashlib.sha256(raw).hexdigest()),
                    dict(path='scripts/client/Avatar.pyc',sha256=hashlib.sha256(raw_avatar).hexdigest())])
    return records
