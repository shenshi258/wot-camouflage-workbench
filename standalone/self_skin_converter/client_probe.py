"""Conservatively inspect the selected client's Python 2 appearance API."""
import hashlib
from client_pyc import Code,Reader,walk

COMMON='scripts/client_common/vehicle_appearance/common_tank_appearance.pyc'
COMPOUND='scripts/client/vehicle_systems/CompoundAppearance.pyc'
VEHICLES='scripts/common/items/vehicles.pyc'


def _methods(data,class_name):
    if len(data)>20*1024*1024 or data[:4]!=b'\x03\xf3\x0d\x0a':
        raise ValueError('客户端脚本格式不受支持。')
    reader=Reader(data);reader.pos=8;root=reader.obj()
    matches=[c for c in walk(root) if c.name==class_name]
    if len(matches)!=1:raise ValueError('客户端车辆外观类无法唯一确认。')
    return {c.name:c for c in matches[0].consts if isinstance(c,Code)}


def verify(catalog, require_composite=False, require_hangar=False):
    try:
        common=catalog.read(COMMON);compound=catalog.read(COMPOUND)
        a=_methods(common,b'CommonTankAppearance');b=_methods(compound,b'CompoundAppearance')
        p=a[b'prerequisites'];pa=a[b'_prepareOutfit'];pb=b[b'_prepareOutfit']
        if tuple(p.varnames[:p.argcount])!=(b'self',b'vID',b'vInfo',b'renderMode'):
            raise ValueError('客户端车辆加载接口不匹配。')
        for method in (pa,pb):
            if tuple(method.varnames[:method.argcount])!=(b'self',b'outfitCD'):
                raise ValueError('客户端外观读取接口不匹配。')
        required={b'_CommonTankAppearance__typeDesc',b'_prepareOutfit',b'typeDescriptor'}
        if not required.issubset(set(p.names)):
            raise ValueError('客户端车辆加载流程不匹配。')
        result=dict(common_sha256=hashlib.sha256(common).hexdigest(),compound_sha256=hashlib.sha256(compound).hexdigest(),
                    api='common-prerequisites-vInfo',status='static_match_only')
        if require_hangar:
            raw=catalog.read('scripts/client/gui/hangar_vehicle_appearance.pyc')
            methods=_methods(raw,b'HangarVehicleAppearance')
            if b'__startBuild' not in methods or b'_HangarVehicleAppearance__vDesc' not in methods[b'__startBuild'].names:
                raise ValueError('客户端车库加载接口不匹配。')
            result['hangar_sha256']=hashlib.sha256(raw).hexdigest()
        if require_composite:
            vehicles=catalog.read(VEHICLES)
            methods=_methods(vehicles,b'CompositeVehicleDescriptor')
            init=methods[b'__init__'];getter=methods[b'__getattr__'];setter=methods[b'__setattr__']
            private={b'_CompositeVehicleDescriptor__vehicleDescr',b'_CompositeVehicleDescriptor__siegeDescr'}
            if not private.issubset(set(init.names)) or not private.issubset(set(getter.names)) or not private.issubset(set(setter.names)):
                raise ValueError('客户端双形态车型的数据结构不匹配。')
            result['composite_sha256']=hashlib.sha256(vehicles).hexdigest()
        return result
    except (KeyError,IndexError,TypeError,AssertionError,OSError) as error:
        raise ValueError('未能确认所选客户端接口：'+str(error)) from error
