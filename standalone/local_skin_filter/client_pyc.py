# -*- coding: utf-8 -*-
"""Minimal reader for the WOT (BigWorld) Python 2.7 pyc variant.

WOT's pyc use an 8-byte header (magic + timestamp) and store every marshal
integer as a fixed 4-byte little-endian value, with no small-int shorthand.
"""
import struct
import sys
import zipfile



REF_TYPE = ord('t')


class Code(object):
    __slots__ = ("argcount", "nlocals", "stacksize", "flags", "code", "consts", "names",
                 "varnames", "freevars", "cellvars", "filename", "name", "firstlineno", "lnotab")

    def __repr__(self):
        return "<code %s>" % self.name


class Reader(object):
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.refs = []

    def u8(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def u32(self):
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def raw(self, n):
        v = self.data[self.pos:self.pos + n]
        assert len(v) == n, (n, self.pos, len(self.data))
        self.pos += n
        return v

    def obj(self):
        t = self.u8()
        if t == ord("R"):
            index = self.u32()
            if index < len(self.refs):
                return self.refs[index]
            return "<ref %d>" % index
        value = self._obj(t)
        if t == REF_TYPE:
            self.refs.append(value)
        return value

    def _obj(self, t):
        if t == ord("c"):
            c = Code()
            c.argcount = self.u32()
            c.nlocals = self.u32()
            c.stacksize = self.u32()
            c.flags = self.u32()
            c.code = self.obj()
            c.consts = self.obj()
            c.names = self.obj()
            c.varnames = self.obj()
            c.freevars = self.obj()
            c.cellvars = self.obj()
            c.filename = self.obj()
            c.name = self.obj()
            c.firstlineno = self.u32()
            c.lnotab = self.obj()
            return c
        if t == ord("s"):
            n = self.u32()
            return self.raw(n)
        if t == ord("t"):
            n = self.u32()
            return self.raw(n)
        if t == ord("u"):
            n = self.u32()
            return self.raw(n).decode("utf-8", "replace")
        if t == ord("i"):
            return self.i32()
        if t == ord("I"):
            v = struct.unpack_from("<q", self.data, self.pos)[0]
            self.pos += 8
            return v
        if t == ord("l"):
            n = self.i32()
            sign = -1 if n < 0 else 1
            value = 0
            for i in range(abs(n)):
                # Python 2 marshal stores base-2**15 digits in 16-bit words.
                # The hangar API contains masks larger than a signed int32.
                value |= (struct.unpack('<H',self.raw(2))[0] << (15 * i))
            return sign * value
        if t == ord("f"):
            n = self.u8()
            return float(self.raw(n))
        if t == ord("g"):
            return struct.unpack("<d", self.raw(8))[0]
        if t == ord("N"):
            return None
        if t == ord("T"):
            return True
        if t == ord("F"):
            return False
        if t == ord("S"):
            return StopIteration
        if t == ord("."):
            return Ellipsis
        if t == ord("("):
            n = self.u32()
            return tuple(self.obj() for _ in range(n))
        if t == ord("["):
            n = self.u32()
            return [self.obj() for _ in range(n)]
        if t == ord("{"):
            out = {}
            while True:
                key = self.obj()
                if key is None:
                    break
                out[key] = self.obj()
            return out
        if t == ord("R"):
            index = self.u32()
            if index < len(self.refs):
                return self.refs[index]
            return "<ref %d>" % index
        if t == ord("?"):
            n = self.u8()
            return self.raw(n)
        raise ValueError("unknown marshal type %r (0x%02x) at %d" % (chr(t), t, self.pos - 1))


def walk(code):
    yield code
    for item in code.consts:
        if isinstance(item, Code):
            yield from walk(item)
