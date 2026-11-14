import unittest
from unittest.mock import patch
from client_pyc import Code
from ae_adapter import code_signature


class AESignatureTests(unittest.TestCase):
    def make_code(self):
        code=Code()
        for name in Code.__slots__:setattr(code,name,())
        code.argcount=0;code.nlocals=0;code.stacksize=1;code.flags=64;code.code=b'\x64\x00\x00\x53'
        code.consts=(None,);code.name=b'<module>';code.filename=b'one.py';code.firstlineno=1;code.lnotab=b''
        return code

    def signature(self,code):
        class FakeReader:
            def __init__(self,data):self.pos=0;self.data=data
            def obj(self):self.pos=len(self.data);return code
        with patch('ae_adapter.Reader',FakeReader):return code_signature(b'\x03\xf3\r\n0000')

    def test_line_metadata_may_differ_but_program_instructions_and_constants_must_match(self):
        code=self.make_code();first=self.signature(code)
        code.filename=b'other.py';code.firstlineno=50;code.lnotab=b'changed'
        self.assertEqual(first,self.signature(code))
        code.consts=(None,False)
        self.assertNotEqual(first,self.signature(code))

    def test_non_python27_data_is_rejected_without_execution(self):
        with self.assertRaisesRegex(ValueError,'格式'):code_signature(b'arbitrary script')


if __name__=='__main__':unittest.main()
