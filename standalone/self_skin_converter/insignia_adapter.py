"""Safely recognise the narrow, declarative insignia registration bytecode.

Never execute an input script. Only an exact sequence of constant keyword
registrations is accepted; unknown opcodes, calls or values are rejected.
"""
import math
import re
from client_pyc import Code,Reader

FIELDS=('vehicle','turret','gun','slotId','rayStart','rayEnd','rayUp','size')
NATIONS={'american':'usa','russian':'ussr','german':'germany','french':'france',
         'british':'uk','chinese':'china','swedish':'sweden','italian':'italy',
         'japanese':'japan','polish':'poland','czech':'czech'}


def parse_script(data,nation,vehicle):
    if len(data)>65536 or data[:4]!=b'\x03\xf3\x0d\x0a':raise ValueError('徽记脚本格式不受支持。')
    try:
        reader=Reader(data);reader.pos=8;code=reader.obj()
        if not isinstance(code,Code) or reader.pos!=len(data) or any(isinstance(x,Code) for x in code.consts):
            raise ValueError('徽记脚本含额外代码。')
        instructions=[];at=0;raw=code.code
        while at<len(raw):
            op=raw[at];at+=1
            if op>=90:
                if at+2>len(raw):raise ValueError('脚本指令不完整。')
                arg=raw[at]|raw[at+1]<<8;at+=2
            else:arg=None
            instructions.append((op,arg))
        position=0
        def read(op, table=None, expected=None):
            nonlocal position
            if position>=len(instructions):raise ValueError('脚本指令不完整。')
            actual,arg=instructions[position];position+=1
            if actual!=op:raise ValueError('脚本包含不受支持的操作。')
            value=table[arg] if table is not None else arg
            if expected is not None and value!=expected:raise ValueError('脚本调用不在安全识别范围。')
            return value
        if read(100,code.consts)!=-1:raise ValueError('脚本导入级别异常。')
        if read(100,code.consts)!=(b'insignia_core',):raise ValueError('脚本导入对象异常。')
        read(108,code.names,b'gui.mods');read(109,code.names,b'insignia_core')
        read(90,code.names,b'insignia_core');read(1)
        result=[]
        while position<len(instructions) and instructions[position][0]==101:
            read(101,code.names,b'insignia_core');read(106,code.names,b'register')
            values={}
            for _ in range(8):
                key=read(100,code.consts);value=read(100,code.consts)
                if not isinstance(key,bytes):raise ValueError('徽记参数名无效。')
                key=key.decode('ascii')
                if key not in FIELDS or key in values:raise ValueError('徽记参数未知或重复。')
                values[key]=value
            if read(131)!=2048:raise ValueError('徽记调用参数格式不受支持。')
            read(1)
            if set(values)!=set(FIELDS):raise ValueError('徽记参数不完整。')
            for key in ('vehicle','turret','gun'):
                value=values[key]
                if not isinstance(value,bytes):raise ValueError('徽记车型或部件名无效。')
                values[key]=value.decode('ascii')
                if not re.fullmatch(r'[A-Za-z0-9_:.\-]+',values[key]):raise ValueError('徽记车型或部件名无效。')
            expected=NATIONS.get(nation.casefold(),nation.casefold())+':'+vehicle.casefold()
            if values['vehicle'].casefold()!=expected:raise ValueError('徽记脚本与输入车型不一致。')
            if type(values['slotId']) is not int or not 0<=values['slotId']<=10000000:
                raise ValueError('徽记槽位编号无效。')
            for key in ('rayStart','rayEnd','rayUp'):
                vector=values[key]
                if not isinstance(vector,tuple) or len(vector)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>10000 for x in vector):
                    raise ValueError('徽记坐标无效。')
                values[key]=tuple(float(x) for x in vector)
            if type(values['size']) not in (int,float) or not math.isfinite(values['size']) or not 0<values['size']<=10000:
                raise ValueError('徽记尺寸无效。')
            values['size']=float(values['size']);result.append(values)
            if len(result)>32:raise ValueError('徽记注册数量过多。')
        if not result or read(100,code.consts) is not None:raise ValueError('脚本结束格式无效。')
        read(83)
        if position!=len(instructions):raise ValueError('脚本包含额外操作。')
        return result
    except (IndexError,KeyError,TypeError,UnicodeError,AssertionError) as error:
        raise ValueError('徽记脚本无法安全解析：'+str(error)) from error
