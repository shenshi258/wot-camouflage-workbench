"""DX10 payload, colour and mip regressions, including the bundled BC7 codec."""
import io, struct, unittest
import numpy as np
from PIL import Image
from wotcamo import dds, paint3d
from test_workflow import reference


def extended(raw,code):
    header=bytearray(raw[:128]);header[84:88]=b'DX10'
    return bytes(header)+struct.pack('<5I',code,3,0,1,1)+raw[128:]


class DX10Tests(unittest.TestCase):
    def test_bc123_srgb_and_bc5_keep_extended_header_and_all_mips(self):
        for fmt,codes in [('DXT1',(70,71,72)),('DXT3',(73,74,75)),('DXT5',(76,77,78))]:
            for code in codes:
                with self.subTest(code=code):
                    raw=extended(reference(8,4,fmt,4),code)
                    out=dds.encode_like(Image.new('RGBA',(8,4),(110,160,210,255)),raw)
                    self.assertEqual(out[:148],raw[:148]);self.assertEqual(len(out),len(raw))
                    self.assertEqual([im.size for im in dds.decode_mips(out)],[(8,4),(4,2),(2,1),(1,1)])
                    self.assertLess(np.abs(np.asarray(dds.decode(out))[...,:3].astype(int)-[110,160,210]).max(),12)
        data=io.BytesIO();Image.new('RGB',(8,4),(70,140,0)).save(data,format='DDS',pixel_format='BC5')
        raw=data.getvalue();header=bytearray(raw);struct.pack_into('<I',header,128,83);struct.pack_into('<I',header,140,1);raw=bytes(header)
        out=dds.encode_like(dds.decode(raw),raw);self.assertEqual(out[:148],raw[:148])
        self.assertEqual(dds.decode(out).getpixel((0,0))[:2],(70,140))

    def test_bc4_payload_is_not_confused_with_rgba(self):
        raw=extended(reference(4,4,'DXT1',1),80)
        raw=raw[:148]+bytes([70,70,0,0,0,0,0,0])
        self.assertEqual(dds.decode(raw).getpixel((0,0)),(70,70,70,255))
        out=dds.encode_like(Image.new('RGBA',(4,4),(120,0,0,255)),raw)
        self.assertEqual(dds.decode(out).getpixel((0,0)),(120,120,120,255))

    def test_bc7_changes_colour_and_preserves_opaque_alpha(self):
        raw=extended(reference(8,4,'DXT5',4),99)
        # Produce valid BC7 source blocks before testing the edited mip chain.
        payload=b''.join(dds._encode_level(Image.new('RGBA',(w,h),(50,80,100,255)),'BC7') for w,h,_ in dds.inspect(raw).sizes())
        raw=raw[:148]+payload
        out=paint3d.encode_preserve_alpha(Image.new('RGBA',(8,4),(220,20,10,255)),raw)
        self.assertEqual(out[:148],raw[:148]);self.assertEqual(len(out),len(raw))
        for im in dds.decode_mips(out):
            a=np.asarray(im);self.assertEqual(int(a[...,3].min()),255);self.assertGreater(int(a[...,0].min()),200)
        self.assertNotEqual(out,raw)

    def test_rgba_and_bgra_mips_preserve_channels(self):
        for code,fmt in [(28,'RGBA8'),(29,'RGBA8'),(87,'BGRA8'),(91,'BGRA8'),(88,'BGRX8')]:
            header=extended(reference(4,2,'DXT5',3),code)[:148]
            raw=header+b'\0'*(4*2*4+2*1*4+1*1*4)
            out=dds.encode_like(Image.new('RGBA',(4,2),(10,80,200,128)),raw)
            self.assertEqual(out[:148],header)
            for im in dds.decode_mips(out):self.assertEqual(im.getpixel((0,0)),(10,80,200,255 if fmt=='BGRX8' else 128))

    def test_truncated_and_unsupported_resources_are_rejected(self):
        good=extended(reference(4,4,'DXT5',1),77)
        for raw in (good[:140],good[:-1],good+b'X'):
            with self.assertRaises(ValueError):dds.inspect(raw)
        for pos,value in [(132,4),(136,4),(140,2),(140,0),(128,95),(128,84),(144,2)]:
            raw=bytearray(good);struct.pack_into('<I',raw,pos,value)
            with self.subTest(pos=pos,value=value),self.assertRaises(ValueError):dds.inspect(raw)
