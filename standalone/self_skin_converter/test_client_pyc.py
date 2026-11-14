import struct,unittest
from client_pyc import Reader


class MarshalReaderTests(unittest.TestCase):
    def test_python27_long_digits_are_16bit_words(self):
        for number in(2**32,2**40+123,-(2**40+123),0):
            value=abs(number);digits=[]
            while value:digits.append(value&32767);value>>=15
            raw=b'l'+struct.pack('<i',len(digits)*(-1 if number<0 else 1))+b''.join(struct.pack('<H',x)for x in digits)
            reader=Reader(raw)
            self.assertEqual(reader.obj(),number);self.assertEqual(reader.pos,len(raw))


if __name__=='__main__':unittest.main()
