import unittest
from unittest.mock import patch
from client_pyc import Code
from insignia_adapter import parse_script


class InsigniaParserTests(unittest.TestCase):
    def make_code(self,tail=None):
        code=Code();code.names=(b'gui.mods',b'insignia_core',b'register')
        code.consts=(-1,(b'insignia_core',),b'vehicle',b'usa:Tank',b'turret',b'Turret_1',
                     b'gun',b'Gun_1',b'slotId',49000,b'rayStart',(0.,0.,3.2),
                     b'rayEnd',(0.,0.,4.14),b'rayUp',(.3,0.,0.),b'size',.6,None)
        ops=[(100,0),(100,1),(108,0),(109,1),(90,1),(1,None),(101,1),(106,2)]
        ops.extend((100,i) for i in range(2,18));ops.extend([(131,2048),(1,None),(100,18),(83,None)])
        if tail:ops.extend(tail)
        raw=bytearray()
        for op,arg in ops:
            raw.append(op)
            if op>=90:raw.extend((arg&255,arg>>8))
        code.code=bytes(raw);return code

    def invoke(self,code,vehicle='Tank'):
        class FakeReader:
            def __init__(self,data):self.data=data;self.pos=0
            def obj(self):self.pos=len(self.data);return code
        with patch('insignia_adapter.Reader',FakeReader):
            return parse_script(b'\x03\xf3\x0d\x0a0000','american',vehicle)

    def test_reads_registration_without_executing_bytecode(self):
        data=self.invoke(self.make_code())
        self.assertEqual(len(data),1);self.assertEqual(data[0]['slotId'],49000)
        self.assertEqual(data[0]['rayEnd'],(0.,0.,4.14))

    def test_extra_op_or_mismatched_vehicle_is_rejected(self):
        with self.assertRaises(ValueError):self.invoke(self.make_code([(1,None)]))
        with self.assertRaises(ValueError):self.invoke(self.make_code(),vehicle='Other')
